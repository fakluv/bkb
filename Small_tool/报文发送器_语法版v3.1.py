# -*- coding: utf-8 -*-
r"""
UDP / TCP Server 十六进制报文发送工具  v3.1

界面布局（三栏）：
  Area 1（左）   协议配置：UDP / TCP Server 切换，发送设置与发送按钮
  Area 2（中上） 报文区域：编辑报文模板
  Area 3（中下） 日志区：发送日志 + TCP Server 收到的数据都在这里
  Area 4（右）   报文模板列表区：读取 exe/脚本同级目录下“报文模板”文件夹（可多级子目录）

多报文分隔符：
  <br>  （不区分大小写，也接受 <BR>、<br/>）
  CB 00 01 02
  <br>
  CA 00 01 03
  一轮发送会把这些段各自建包、连续发出（UDP = 多个独立数据报，TCP = 多次 sendall）。
  每段独立解析 {} / []；L 的顺序级联在所有段之间统一排队。

指令说明：
  {} 内：HEX + 可选指令
    {02 T(0,30)}      随机，十进制闭区间
    {02 T}            随机，使用“编辑 T 范围”的全局范围；未设置则字段满量程
    {02 P}            自增，满量程后回 0
    {02 P(100)}       自增，最大值 100，到 100 后回初始字节值
    {02 L(55,255,33)} 按内联列表循环
    {02 L(1,2,3@5)}   按内联列表循环，每 5 秒切换一格
    {02 L(1,2,3@5,stop)} 按内联列表，走完最后一格后停止发送
    {02 L(1,2,3@5,loop)} 按内联列表循环
    {02 L}            使用“编辑 L 列表”的全局列表 + 全局秒数 + 全局到尽头设置

  L 顺序（级联，像里程表）：
    {00 L1(0,1,2)} {00 L2(2,3,4)}
      L2 每发一包走一格；L2 这一圈走完，L1 才进一格：
      00 02 / 00 03 / 00 04 / 01 02 / 01 03 / 01 04 / 02 02 / 02 03 / 02 04
      序号小的变化更慢。不写序号时按报文出现顺序自动排序（越靠右越快）。
      完全相同的定义（同样的值 / 秒数 / 到尽头 / 序号）共用一个游标。

  到尽头：
    loop = 走完回到第一个值
    stop = 所有组合走完一遍后停止发送
           多级级联时，L1 × L2 × … 全部组合走完才算结束。

  编辑 L 列表的三种生成方式：
    ① 自行填写列表   手动输入数值
    ② 按bit位（单bit）1,2,4,8…（2 的幂），可用“起始bit”指定从哪一位开始
    ③ 按bit位（逐位累进）2^(n+1)-1 递增，n 从起始bit 起：
                      起始 0、4 位 → 1,3,7,15；起始 2、6 位 → 7,15,31,63,127,255
    字节数决定 bit 上限：1 字节 → bit 0~7，2 字节 → bit 0~15，依次类推。

    勾选“列表值反转”：
      · 单bit          → 只是把列表倒序：4 位 → 8,4,2,1
      · 逐位累进       → 换成“全 1 逐位关位”语义，值 = 全 1 基准值 - (2^n - 1)，
                         n 从 起始bit+1 起、共“位数”个：
                         1 字节、8 位 → 254, 252, 248, 240, 224, 192, 128, 0
      · 逐位累进 + 勾“从 FF 开始” → n 从 0 起，序列最前面多一个全 1：
                         1 字节、8 位 → FF, FE, FC, F8, F0, E0, C0, 80
                         2 字节、8 位 → FFFE, FFFC, FFF8, FFF0, FFE0, FFC0, FF80, FF00
      · 手动填写       → 直接把编辑框里的列表倒序（所见即所得）

  [] 内：HEX 时间戳 + 可选修饰符
    [6A DB 23 E4]        4 字节秒级时间戳（实时）
    [6A DB 23 E4 -8]     秒级时间戳减 8 小时
    [6A DB 23 E4 +8]     秒级时间戳加 8 小时
    [6A DB 23 E4 R]      秒级时间戳反转字节
    [1A 09 1A 10 00 1A]  6 字节年月日时分秒（21 世纪，年份偏移 2000）
    6 字节同样支持 +/-N 与 R；+/-N 做完整日期运算。
    +/-N 与 R 二选一，同时出现报错。

配置保存在注册表 HKEY_CURRENT_USER\Software\UdpHexSender 下。
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

# L 列表生成方式
GEN_MODE_MANUAL = "manual"
GEN_MODE_SINGLE = "single"
GEN_MODE_CUMULATIVE = "cumulative"

# <br> 分隔符
BR_SPLIT_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)

TEMPLATE_DIR_NAME = "报文模板"


# ============================================================
# 路径 / 图标
# ============================================================

def app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def template_root_dir():
    return os.path.join(app_base_dir(), TEMPLATE_DIR_NAME)


def _get_icon_path():
    icon_name = "Benzlee-Free-Christmas-Paper-airplane.ico"
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, icon_name)


ICON_PATH = _get_icon_path()


def apply_app_icon(window):
    try:
        window.iconbitmap(default=ICON_PATH)
    except Exception:
        try:
            window.iconbitmap(ICON_PATH)
        except Exception:
            pass


def show_dialog_centered(win, parent, width=None, height=None):
    """弹窗已 withdraw 时调用：按内容/指定尺寸居中到父窗口后一次性显示。"""
    try:
        win.update_idletasks()
        ww = width if width is not None else win.winfo_reqwidth()
        wh = height if height is not None else win.winfo_reqheight()

        parent.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        if pw <= 1:
            pw = parent.winfo_reqwidth()
        if ph <= 1:
            ph = parent.winfo_reqheight()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()

        x = max(0, px + (pw - ww) // 2)
        y = max(0, py + (ph - wh) // 2)
        win.geometry(f"{ww}x{wh}+{x}+{y}")
        win.deiconify()
        try:
            win.wait_visibility()
        except tk.TclError:
            return
        try:
            win.grab_set()
        except tk.TclError:
            pass
    except Exception:
        try:
            win.deiconify()
            win.grab_set()
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


def read_text_file(path):
    """读文本文件，自动识别 UTF-8 / UTF-8-BOM / GBK。"""
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


# ============================================================
# 报文解析
# ============================================================

# 指令：T / P / L，L 后面允许跟序号（L1 / L2 …）
INSTR_RE = re.compile(r'([TtPpLl])(\d*)(?:\(([^)]*)\))?\s*$')

# 报文里的“区块”起始符：{ 变量区 / [ 时间戳区
DELIM_RE = re.compile(r"[{\[]")


class SequenceFinished(Exception):
    """L 顺序序列已走完（“到尽头”为停止时）。"""


def strip_comments(text: str) -> str:
    """去掉 #...# 注释：每行独立配对，未闭合则丢弃行尾。

    用 split("#") 取偶数段（C 级实现），比逐字符扫描快很多；
    "##"、 "#  #" 这类空注释天然等价于“不注释”，无需额外合并处理。
    """
    if "#" not in text:
        return text
    out = []
    for line in text.splitlines():
        if "#" in line:
            out.append("".join(line.split("#")[0::2]))
        else:
            out.append(line)
    return "\n".join(out)


_HEX_RUN_RE = re.compile(r"[0-9a-fA-F]+")
# 时间戳里除十六进制与空白以外的字符（用于快速校验）
_TS_BAD_RE = re.compile(r"[^0-9a-fA-F\s]")


def parse_hex_tokens(text: str):
    """取出全部十六进制片段（长度 1 的忽略，奇数长度报错）。"""
    runs = _HEX_RUN_RE.findall(text)
    if not runs:
        return []
    tokens = [t for t in runs if len(t) > 1]
    for tok in tokens:
        if len(tok) & 1:
            raise ValueError(
                f"十六进制字符数不是偶数: {tok!r}\n"
                "请检查 #...# 内是否混入说明文字，或 # 是否成对闭合。"
            )
    return tokens


def hex_tokens_to_bytes(tokens):
    """批量转字节：拼接后一次 bytes.fromhex（比逐字节 int 快一个量级）。"""
    if not tokens:
        return b""
    return bytes.fromhex("".join(tokens))


def text_to_bytes(text):
    """一步到位：hex 文本 → bytes。

    快路径：删掉空白后直接 bytes.fromhex（C 级，绝大多数模板走这里）；
    含中文/标点等非十六进制字符时退回逐段提取。
    """
    if not text:
        return b""
    try:
        return bytes.fromhex(text)      # fromhex 本身会忽略空白
    except ValueError:
        pass

    runs = _HEX_RUN_RE.findall(text)
    tokens = [t for t in runs if len(t) > 1]
    for tok in tokens:
        if len(tok) & 1:
            raise ValueError(
                f"十六进制字符数不是偶数: {tok!r}\n"
                "请检查 #...# 内是否混入说明文字，或 # 是否成对闭合。"
            )
    if not tokens:
        return b""
    return bytes.fromhex("".join(tokens))


def parse_numeric_args(args_str, expected_len, name):
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


def compile_template(template: str, var_offset=0):
    """把一段报文编译成 parts；var_offset 用于多段报文时让字段序号连续。

    用正则跳到下一个 { 或 [ ，不再逐字符扫描（大模板快 2~3 倍）；
    孤立的 } 当作普通字符忽略，避免以前那种死循环。
    """
    text = strip_comments(template)
    parts = []
    var_idx = var_offset
    pos = 0
    total = len(text)

    while pos < total:
        m = DELIM_RE.search(text, pos)
        begin = m.start() if m else total
        if begin > pos:
            b = text_to_bytes(text[pos:begin])
            if b:
                parts.append(("fixed", b))
        if not m:
            break

        if text[begin] == "{":
            end = text.find("}", begin + 1)
            if end < 0:
                raise ValueError("未找到匹配的 }")
            content = text[begin + 1:end]

            mm = INSTR_RE.search(content)
            level = None
            if mm:
                hex_part = content[:mm.start()]
                instr = mm.group(1).lower()
                level_str = mm.group(2)
                args_str = mm.group(3)
                if level_str:
                    if instr != "l":
                        raise ValueError(
                            f"{instr.upper()} 不支持序号写法，"
                            "只有 L 支持 L1 / L2 顺序标记"
                        )
                    level = int(level_str)
            else:
                hex_part = content
                instr = None
                args_str = None

            b = text_to_bytes(hex_part)
            if not b:
                raise ValueError("{} 内没有有效的十六进制字节")
            nbytes = len(b)
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

            parts.append(("var", nbytes, var_idx, instr, args, init_value, level))
            var_idx += 1
            pos = end + 1

        else:  # "["
            end = text.find("]", begin + 1)
            if end < 0:
                raise ValueError("未找到匹配的 ]")
            content = text[begin + 1:end].strip()

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

            if _TS_BAD_RE.search(content):
                raise ValueError(f"时间戳内包含非法字符: {content!r}")

            b = text_to_bytes(content)
            if len(b) not in (4, 6):
                raise ValueError(f"时间戳字节数必须为 4 或 6，当前 {len(b)} 字节")
            parts.append(("ts", len(b), reverse, offset_hours))
            pos = end + 1

    return parts


def split_segments(text):
    """按 <br> 切分成多段报文，去掉空白段。

    先整段去注释再切分：注释里的 <br> 不当作分隔符，且只去一次注释（省一半开销）。
    """
    stripped = strip_comments(text or "")
    return [raw for raw in BR_SPLIT_RE.split(stripped) if raw.strip()]


def compile_segments(text):
    """返回 [parts, parts, …]，多段之间字段序号连续（L 级联统一排队）。"""
    stripped = strip_comments(text or "")
    segments = []
    idx = 0
    for raw in BR_SPLIT_RE.split(stripped):
        if not raw.strip():
            continue
        parts = compile_template(raw, var_offset=idx)
        idx += sum(1 for p in parts if p[0] == "var")
        if parts:
            segments.append(parts)
    if not segments:
        raise ValueError("报文为空或没有有效十六进制内容")
    return segments


def _resolve_l_slots(parts, list_values, list_hold, list_mode):
    """
    把报文里所有 L 字段归并成“游标槽位”。
    返回 (slots, field_slot)
    完全相同的定义共用一个槽位（同一个游标，取值同步）。
    """
    slots = {}
    field_slot = {}
    auto_seq = 0
    seen = 0

    for part in parts:
        if part[0] != "var" or part[3] != "l":
            continue
        _, _n, idx, _instr, args, _init, level = part

        if args is None:
            if not list_values:
                raise ValueError("存在 {.. L} 但全局 L 列表为空，请先编辑 L 列表")
            vals = tuple(list_values)
            hold = float(list_hold)
            mode = list_mode
        else:
            lv, lh, lm = args
            vals = tuple(lv)
            hold = float(list_hold) if lh is None else float(lh)
            mode = list_mode if lm is None else lm

        if level is None:
            key = (vals, hold, mode, None)
        else:
            key = (vals, hold, mode, level)

        if key not in slots:
            if level is not None:
                eff_level = level
            else:
                auto_seq += 1
                eff_level = auto_seq
            slots[key] = {
                "list": list(vals),
                "hold": hold,
                "mode": mode,
                "level": eff_level,
                "seen": seen,
            }
            seen += 1

        field_slot[idx] = key

    return slots, field_slot


def _update_l_positions(slots, counters):
    """
    按“里程表”推进：排好序后越靠后的槽位变化越快。
    序列走完（停止模式）时抛 SequenceFinished。
    """
    ordered = sorted(slots.values(), key=lambda s: (s["level"], s["seen"]))
    total = 1
    for s in ordered:
        total *= len(s["list"])
    finite = any(s["mode"] == "stop" for s in ordered)
    fastest_hold = ordered[-1]["hold"] if ordered else 0.0

    tick = int(counters.get("l_tick", 0))
    advance = True

    if fastest_hold > 0:
        now = time.time()
        last = counters.get("l_tick_time")
        if last is None:
            counters["l_tick_time"] = now
        elif now - last >= fastest_hold:
            tick += 1
            counters["l_tick_time"] = now
        advance = False
    else:
        counters.pop("l_tick_time", None)

    counters["l_tick"] = tick

    if finite and tick >= total:
        counters["l_tick"] = 0
        counters.pop("l_tick_time", None)
        raise SequenceFinished(f"L 列表已走完（共 {total} 种组合），发送结束")

    strides_rev = []
    stride = 1
    for s in reversed(ordered):
        strides_rev.append(stride)
        stride *= len(s["list"])
    strides = list(reversed(strides_rev))

    for s, st in zip(ordered, strides):
        s["pos"] = (tick // st) % len(s["list"])

    if advance:
        counters["l_tick"] = tick + 1


def _build_segment(parts, counters, slots, field_slot, t_range):
    out = bytearray()

    for part in parts:
        kind = part[0]
        if kind == "fixed":
            out.extend(part[1])

        elif kind == "var":
            _, n, idx, instr, args, init_value, _level = part
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
                g = slots[field_slot[idx]]
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


def build_payloads(segments, counters, list_values=None, list_hold=0,
                   t_range=None, list_mode="loop"):
    """多段报文统一推进 L 游标，再逐段建包，返回 [bytes, bytes, …]。"""
    flat = [p for parts in segments for p in parts]
    slots, field_slot = _resolve_l_slots(flat, list_values or [], list_hold, list_mode)
    if slots:
        _update_l_positions(slots, counters)

    return [_build_segment(parts, counters, slots, field_slot, t_range)
            for parts in segments]


def build_payload(parts, counters, list_values=None, list_hold=0,
                  t_range=None, list_mode="loop"):
    """单段报文的便捷入口。"""
    return build_payloads([parts], counters, list_values, list_hold,
                          t_range, list_mode)[0]


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


def build_bit_list(gen_mode, total_bits, start_bit, count, reverse=False,
                   from_ff=False):
    """
    按 bit 位生成列表。
      gen_mode=single     → 只有 1 个 bit 为 1：1,2,4,8（从 start_bit 起）
      gen_mode=cumulative → 2 的 (n+1) 次方减 1 递增，n 从起始 bit 开始
    reverse=True 且 cumulative → “全 1 逐位关位”：值 = 全 1 基准值 - (2^n - 1)，
        n 从 起始bit+1 起共 count 个；from_ff=True 时 n 从 0 起（最前面多一个全 1）。
    """
    if total_bits <= 0:
        raise ValueError("字节数必须大于 0")
    if count < 1:
        raise ValueError("位数至少为 1")
    if start_bit < 0 or start_bit >= total_bits:
        raise ValueError(f"起始 bit 必须在 0~{total_bits - 1}")

    if gen_mode == GEN_MODE_SINGLE:
        if start_bit + count > total_bits:
            raise ValueError(
                f"起始 bit {start_bit} + 位数 {count} 超出 bit 0~{total_bits - 1}")
        vals = [1 << (start_bit + i) for i in range(count)]
        return vals[::-1] if reverse else vals

    if reverse:
        base = (1 << total_bits) - 1
        n0 = 0 if from_ff else start_bit + 1
        n_last = n0 + count - 1
        if n_last > total_bits:
            raise ValueError(
                f"从 n={n0} 起共 {count} 个值，最大指数 {n_last} 超出上限 {total_bits}"
                f"（{total_bits} 位字段最多能关到 0）"
            )
        return [base - ((1 << n) - 1) for n in range(n0, n0 + count)]

    if start_bit + count > total_bits:
        raise ValueError(
            f"起始 bit {start_bit} + 位数 {count} 超出 bit 0~{total_bits - 1}")
    return [(1 << (start_bit + k)) - 1 for k in range(1, count + 1)]


def detect_l_widths(template_text):
    """返回报文里所有“使用全局列表”的 {.. L} 字段字节数（多段合并）。"""
    if not template_text:
        return []
    widths = []
    for raw in split_segments(template_text) or [template_text]:
        try:
            parts = compile_template(raw)
        except Exception:
            continue
        for p in parts:
            if p[0] == "var" and p[3] == "l" and p[4] is None:
                widths.append(p[1])
    return widths


# ============================================================
# 编辑 L 列表弹窗
# ============================================================

class LListDialog:
    def __init__(self, parent, tpl_getter, on_save,
                 list_values, hold_str, list_mode, gen_state, sel_getter=None):
        self.parent = parent
        self.tpl_getter = tpl_getter
        self.on_save = on_save
        self.list_values = list(list_values or [])
        self.hold_str = hold_str
        self.list_mode = list_mode or "loop"
        self.gen_state = dict(gen_state or {})
        self.sel_getter = sel_getter

        self.win = None
        self.detected = []
        self.sel_bytes = 0

    # ---------------- 生命周期 ----------------

    def is_open(self):
        try:
            return self.win is not None and self.win.winfo_exists()
        except tk.TclError:
            return False

    def focus(self):
        try:
            self.win.deiconify()
            self.win.lift()
            self.win.focus_force()
        except Exception:
            pass

    def close(self):
        try:
            self.win.grab_release()
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass
        self.win = None

    # ---------------- 构建界面 ----------------

    def open(self):
        win = tk.Toplevel(self.parent)
        win.withdraw()
        self.win = win
        apply_app_icon(win)
        win.title("编辑 L 全局列表")
        win.transient(self.parent.winfo_toplevel())
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self.close)

        self.rev_var = tk.BooleanVar(
            value=str(self.gen_state.get("rev", "0")).lower() in ("1", "true"))

        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=10, pady=8)

        # ---- ① 生成方式 ----
        gen = ttk.LabelFrame(body, text="① 生成方式")
        gen.pack(fill="x")

        self.gen_var = tk.StringVar(
            value=self.gen_state.get("mode") or GEN_MODE_MANUAL)
        ttk.Radiobutton(
            gen, text="自行填写列表（在下面直接输入数值）",
            variable=self.gen_var, value=GEN_MODE_MANUAL,
            command=self._on_gen_mode,
        ).grid(row=0, column=0, columnspan=6, sticky="w", padx=10, pady=(6, 0))
        ttk.Radiobutton(
            gen, text="按bit位（单bit）：每个值只有 1 个 bit 为 1，如 4 位 → 1, 2, 4, 8",
            variable=self.gen_var, value=GEN_MODE_SINGLE,
            command=self._on_gen_mode,
        ).grid(row=1, column=0, columnspan=6, sticky="w", padx=10, pady=(4, 0))
        ttk.Radiobutton(
            gen, text="按bit位（逐位累进）：值 = 2^(n+1)-1，n 从起始bit 起，如起始0、4位 → 1, 3, 7, 15",
            variable=self.gen_var, value=GEN_MODE_CUMULATIVE,
            command=self._on_gen_mode,
        ).grid(row=2, column=0, columnspan=6, sticky="w", padx=10, pady=(4, 0))

        self.param = ttk.Frame(gen)
        self.param.grid(row=3, column=0, columnspan=6, sticky="ew",
                        padx=16, pady=(8, 8))

        ttk.Label(self.param, text="字节数").grid(row=0, column=0, sticky="w")
        self.bytes_var = tk.StringVar(
            value=str(self.gen_state.get("bytes") or "1"))
        self.entry_bytes = ttk.Entry(
            self.param, textvariable=self.bytes_var, width=5)
        self.entry_bytes.grid(row=0, column=1, sticky="w", padx=(4, 6))
        self.range_var = tk.StringVar(value="")
        ttk.Label(self.param, textvariable=self.range_var,
                  foreground="gray").grid(row=0, column=2, sticky="w",
                                          padx=(0, 10))
        self.btn_detect = ttk.Button(
            self.param, text="按报文填入", width=11, command=self._use_template_width)
        self.btn_detect.grid(row=0, column=3, padx=(0, 4))
        self.btn_sel = ttk.Button(
            self.param, text="取选中字节", width=11, command=self._use_selection_width)
        self.btn_sel.grid(row=0, column=4)

        bits_row = ttk.Frame(self.param)
        bits_row.grid(row=1, column=0, columnspan=5, sticky="w", pady=(6, 0))
        ttk.Label(bits_row, text="起始bit").pack(side="left")
        self.start_var = tk.StringVar(
            value=str(self.gen_state.get("start") or "0"))
        self.entry_start = ttk.Entry(
            bits_row, textvariable=self.start_var, width=5)
        self.entry_start.pack(side="left", padx=(4, 18))
        ttk.Label(bits_row, text="位数").pack(side="left")
        self.bits_var = tk.StringVar(
            value=str(self.gen_state.get("bits") or "4"))
        self.entry_bits = ttk.Entry(
            bits_row, textvariable=self.bits_var, width=5)
        self.entry_bits.pack(side="left", padx=(4, 0))

        self.preview_var = tk.StringVar(value="")
        ttk.Label(self.param, textvariable=self.preview_var,
                  foreground="#1a5fb4", wraplength=560,
                  justify="left").grid(row=2, column=0, columnspan=5,
                                       sticky="w", pady=(6, 0))
        self.tip_var = tk.StringVar(value="")
        ttk.Label(self.param, textvariable=self.tip_var, foreground="gray",
                  wraplength=560, justify="left").grid(
            row=3, column=0, columnspan=5, sticky="w", pady=(2, 0))

        # ---- ② 列表值 ----
        lf = ttk.LabelFrame(body, text="② 列表值（可手动修改；一行一个，或逗号/空格分隔）")
        lf.pack(fill="both", expand=True, pady=(8, 0))
        rev_row = ttk.Frame(lf)
        rev_row.pack(fill="x", anchor="w", padx=8, pady=(6, 0))
        ttk.Checkbutton(
            rev_row, text="列表值反转（倒序，如 1, 3, 7 → 7, 3, 1）",
            variable=self.rev_var,
            command=self._on_rev_toggle,
        ).pack(side="left")
        self.ff_var = tk.BooleanVar(
            value=str(self.gen_state.get("ff", "0")).lower() in ("1", "true"))
        ff_row = ttk.Frame(lf)
        ff_row.pack(fill="x", anchor="w", padx=8, pady=(2, 0))
        self.chk_ff = ttk.Checkbutton(
            ff_row, text="从 FF 开始（仅“逐位累进+反转”生效：FF, FE, FC, F8 …）",
            variable=self.ff_var, command=self._on_ff_toggle,
        )
        self.chk_ff.pack(side="left")

        box_frame = ttk.Frame(lf)
        box_frame.pack(fill="both", expand=True, padx=6, pady=6)
        self.box = tk.Text(box_frame, height=12, width=54, font=("Consolas", 10),
                           undo=True, autoseparators=True, maxundo=-1)
        vscroll = ttk.Scrollbar(box_frame, orient="vertical",
                                command=self.box.yview)
        self.box.configure(yscrollcommand=vscroll.set)
        self.box.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")
        if self.list_values:
            self.box.insert("1.0", "\n".join(map(str, self.list_values)))
        enable_text_undo(self.box)

        # ---- ③ 切换与结束 ----
        of = ttk.LabelFrame(body, text="③ 切换与结束")
        of.pack(fill="x", pady=(8, 0))
        ttk.Label(
            of,
            text="列表保持(秒)：0 = 每发一包切换；>0 = 每 N 秒推进一格（期间重复发送当前组合）",
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(6, 0))
        self.hold_var = tk.StringVar(value=self.hold_str or "0")
        self.entry_hold = ttk.Entry(of, textvariable=self.hold_var, width=10)
        self.entry_hold.grid(row=1, column=0, sticky="w", padx=10, pady=(2, 8))
        enable_entry_undo(self.entry_hold, self.hold_var)

        ttk.Label(of, text="到尽头：").grid(row=2, column=0, sticky="w", padx=10)
        self.mode_var = tk.StringVar(value=self.list_mode)
        ttk.Radiobutton(of, text="循环（走完回到第一个值）",
                        variable=self.mode_var, value="loop").grid(
            row=2, column=1, sticky="w", padx=(0, 12))
        ttk.Radiobutton(of, text="停止（所有组合走完一遍后停止发送）",
                        variable=self.mode_var, value="stop").grid(
            row=2, column=2, sticky="w")
        ttk.Label(
            of,
            text="顺序级联时：L1 × L2 × … 的全部组合走完才算结束",
            foreground="gray",
        ).grid(row=3, column=0, columnspan=4, sticky="w", padx=10, pady=(4, 8))

        row = ttk.Frame(body)
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text="确定", width=10, command=self._save).pack(side="right")
        ttk.Button(row, text="取消", width=10, command=self.close).pack(
            side="right", padx=6)

        # 报文宽度提示（选中内容在弹窗弹出后可能失效，这里先快照）
        if self.sel_getter is not None:
            try:
                self.sel_bytes = int(self.sel_getter() or 0)
            except Exception:
                self.sel_bytes = 0
        try:
            self.detected = detect_l_widths(self.tpl_getter() or "")
        except Exception:
            self.detected = []
        self._update_template_tip()

        for v in (self.bytes_var, self.start_var, self.bits_var):
            v.trace_add("write", lambda *_: self._on_param_change())
        self._on_gen_mode()

        show_dialog_centered(win, self.parent.winfo_toplevel())

    # ---------------- 生成方式 ----------------

    def _update_template_tip(self):
        uniq = sorted(set(self.detected))
        if not uniq:
            self.tip_var.set(
                "提示：报文里暂未找到使用全局列表的 {.. L} 字段，可手动填写字节数，"
                "或先点“按报文填入”。")
        elif len(uniq) == 1:
            self.tip_var.set(
                f"提示：报文里的 {{.. L}} 字段为 {uniq[0]} 字节"
                f"（bit 0~{uniq[0] * 8 - 1}）。")
        else:
            self.tip_var.set(
                "提示：报文里的 {.. L} 字段宽度不一致（"
                + " / ".join(f"{w} 字节" for w in uniq)
                + "），请按需填写字节数。")

    def _ff_active(self):
        """“从 FF 开始”只在 逐位累进 + 列表值反转 时生效。"""
        return (self.gen_var.get() == GEN_MODE_CUMULATIVE
                and bool(self.rev_var.get()))

    def _refresh_param_states(self):
        bit_mode = self.gen_var.get() in (GEN_MODE_SINGLE, GEN_MODE_CUMULATIVE)
        state = "normal" if bit_mode else "disabled"
        for w in (self.entry_bytes, self.entry_bits, self.btn_detect, self.btn_sel):
            try:
                w.configure(state=state)
            except Exception:
                pass
        start_state = "disabled" if (self._ff_active() and self.ff_var.get()) else state
        try:
            self.entry_start.configure(state=start_state)
        except Exception:
            pass
        try:
            self.chk_ff.configure(state="normal" if self._ff_active() else "disabled")
            if not self._ff_active():
                self.ff_var.set(False)
        except Exception:
            pass

    def _on_gen_mode(self, *_):
        self._refresh_param_states()
        self._update_range_hint()
        if self.gen_var.get() in (GEN_MODE_SINGLE, GEN_MODE_CUMULATIVE):
            self._fill_from_bits()
        else:
            self.preview_var.set("")

    def _on_ff_toggle(self):
        self._refresh_param_states()
        if self.gen_var.get() in (GEN_MODE_SINGLE, GEN_MODE_CUMULATIVE):
            self._fill_from_bits()

    def _update_range_hint(self):
        try:
            nb = int(self.bytes_var.get().strip() or "1")
        except ValueError:
            self.range_var.set("字节数无效")
            return
        if not 1 <= nb <= 16:
            self.range_var.set("字节数 1~16")
            return
        total = nb * 8
        self.range_var.set(f"bit 0~{total - 1}，字段最大值 {2 ** total - 1}")

    def _on_param_change(self):
        self._update_range_hint()
        if self.gen_var.get() in (GEN_MODE_SINGLE, GEN_MODE_CUMULATIVE):
            self._fill_from_bits()

    def _bit_params(self):
        try:
            nb = int(self.bytes_var.get().strip() or "1")
        except ValueError:
            raise ValueError("字节数必须是整数")
        if not 1 <= nb <= 16:
            raise ValueError("字节数范围 1~16")
        try:
            start = int(self.start_var.get().strip() or "0")
        except ValueError:
            raise ValueError("起始 bit 必须是整数")
        try:
            count = int(self.bits_var.get().strip() or "0")
        except ValueError:
            raise ValueError("位数必须是整数")
        total = nb * 8
        if start < 0 or start >= total:
            raise ValueError(f"起始 bit 范围 0~{total - 1}")
        if count < 1:
            raise ValueError("位数至少为 1")
        return total, start, count

    def _fill_from_bits(self):
        try:
            total, start, count = self._bit_params()
            from_ff = self._ff_active() and bool(self.ff_var.get())
            vals = build_bit_list(self.gen_var.get(), total, start, count,
                                  reverse=bool(self.rev_var.get()),
                                  from_ff=from_ff)
        except ValueError as e:
            self.preview_var.set(f"参数错误：{e}")
            return

        self.box.delete("1.0", "end")
        self.box.insert("1.0", "\n".join(map(str, vals)))

        hexw = max(2, (total + 3) // 4)
        head = ", ".join(f"{v}(0x{v:0{hexw}X})" for v in vals[:4])
        more = f" …（共 {len(vals)} 个值）" if len(vals) > 4 else f"（共 {len(vals)} 个值）"
        if from_ff:
            self.preview_var.set("预览（从 FF 起逐位关位）：" + head + more)
        elif self.gen_var.get() == GEN_MODE_CUMULATIVE and self.rev_var.get():
            self.preview_var.set("预览（逐位关位）：" + head + more)
        else:
            self.preview_var.set("预览：" + head + more)

    def _use_template_width(self):
        try:
            self.detected = detect_l_widths(self.tpl_getter() or "")
        except Exception:
            self.detected = []
        self._update_template_tip()
        if not self.detected:
            messagebox.showinfo(
                "提示", "报文里没有找到使用全局列表的 {.. L} 字段。",
                parent=self.win)
            return
        uniq = sorted(set(self.detected))
        self.bytes_var.set(str(uniq[-1]))

    def _use_selection_width(self):
        n = self.sel_bytes
        if not n and self.sel_getter is not None:
            try:
                n = int(self.sel_getter() or 0)
            except Exception:
                n = 0
        if not n:
            self.tip_var.set(
                "没有取到选中内容：请先在报文里框选一段十六进制字节，"
                "再点“编辑 L 列表”打开这个窗口。")
            return
        if n > 16:
            self.tip_var.set(f"选中的内容有 {n} 字节，超出支持范围 1~16 字节。")
            return
        self.bytes_var.set(str(n))
        self.tip_var.set(f"已按选中的 {n} 字节填入（bit 0~{n * 8 - 1}）。")

    # ---------------- 反转 / 保存 ----------------

    def _read_box_values(self):
        raw = self.box.get("1.0", "end-1c")
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
        return vals

    def _write_box_values(self, vals):
        self.box.delete("1.0", "end")
        self.box.insert("1.0", "\n".join(map(str, vals)))

    def _on_rev_toggle(self):
        """勾选/取消“列表值反转”：bit 模式重新生成，手动模式直接倒序现有内容。"""
        if self.gen_var.get() in (GEN_MODE_SINGLE, GEN_MODE_CUMULATIVE):
            self._refresh_param_states()
            self._fill_from_bits()
            return
        try:
            vals = self._read_box_values()
        except ValueError as e:
            self.rev_var.set(not self.rev_var.get())
            self.tip_var.set(f"无法反转：{e}")
            return
        if not vals:
            return
        vals.reverse()
        self._write_box_values(vals)
        self.tip_var.set("已反转列表顺序：" + ", ".join(map(str, vals[:10]))
                         + (" …" if len(vals) > 10 else ""))

    def _save(self):
        try:
            vals = self._read_box_values()
            if not vals:
                raise ValueError("请至少输入一个数字")
            if any(v < 0 for v in vals):
                raise ValueError("列表数字必须是非负整数")
            parse_hold_seconds(self.hold_var.get())

            gen_state = {
                "mode": self.gen_var.get(),
                "bytes": self.bytes_var.get().strip() or "1",
                "start": self.start_var.get().strip() or "0",
                "bits": self.bits_var.get().strip() or "4",
                "rev": "1" if self.rev_var.get() else "0",
                "ff": "1" if (self._ff_active() and self.ff_var.get()) else "0",
            }
            self.on_save(vals,
                         self.hold_var.get().strip() or "0",
                         self.mode_var.get() or "loop",
                         gen_state)
            self.close()
        except ValueError as e:
            messagebox.showerror("列表格式错误", str(e), parent=self.win)
            try:
                self.win.grab_set()
            except tk.TclError:
                pass


# ============================================================
# 编辑 T 范围弹窗
# ============================================================

class TRangeDialog:
    def __init__(self, parent, t_range, on_save):
        self.parent = parent
        self.t_range = t_range
        self.on_save = on_save
        self.win = None

    def is_open(self):
        try:
            return self.win is not None and self.win.winfo_exists()
        except tk.TclError:
            return False

    def focus(self):
        try:
            self.win.deiconify()
            self.win.lift()
            self.win.focus_force()
        except Exception:
            pass

    def close(self):
        try:
            self.win.grab_release()
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass
        self.win = None

    def open(self):
        win = tk.Toplevel(self.parent)
        win.withdraw()
        self.win = win
        apply_app_icon(win)
        win.title("编辑 T 全局范围")
        win.transient(self.parent.winfo_toplevel())
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self.close)

        ttk.Label(
            win,
            text="未设置时按字段满量程处理（1 字节 0~255、2 字节 0~65535…）。",
        ).pack(anchor="w", padx=10, pady=(10, 4))
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
                self.on_save(None)
                self.close()
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
            self.on_save((lo, hi))
            self.close()

        row = ttk.Frame(win)
        row.pack(fill="x", padx=10, pady=8)
        ttk.Button(row, text="确定", command=save).pack(side="right")
        ttk.Button(row, text="取消", command=self.close).pack(side="right", padx=6)

        show_dialog_centered(win, self.parent.winfo_toplevel())


# ============================================================
# 报文模板树（Area 4）
# ============================================================

class TemplatePanel(ttk.Frame):
    def __init__(self, parent, on_apply, log_func):
        super().__init__(parent)
        self.on_apply = on_apply
        self.log_func = log_func
        self.root_dir = template_root_dir()
        self.node_path = {}
        self.order = []

        self.path_var = tk.StringVar(value=self.root_dir)
        self.hint_var = tk.StringVar(value="")

        self.build_ui()
        self.scan()

    def build_ui(self):
        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text="模板目录：", foreground="gray").pack(side="left")
        ttk.Label(head, textvariable=self.path_var, foreground="#555",
                  wraplength=240, justify="left").pack(side="left", fill="x",
                                                      expand=True)

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True, pady=(4, 0))

        style_name = "Template.Treeview"
        style = ttk.Style(self)
        try:
            style.configure(style_name, rowheight=22)
            style.map(style_name,
                      background=[("selected", "#1565C0")],
                      foreground=[("selected", "#FFFFFF")])
        except Exception:
            pass

        self.tree = ttk.Treeview(tree_frame, show="tree",
                                 selectmode="extended",
                                 style=style_name)
        yscroll = ttk.Scrollbar(tree_frame, orient="vertical",
                                command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        self.tree.tag_configure("dir", foreground="#333333")
        self.tree.tag_configure("file", foreground="#0D47A1")
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_changed)

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(btn_row, text="刷新", width=8,
                   command=self.scan).pack(side="left")
        ttk.Label(btn_row, text="点选即填入｜Ctrl 多选",
                  foreground="gray", wraplength=200, justify="left").pack(
            side="left", padx=(8, 0))

        ttk.Label(self, textvariable=self.hint_var, foreground="gray",
                  wraplength=230, justify="left").pack(fill="x", pady=(4, 0))

    # ---------------- 扫描 ----------------

    def scan(self):
        # 记住刷新前哪些目录是展开的，刷新后恢复
        open_dirs = set()
        for item, path in self.node_path.items():
            try:
                if ("dir" in self.tree.item(item, "tags")
                        and self.tree.item(item, "open")):
                    open_dirs.add(path)
            except tk.TclError:
                pass

        self.root_dir = template_root_dir()
        self.path_var.set(self.root_dir)
        self.node_path.clear()
        self.order = []
        self.tree.delete(*self.tree.get_children())

        if not os.path.isdir(self.root_dir):
            try:
                os.makedirs(self.root_dir, exist_ok=True)
            except Exception:
                self.hint_var.set(
                    f"未找到“{TEMPLATE_DIR_NAME}”文件夹，且无法创建。\n"
                    f"路径：{self.root_dir}")
                return
            self.hint_var.set(
                f"已创建空的“{TEMPLATE_DIR_NAME}”文件夹，把 txt 模板放进去后点“刷新”。\n"
                f"路径：{self.root_dir}")
            return

        count = [0]

        def add_dir(parent_item, path, depth):
            try:
                entries = sorted(os.listdir(path))
            except OSError:
                return
            for name in entries:
                full = os.path.join(path, name)
                if os.path.isdir(full):
                    item = self.tree.insert(
                        parent_item, "end", text=name,
                        open=(full in open_dirs), tags=("dir",))
                    self.node_path[item] = full
                    add_dir(item, full, depth + 1)
                elif name.lower().endswith(".txt"):
                    item = self.tree.insert(
                        parent_item, "end", text=name, tags=("file",))
                    self.node_path[item] = full
                    self.order.append(full)
                    count[0] += 1

        add_dir("", self.root_dir, 0)

        if count[0] == 0:
            self.hint_var.set("还没有 .txt 模板，放进去后点“刷新”。")
        else:
            self.hint_var.set(f"共 {count[0]} 个模板")

    # ---------------- 选择 ----------------

    def _selected_files(self):
        sel = set(self.tree.selection())
        files = []
        for item, path in self.node_path.items():
            if item in sel and os.path.isfile(path):
                files.append(path)
        order_idx = {p: i for i, p in enumerate(self.order)}
        files.sort(key=lambda p: order_idx.get(p, 1 << 30))
        return files

    def _on_selection_changed(self, _event=None):
        """选中文件即填入报文区（点到目录或清空选择时不动作）。"""
        files = self._selected_files()
        if not files:
            return
        self.apply_files(files, quiet=True)

    def apply_selected(self):
        return self.apply_files(self._selected_files())

    def apply_files(self, files, quiet=False):
        if not files:
            if not quiet:
                messagebox.showinfo("提示", "请先在列表里选中至少一个 .txt 模板。",
                                    parent=self.winfo_toplevel())
            return None

        texts = []
        for path in files:
            try:
                t = read_text_file(path).strip()
            except Exception as e:
                messagebox.showerror("读取失败", f"{path}\n{e}",
                                     parent=self.winfo_toplevel())
                return None
            if t:
                texts.append(t)

        if not texts:
            if not quiet:
                messagebox.showinfo("提示", "选中的模板内容为空。",
                                    parent=self.winfo_toplevel())
            return None

        content = "\n<br>\n".join(texts)
        self.on_apply(content, files)
        self.hint_var.set(f"已填入 {len(texts)} 个模板（详见日志）")
        return content


# ============================================================
# 主窗口
# ============================================================

class App:
    def __init__(self, root):
        self.root = root
        root.title("报文发送器 v3.1 语法版")
        apply_app_icon(root)

        # 共享设置
        self.t_range = None
        self.list_values = []
        self.list_mode = "loop"
        self.l_gen_state = {"mode": GEN_MODE_MANUAL, "bytes": "1",
                            "start": "0", "bits": "4", "rev": "0", "ff": "0"}
        self._dlg_l_list = None
        self._dlg_t_range = None

        # 协议运行态
        self.counters = {"udp": {}, "tcp": {}}
        self.udp_thread = None
        self.udp_stop = threading.Event()
        self.sent_count = 0

        self.server_socket = None
        self.accept_thread = None
        self.server_stop = threading.Event()
        self.clients = {}
        self.client_lock = threading.Lock()
        self.client_counter = 0
        self.tcp_thread = None
        self.tcp_stop = threading.Event()
        self.tcp_sent = 0

        self.ui_queue = queue.Queue()
        self._schedule_poll()
        self._seg_after_id = None
        self._seg_cache = (None, None)
        self._log_buf = []
        self._log_after_id = None

        # 变量
        self.var_proto = tk.StringVar(value="udp")
        self.var_list_hold = tk.StringVar(value="0")
        self.status_var = tk.StringVar(value="就绪")
        self.seg_var = tk.StringVar(value="当前无有效报文")

        self.var_udp_local_ip = tk.StringVar(value="0.0.0.0")
        self.var_udp_local_port = tk.StringVar(value="0")
        self.var_udp_target_ip = tk.StringVar(value="127.0.0.1")
        self.var_udp_target_port = tk.StringVar(value="9000")
        self.var_udp_interval = tk.StringVar(value="1000")
        self.var_udp_continuous = tk.BooleanVar(value=False)

        self.var_tcp_ip = tk.StringVar(value="0.0.0.0")
        self.var_tcp_port = tk.StringVar(value="8000")
        self.var_tcp_interval = tk.StringVar(value="1000")
        self.var_tcp_continuous = tk.BooleanVar(value=False)
        self.var_client = tk.StringVar()
        self.tcp_status_var = tk.StringVar(value="未连接")
        self.btn_conn_text = tk.StringVar(value="连接")

        self.build_ui()
        self.load_config()
        self.refresh_client_list()
        self._on_proto_change()
        self._update_seg_label()
        self._on_template_modified(reset=True)

    # ---------------- 队列 / 日志 ----------------

    def _schedule_poll(self):
        self.root.after(50, self._poll_queue)

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

    def log(self, msg):
        """日志先进缓冲区，120ms 批量刷新一次，避免高频插入拖慢界面。"""
        try:
            self._log_buf.append(time.strftime("%H:%M:%S ") + msg)
        except Exception:
            return
        if self._log_after_id is None:
            try:
                self._log_after_id = self.root.after(120, self._flush_log)
            except Exception:
                self._log_after_id = None

    def _flush_log(self):
        self._log_after_id = None
        if not self._log_buf:
            return
        chunk = "\n".join(self._log_buf) + "\n"
        self._log_buf.clear()
        try:
            self.txt_log.insert("end", chunk)
            self.txt_log.see("end")
            line_count = int(self.txt_log.index("end-1c").split(".")[0])
            if line_count > 800:
                self.txt_log.delete("1.0", "401.0")
        except Exception:
            pass

    def clear_log(self):
        self._log_buf.clear()
        try:
            self.txt_log.delete("1.0", "end")
        except Exception:
            pass

    # ---------------- 界面 ----------------

    def _entry(self, parent, var, **kwargs):
        e = ttk.Entry(parent, textvariable=var, **kwargs)
        enable_entry_undo(e, var)
        return e

    def build_ui(self):
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True, padx=6, pady=6)

        outer.columnconfigure(0, weight=0, minsize=330)
        outer.columnconfigure(1, weight=1)
        outer.columnconfigure(2, weight=0, minsize=270)
        outer.rowconfigure(0, weight=3)
        outer.rowconfigure(1, weight=1)

        # ---------- Area 1 ----------
        area1 = ttk.LabelFrame(outer, text="① 配置")
        area1.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 6))
        self.build_area1(area1)

        # ---------- Area 2 ----------
        area2 = ttk.LabelFrame(
            outer,
            text="② 报文区域（# # 注释｜{..} 变化值｜[..] 时间戳｜<br> 分隔多报文）")
        area2.grid(row=0, column=1, sticky="nsew", pady=(0, 6))
        self.build_area2(area2)

        # ---------- Area 3 ----------
        area3 = ttk.LabelFrame(outer, text="③ 日志")
        area3.grid(row=1, column=1, sticky="nsew")
        self.build_area3(area3)

        # ---------- Area 4 ----------
        area4 = ttk.LabelFrame(outer, text="④ 报文模板")
        area4.grid(row=0, column=2, rowspan=2, sticky="nsew", padx=(6, 0))
        self.template_panel = TemplatePanel(
            area4,
            on_apply=self.on_template_applied,
            log_func=self.log,
        )
        self.template_panel.pack(fill="both", expand=True, padx=6, pady=6)

    def build_area1(self, parent):
        proto_row = ttk.Frame(parent)
        proto_row.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(proto_row, text="协议：").pack(side="left")
        ttk.Radiobutton(proto_row, text="UDP", value="udp",
                        variable=self.var_proto,
                        command=self._on_proto_change).pack(side="left")
        ttk.Radiobutton(proto_row, text="TCP Server", value="tcp",
                        variable=self.var_proto,
                        command=self._on_proto_change).pack(side="left", padx=(12, 0))

        self.proto_holder = ttk.Frame(parent)
        self.proto_holder.pack(fill="x", padx=8)
        self.proto_holder.columnconfigure(0, weight=1)

        # --- UDP 配置 ---
        self.udp_frame = ttk.Frame(self.proto_holder)
        grid = self.udp_frame
        ttk.Label(grid, text="本机 IP").grid(row=0, column=0, sticky="w", pady=3)
        self._entry(grid, self.var_udp_local_ip, width=16).grid(
            row=0, column=1, sticky="ew", padx=(4, 0), pady=3)
        ttk.Label(grid, text="本机端口").grid(row=1, column=0, sticky="w", pady=3)
        self._entry(grid, self.var_udp_local_port, width=16).grid(
            row=1, column=1, sticky="ew", padx=(4, 0), pady=3)
        ttk.Label(grid, text="目标 IP").grid(row=2, column=0, sticky="w", pady=3)
        self._entry(grid, self.var_udp_target_ip, width=16).grid(
            row=2, column=1, sticky="ew", padx=(4, 0), pady=3)
        ttk.Label(grid, text="目标端口").grid(row=3, column=0, sticky="w", pady=3)
        self._entry(grid, self.var_udp_target_port, width=16).grid(
            row=3, column=1, sticky="ew", padx=(4, 0), pady=3)
        ttk.Label(grid, text="发送间隔(ms)").grid(row=4, column=0, sticky="w", pady=3)
        self._entry(grid, self.var_udp_interval, width=16).grid(
            row=4, column=1, sticky="ew", padx=(4, 0), pady=3)
        ttk.Checkbutton(grid, text="持续发送", variable=self.var_udp_continuous).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))
        grid.columnconfigure(1, weight=1)

        # --- TCP Server 配置 ---
        self.tcp_frame = ttk.Frame(self.proto_holder)
        g2 = self.tcp_frame
        ttk.Label(g2, text="监听 IP").grid(row=0, column=0, sticky="w", pady=3)
        self._entry(g2, self.var_tcp_ip, width=16).grid(
            row=0, column=1, sticky="ew", padx=(4, 0), pady=3)
        ttk.Label(g2, text="监听端口").grid(row=1, column=0, sticky="w", pady=3)
        self._entry(g2, self.var_tcp_port, width=16).grid(
            row=1, column=1, sticky="ew", padx=(4, 0), pady=3)

        conn_row = ttk.Frame(g2)
        conn_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.btn_conn = ttk.Button(conn_row, textvariable=self.btn_conn_text,
                                   width=10, command=self.on_button_conn)
        self.btn_conn.pack(side="left")
        ttk.Label(conn_row, textvariable=self.tcp_status_var).pack(
            side="left", padx=(8, 0))

        ttk.Label(g2, text="客户端").grid(row=3, column=0, sticky="w", pady=(6, 3))
        self.combo_clients = ttk.Combobox(g2, textvariable=self.var_client,
                                          values=[], width=16, state="readonly")
        self.combo_clients.grid(row=3, column=1, sticky="ew", padx=(4, 0),
                                pady=(6, 3))
        ttk.Button(g2, text="刷新", width=6, command=self.refresh_client_list).grid(
            row=4, column=1, sticky="e", pady=(0, 3))

        ttk.Label(g2, text="发送间隔(ms)").grid(row=5, column=0, sticky="w", pady=3)
        self._entry(g2, self.var_tcp_interval, width=16).grid(
            row=5, column=1, sticky="ew", padx=(4, 0), pady=3)
        ttk.Checkbutton(g2, text="持续发送", variable=self.var_tcp_continuous).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))
        g2.columnconfigure(1, weight=1)

        # --- 共享：T/L 与发送 ---
        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=8, pady=10)

        tl_row = ttk.Frame(parent)
        tl_row.pack(fill="x", padx=8)
        ttk.Button(tl_row, text="编辑 T 范围", command=self.edit_t_range).pack(
            side="left")
        ttk.Button(tl_row, text="编辑 L 列表", command=self.edit_l_list).pack(
            side="left", padx=6)

        send_row = ttk.Frame(parent)
        send_row.pack(fill="x", padx=8, pady=(8, 0))
        self.btn_send = ttk.Button(send_row, text="发送", width=10,
                                   command=self.on_send)
        self.btn_send.pack(side="left")
        self.btn_send_once = ttk.Button(send_row, text="发送一次", width=10,
                                        command=self.on_send_once)
        self.btn_send_once.pack(side="left", padx=6)

        ttk.Label(parent, textvariable=self.status_var, foreground="#0D47A1",
                  wraplength=300, justify="left").pack(fill="x", padx=8, pady=(8, 0))

        ttk.Label(
            parent,
            text="提示：<br> 分隔的每一段各自建包、连续发出；L 的顺序级联在所有段之间统一排队。",
            foreground="gray", wraplength=300, justify="left",
        ).pack(fill="x", padx=8, pady=(8, 8))

    def build_area2(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=6, pady=(4, 0))
        ttk.Label(bar, textvariable=self.seg_var, foreground="#555").pack(side="left")
        ttk.Button(bar, text="清空", width=6,
                   command=self.clear_template).pack(side="right")

        text_frame = ttk.Frame(parent)
        text_frame.pack(fill="both", expand=True, padx=6, pady=(2, 6))
        self.txt_template = tk.Text(text_frame, wrap="char",
                                    font=("Consolas", 10),
                                    undo=True, autoseparators=True, maxundo=300)
        yscroll = ttk.Scrollbar(text_frame, orient="vertical",
                                command=self.txt_template.yview)
        self.txt_template.configure(yscrollcommand=yscroll.set)
        self.txt_template.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        enable_text_undo(self.txt_template)
        self.txt_template.bind("<<Modified>>", self._on_template_modified)

    def build_area3(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", padx=6, pady=(4, 0))
        ttk.Button(bar, text="清空日志", width=10,
                   command=self.clear_log).pack(side="right")

        log_frame = ttk.Frame(parent)
        log_frame.pack(fill="both", expand=True, padx=6, pady=(2, 6))
        self.txt_log = tk.Text(log_frame, height=8, wrap="word",
                               font=("Consolas", 9),
                               undo=True, autoseparators=True, maxundo=100)
        yscroll = ttk.Scrollbar(log_frame, orient="vertical",
                                command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=yscroll.set)
        self.txt_log.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        enable_text_undo(self.txt_log)

    # ---------------- 报文区辅助 ----------------

    def clear_template(self):
        self.txt_template.delete("1.0", "end")
        self._update_seg_label()

    def _on_template_modified(self, _event=None, reset=False):
        try:
            if reset:
                self.txt_template.edit_modified(False)
                self._update_seg_label()
                return
            if not self.txt_template.edit_modified():
                return
            self.txt_template.edit_modified(False)
        except Exception:
            return
        # 输入停顿 300ms 后再统计段数，避免每敲一个键就全文解析一遍
        if self._seg_after_id is not None:
            try:
                self.root.after_cancel(self._seg_after_id)
            except Exception:
                pass
        self._seg_after_id = self.root.after(300, self._update_seg_label)

    def _update_seg_label(self):
        if self._seg_after_id is not None:
            try:
                self.root.after_cancel(self._seg_after_id)
            except Exception:
                pass
            self._seg_after_id = None
        text = self.txt_template.get("1.0", "end-1c")
        if not text.strip():
            self.seg_var.set("当前无有效报文")
            return
        if len(text) > 200_000:
            # 大报文：不做完整的去注释解析，只粗略数一下 <br>
            n = sum(1 for raw in BR_SPLIT_RE.split(text) if raw.strip())
            if n > 1:
                self.seg_var.set(f"当前 {n} 段报文（约 {len(text) // 1000}K 字符）")
            else:
                self.seg_var.set(f"当前 1 段报文（约 {len(text) // 1000}K 字符）")
            return
        try:
            n = len(split_segments(text))
        except Exception:
            n = 0
        if n <= 1:
            self.seg_var.set("当前 1 段报文" if n else "当前无有效报文")
        else:
            self.seg_var.set(f"当前 {n} 段报文（<br> 分隔，一轮全部发出）")

    def _get_segments(self):
        """编译结果缓存：报文没改动就不重复解析（大模板每次能省 100ms 以上）。"""
        text = self.txt_template.get("1.0", "end-1c")
        cached_text, cached = self._seg_cache
        if cached is not None and cached_text == text:
            return cached
        segs = compile_segments(text)
        self._seg_cache = (text, segs)
        return segs

    def on_template_applied(self, content, files):
        self.txt_template.delete("1.0", "end")
        self.txt_template.insert("1.0", content)
        self._update_seg_label()
        self.log(f"已从模板填充 {len(files)} 个文件：" +
                 "、".join(os.path.basename(p) for p in files))
        self.status_var.set(f"已填充 {len(files)} 个模板")

    def _get_selected_bytes(self, text_widget):
        try:
            if not text_widget.tag_ranges("sel"):
                return 0
            raw = text_widget.get("sel.first", "sel.last")
        except tk.TclError:
            return 0
        try:
            tokens = parse_hex_tokens(strip_comments(raw))
            return len(hex_tokens_to_bytes(tokens))
        except Exception:
            return 0

    # ---------------- 协议切换 ----------------

    def _on_proto_change(self):
        if self.var_proto.get() == "udp":
            self.tcp_frame.grid_remove()
            self.udp_frame.grid(row=0, column=0, sticky="ew")
        else:
            self.udp_frame.grid_remove()
            self.tcp_frame.grid(row=0, column=0, sticky="ew")
        self._refresh_send_buttons()

    def _refresh_send_buttons(self):
        if self.var_proto.get() == "udp":
            running = self.udp_thread is not None and self.udp_thread.is_alive()
        else:
            running = self.tcp_thread is not None and self.tcp_thread.is_alive()
        if running:
            self.btn_send.config(text="停止发送")
            self.btn_send_once.config(state="disabled")
        else:
            self.btn_send.config(text="发送", state="normal")
            self.btn_send_once.config(state="normal")

    # ---------------- T 范围 / L 列表 ----------------

    def edit_t_range(self):
        dlg = self._dlg_t_range
        if dlg is not None and dlg.is_open():
            dlg.focus()
            return

        def on_save(new_range):
            self.t_range = new_range
            if new_range is None:
                self.log("已清除 T 全局范围（按字段满量程）")
            else:
                self.log(f"已设置 T 全局范围 {new_range[0]}~{new_range[1]}")

        self._dlg_t_range = TRangeDialog(self.root, self.t_range, on_save)
        self._dlg_t_range.open()

    def edit_l_list(self):
        dlg = self._dlg_l_list
        if dlg is not None and dlg.is_open():
            dlg.focus()
            return

        self._dlg_l_list = LListDialog(
            parent=self.root,
            tpl_getter=lambda: self.txt_template.get("1.0", "end-1c"),
            on_save=self._on_l_saved,
            list_values=self.list_values,
            hold_str=self.var_list_hold.get(),
            list_mode=self.list_mode,
            gen_state=self.l_gen_state,
            sel_getter=lambda: self._get_selected_bytes(self.txt_template),
        )
        self._dlg_l_list.open()

    def _on_l_saved(self, vals, hold_str, mode, gen_state):
        self.list_values = vals
        self.var_list_hold.set(hold_str)
        self.list_mode = mode
        self.l_gen_state = gen_state
        self.reset_l_counters()
        self.log(f"已设置 L 全局列表，共 {len(vals)} 个值，保持 {float(hold_str)} 秒，"
                 f"{'循环' if mode == 'loop' else '走完即停'}")

    def reset_l_counters(self):
        for d in (self.counters["udp"], self.counters["tcp"]):
            for k in [k for k in d if k.startswith("l_")]:
                del d[k]

    # ---------------- 发送公共 ----------------

    def _current_conf(self):
        if self.var_proto.get() == "udp":
            return (self.var_udp_interval.get(), self.var_udp_continuous.get())
        return (self.var_tcp_interval.get(), self.var_tcp_continuous.get())

    def _parse_interval(self, text):
        try:
            v = int((text or "").strip() or "1000")
        except ValueError:
            raise ValueError("发送间隔必须是整数毫秒")
        return max(1, v)

    def _prepare_send(self):
        segments = self._get_segments()
        list_hold = parse_hold_seconds(self.var_list_hold.get())
        _iv, continuous = self._current_conf()
        return segments, list_hold, continuous

    def on_send(self):
        if self.var_proto.get() == "udp":
            self.udp_send()
        else:
            self.tcp_send()

    def on_send_once(self):
        if self.var_proto.get() == "udp":
            self.udp_send_once()
        else:
            self.tcp_send_once()

    # ---------------- UDP ----------------

    def get_udp_conf(self):
        local_ip = self.var_udp_local_ip.get().strip() or "0.0.0.0"
        try:
            local_port = int(self.var_udp_local_port.get().strip() or "0")
        except ValueError:
            raise ValueError("本机端口必须是整数")
        if not 0 <= local_port <= 65535:
            raise ValueError("本机端口范围 0~65535")

        target_ip = self.var_udp_target_ip.get().strip()
        if not target_ip:
            raise ValueError("目标 IP 不能为空")

        try:
            target_port = int(self.var_udp_target_port.get().strip())
        except ValueError:
            raise ValueError("目标端口必须是整数")
        if not 1 <= target_port <= 65535:
            raise ValueError("目标端口范围 1~65535")

        interval = self._parse_interval(self.var_udp_interval.get())
        return local_ip, local_port, target_ip, target_port, interval

    def udp_send(self):
        if self.udp_thread is not None and self.udp_thread.is_alive():
            self.udp_stop.set()
            self.btn_send.config(state="disabled", text="停止中...")
            return

        try:
            local_ip, local_port, target_ip, target_port, interval = self.get_udp_conf()
            segments, list_hold, continuous = self._prepare_send()
            self.sent_count = 0
            self.udp_stop.clear()

            if continuous:
                self.reset_l_counters()
                self.btn_send.config(text="停止发送")
                self.btn_send_once.config(state="disabled")
                self.udp_thread = threading.Thread(
                    target=self.udp_loop,
                    args=(segments, local_ip, local_port, target_ip,
                          target_port, interval, list_hold),
                    daemon=True)
                self.udp_thread.start()
            else:
                try:
                    payloads = build_payloads(
                        segments, self.counters["udp"], self.list_values,
                        list_hold, self.t_range, self.list_mode)
                except SequenceFinished as e:
                    self.reset_l_counters()
                    self.log(f"{e}；已重置，下次发送从第一个组合开始")
                    messagebox.showinfo(
                        "列表已走完",
                        f"{e}\n已重置，下次发送会从第一个组合重新开始。",
                        parent=self.root)
                    self.status_var.set("L 列表已走完")
                    return

                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    sock.bind((local_ip, local_port))
                    for i, p in enumerate(payloads, 1):
                        sock.sendto(p, (target_ip, target_port))
                        self.log(f"发送 [{i}/{len(payloads)}] {len(p)} 字节: "
                                 f"{hex_preview(p)}")
                finally:
                    sock.close()
                self.sent_count = len(payloads)
                self.status_var.set(
                    f"已发送 {len(payloads)} 包（{len(segments)} 段报文）")
        except Exception as e:
            self.udp_stop.set()
            self._refresh_send_buttons()
            messagebox.showerror("错误", str(e))

    def udp_send_once(self):
        if self.udp_thread is not None and self.udp_thread.is_alive():
            messagebox.showwarning("提示", "持续发送中，请先停止再使用“发送一次”")
            return
        try:
            local_ip, local_port, target_ip, target_port, _iv = self.get_udp_conf()
            segments, list_hold, _cont = self._prepare_send()
            try:
                payloads = build_payloads(
                    segments, self.counters["udp"], self.list_values,
                    list_hold, self.t_range, self.list_mode)
            except SequenceFinished as e:
                self.reset_l_counters()
                self.log(f"{e}；已重置，下次发送从第一个组合开始")
                messagebox.showinfo(
                    "列表已走完",
                    f"{e}\n已重置，下次发送会从第一个组合重新开始。",
                    parent=self.root)
                return

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.bind((local_ip, local_port))
                for i, p in enumerate(payloads, 1):
                    sock.sendto(p, (target_ip, target_port))
                    self.log(f"[单次 {i}/{len(payloads)}] {len(p)} 字节: "
                             f"{hex_preview(p)}")
            finally:
                sock.close()
            self.status_var.set(
                f"已单次发送 {len(payloads)} 包（{len(segments)} 段报文）")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def udp_loop(self, segments, local_ip, local_port, target_ip,
                 target_port, interval, list_hold):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((local_ip, local_port))
        except Exception as e:
            self.ui_call(lambda e=e: messagebox.showerror("绑定失败", str(e)))
            self.ui_call(self.finish_udp)
            sock.close()
            return

        seq_done = False
        cycle = 0
        try:
            while not self.udp_stop.is_set():
                try:
                    payloads = build_payloads(
                        segments, self.counters["udp"], self.list_values,
                        list_hold, self.t_range, self.list_mode)
                except SequenceFinished as e:
                    seq_done = True
                    msg = str(e)
                    self.ui_call(self.log, msg)
                    break
                except Exception as e:
                    msg = str(e)
                    self.ui_call(self.log, f"发送中止：{msg}")
                    self.ui_call(lambda msg=msg: messagebox.showerror(
                        "发送中止", msg, parent=self.root))
                    break

                cycle += 1
                for i, p in enumerate(payloads, 1):
                    sock.sendto(p, (target_ip, target_port))
                    self.sent_count += 1
                    if cycle == 1:
                        idx, total, ln, data = i, len(payloads), len(p), hex_preview(p)
                        self.ui_call(
                            self.log,
                            f"发送 [{idx}/{total}] {ln} 字节: {data}")
                if cycle == 1 and len(payloads) > 1:
                    self.ui_call(self.log, f"每轮 {len(payloads)} 段报文，"
                                           f"间隔 {interval}ms 循环")

                cnt = self.sent_count
                self.ui_call(
                    lambda cnt=cnt: self.status_var.set(
                        f"持续发送中：已发送 {cnt} 包（每轮 {len(payloads)} 段）"))
                self.udp_stop.wait(interval / 1000.0)
        finally:
            sock.close()
            self.ui_call(self.finish_udp, seq_done)

    def finish_udp(self, seq_done=False):
        self.udp_thread = None
        self.sent_count = getattr(self, "sent_count", 0)
        self._refresh_send_buttons()
        if seq_done:
            self.status_var.set(f"列表已走完，共发送 {self.sent_count} 包（已停止）")
        else:
            self.status_var.set(f"已停止，共发送 {self.sent_count} 包")

    # ---------------- TCP Server ----------------

    def on_button_conn(self):
        if self.server_socket is None:
            self.start_server()
        else:
            self.stop_server()

    def start_server(self):
        ip = self.var_tcp_ip.get().strip() or "0.0.0.0"
        try:
            port = int(self.var_tcp_port.get().strip())
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
        self.server_stop.clear()
        self.btn_conn_text.set("关闭连接")
        self.tcp_status_var.set(f"监听中 {ip}:{port}，客户端 0")
        self.log(f"[系统] 开始监听 {ip}:{port}")

        self.accept_thread = threading.Thread(
            target=self.accept_loop, args=(s,), daemon=True)
        self.accept_thread.start()

    def accept_loop(self, sock):
        while not self.server_stop.is_set():
            try:
                conn, addr = sock.accept()
            except OSError:
                break
            except Exception:
                break

            with self.client_lock:
                self.client_counter += 1
                cid = self.client_counter
                self.clients[cid] = {"conn": conn, "addr": addr}

            t = threading.Thread(target=self.client_recv_loop,
                                 args=(cid, conn, addr), daemon=True)
            t.start()
            self.ui_call(self.on_client_connected, cid, addr)

    def on_client_connected(self, cid, addr):
        self.refresh_client_list()
        self.log(f"[系统] 客户端 #{cid} 已连接 {addr[0]}:{addr[1]}")
        with self.client_lock:
            n = len(self.clients)
        if self.server_socket is not None:
            self.tcp_status_var.set(f"监听中，客户端 {n}")

    def client_recv_loop(self, cid, conn, addr):
        while not self.server_stop.is_set():
            try:
                data = conn.recv(65535)
            except OSError:
                break
            except Exception:
                break
            if not data:
                break
            hexstr = hex_preview(data)
            self.ui_call(self.log_recv, cid, addr, hexstr, len(data))

        try:
            conn.close()
        except Exception:
            pass
        with self.client_lock:
            self.clients.pop(cid, None)
        self.ui_call(self.on_client_disconnected, cid, addr)

    def log_recv(self, cid, addr, hexstr, nbytes):
        self.log(f"收 #{cid} {addr[0]}:{addr[1]} ({nbytes}B): {hexstr}")

    def on_client_disconnected(self, cid, addr):
        self.refresh_client_list()
        self.log(f"[系统] 客户端 #{cid} 已断开 {addr[0]}:{addr[1]}")
        with self.client_lock:
            n = len(self.clients)
        if self.server_socket is not None:
            self.tcp_status_var.set(f"监听中，客户端 {n}")

    def stop_server(self):
        was_active = self.server_socket is not None or bool(self.clients)
        self.server_stop.set()

        if self.tcp_thread is not None and self.tcp_thread.is_alive():
            self.tcp_stop.set()

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
        for _cid, info in clients:
            try:
                info["conn"].close()
            except Exception:
                pass

        self.btn_conn_text.set("连接")
        self.tcp_status_var.set("未连接")
        self.var_client.set("")
        self.combo_clients["values"] = []

        if was_active:
            self.log("[系统] 已关闭连接")

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

    def _selected_cid(self):
        sel = self.var_client.get().strip()
        if not sel:
            messagebox.showwarning("提示", "请先选择客户端")
            return None
        try:
            cid = int(sel.split(" ")[0].lstrip("#"))
        except Exception:
            messagebox.showerror("错误", "客户端选择无效")
            return None
        with self.client_lock:
            if cid not in self.clients:
                messagebox.showerror("错误", "客户端已断开")
                return None
        return cid

    def tcp_send(self):
        if self.tcp_thread is not None and self.tcp_thread.is_alive():
            self.tcp_stop.set()
            self.btn_send.config(state="disabled", text="停止中...")
            return

        cid = self._selected_cid()
        if cid is None:
            return

        try:
            segments, list_hold, continuous = self._prepare_send()
            interval = self._parse_interval(self.var_tcp_interval.get())
            self.tcp_sent = 0
            self.tcp_stop.clear()

            if continuous:
                self.reset_l_counters()
                self.btn_send.config(text="停止发送")
                self.btn_send_once.config(state="disabled")
                self.tcp_thread = threading.Thread(
                    target=self.tcp_loop,
                    args=(segments, cid, interval, list_hold),
                    daemon=True)
                self.tcp_thread.start()
            else:
                try:
                    payloads = build_payloads(
                        segments, self.counters["tcp"], self.list_values,
                        list_hold, self.t_range, self.list_mode)
                except SequenceFinished as e:
                    self.reset_l_counters()
                    self.log(f"[系统] {e}；已重置，下次发送从第一个组合开始")
                    messagebox.showinfo(
                        "列表已走完",
                        f"{e}\n已重置，下次发送会从第一个组合重新开始。",
                        parent=self.root)
                    self.status_var.set("L 列表已走完")
                    return

                with self.client_lock:
                    info = self.clients.get(cid)
                if info is None:
                    raise RuntimeError("客户端已断开")
                for i, p in enumerate(payloads, 1):
                    info["conn"].sendall(p)
                    addr = info["addr"]
                    self.log(f"发 #{cid} {addr[0]}:{addr[1]} "
                             f"[{i}/{len(payloads)}] ({len(p)}B): {hex_preview(p)}")
                self.tcp_sent = len(payloads)
                self.status_var.set(
                    f"已发送 {len(payloads)} 包（{len(segments)} 段报文）")
        except Exception as e:
            self.tcp_stop.set()
            self._refresh_send_buttons()
            messagebox.showerror("发送失败", str(e))

    def tcp_send_once(self):
        if self.tcp_thread is not None and self.tcp_thread.is_alive():
            messagebox.showwarning("提示", "持续发送中，请先停止再使用“发送一次”")
            return

        cid = self._selected_cid()
        if cid is None:
            return

        try:
            segments, list_hold, _cont = self._prepare_send()
            try:
                payloads = build_payloads(
                    segments, self.counters["tcp"], self.list_values,
                    list_hold, self.t_range, self.list_mode)
            except SequenceFinished as e:
                self.reset_l_counters()
                self.log(f"[系统] {e}；已重置，下次发送从第一个组合开始")
                messagebox.showinfo(
                    "列表已走完",
                    f"{e}\n已重置，下次发送会从第一个组合重新开始。",
                    parent=self.root)
                return

            with self.client_lock:
                info = self.clients.get(cid)
            if info is None:
                raise RuntimeError("客户端已断开")
            for i, p in enumerate(payloads, 1):
                info["conn"].sendall(p)
                addr = info["addr"]
                self.log(f"发(单次) #{cid} {addr[0]}:{addr[1]} "
                         f"[{i}/{len(payloads)}] ({len(p)}B): {hex_preview(p)}")
            self.status_var.set(
                f"已单次发送 {len(payloads)} 包（{len(segments)} 段报文）")
        except Exception as e:
            messagebox.showerror("发送失败", str(e))

    def tcp_loop(self, segments, cid, interval, list_hold):
        seq_done = False
        cycle = 0
        while not self.tcp_stop.is_set():
            with self.client_lock:
                info = self.clients.get(cid)
            if info is None:
                self.ui_call(self.log, "[系统] 客户端已断开，停止持续发送")
                break
            try:
                try:
                    payloads = build_payloads(
                        segments, self.counters["tcp"], self.list_values,
                        list_hold, self.t_range, self.list_mode)
                except SequenceFinished as e:
                    seq_done = True
                    msg = str(e)
                    self.ui_call(self.log, f"[系统] {msg}")
                    break
                except Exception as e:
                    msg = str(e)
                    self.ui_call(self.log, f"[系统] 发送中止：{msg}")
                    self.ui_call(lambda msg=msg: messagebox.showerror(
                        "发送中止", msg, parent=self.root))
                    break

                cycle += 1
                addr = info["addr"]
                for i, p in enumerate(payloads, 1):
                    info["conn"].sendall(p)
                    self.tcp_sent += 1
                    hexstr = hex_preview(p)
                    ln = len(p)
                    self.ui_call(
                        self.log,
                        f"发 #{cid} {addr[0]}:{addr[1]} [{i}/{len(payloads)}] "
                        f"({ln}B): {hexstr}")
                cnt = self.tcp_sent
                self.ui_call(
                    self.status_var.set,
                    f"持续发送中：已发送 {cnt} 包（每轮 {len(payloads)} 段）")
            except Exception as e:
                self.ui_call(self.log, f"[系统] 发送失败: {e}")
                break
            self.tcp_stop.wait(interval / 1000.0)
        self.ui_call(self.finish_tcp, seq_done)

    def finish_tcp(self, seq_done=False):
        self.tcp_thread = None
        self._refresh_send_buttons()
        if seq_done:
            self.status_var.set(f"列表已走完，共发送 {self.tcp_sent} 包（已停止）")
        else:
            self.status_var.set(f"已停止，共发送 {self.tcp_sent} 包")

    # ---------------- 配置读写 ----------------

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

    def _load_common(self, suffix, default=""):
        """共享配置：优先 common.*，其次从旧版 udp.* / tcp.* 迁移。"""
        v = self.load_setting(f"common.{suffix}", None)
        if v not in (None, ""):
            return v
        for old in (f"udp.{suffix}", f"tcp.{suffix}"):
            v = self.load_setting(old, None)
            if v not in (None, ""):
                return v
        return default

    def load_config(self):
        # 窗口尺寸：优先恢复上次，其次按屏幕自适应，并做一次屏幕内夹取
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        dw = min(1320, max(1000, int(sw * 0.86)))
        dh = min(900, max(680, int(sh * 0.84)))
        self.root.minsize(min(1080, sw - 80), min(640, sh - 120))

        w, h, x, y = dw, dh, None, None
        geo = self.load_setting("ui.geometry", "")
        mm = re.match(r"(\d+)x(\d+)([+-]-?\d+)([+-]-?\d+)$", geo or "")
        if mm:
            gw, gh = int(mm.group(1)), int(mm.group(2))
            gx, gy = int(mm.group(3)), int(mm.group(4))
            if 400 <= gw <= sw and 300 <= gh <= sh:
                w, h, x, y = gw, gh, gx, gy
        if x is None:
            self.root.geometry(f"{w}x{h}")
        else:
            self.root.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

        proto = self.load_setting("ui.protocol", "udp")
        self.var_proto.set("tcp" if proto == "tcp" else "udp")

        # 共享模板 / T / L
        tpl = self._load_common("template", "")
        if tpl:
            self.txt_template.insert("1.0", tpl)

        t_min = self._load_common("t_min", "")
        t_max = self._load_common("t_max", "")
        if t_min != "" and t_max != "":
            try:
                self.t_range = (int(t_min), int(t_max))
            except ValueError:
                self.t_range = None

        raw_list = self._load_common("list_values", "")
        try:
            self.list_values = [int(x) for x in raw_list.split(",") if x.strip()]
        except ValueError:
            self.list_values = []

        self.var_list_hold.set(self._load_common("list_hold", "0") or "0")
        self.list_mode = self._load_common("list_mode", "loop") or "loop"
        for k in ("mode", "bytes", "start", "bits", "rev", "ff"):
            val = self._load_common(f"list_gen_{k}", self.l_gen_state.get(k, ""))
            if val:
                self.l_gen_state[k] = val

        # UDP
        self.var_udp_local_ip.set(self.load_setting("udp.local_ip", "0.0.0.0"))
        self.var_udp_local_port.set(self.load_setting("udp.local_port", "0"))
        self.var_udp_target_ip.set(self.load_setting("udp.target_ip", "127.0.0.1"))
        self.var_udp_target_port.set(self.load_setting("udp.target_port", "9000"))
        self.var_udp_interval.set(self.load_setting("udp.interval", "1000"))
        self.var_udp_continuous.set(
            self.load_setting("udp.continuous", "0") == "1")

        # TCP
        self.var_tcp_ip.set(self.load_setting("tcp.local_ip", "0.0.0.0"))
        self.var_tcp_port.set(self.load_setting("tcp.local_port", "8000"))
        self.var_tcp_interval.set(self.load_setting("tcp.interval", "1000"))
        self.var_tcp_continuous.set(
            self.load_setting("tcp.continuous", "0") == "1")

    def save_config(self):
        try:
            self.root.update_idletasks()
            self.save_setting("ui.geometry", self.root.geometry())
        except Exception:
            pass
        self.save_setting("ui.protocol", self.var_proto.get())

        self.save_setting("common.template",
                          self.txt_template.get("1.0", "end-1c"))
        if self.t_range is not None:
            self.save_setting("common.t_min", str(self.t_range[0]))
            self.save_setting("common.t_max", str(self.t_range[1]))
        else:
            self.save_setting("common.t_min", "")
            self.save_setting("common.t_max", "")
        self.save_setting("common.list_values",
                          ",".join(map(str, self.list_values)))
        self.save_setting("common.list_hold", self.var_list_hold.get().strip())
        self.save_setting("common.list_mode", self.list_mode)
        gs = self.l_gen_state or {}
        for k, d in (("mode", GEN_MODE_MANUAL), ("bytes", "1"), ("start", "0"),
                     ("bits", "4"), ("rev", "0"), ("ff", "0")):
            self.save_setting(f"common.list_gen_{k}", gs.get(k, d))

        self.save_setting("udp.local_ip", self.var_udp_local_ip.get().strip())
        self.save_setting("udp.local_port", self.var_udp_local_port.get().strip())
        self.save_setting("udp.target_ip", self.var_udp_target_ip.get().strip())
        self.save_setting("udp.target_port", self.var_udp_target_port.get().strip())
        self.save_setting("udp.interval", self.var_udp_interval.get().strip())
        self.save_setting("udp.continuous",
                          "1" if self.var_udp_continuous.get() else "0")

        self.save_setting("tcp.local_ip", self.var_tcp_ip.get().strip())
        self.save_setting("tcp.local_port", self.var_tcp_port.get().strip())
        self.save_setting("tcp.interval", self.var_tcp_interval.get().strip())
        self.save_setting("tcp.continuous",
                          "1" if self.var_tcp_continuous.get() else "0")

    # ---------------- 退出 ----------------

    def on_close(self):
        try:
            self.udp_stop.set()
            self.tcp_stop.set()
            self.server_stop.set()
        except Exception:
            pass
        try:
            self.save_config()
        except Exception:
            pass
        try:
            if self.server_socket is not None:
                self.stop_server()
        except Exception:
            pass
        self.root.destroy()


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
