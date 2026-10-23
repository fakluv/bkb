# -*- coding: utf-8 -*-
r"""
UDP / TCP Server 十六进制报文发送工具

功能：
1. UDP 发送页面：本机/目标 IP 与端口、持续发送、{} 变化值（随机/自增/按列表）、[] 时间戳（含 R 反转）。
2. TCP Server 页面：
   - 点击“连接”进入监听状态；监听期间即使不发送数据也不会断开；
   - “连接/关闭连接”为同一个按钮，文字动态切换；
   - 支持多客户端；可接收 HEX 数据；
   - 发送侧支持与 UDP 相同的 {} 变化值、[] 时间戳、发送间隔、持续发送、发送按钮动态切换。
3. #...# 之间为注释，发送前会被删除；"# #" 连写会自动合并。
4. 配置全部保存在注册表 HKEY_CURRENT_USER\Software\UdpHexSender 下，不生成配置文件。
5. 列表模式支持“列表保持(秒)”：
   - 0：每发一包切换一个列表值（原行为）；
   - >0：每 N 秒切换一个列表值，N 秒内重复发送当前值。
"""

import tkinter as tk
from tkinter import ttk, messagebox
import socket
import threading
import time
import random
import re
import queue

REG_PATH = r"Software\UdpHexSender"

try:
    import winreg
except ImportError:
    winreg = None


# ============================================================
# 报文解析公用函数
# ============================================================

HEX_CHARS = set("0123456789abcdefABCDEF")


def strip_comments(text: str) -> str:
 """
 删除 #...# 注释。

 处理规则：
 1. 先做行内预处理：把 "# #"、"#  #" 这类连续 # 合并为单个 #，
    以兼容原文中 "00 # #本端雷达状态字#" 这种写法。
 2. 再逐行扫描：遇到 # 切换注释状态，注释状态内的字符全部丢弃。
 3. 行尾仍在注释状态时，说明注释到行尾结束，正常结`束。
 """
 import re

 # 行内合并 "# #" -> "#"，不影响跨行注释
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
    """提取连续十六进制字符；避免逐字符 Python 循环。"""
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


def count_bytes_from_content(content: str) -> int:
    tokens = parse_hex_tokens(content)
    return sum(len(t) // 2 for t in tokens)


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
            n = count_bytes_from_content(content)
            if n <= 0:
                raise ValueError("{} 内没有有效的十六进制字节")
            parts.append(("var", n, var_idx))
            var_idx += 1
            i = j + 1

        elif ch == "[":
            j = text.find("]", i + 1)
            if j < 0:
                raise ValueError("未找到匹配的 ]")
            content = text[i + 1:j].strip()
            reverse = False
            if content and content[-1] in ("R", "r"):
                reverse = True
                content = content[:-1].strip()
            n = count_bytes_from_content(content)
            if n <= 0:
                n = 4
            parts.append(("ts", n, reverse))
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


def build_payload(parts, mode: str, counters: dict, list_values=None,
                  list_hold: float = 0) -> bytes:
    out = bytearray()
    list_values = list_values or []
    has_var = False

    # 先算出本次使用的列表位置
    if mode == "list" and list_values:
        if list_hold > 0:
            # 按时间推进：每 list_hold 秒切换一个值
            now = time.time()
            anchor = counters.get("__list_anchor")
            if anchor is None:
                anchor = now
                counters["__list_anchor"] = anchor
            list_pos = int((now - anchor) // list_hold) % len(list_values)
            counters["__list_idx"] = list_pos
        else:
            # 按包推进：每次发送切换一格
            list_pos = counters.get("__list_idx", 0) % len(list_values)
    else:
        list_pos = 0

    for part in parts:
        kind = part[0]
        if kind == "fixed":
            out.extend(part[1])
        elif kind == "var":
            has_var = True
            _, n, idx = part
            maxv = (1 << (8 * n)) - 1
            if mode == "random":
                v = random.randint(0, maxv)
            elif mode == "list":
                if not list_values:
                    raise ValueError("已选择‘按列表’，请先点击‘按列表’输入数字列表")
                v = list_values[list_pos]
                if v < 0 or v > maxv:
                    raise ValueError(
                        f"列表数值 {v} 超出当前 {{}} 字段可表示范围 0~{maxv}"
                    )
            else:
                v = counters.get(idx, 0)
                counters[idx] = (v + 1) % (maxv + 1)
            out.extend(v.to_bytes(n, "big"))
        elif kind == "ts":
            _, n, reverse = part
            v = int(time.time()) & ((1 << (8 * n)) - 1)
            b = v.to_bytes(n, "big")
            out.extend(b[::-1] if reverse else b)

    # 仅“按包推进”模式在末尾前进一格；“按时间推进”模式由时间决定
    if mode == "list" and has_var and list_values and list_hold <= 0:
        counters["__list_idx"] = (list_pos + 1) % len(list_values)
    return bytes(out)


def hex_preview(payload: bytes, limit: int = 256) -> str:
    """限制日志中的 HEX 展示长度，避免超长报文拖慢 Tk 文本控件。"""
    shown = payload[:limit].hex(" ").upper()
    if len(payload) > limit:
        shown += f" ...（省略 {len(payload) - limit} 字节）"
    return shown


def parse_hold_seconds(text: str) -> float:
    """解析“列表保持(秒)”；0 表示每发一包切换一格。"""
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
        root.title("UDP / TCP Server 报文发送工具")
        root.geometry("1040x780")

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
        self.sent_count = 0

        self.ui_queue = queue.Queue()
        self._schedule_poll()

        self.var_local_ip = tk.StringVar(value="0.0.0.0")
        self.var_local_port = tk.StringVar(value="0")
        self.var_target_ip = tk.StringVar(value="127.0.0.1")
        self.var_target_port = tk.StringVar(value="9000")
        self.var_interval = tk.StringVar(value="1000")
        self.var_continuous = tk.BooleanVar(value=False)
        self.var_mode = tk.StringVar(value="random")
        self.var_list_hold = tk.StringVar(value="0")
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
        self.var_mode.set(self.app.load_setting("udp.mode", "random"))
        self.var_list_hold.set(self.app.load_setting("udp.list_hold", "0"))
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
        self.app.save_setting("udp.mode", self.var_mode.get())
        self.app.save_setting("udp.list_hold", self.var_list_hold.get().strip())
        self.app.save_setting("udp.template", self.txt_template.get("1.0", "end-1c"))
        self.app.save_setting("udp.list_values", ",".join(map(str, self.list_values)))

    def build_ui(self):
        cfg = ttk.LabelFrame(self, text="UDP 配置")
        cfg.pack(fill="x", padx=4, pady=4)

        ttk.Label(cfg, text="本机 IP").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(cfg, textvariable=self.var_local_ip, width=18).grid(row=0, column=1, padx=4, pady=4)
        ttk.Label(cfg, text="本机端口").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        ttk.Entry(cfg, textvariable=self.var_local_port, width=10).grid(row=0, column=3, padx=4, pady=4)
        ttk.Label(cfg, text="目标 IP").grid(row=0, column=4, sticky="w", padx=4, pady=4)
        ttk.Entry(cfg, textvariable=self.var_target_ip, width=18).grid(row=0, column=5, padx=4, pady=4)
        ttk.Label(cfg, text="目标端口").grid(row=0, column=6, sticky="w", padx=4, pady=4)
        ttk.Entry(cfg, textvariable=self.var_target_port, width=10).grid(row=0, column=7, padx=4, pady=4)

        ttk.Label(cfg, text="发送间隔(ms)").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(cfg, textvariable=self.var_interval, width=10).grid(row=1, column=1, padx=4, pady=4)
        ttk.Label(cfg, text="{} 变化方式").grid(row=1, column=2, sticky="w", padx=4, pady=4)
        ttk.Radiobutton(cfg, text="随机", variable=self.var_mode, value="random").grid(
            row=1, column=3, sticky="w", padx=4, pady=4)
        ttk.Radiobutton(cfg, text="自增", variable=self.var_mode, value="inc").grid(
            row=1, column=4, sticky="w", padx=4, pady=4)
        ttk.Radiobutton(cfg, text="按列表", variable=self.var_mode, value="list").grid(
            row=1, column=5, sticky="w", padx=4, pady=4)
        ttk.Button(cfg, text="编辑列表", command=self.edit_list).grid(row=1, column=6, padx=4, pady=4)
        ttk.Checkbutton(cfg, text="持续发送", variable=self.var_continuous).grid(
            row=1, column=7, sticky="w", padx=4, pady=4)

        ttk.Label(cfg, text="列表保持(秒)").grid(row=2, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(cfg, textvariable=self.var_list_hold, width=10).grid(row=2, column=1, padx=4, pady=4)
        ttk.Label(
            cfg,
            text="0 = 每发一包切换；>0 = 每 N 秒切换（期间重复发送当前值）",
            foreground="gray",
        ).grid(row=2, column=2, columnspan=6, sticky="w", padx=4, pady=4)

        tf = ttk.LabelFrame(
            self,
            text="报文模板：#...# 为注释； {..} 为变化值； [..] 为时间戳； [.. R] 为反转时间戳"
        )
        tf.pack(fill="both", expand=True, padx=4, pady=4)

        self.txt_template = tk.Text(tf, height=22, wrap="none", font=("Consolas", 10))
        yscroll = ttk.Scrollbar(tf, orient="vertical", command=self.txt_template.yview)
        xscroll = ttk.Scrollbar(tf, orient="horizontal", command=self.txt_template.xview)
        self.txt_template.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.txt_template.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)

        bf = ttk.Frame(self)
        bf.pack(fill="x", padx=4, pady=4)
        self.btn_send = ttk.Button(bf, text="发送", command=self.on_send)
        self.btn_send.pack(side="left")
        ttk.Button(bf, text="清空日志", command=self.clear_log).pack(side="left", padx=6)
        ttk.Label(bf, textvariable=self.status_var).pack(side="right")

        lf = ttk.LabelFrame(self, text="日志")
        lf.pack(fill="x", padx=4, pady=4)
        self.txt_log = tk.Text(lf, height=7, wrap="word", font=("Consolas", 9))
        log_scroll = ttk.Scrollbar(lf, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=log_scroll.set)
        self.txt_log.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

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

    def edit_list(self):
        win = tk.Toplevel(self)
        win.title("{} 按列表设置")
        win.transient(self.winfo_toplevel())
        win.geometry("360x340")
        ttk.Label(win, text="每行输入一个十进制整数，按输入顺序循环使用：").pack(
            anchor="w", padx=10, pady=(10, 4))
        box = tk.Text(win, height=14, width=36, font=("Consolas", 10))
        box.pack(fill="both", expand=True, padx=10, pady=4)
        if self.list_values:
            box.insert("1.0", "\n".join(map(str, self.list_values)))

        def save():
            try:
                vals = [int(line.strip(), 10) for line in
                        box.get("1.0", "end-1c").splitlines() if line.strip()]
                if not vals:
                    raise ValueError("请至少输入一个数字")
                if any(v < 0 for v in vals):
                    raise ValueError("列表数字必须是非负整数")
                self.list_values = vals
                self.var_mode.set("list")
                self.counters["__list_idx"] = 0
                self.counters.pop("__list_anchor", None)
                win.destroy()
                self.log(f"已设置按列表模式，共 {len(vals)} 个数值")
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
            mode = self.var_mode.get()
            self.sent_count = 0
            self.stop_event.clear()

            if self.var_continuous.get():
                # 启动持续发送时从列表第一个值开始（保持模式下重新计时）
                if mode == "list":
                    self.counters.pop("__list_anchor", None)
                    self.counters["__list_idx"] = 0
                self.btn_send.config(text="停止发送")
                self.thread = threading.Thread(
                    target=self.sender_loop,
                    args=(parts, local_ip, local_port, target_ip,
                          target_port, interval, mode, list_hold),
                    daemon=True,
                )
                self.thread.start()
            else:
                payload = build_payload(
                    parts, mode, self.counters, self.list_values, list_hold
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
                    target_port, interval, mode, list_hold):
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
                        parts, mode, self.counters, self.list_values, list_hold
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
        self.var_mode = tk.StringVar(value="random")
        self.var_list_hold = tk.StringVar(value="0")
        self.send_status_var = tk.StringVar(value="")

        self.build_ui()
        self.load_config()

    # ---- UI 队列 ----

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

    # ---- 配置 ----

    def load_config(self):
        self.var_listen_ip.set(self.app.load_setting("tcp.local_ip", "0.0.0.0"))
        self.var_listen_port.set(self.app.load_setting("tcp.local_port", "8000"))
        self.var_interval.set(self.app.load_setting("tcp.interval", "1000"))
        self.var_continuous.set(self.app.load_setting("tcp.continuous", "0") == "1")
        self.var_mode.set(self.app.load_setting("tcp.mode", "random"))
        self.var_list_hold.set(self.app.load_setting("tcp.list_hold", "0"))
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
        self.app.save_setting("tcp.mode", self.var_mode.get())
        self.app.save_setting("tcp.list_hold", self.var_list_hold.get().strip())
        self.app.save_setting("tcp.template", self.txt_send.get("1.0", "end-1c"))
        self.app.save_setting("tcp.list_values", ",".join(map(str, self.list_values)))

    # ---- UI ----

    def build_ui(self):
        cfg = ttk.LabelFrame(self, text="TCP Server 配置")
        cfg.pack(fill="x", padx=4, pady=4)

        ttk.Label(cfg, text="监听 IP").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(cfg, textvariable=self.var_listen_ip, width=18).grid(row=0, column=1, padx=4, pady=4)
        ttk.Label(cfg, text="监听端口").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        ttk.Entry(cfg, textvariable=self.var_listen_port, width=10).grid(row=0, column=3, padx=4, pady=4)
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

        # 发送配置
        sc = ttk.LabelFrame(self, text="发送配置")
        sc.pack(fill="x", padx=4, pady=4)
        ttk.Label(sc, text="发送间隔(ms)").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(sc, textvariable=self.var_interval, width=10).grid(row=0, column=1, padx=4, pady=4)
        ttk.Label(sc, text="{} 变化方式").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        ttk.Radiobutton(sc, text="随机", variable=self.var_mode, value="random").grid(
            row=0, column=3, sticky="w", padx=4, pady=4)
        ttk.Radiobutton(sc, text="自增", variable=self.var_mode, value="inc").grid(
            row=0, column=4, sticky="w", padx=4, pady=4)
        ttk.Radiobutton(sc, text="按列表", variable=self.var_mode, value="list").grid(
            row=0, column=5, sticky="w", padx=4, pady=4)
        ttk.Button(sc, text="编辑列表", command=self.edit_list).grid(row=0, column=6, padx=4, pady=4)
        ttk.Checkbutton(sc, text="持续发送", variable=self.var_continuous).grid(
            row=0, column=7, sticky="w", padx=4, pady=4)
        self.btn_send = ttk.Button(sc, text="发送", command=self.on_send_button, width=10)
        self.btn_send.grid(row=0, column=8, padx=4, pady=4)
        ttk.Label(sc, textvariable=self.send_status_var).grid(
            row=0, column=9, sticky="w", padx=4, pady=4)

        ttk.Label(sc, text="列表保持(秒)").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        ttk.Entry(sc, textvariable=self.var_list_hold, width=10).grid(row=1, column=1, padx=4, pady=4)
        ttk.Label(
            sc,
            text="0 = 每发一包切换；>0 = 每 N 秒切换（期间重复发送当前值）",
            foreground="gray",
        ).grid(row=1, column=2, columnspan=6, sticky="w", padx=4, pady=4)

        sf = ttk.LabelFrame(
            self,
            text="发送数据 (HEX，支持 #...# 注释、{..} 变化值、[..] 时间戳、[.. R] 反转)"
        )
        sf.pack(fill="x", padx=4, pady=4)
        self.txt_send = tk.Text(sf, height=22, wrap="none", font=("Consolas", 10))
        tscroll = ttk.Scrollbar(sf, orient="vertical", command=self.txt_send.yview)
        self.txt_send.configure(yscrollcommand=tscroll.set)
        self.txt_send.pack(side="left", fill="both", expand=True)
        tscroll.pack(side="right", fill="y")

        rf = ttk.LabelFrame(self, text="接收数据 (HEX)")
        rf.pack(fill="x", padx=4, pady=4)
        self.txt_recv = tk.Text(rf, height=7, wrap="word", font=("Consolas", 9))
        rs = ttk.Scrollbar(rf, orient="vertical", command=self.txt_recv.yview)
        self.txt_recv.configure(yscrollcommand=rs.set)
        self.txt_recv.pack(side="left", fill="both", expand=True)
        rs.pack(side="right", fill="y")

        bf = ttk.Frame(self)
        bf.pack(fill="x", padx=4, pady=4)
        ttk.Button(bf, text="清空接收",
                   command=lambda: self.txt_recv.delete("1.0", "end")).pack(side="left")

    # ---- 日志 ----

    def log_recv(self, msg):
        self.txt_recv.insert("end", msg + "\n")
        self.txt_recv.see("end")
        try:
            line_count = int(self.txt_recv.index("end-1c").split(".")[0])
            if line_count > 500:
                self.txt_recv.delete("1.0", "201.0")
        except Exception:
            pass

    # ---- 连接 / 关闭 ----

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

    # ---- 发送 ----

    def edit_list(self):
        win = tk.Toplevel(self)
        win.title("{} 按列表设置")
        win.transient(self.winfo_toplevel())
        win.geometry("360x340")
        ttk.Label(win, text="每行输入一个十进制整数，按输入顺序循环使用：").pack(
            anchor="w", padx=10, pady=(10, 4))
        box = tk.Text(win, height=14, width=36, font=("Consolas", 10))
        box.pack(fill="both", expand=True, padx=10, pady=4)
        if self.list_values:
            box.insert("1.0", "\n".join(map(str, self.list_values)))

        def save():
            try:
                vals = [int(line.strip(), 10) for line in
                        box.get("1.0", "end-1c").splitlines() if line.strip()]
                if not vals:
                    raise ValueError("请至少输入一个数字")
                if any(v < 0 for v in vals):
                    raise ValueError("列表数字必须是非负整数")
                self.list_values = vals
                self.var_mode.set("list")
                self.send_counters["__list_idx"] = 0
                self.send_counters.pop("__list_anchor", None)
                win.destroy()
                self.log_recv(f"[系统] 已设置按列表模式，共 {len(vals)} 个数值")
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

        mode = self.var_mode.get()
        self.sent_count = 0
        self.send_stop_event.clear()

        if self.var_continuous.get():
            if mode == "list":
                self.send_counters.pop("__list_anchor", None)
                self.send_counters["__list_idx"] = 0
            self.btn_send.config(text="停止发送")
            self.send_status_var.set("持续发送中...")
            self.send_thread = threading.Thread(
                target=self.send_loop,
                args=(parts, cid, interval, mode, list_hold),
                daemon=True,
            )
            self.send_thread.start()
        else:
            try:
                payload = build_payload(
                    parts, mode, self.send_counters, self.list_values, list_hold
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

    def send_loop(self, parts, cid, interval, mode, list_hold):
        local_count = 0
        while not self.send_stop_event.is_set():
            with self.client_lock:
                info = self.clients.get(cid)
            if info is None:
                self.ui_call(self.log_recv, "[系统] 客户端已断开，停止持续发送")
                break
            try:
                payload = build_payload(
                    parts, mode, self.send_counters, self.list_values, list_hold
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