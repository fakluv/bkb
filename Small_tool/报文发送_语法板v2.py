# -*- coding: utf-8 -*-
r"""
UDP / TCP Server 十六进制报文发送工具

功能：
1. UDP 发送页面 / TCP Server 页面：多客户端、HEX 收发、持续发送。
2. #...# 之间为注释；"# #" 连写会自动合并。
3. 配置全部保存在注册表 HKEY_CURRENT_USER\Software\UdpHexSender 下。

指令说明：
  {} 内：HEX + 可选指令
    {02 T(0,30)}      随机，十进制闭区间
    {02 T}            随机，使用“编辑 T 范围”的全局范围；未设置则字段满量程
    {02 P}            自增，满量程后回 0
    {02 P(100)}       自增，最大值 100，到 100 后回初始字节值
    {02 L(55,255,33)} 按内联列表循环，秒数和循环/停止用全局设置
    {02 L(1,2,3@5)}   按内联列表循环，每 5 秒切换一格（秒数用全局 stop/loop）
    {02 L(1,2,3@5,stop)} 按内联列表，每 5 秒一格，到尽头停在最后一个值
    {02 L(1,2,3@5,loop)} 按内联列表，每 5 秒一格，到尽头循环
    {02 L}            按“编辑 L 列表”的全局列表 + 全局秒数 + 全局循环/停止
  多字段 L 共享进度规则：列表值相同、秒数相同、模式相同 → 共享进度；
  全局 L 与内联 L 各自独立。

  [] 内：HEX 时间戳 + 可选修饰符
    [6A DB 23 E4]        4 字节秒级时间戳（实时）
    [6A DB 23 E4 -8]     秒级时间戳减 8 小时
    [6A DB 23 E4 +8]     秒级时间戳加 8 小时
    [6A DB 23 E4 R]      秒级时间戳反转字节
    [1A 09 1A 10 00 1A]  6 字节年月日时分秒（21 世纪，年份偏移 2000）
    6 字节同样支持 +/-N 与 R；+/-N 做完整日期运算。
    +/-N 与 R 二选一，同时出现报错。
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import socket
import threading
import time
import random
import re
import queue
import datetime

REG_PATH = r"Software\UdpHexSender"


# ============================================================
# 图标
# ============================================================

def _get_icon_path():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "Benzlee-Free-Christmas-Paper-airplane.ico")


ICON_PATH = _get_icon_path()


def apply_app_icon(window):
    try:
        window.iconbitmap(default=ICON_PATH)
    except Exception:
        try:
            window.iconbitmap(ICON_PATH)
        except Exception:
            pass


def center_on_parent(win, parent):
    """把弹窗居中到父窗口。"""
    try:
        win.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        ww = win.winfo_width()
        wh = win.winfo_height()
        if pw <= 1:
            pw = parent.winfo_reqwidth()
        if ph <= 1:
            ph = parent.winfo_reqheight()
        if ww <= 1:
            ww = win.winfo_reqwidth()
        if wh <= 1:
            wh = win.winfo_reqheight()
        x = max(0, px + (pw - ww) // 2)
        y = max(0, py + (ph - wh) // 2)
        win.geometry(f"+{x}+{y}")
    except Exception:
        pass


try:
    import winreg
except ImportError:
    winreg = None


# ============================================================
# 撤销支持
# ============================================================

def enable_entry_undo(entry, var):
    """给 ttk.Entry + StringVar 加多级 Ctrl+Z 撤销。"""
    history = [var.get()]
    lock = [False]

    def on_write(*_args):
        if lock[0]:
            return
        new = var.get()
        if new != history[-1]:
            history.append(new)

    def undo(_event=None):
        if len(history) >= 2:
            history.pop()
            last = history[-1]
            lock[0] = True
            try:
                var.set(last)
            finally:
                lock[0] = False
        return "break"

    var.trace_add("write", on_write)
    entry.bind("<Control-z>", undo)
    entry.bind("<Control-Z>", undo)


def enable_text_undo(text):
    """给 tk.Text 加 Ctrl+Z 撤销（需 undo=True）。"""
    def undo(_event=None):
        try:
            text.edit_undo()
        except tk.TclError:
            pass
        return "break"

    text.bind("<Control-z>", undo)
    text.bind("<Control-Z>", undo)


# ============================================================
# 报文解析公用函数
# ============================================================

INSTR_RE = re.compile(r'([TtPpLl])(?:\(([^)]*)\))?\s*$')


def strip_comments(text: str) -> str:
    text = re.sub(r"#[ \t]*#", "#", text)
    out_lines = []
    for line in text.splitlines():
        in_comment = False
        keep = []
        for ch in line:
            if ch == "#":
                in_comment = not in_comment
                continue
            if not in_comment:
                keep.append(ch)
        out_lines.append("".join(keep))
    return "\n".join(out_lines)


def parse_hex_tokens(text: str):
    tokens = []
    for match in re.finditer(r"[0-9a-fA-F]+", text):
        tok = match.group(0)
        if len(tok) == 1:
            continue
        if len(tok) % 2:
            raise ValueError(
                f"十六进制字符数不是偶数: {tok!r}\n"
                "请检查 #...# 内是否混入说明文字，或 # 是否成对闭合。"
            )
        tokens.append(tok)
    return tokens


def hex_tokens_to_bytes(tokens):
    out = bytearray()
    for tok in tokens:
        for i in range(0, len(tok), 2):
            out.append(int(tok[i:i + 2], 16))
    return bytes(out)


def parse_numeric_args(args_str, expected_len, name):
    """解析 T / P 括号内的纯数字参数。"""
    if args_str is None:
        return None
    items = [x.strip() for x in args_str.split(",") if x.strip()]
    if len(items) != expected_len:
        raise ValueError(f"{name} 括号内需要 {expected_len} 个参数")
    try:
        return tuple(int(x, 10) for x in items)
    except ValueError:
        raise ValueError(f"{name} 参数必须是十进制整数")


def parse_l_args(args_str):
    """
    解析 L(...) 参数。
    返回 None（无括号）或 (vals_tuple, hold_or_None, mode_or_None)。
    """
    if args_str is None:
        return None
    s = args_str.strip()
    if not s:
        raise ValueError("L 括号内参数不能为空")

    parts = s.split(",")
    mode = None
    last = parts[-1].strip().lower()
    if last in ("stop", "loop"):
        mode = last
        parts = parts[:-1]
        if not parts:
            raise ValueError("L 只写了 stop/loop，缺少列表值")

    rest = ",".join(parts)

    if "@" in rest:
        list_part, hold_part = rest.split("@", 1)
        try:
            hold = float(hold_part.strip())
        except ValueError:
            raise ValueError(f"L 秒数无效: {hold_part!r}")
        if hold < 0:
            raise ValueError("L 秒数不能为负")
        list_strs = list_part.split(",")
    else:
        hold = None
        list_strs = rest.split(",")

    try:
        vals = tuple(int(x.strip(), 10) for x in list_strs if x.strip())
    except ValueError:
        raise ValueError(f"L 列表值必须是十进制整数: {list_strs!r}")

    if not vals:
        raise ValueError("L 列表不能为空")
    if any(v < 0 for v in vals):
        raise ValueError("L 列表值必须是非负整数")

    return (vals, hold, mode)


def compile_template(template: str):
    text = strip_comments(template)
    parts = []
    var_idx = 0
    i = 0
    while i < len(text):
        ch = text[i]

        if ch == "{":
            j = text.find("}", i + 1)
            if j < 0:
                raise ValueError("未找到匹配的 }")
            content = text[i + 1:j]

            m = INSTR_RE.search(content)
            if m:
                hex_part = content[:m.start()]
                instr = m.group(1).lower()
                args_str = m.group(2)
            else:
                hex_part = content
                instr = None
                args_str = None

            tokens = parse_hex_tokens(hex_part)
            b = hex_tokens_to_bytes(tokens)
            if not b:
                raise ValueError("{} 内没有有效的十六进制字节")
            n = len(b)
            init_value = int.from_bytes(b, "big")

            if instr == "t":
                args = parse_numeric_args(args_str, 2, "T")
                if args is not None:
                    if args[0] < 0:
                        raise ValueError("T 范围不能为负")
                    if args[0] > args[1]:
                        raise ValueError("T 范围最小值不能大于最大值")
            elif instr == "p":
                args = parse_numeric_args(args_str, 1, "P")
                if args is not None:
                    if args[0] < 0:
                        raise ValueError("P 最大值不能为负")
                    if init_value > args[0]:
                        raise ValueError(
                            f"P 初始值 {init_value} 超出最大值 {args[0]}"
                        )
            elif instr == "l":
                args = parse_l_args(args_str)
            else:
                args = None

            parts.append(("var", n, var_idx, instr, args, init_value))
            var_idx += 1
            i = j + 1

        elif ch == "[":
            j = text.find("]", i + 1)
            if j < 0:
                raise ValueError("未找到匹配的 ]")
            content = text[i + 1:j].strip()

            reverse = False
            offset_hours = 0
            mm = re.search(r"(\s+)([+-]\d+|[Rr])\s*$", content)
            if mm:
                mod = mm.group(2)
                content = content[:mm.start()].strip()
                if mod in ("R", "r"):
                    reverse = True
                else:
                    offset_hours = int(mod)

            if re.sub(r"[0-9a-fA-F\s]", "", content):
                raise ValueError(f"时间戳内包含非法字符: {content!r}")

            tokens = parse_hex_tokens(content)
            b = hex_tokens_to_bytes(tokens)
            n = len(b)
            if n not in (4, 6):
                raise ValueError(f"时间戳字节数必须为 4 或 6，当前 {n} 字节")
            parts.append(("ts", n, reverse, offset_hours))
            i = j + 1

        else:
            j = i
            while j < len(text) and text[j] not in "{[}":
                j += 1
            fixed_text = text[i:j]
            tokens = parse_hex_tokens(fixed_text)
            b = hex_tokens_to_bytes(tokens)
            if b:
                parts.append(("fixed", b))
            i = j

    return parts


def build_payload(parts, counters, list_values=None, list_hold=0,
                  t_range=None, list_mode="loop"):
    out = bytearray()
    list_values = list_values or []

    # ---------- 第一遍：收集 L 组 ----------
    l_groups = {}
    l_field_group = {}

    for part in parts:
        if part[0] != "var" or part[3] != "l":
            continue
        _, n, idx, instr, args, init_value = part
        if args is None:
            if not list_values:
                raise ValueError("存在 {.. L} 但全局 L 列表为空，请先编辑 L 列表")
            eff_hold = float(list_hold)
            eff_mode = list_mode
            key = ("__GLOBAL__", eff_hold, eff_mode)
            if key not in l_groups:
                l_groups[key] = {"list": list(list_values),
                                 "hold": eff_hold, "mode": eff_mode}
        else:
            vals, hold, mode = args
            eff_hold = float(list_hold) if hold is None else float(hold)
            eff_mode = list_mode if mode is None else mode
            key = (vals, eff_hold, eff_mode)
            if key not in l_groups:
                l_groups[key] = {"list": list(vals),
                                 "hold": eff_hold, "mode": eff_mode}
        l_field_group[idx] = key

    # ---------- 第二遍：计算每组 list_pos ----------
    for key, g in l_groups.items():
        lst = g["list"]
        hold = g["hold"]
        mode = g["mode"]
        key_repr = repr(key)

        if hold > 0:
            anchor_key = f"l_anchor_{key_repr}"
            now = time.time()
            anchor = counters.get(anchor_key)
            if anchor is None:
                anchor = now
                counters[anchor_key] = anchor
            raw_pos = int((now - anchor) // hold)
        else:
            idx_key = f"l_idx_{key_repr}"
            raw_pos = counters.get(idx_key, 0)
            counters[idx_key] = raw_pos + 1

        if mode == "stop":
            pos = min(raw_pos, len(lst) - 1)
        else:
            pos = raw_pos % len(lst)
        g["pos"] = pos

    # ---------- 第三遍：生成字节 ----------
    for part in parts:
        kind = part[0]
        if kind == "fixed":
            out.extend(part[1])

        elif kind == "var":
            _, n, idx, instr, args, init_value = part
            maxv = (1 << (8 * n)) - 1

            if instr is None or instr == "t":
                if instr == "t" and args is not None:
                    lo, hi = args
                elif t_range is not None:
                    lo, hi = t_range
                else:
                    lo, hi = 0, maxv
                if lo < 0 or hi > maxv:
                    raise ValueError(
                        f"T 范围 {lo}~{hi} 超出 {n} 字节字段可表示范围 0~{maxv}"
                    )
                if lo > hi:
                    raise ValueError("T 范围最小值不能大于最大值")
                v = random.randint(lo, hi)
                out.extend(v.to_bytes(n, "big"))

            elif instr == "p":
                key = f"p_{idx}"
                v = counters.get(key, init_value)
                if args is not None:
                    max_val = args[0]
                    if v > max_val:
                        v = init_value
                    next_v = v + 1
                    if next_v > max_val:
                        next_v = init_value
                else:
                    next_v = (v + 1) % (maxv + 1)
                counters[key] = next_v
                out.extend(v.to_bytes(n, "big"))

            elif instr == "l":
                g = l_groups[l_field_group[idx]]
                v = g["list"][g["pos"]]
                if v < 0 or v > maxv:
                    raise ValueError(
                        f"L 列表值 {v} 超出 {n} 字节字段可表示范围 0~{maxv}"
                    )
                out.extend(v.to_bytes(n, "big"))

        elif kind == "ts":
            _, n, reverse, offset_hours = part
            if n == 4:
                v = (int(time.time()) + offset_hours * 3600) & 0xFFFFFFFF
                b = v.to_bytes(4, "big")
                out.extend(b[::-1] if reverse else b)
            else:
                dt = datetime.datetime.now() + datetime.timedelta(hours=offset_hours)
                fields = [dt.year - 2000, dt.month, dt.day,
                          dt.hour, dt.minute, dt.second]
                if any(x < 0 or x > 255 for x in fields):
                    raise ValueError("时间戳字段超出 0~255 范围")
                b = bytes(fields)
                out.extend(b[::-1] if reverse else b)

    return bytes(out)


def hex_preview(payload: bytes, limit: int = 256) -> str:
    shown = payload[:limit].hex(" ").upper()
    if len(payload) > limit:
        shown += f" ...（省略 {len(payload) - limit} 字节）"
    return shown


def parse_hold_seconds(text: str) -> float:
    try:
        v = float((text or "0").strip() or "0")
    except ValueError:
        raise ValueError("列表保持时间必须是数字（秒）")
    if v < 0:
        raise ValueError("列表保持时间不能为负")
    return v


# ============================================================
# 主窗口
# ============================================================

class App:
    def __init__(self, root):
        self.root = root
        root.title("报文发送器 v2.0 语法版")
        root.geometry("1040x800")
        apply_app_icon(root)

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=6, pady=6)

        self.udp_page = UdpPage(notebook, self)
        self.tcp_page = TcpServerPage(notebook, self)

        notebook.add(self.udp_page, text="UDP 发送")
        notebook.add(self.tcp_page, text="TCP Server")

        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def save_setting(self, name, value):
        if winreg is None:
            return
        try:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, str(value))
            winreg.CloseKey(key)
        except Exception:
            pass

    def load_setting(self, name, default=""):
        if winreg is None:
            return default
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH)
        except OSError:
            return default
        try:
            return winreg.QueryValueEx(key, name)[0]
        except OSError:
            return default
        finally:
            winreg.CloseKey(key)

    def on_close(self):
        for page in (self.udp_page, self.tcp_page):
            try:
                page.save_config()
            except Exception:
                pass
            try:
                page.cleanup()
            except Exception:
                pass
        self.root.destroy()


# ============================================================
# UDP 页面
# ============================================================

class UdpPage(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app

        self.thread = None
        self.stop_event = threading.Event()
        self.counters = {}
        self.list_values = []
        self.t_range = None
        self.sent_count = 0

        self.ui_queue = queue.Queue()
        self._schedule_poll()

        self.var_local_ip = tk.StringVar(value="0.0.0.0")
        self.var_local_port = tk.StringVar(value="0")
        self.var_target_ip = tk.StringVar(value="127.0.0.1")
        self.var_target_port = tk.StringVar(value="9000")
        self.var_interval = tk.StringVar(value="1000")
        self.var_continuous = tk.BooleanVar(value=False)
        self.var_list_hold = tk.StringVar(value="0")
        self.list_mode = "loop"
        self.status_var = tk.StringVar(value="就绪")

        self.build_ui()
        self.load_config()

    def _schedule_poll(self):
        self.after(50, self._poll_queue)

    def _poll_queue(self):
        while True:
            try:
                fn, args = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args)
            except Exception:
                pass
        self._schedule_poll()

    def ui_call(self, fn, *args):
        self.ui_queue.put((fn, args))

    def load_config(self):
        self.var_local_ip.set(self.app.load_setting("udp.local_ip", "0.0.0.0"))
        self.var_local_port.set(self.app.load_setting("udp.local_port", "0"))
        self.var_target_ip.set(self.app.load_setting("udp.target_ip", "127.0.0.1"))
        self.var_target_port.set(self.app.load_setting("udp.target_port", "9000"))
        self.var_interval.set(self.app.load_setting("udp.interval", "1000"))
        self.var_continuous.set(self.app.load_setting("udp.continuous", "0") == "1")
        self.var_list_hold.set(self.app.load_setting("udp.list_hold", "0"))
        self.list_mode = self.app.load_setting("udp.list_mode", "loop") or "loop"

        t_min = self.app.load_setting("udp.t_min", "")
        t_max = self.app.load_setting("udp.t_max", "")
        if t_min != "" and t_max != "":
            try:
                self.t_range = (int(t_min), int(t_max))
            except ValueError:
                self.t_range = None
        else:
            self.t_range = None

        tpl = self.app.load_setting("udp.template", "")
        if tpl:
            self.txt_template.insert("1.0", tpl)
        try:
            self.list_values = [int(x) for x in
                                self.app.load_setting("udp.list_values", "").split(",")
                                if x.strip()]
        except ValueError:
            self.list_values = []

    def save_config(self):
        self.app.save_setting("udp.local_ip", self.var_local_ip.get().strip())
        self.app.save_setting("udp.local_port", self.var_local_port.get().strip())
        self.app.save_setting("udp.target_ip", self.var_target_ip.get().strip())
        self.app.save_setting("udp.target_port", self.var_target_port.get().strip())
        self.app.save_setting("udp.interval", self.var_interval.get().strip())
        self.app.save_setting("udp.continuous", "1" if self.var_continuous.get() else "0")
        self.app.save_setting("udp.list_hold", self.var_list_hold.get().strip())
        self.app.save_setting("udp.list_mode", self.list_mode)
        if self.t_range is not None:
            self.app.save_setting("udp.t_min", str(self.t_range[0]))
            self.app.save_setting("udp.t_max", str(self.t_range[1]))
        else:
            self.app.save_setting("udp.t_min", "")
            self.app.save_setting("udp.t_max", "")
        self.app.save_setting("udp.template", self.txt_template.get("1.0", "end-1c"))
        self.app.save_setting("udp.list_values", ",".join(map(str, self.list_values)))

    def _entry(self, parent, var, **kwargs):
        e = ttk.Entry(parent, textvariable=var, **kwargs)
        enable_entry_undo(e, var)
        return e

    def build_ui(self):
        cfg = ttk.LabelFrame(self, text="UDP 配置")
        cfg.pack(fill="x", padx=4, pady=4)

        ttk.Label(cfg, text="本机 IP").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self._entry(cfg, self.var_local_ip, width=18).grid(row=0, column=1, padx=4, pady=4)
        ttk.Label(cfg, text="本机端口").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        self._entry(cfg, self.var_local_port, width=10).grid(row=0, column=3, padx=4, pady=4)
        ttk.Label(cfg, text="目标 IP").grid(row=0, column=4, sticky="w", padx=4, pady=4)
        self._entry(cfg, self.var_target_ip, width=18).grid(row=0, column=5, padx=4, pady=4)
        ttk.Label(cfg, text="目标端口").grid(row=0, column=6, sticky="w", padx=4, pady=4)
        self._entry(cfg, self.var_target_port, width=10).grid(row=0, column=7, padx=4, pady=4)

        ttk.Label(cfg, text="发送间隔(ms)").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self._entry(cfg, self.var_interval, width=10).grid(row=1, column=1, padx=4, pady=4)
        ttk.Button(cfg, text="编辑 T 范围", command=self.edit_t_range).grid(
            row=1, column=2, padx=4, pady=4)
        ttk.Button(cfg, text="编辑 L 列表", command=self.edit_l_list).grid(
            row=1, column=3, padx=4, pady=4)
        ttk.Checkbutton(cfg, text="持续发送", variable=self.var_continuous).grid(
            row=1, column=4, sticky="w", padx=4, pady=4)
        ttk.Label(
            cfg,
            text="{.. T} / {.. P} / {.. L} 可在报文中直接指定；无指令默认随机",
            foreground="gray",
        ).grid(row=1, column=5, columnspan=3, sticky="w", padx=4, pady=4)

        tf = ttk.LabelFrame(
            self,
            text="报文模板：#...# 为注释； {..} 为变化值； [..] 为时间戳； [.. +/-N] 小时偏移； [.. R] 反转"
        )
        tf.pack(fill="both", expand=True, padx=4, pady=4)

        self.txt_template = tk.Text(tf, height=22, wrap="char",
                                    font=("Consolas", 10),
                                    undo=True, autoseparators=True, maxundo=-1)
        yscroll = ttk.Scrollbar(tf, orient="vertical", command=self.txt_template.yview)
        self.txt_template.configure(yscrollcommand=yscroll.set)
        self.txt_template.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)
        enable_text_undo(self.txt_template)

        bf = ttk.Frame(self)
        bf.pack(fill="x", padx=4, pady=4)
        self.btn_send = ttk.Button(bf, text="发送", command=self.on_send)
        self.btn_send.pack(side="left")
        ttk.Button(bf, text="清空日志", command=self.clear_log).pack(side="left", padx=6)
        ttk.Label(bf, textvariable=self.status_var).pack(side="right")

        lf = ttk.LabelFrame(self, text="日志")
        lf.pack(fill="x", padx=4, pady=4)
        self.txt_log = tk.Text(lf, height=7, wrap="word",
                               font=("Consolas", 9),
                               undo=True, autoseparators=True, maxundo=-1)
        log_scroll = ttk.Scrollbar(lf, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=log_scroll.set)
        self.txt_log.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")
        enable_text_undo(self.txt_log)

    def log(self, msg):
        self.txt_log.insert("end", time.strftime("%H:%M:%S ") + msg + "\n")
        self.txt_log.see("end")
        try:
            line_count = int(self.txt_log.index("end-1c").split(".")[0])
            if line_count > 500:
                self.txt_log.delete("1.0", "201.0")
        except Exception:
            pass

    def clear_log(self):
        self.txt_log.delete("1.0", "end")

    def edit_t_range(self):
        win = tk.Toplevel(self)
        apply_app_icon(win)
        win.title("编辑 T 全局范围")
        win.transient(self.winfo_toplevel())
        win.geometry("360x180")
        win.after_idle(lambda: center_on_parent(win, self.winfo_toplevel()))
        ttk.Label(win, text="未设置时按字段满量程处理（1 字节 0~255、2 字节 0~65535…）。").pack(
            anchor="w", padx=10, pady=(10, 4))
        ttk.Label(win, text="最小值").pack(anchor="w", padx=10)
        lo_var = tk.StringVar(value=str(self.t_range[0]) if self.t_range else "")
        lo_entry = ttk.Entry(win, textvariable=lo_var, width=18)
        lo_entry.pack(anchor="w", padx=10, pady=2)
        enable_entry_undo(lo_entry, lo_var)
        ttk.Label(win, text="最大值").pack(anchor="w", padx=10)
        hi_var = tk.StringVar(value=str(self.t_range[1]) if self.t_range else "")
        hi_entry = ttk.Entry(win, textvariable=hi_var, width=18)
        hi_entry.pack(anchor="w", padx=10, pady=2)
        enable_entry_undo(hi_entry, hi_var)

        def save():
            lo_s = lo_var.get().strip()
            hi_s = hi_var.get().strip()
            if not lo_s and not hi_s:
                self.t_range = None
                win.destroy()
                self.log("已清除 T 全局范围（按字段满量程）")
                return
            try:
                lo = int(lo_s)
                hi = int(hi_s)
            except ValueError:
                messagebox.showerror("错误", "范围必须是整数", parent=win)
                return
            if lo < 0 or hi < 0:
                messagebox.showerror("错误", "范围必须是非负整数", parent=win)
                return
            if lo > hi:
                messagebox.showerror("错误", "最小值不能大于最大值", parent=win)
                return
            self.t_range = (lo, hi)
            win.destroy()
            self.log(f"已设置 T 全局范围 {lo}~{hi}")

        row = ttk.Frame(win)
        row.pack(fill="x", padx=10, pady=8)
        ttk.Button(row, text="确定", command=save).pack(side="right")
        ttk.Button(row, text="取消", command=win.destroy).pack(side="right", padx=6)

    def edit_l_list(self):
        win = tk.Toplevel(self)
        apply_app_icon(win)
        win.title("编辑 L 全局列表")
        win.transient(self.winfo_toplevel())
        win.geometry("560x560")
        win.after_idle(lambda: center_on_parent(win, self.winfo_toplevel()))

        ttk.Label(
            win,
            text="支持一行一个值，或用逗号 / 空格 / 斜杠 / 中文逗号 分隔（如 1,2,3 或 1 2 3 或 1/2/3）：",
        ).pack(anchor="w", padx=10, pady=(10, 4))

        box_frame = ttk.Frame(win)
        box_frame.pack(fill="both", expand=True, padx=10, pady=4)
        box = tk.Text(box_frame, height=12, width=40, font=("Consolas", 10),
                      undo=True, autoseparators=True, maxundo=-1)
        vscroll = ttk.Scrollbar(box_frame, orient="vertical", command=box.yview)
        box.configure(yscrollcommand=vscroll.set)
        box.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")
        if self.list_values:
            box.insert("1.0", "\n".join(map(str, self.list_values)))
        enable_text_undo(box)

        ttk.Label(win, text="列表保持(秒)：0 = 每发一包切换；>0 = 每 N 秒切换（期间重复发送当前值）").pack(
            anchor="w", padx=10, pady=(6, 2))
        hold_var = tk.StringVar(value=self.var_list_hold.get())
        hold_entry = ttk.Entry(win, textvariable=hold_var, width=12)
        hold_entry.pack(anchor="w", padx=10, pady=2)
        enable_entry_undo(hold_entry, hold_var)

        ttk.Label(win, text="到尽头：").pack(anchor="w", padx=10, pady=(10, 2))
        mode_var = tk.StringVar(value=self.list_mode)
        ttk.Radiobutton(win, text="循环（回到第一个值）", variable=mode_var,
                        value="loop").pack(anchor="w", padx=20)
        ttk.Radiobutton(win, text="停止（停在最后一个值）", variable=mode_var,
                        value="stop").pack(anchor="w", padx=20)

        def save():
            try:
                raw = box.get("1.0", "end-1c")
                tokens = re.split(r"[\s,，/;；、]+", raw)
                vals = []
                for t in tokens:
                    t = t.strip()
                    if not t:
                        continue
                    try:
                        vals.append(int(t, 10))
                    except ValueError:
                        raise ValueError(f"无法解析的列表值: {t!r}")
                if not vals:
                    raise ValueError("请至少输入一个数字")
                if any(v < 0 for v in vals):
                    raise ValueError("列表数字必须是非负整数")
                hold = parse_hold_seconds(hold_var.get())
                self.list_values = vals
                self.var_list_hold.set(hold_var.get().strip() or "0")
                self.list_mode = mode_var.get() or "loop"
                for k in [k for k in self.counters if k.startswith("l_")]:
                    del self.counters[k]
                win.destroy()
                self.log(
                    f"已设置 L 全局列表，共 {len(vals)} 个值，保持 {hold} 秒，"
                    f"{'循环' if self.list_mode == 'loop' else '停止'}"
                )
            except ValueError as e:
                messagebox.showerror("列表格式错误", str(e), parent=win)

        row = ttk.Frame(win)
        row.pack(fill="x", padx=10, pady=8)
        ttk.Button(row, text="确定", command=save).pack(side="right")
        ttk.Button(row, text="取消", command=win.destroy).pack(side="right", padx=6)

    def get_net_config(self):
        local_ip = self.var_local_ip.get().strip() or "0.0.0.0"
        try:
            local_port = int(self.var_local_port.get().strip() or "0")
        except ValueError:
            raise ValueError("本机端口必须是整数")
        if not 0 <= local_port <= 65535:
            raise ValueError("本机端口范围 0~65535")

        target_ip = self.var_target_ip.get().strip()
        if not target_ip:
            raise ValueError("目标 IP 不能为空")

        try:
            target_port = int(self.var_target_port.get().strip())
        except ValueError:
            raise ValueError("目标端口必须是整数")
        if not 1 <= target_port <= 65535:
            raise ValueError("目标端口范围 1~65535")

        try:
            interval = int(self.var_interval.get().strip() or "1000")
        except ValueError:
            raise ValueError("发送间隔必须是整数毫秒")
        if interval < 1:
            interval = 1

        return local_ip, local_port, target_ip, target_port, interval

    def on_send(self):
        if self.thread is not None and self.thread.is_alive():
            self.stop_event.set()
            self.btn_send.config(state="disabled", text="停止中...")
            return

        try:
            local_ip, local_port, target_ip, target_port, interval = self.get_net_config()
            list_hold = parse_hold_seconds(self.var_list_hold.get())
            template = self.txt_template.get("1.0", "end-1c")
            parts = compile_template(template)
            if not parts:
                raise ValueError("报文为空或没有有效十六进制内容")
            self.sent_count = 0
            self.stop_event.clear()

            if self.var_continuous.get():
                for k in [k for k in self.counters if k.startswith("l_")]:
                    del self.counters[k]
                self.btn_send.config(text="停止发送")
                self.thread = threading.Thread(
                    target=self.sender_loop,
                    args=(parts, local_ip, local_port, target_ip,
                          target_port, interval, list_hold, self.list_mode),
                    daemon=True,
                )
                self.thread.start()
            else:
                payload = build_payload(
                    parts, self.counters, self.list_values,
                    list_hold, self.t_range, self.list_mode,
                )
                self.send_single_udp(payload, local_ip, local_port,
                                     target_ip, target_port)
                self.sent_count = 1
                self.status_var.set(f"已发送 1 包，共 {len(payload)} 字节")
                self.log(f"发送 {len(payload)} 字节: {hex_preview(payload)}")
        except Exception as e:
            self.stop_event.set()
            self.btn_send.config(state="normal", text="发送")
            messagebox.showerror("错误", str(e))

    def send_single_udp(self, payload, local_ip, local_port, target_ip, target_port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((local_ip, local_port))
            sock.sendto(payload, (target_ip, target_port))
        finally:
            sock.close()

    def sender_loop(self, parts, local_ip, local_port, target_ip,
                    target_port, interval, list_hold, list_mode):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((local_ip, local_port))
        except Exception as e:
            self.ui_call(lambda e=e: messagebox.showerror("绑定失败", str(e)))
            self.ui_call(self.finish_sending)
            sock.close()
            return

        try:
            while not self.stop_event.is_set():
                try:
                    payload = build_payload(
                        parts, self.counters, self.list_values,
                        list_hold, self.t_range, list_mode,
                    )
                    sock.sendto(payload, (target_ip, target_port))
                    self.sent_count += 1
                    if self.sent_count == 1 or self.sent_count % 10 == 0:
                        cnt = self.sent_count
                        ln = len(payload)
                        self.ui_call(
                            lambda cnt=cnt, ln=ln: self.status_var.set(
                                f"持续发送中：已发送 {cnt} 包，最后 {ln} 字节"
                            )
                        )
                except Exception as e:
                    self.ui_call(lambda e=e: self.log(f"发送失败: {e}"))
                    break
                self.stop_event.wait(interval / 1000.0)
        finally:
            sock.close()
            self.ui_call(self.finish_sending)

    def finish_sending(self):
        self.thread = None
        self.btn_send.config(state="normal", text="发送")
        self.status_var.set(f"已停止，共发送 {self.sent_count} 包")

    def cleanup(self):
        self.stop_event.set()


# ============================================================
# TCP Server 页面
# ============================================================

class TcpServerPage(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app

        self.server_socket = None
        self.accept_thread = None
        self.stop_event = threading.Event()
        self.clients = {}
        self.client_lock = threading.Lock()
        self.client_counter = 0

        self.send_thread = None
        self.send_stop_event = threading.Event()
        self.send_counters = {}
        self.list_values = []
        self.t_range = None
        self.list_mode = "loop"
        self.sent_count = 0

        self.ui_queue = queue.Queue()
        self._schedule_poll()

        self.var_listen_ip = tk.StringVar(value="0.0.0.0")
        self.var_listen_port = tk.StringVar(value="8000")
        self.var_client = tk.StringVar()
        self.status_var = tk.StringVar(value="未连接")
        self.btn_text = tk.StringVar(value="连接")

        self.var_interval = tk.StringVar(value="1000")
        self.var_continuous = tk.BooleanVar(value=False)
        self.var_list_hold = tk.StringVar(value="0")
        self.send_status_var = tk.StringVar(value="")

        self.build_ui()
        self.load_config()

    def _schedule_poll(self):
        self.after(50, self._poll_queue)

    def _poll_queue(self):
        while True:
            try:
                fn, args = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args)
            except Exception:
                pass
        self._schedule_poll()

    def ui_call(self, fn, *args):
        self.ui_queue.put((fn, args))

    def load_config(self):
        self.var_listen_ip.set(self.app.load_setting("tcp.local_ip", "0.0.0.0"))
        self.var_listen_port.set(self.app.load_setting("tcp.local_port", "8000"))
        self.var_interval.set(self.app.load_setting("tcp.interval", "1000"))
        self.var_continuous.set(self.app.load_setting("tcp.continuous", "0") == "1")
        self.var_list_hold.set(self.app.load_setting("tcp.list_hold", "0"))
        self.list_mode = self.app.load_setting("tcp.list_mode", "loop") or "loop"

        t_min = self.app.load_setting("tcp.t_min", "")
        t_max = self.app.load_setting("tcp.t_max", "")
        if t_min != "" and t_max != "":
            try:
                self.t_range = (int(t_min), int(t_max))
            except ValueError:
                self.t_range = None
        else:
            self.t_range = None

        tpl = self.app.load_setting("tcp.template", "")
        if tpl:
            self.txt_send.insert("1.0", tpl)
        try:
            self.list_values = [int(x) for x in
                                self.app.load_setting("tcp.list_values", "").split(",")
                                if x.strip()]
        except ValueError:
            self.list_values = []

    def save_config(self):
        self.app.save_setting("tcp.local_ip", self.var_listen_ip.get().strip())
        self.app.save_setting("tcp.local_port", self.var_listen_port.get().strip())
        self.app.save_setting("tcp.interval", self.var_interval.get().strip())
        self.app.save_setting("tcp.continuous", "1" if self.var_continuous.get() else "0")
        self.app.save_setting("tcp.list_hold", self.var_list_hold.get().strip())
        self.app.save_setting("tcp.list_mode", self.list_mode)
        if self.t_range is not None:
            self.app.save_setting("tcp.t_min", str(self.t_range[0]))
            self.app.save_setting("tcp.t_max", str(self.t_range[1]))
        else:
            self.app.save_setting("tcp.t_min", "")
            self.app.save_setting("tcp.t_max", "")
        self.app.save_setting("tcp.template", self.txt_send.get("1.0", "end-1c"))
        self.app.save_setting("tcp.list_values", ",".join(map(str, self.list_values)))

    def _entry(self, parent, var, **kwargs):
        e = ttk.Entry(parent, textvariable=var, **kwargs)
        enable_entry_undo(e, var)
        return e

    def build_ui(self):
        cfg = ttk.LabelFrame(self, text="TCP Server 配置")
        cfg.pack(fill="x", padx=4, pady=4)

        ttk.Label(cfg, text="监听 IP").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self._entry(cfg, self.var_listen_ip, width=18).grid(row=0, column=1, padx=4, pady=4)
        ttk.Label(cfg, text="监听端口").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        self._entry(cfg, self.var_listen_port, width=10).grid(row=0, column=3, padx=4, pady=4)
        self.btn_conn = ttk.Button(cfg, textvariable=self.btn_text, command=self.on_button, width=12)
        self.btn_conn.grid(row=0, column=4, padx=8, pady=4)
        ttk.Label(cfg, textvariable=self.status_var).grid(row=0, column=5, sticky="w", padx=8, pady=4)

        cf = ttk.Frame(self)
        cf.pack(fill="x", padx=4, pady=2)
        ttk.Label(cf, text="客户端:").pack(side="left")
        self.combo_clients = ttk.Combobox(
            cf, textvariable=self.var_client, values=[], width=45, state="readonly"
        )
        self.combo_clients.pack(side="left", padx=4)
        ttk.Button(cf, text="刷新", command=self.refresh_client_list).pack(side="left")

        sc = ttk.LabelFrame(self, text="发送配置")
        sc.pack(fill="x", padx=4, pady=4)
        ttk.Label(sc, text="发送间隔(ms)").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self._entry(sc, self.var_interval, width=10).grid(row=0, column=1, padx=4, pady=4)
        ttk.Button(sc, text="编辑 T 范围", command=self.edit_t_range).grid(
            row=0, column=2, padx=4, pady=4)
        ttk.Button(sc, text="编辑 L 列表", command=self.edit_l_list).grid(
            row=0, column=3, padx=4, pady=4)
        ttk.Checkbutton(sc, text="持续发送", variable=self.var_continuous).grid(
            row=0, column=4, sticky="w", padx=4, pady=4)
        self.btn_send = ttk.Button(sc, text="发送", command=self.on_send_button, width=10)
        self.btn_send.grid(row=0, column=5, padx=4, pady=4)
        ttk.Label(sc, textvariable=self.send_status_var).grid(
            row=0, column=6, sticky="w", padx=4, pady=4)
        ttk.Label(
            sc,
            text="{.. T} / {.. P} / {.. L} 可在报文中直接指定；无指令默认随机",
            foreground="gray",
        ).grid(row=1, column=0, columnspan=7, sticky="w", padx=4, pady=2)

        sf = ttk.LabelFrame(
            self,
            text="发送数据 (HEX，支持 #...# 注释、{..} 变化值、[..] 时间戳、[.. +/-N] 小时偏移、[.. R] 反转)"
        )
        sf.pack(fill="x", padx=4, pady=4)
        self.txt_send = tk.Text(sf, height=18, wrap="char",
                                font=("Consolas", 10),
                                undo=True, autoseparators=True, maxundo=-1)
        tscroll = ttk.Scrollbar(sf, orient="vertical", command=self.txt_send.yview)
        self.txt_send.configure(yscrollcommand=tscroll.set)
        self.txt_send.pack(side="left", fill="both", expand=True)
        tscroll.pack(side="right", fill="y")
        enable_text_undo(self.txt_send)

        rf = ttk.LabelFrame(self, text="接收数据 (HEX)")
        rf.pack(fill="x", padx=4, pady=4)
        self.txt_recv = tk.Text(rf, height=7, wrap="word",
                                font=("Consolas", 9),
                                undo=True, autoseparators=True, maxundo=-1)
        rs = ttk.Scrollbar(rf, orient="vertical", command=self.txt_recv.yview)
        self.txt_recv.configure(yscrollcommand=rs.set)
        self.txt_recv.pack(side="left", fill="both", expand=True)
        rs.pack(side="right", fill="y")
        enable_text_undo(self.txt_recv)

        bf = ttk.Frame(self)
        bf.pack(fill="x", padx=4, pady=4)
        ttk.Button(bf, text="清空接收",
                   command=lambda: self.txt_recv.delete("1.0", "end")).pack(side="left")

    def log_recv(self, msg):
        self.txt_recv.insert("end", msg + "\n")
        self.txt_recv.see("end")
        try:
            line_count = int(self.txt_recv.index("end-1c").split(".")[0])
            if line_count > 500:
                self.txt_recv.delete("1.0", "201.0")
        except Exception:
            pass

    def on_button(self):
        if self.server_socket is None:
            self.start_server()
        else:
            self.stop_server()

    def start_server(self):
        ip = self.var_listen_ip.get().strip() or "0.0.0.0"
        try:
            port = int(self.var_listen_port.get().strip())
        except ValueError:
            messagebox.showerror("错误", "监听端口必须是整数")
            return
        if not 0 <= port <= 65535:
            messagebox.showerror("错误", "端口范围 0~65535")
            return

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((ip, port))
            s.listen(10)
        except Exception as e:
            messagebox.showerror("监听失败", str(e))
            return

        self.server_socket = s
        self.stop_event.clear()
        self.btn_text.set("关闭连接")
        self.status_var.set(f"监听中 {ip}:{port}，客户端 0")
        self.log_recv(f"[系统] 开始监听 {ip}:{port}")

        self.accept_thread = threading.Thread(target=self.accept_loop, args=(s,), daemon=True)
        self.accept_thread.start()

    def accept_loop(self, sock):
        while not self.stop_event.is_set():
            try:
                conn, addr = sock.accept()
            except OSError:
                break
            except Exception:
                break

            with self.client_lock:
                self.client_counter += 1
                cid = self.client_counter
                self.clients[cid] = {"conn": conn, "addr": addr, "thread": None}

            t = threading.Thread(
                target=self.client_recv_loop, args=(cid, conn, addr), daemon=True
            )
            with self.client_lock:
                if cid in self.clients:
                    self.clients[cid]["thread"] = t
            t.start()

            self.ui_call(self.on_client_connected, cid, addr)

    def on_client_connected(self, cid, addr):
        self.refresh_client_list()
        self.log_recv(f"[系统] 客户端 #{cid} 已连接 {addr[0]}:{addr[1]}")
        with self.client_lock:
            n = len(self.clients)
        if self.server_socket is not None:
            self.status_var.set(f"监听中，客户端 {n}")

    def client_recv_loop(self, cid, conn, addr):
        while not self.stop_event.is_set():
            try:
                data = conn.recv(65535)
            except OSError:
                break
            except Exception:
                break
            if not data:
                break
            hexstr = hex_preview(data)
            self.ui_call(self.on_data_received, cid, addr, hexstr)

        try:
            conn.close()
        except Exception:
            pass
        with self.client_lock:
            self.clients.pop(cid, None)
        self.ui_call(self.on_client_disconnected, cid, addr)

    def on_data_received(self, cid, addr, hexstr):
        ts = time.strftime("%H:%M:%S")
        n_bytes = len(hexstr.split())
        self.log_recv(f"[{ts}] 收 #{cid} {addr[0]}:{addr[1]} ({n_bytes}B): {hexstr}")

    def on_client_disconnected(self, cid, addr):
        self.refresh_client_list()
        self.log_recv(f"[系统] 客户端 #{cid} 已断开 {addr[0]}:{addr[1]}")
        with self.client_lock:
            n = len(self.clients)
        if self.server_socket is not None:
            self.status_var.set(f"监听中，客户端 {n}")

    def stop_server(self):
        was_active = self.server_socket is not None or bool(self.clients)
        self.stop_event.set()

        if self.send_thread is not None and self.send_thread.is_alive():
            self.send_stop_event.set()

        s = self.server_socket
        self.server_socket = None
        if s is not None:
            try:
                s.close()
            except Exception:
                pass

        with self.client_lock:
            clients = list(self.clients.items())
            self.clients.clear()
        for cid, info in clients:
            try:
                info["conn"].close()
            except Exception:
                pass

        self.btn_text.set("连接")
        self.status_var.set("未连接")
        self.var_client.set("")
        self.combo_clients["values"] = []

        if was_active:
            self.log_recv("[系统] 已关闭连接")

    def refresh_client_list(self):
        with self.client_lock:
            items = list(self.clients.items())
        values = [f"#{cid} {info['addr'][0]}:{info['addr'][1]}" for cid, info in items]
        self.combo_clients["values"] = values
        cur = self.var_client.get()
        if values and cur not in values:
            self.var_client.set(values[0])
        elif not values:
            self.var_client.set("")

    def edit_t_range(self):
        win = tk.Toplevel(self)
        apply_app_icon(win)
        win.title("编辑 T 全局范围")
        win.transient(self.winfo_toplevel())
        win.geometry("360x180")
        win.after_idle(lambda: center_on_parent(win, self.winfo_toplevel()))
        ttk.Label(win, text="未设置时按字段满量程处理（1 字节 0~255、2 字节 0~65535…）。").pack(
            anchor="w", padx=10, pady=(10, 4))
        ttk.Label(win, text="最小值").pack(anchor="w", padx=10)
        lo_var = tk.StringVar(value=str(self.t_range[0]) if self.t_range else "")
        lo_entry = ttk.Entry(win, textvariable=lo_var, width=18)
        lo_entry.pack(anchor="w", padx=10, pady=2)
        enable_entry_undo(lo_entry, lo_var)
        ttk.Label(win, text="最大值").pack(anchor="w", padx=10)
        hi_var = tk.StringVar(value=str(self.t_range[1]) if self.t_range else "")
        hi_entry = ttk.Entry(win, textvariable=hi_var, width=18)
        hi_entry.pack(anchor="w", padx=10, pady=2)
        enable_entry_undo(hi_entry, hi_var)

        def save():
            lo_s = lo_var.get().strip()
            hi_s = hi_var.get().strip()
            if not lo_s and not hi_s:
                self.t_range = None
                win.destroy()
                self.log_recv("[系统] 已清除 T 全局范围（按字段满量程）")
                return
            try:
                lo = int(lo_s)
                hi = int(hi_s)
            except ValueError:
                messagebox.showerror("错误", "范围必须是整数", parent=win)
                return
            if lo < 0 or hi < 0:
                messagebox.showerror("错误", "范围必须是非负整数", parent=win)
                return
            if lo > hi:
                messagebox.showerror("错误", "最小值不能大于最大值", parent=win)
                return
            self.t_range = (lo, hi)
            win.destroy()
            self.log_recv(f"[系统] 已设置 T 全局范围 {lo}~{hi}")

        row = ttk.Frame(win)
        row.pack(fill="x", padx=10, pady=8)
        ttk.Button(row, text="确定", command=save).pack(side="right")
        ttk.Button(row, text="取消", command=win.destroy).pack(side="right", padx=6)

    def edit_l_list(self):
        win = tk.Toplevel(self)
        apply_app_icon(win)
        win.title("编辑 L 全局列表")
        win.transient(self.winfo_toplevel())
        win.geometry("560x560")
        win.after_idle(lambda: center_on_parent(win, self.winfo_toplevel()))

        ttk.Label(
            win,
            text="支持一行一个值，或用逗号 / 空格 / 斜杠 / 中文逗号 分隔（如 1,2,3 或 1 2 3 或 1/2/3）：",
        ).pack(anchor="w", padx=10, pady=(10, 4))

        box_frame = ttk.Frame(win)
        box_frame.pack(fill="both", expand=True, padx=10, pady=4)
        box = tk.Text(box_frame, height=12, width=40, font=("Consolas", 10),
                      undo=True, autoseparators=True, maxundo=-1)
        vscroll = ttk.Scrollbar(box_frame, orient="vertical", command=box.yview)
        box.configure(yscrollcommand=vscroll.set)
        box.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")
        if self.list_values:
            box.insert("1.0", "\n".join(map(str, self.list_values)))
        enable_text_undo(box)

        ttk.Label(win, text="列表保持(秒)：0 = 每发一包切换；>0 = 每 N 秒切换（期间重复发送当前值）").pack(
            anchor="w", padx=10, pady=(6, 2))
        hold_var = tk.StringVar(value=self.var_list_hold.get())
        hold_entry = ttk.Entry(win, textvariable=hold_var, width=12)
        hold_entry.pack(anchor="w", padx=10, pady=2)
        enable_entry_undo(hold_entry, hold_var)

        ttk.Label(win, text="到尽头：").pack(anchor="w", padx=10, pady=(10, 2))
        mode_var = tk.StringVar(value=self.list_mode)
        ttk.Radiobutton(win, text="循环（回到第一个值）", variable=mode_var,
                        value="loop").pack(anchor="w", padx=20)
        ttk.Radiobutton(win, text="停止（停在最后一个值）", variable=mode_var,
                        value="stop").pack(anchor="w", padx=20)

        def save():
            try:
                raw = box.get("1.0", "end-1c")
                tokens = re.split(r"[\s,，/;；、]+", raw)
                vals = []
                for t in tokens:
                    t = t.strip()
                    if not t:
                        continue
                    try:
                        vals.append(int(t, 10))
                    except ValueError:
                        raise ValueError(f"无法解析的列表值: {t!r}")
                if not vals:
                    raise ValueError("请至少输入一个数字")
                if any(v < 0 for v in vals):
                    raise ValueError("列表数字必须是非负整数")
                hold = parse_hold_seconds(hold_var.get())
                self.list_values = vals
                self.var_list_hold.set(hold_var.get().strip() or "0")
                self.list_mode = mode_var.get() or "loop"
                for k in [k for k in self.send_counters if k.startswith("l_")]:
                    del self.send_counters[k]
                win.destroy()
                self.log_recv(
                    f"[系统] 已设置 L 全局列表，共 {len(vals)} 个值，保持 {hold} 秒，"
                    f"{'循环' if self.list_mode == 'loop' else '停止'}"
                )
            except ValueError as e:
                messagebox.showerror("列表格式错误", str(e), parent=win)

        row = ttk.Frame(win)
        row.pack(fill="x", padx=10, pady=8)
        ttk.Button(row, text="确定", command=save).pack(side="right")
        ttk.Button(row, text="取消", command=win.destroy).pack(side="right", padx=6)

    def on_send_button(self):
        if self.send_thread is not None and self.send_thread.is_alive():
            self.send_stop_event.set()
            self.btn_send.config(state="disabled", text="停止中...")
            return

        sel = self.var_client.get().strip()
        if not sel:
            messagebox.showwarning("提示", "请先选择客户端")
            return
        try:
            cid = int(sel.split(" ")[0].lstrip("#"))
        except Exception:
            messagebox.showerror("错误", "客户端选择无效")
            return

        with self.client_lock:
            if cid not in self.clients:
                messagebox.showerror("错误", "客户端已断开")
                return

        text = self.txt_send.get("1.0", "end-1c")
        try:
            parts = compile_template(text)
        except Exception as e:
            messagebox.showerror("报文解析失败", str(e))
            return
        if not parts:
            messagebox.showwarning("提示", "发送内容为空")
            return

        try:
            interval = int(self.var_interval.get().strip() or "1000")
        except ValueError:
            interval = 1000
        if interval < 1:
            interval = 1

        try:
            list_hold = parse_hold_seconds(self.var_list_hold.get())
        except ValueError as e:
            messagebox.showerror("错误", str(e))
            return

        self.sent_count = 0
        self.send_stop_event.clear()

        if self.var_continuous.get():
            for k in [k for k in self.send_counters if k.startswith("l_")]:
                del self.send_counters[k]
            self.btn_send.config(text="停止发送")
            self.send_status_var.set("持续发送中...")
            self.send_thread = threading.Thread(
                target=self.send_loop,
                args=(parts, cid, interval, list_hold, self.list_mode),
                daemon=True,
            )
            self.send_thread.start()
        else:
            try:
                payload = build_payload(
                    parts, self.send_counters, self.list_values,
                    list_hold, self.t_range, self.list_mode,
                )
                with self.client_lock:
                    info = self.clients.get(cid)
                if info is None:
                    raise RuntimeError("客户端已断开")
                info["conn"].sendall(payload)
                self.sent_count = 1
                ts = time.strftime("%H:%M:%S")
                addr = info["addr"]
                self.log_recv(
                    f"[{ts}] 发 #{cid} {addr[0]}:{addr[1]} ({len(payload)}B): "
                    f"{hex_preview(payload)}"
                )
                self.send_status_var.set(f"已发送 1 包，共 {len(payload)} 字节")
            except Exception as e:
                messagebox.showerror("发送失败", str(e))

    def send_loop(self, parts, cid, interval, list_hold, list_mode):
        local_count = 0
        while not self.send_stop_event.is_set():
            with self.client_lock:
                info = self.clients.get(cid)
            if info is None:
                self.ui_call(self.log_recv, "[系统] 客户端已断开，停止持续发送")
                break
            try:
                payload = build_payload(
                    parts, self.send_counters, self.list_values,
                    list_hold, self.t_range, list_mode,
                )
                info["conn"].sendall(payload)
                local_count += 1
                addr = info["addr"]
                ts = time.strftime("%H:%M:%S")
                ln = len(payload)
                hexstr = hex_preview(payload)
                self.ui_call(
                    self.log_recv,
                    f"[{ts}] 发 #{cid} {addr[0]}:{addr[1]} ({ln}B): {hexstr}",
                )
                if local_count == 1 or local_count % 10 == 0:
                    cnt = local_count
                    self.ui_call(
                        self.send_status_var.set,
                        f"持续发送中：已发送 {cnt} 包",
                    )
            except Exception as e:
                self.ui_call(self.log_recv, f"[系统] 发送失败: {e}")
                break
            self.send_stop_event.wait(interval / 1000.0)
        self.ui_call(self.finish_send, local_count)

    def finish_send(self, count):
        self.send_thread = None
        self.btn_send.config(state="normal", text="发送")
        self.send_status_var.set(f"已停止，共发送 {count} 包")

    def cleanup(self):
        try:
            self.send_stop_event.set()
        except Exception:
            pass
        try:
            self.stop_server()
        except Exception:
            pass


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()