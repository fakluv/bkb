# -*- coding: utf-8 -*-
"""
字节工具集（GUI 版）
功能：
  1. 字节按组分隔：直接粘贴 16 进制报文，按「每组字节数」「分割组数」分隔
  2. 批量生成 16 进制编号：填写编号列表，生成固定字节宽的 16 进制
                          （字节之间空格隔开，可带 #原十进制# 注释）
"""

import re
import tkinter as tk
from tkinter import ttk, messagebox


# ============================================================
# 核心逻辑：字节按组分隔
# ============================================================
def parse_hex_bytes(text: str):
    s = re.sub(r"[\s,;:\-_]+", "", text)
    s = re.sub(r"0[xX]", "", s)
    if not s:
        return None, "输入内容为空，请先粘贴 16 进制报文"

    bad = re.findall(r"[^0-9a-fA-F]", s)
    if bad:
        return None, "存在非 16 进制字符：" + "".join(sorted(set(bad)))

    if len(s) % 2:
        return None, f"16 进制字符个数为奇数（{len(s)} 个），无法两两组成字节"

    return [s[i:i + 2].upper() for i in range(0, len(s), 2)], None


def split_bytes(tokens, bytes_per_group, stop_group):
    total = len(tokens)
    stop_index = bytes_per_group * stop_group
    result = []

    group_no = 0
    i = 0
    while i < min(stop_index, total):
        group_no += 1
        result.append((" ".join(tokens[i:i + bytes_per_group]), group_no))
        i += bytes_per_group

    if total > stop_index:
        result.append((" ".join(tokens[stop_index:]), None))

    return result, group_no


# ============================================================
# 核心逻辑：批量生成 16 进制编号
# ============================================================
def parse_number_list(text: str):
    tokens = re.split(r"[\s,;，；、]+", text.strip())
    nums = []
    for t in tokens:
        if not t:
            continue
        if re.fullmatch(r"0[xX][0-9a-fA-F]+", t):
            nums.append(int(t, 16))
        elif re.fullmatch(r"\d+", t):
            nums.append(int(t, 10))
        else:
            return None, (f"无法识别的编号：{t}\n"
                          f"只支持十进制数字（如 10）或 0x 开头的十六进制（如 0x0A）")
    if not nums:
        return None, "输入为空，请先填写要转换的编号"
    return nums, None


def format_hex_numbers(nums, byte_width, upper=True, prefix=False):
    hex_digits = byte_width * 2
    limit = 1 << (byte_width * 8)
    out = []
    for n in nums:
        if n < 0:
            return None, f"编号不能为负数：{n}"
        if n >= limit:
            return None, (f"编号 {n} 超出 {byte_width} 字节表示范围"
                          f"（最大 {limit - 1}，即 0x{limit - 1:X}）")
        s = format(n, "X" if upper else "x").zfill(hex_digits)
        if prefix:
            s = ("0X" if upper else "0x") + s
        out.append(s)
    return out, None


# ============================================================
# 公共小工具
# ============================================================
def copy_widget_text(widget, status_var, empty_hint="还没有可复制的结果，请先生成"):
    content = widget.get("1.0", "end-1c")
    if not content.strip():
        messagebox.showinfo("提示", empty_hint)
        return
    widget.clipboard_clear()
    widget.clipboard_append(content)
    widget.update()
    status_var.set("✔ 结果已复制到剪贴板")
    widget.after(2500, lambda: status_var.set("就绪"))


# ============================================================
# 页面 1：字节按组分隔
# ============================================================
class SplitTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=10)

        bar = ttk.LabelFrame(self, text="参数设置", padding=(10, 8))
        bar.pack(fill="x")

        ttk.Label(bar, text="每组字节数：").grid(row=0, column=0, sticky="w")
        self.bytes_var = tk.StringVar(value="5")
        ttk.Spinbox(bar, from_=1, to=99999, textvariable=self.bytes_var,
                    width=8).grid(row=0, column=1, sticky="w")

        ttk.Label(bar, text="分割组数：").grid(row=0, column=2, sticky="w", padx=(24, 0))
        self.groups_var = tk.StringVar(value="8")
        ttk.Spinbox(bar, from_=1, to=99999, textvariable=self.groups_var,
                    width=8).grid(row=0, column=3, sticky="w")

        self.comment_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="显示组号注释",
                        variable=self.comment_var).grid(row=0, column=4, padx=(24, 0))

        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=(10, 6))

        ttk.Button(btns, text="开始分割", command=self.do_split).pack(side="left")
        ttk.Button(btns, text="复制结果",
                   command=lambda: copy_widget_text(
                       self.output_text, self.status_var,
                       "还没有可复制的结果，请先点击【开始分割】")).pack(side="left", padx=8)
        ttk.Button(btns, text="清空全部", command=self.clear_all).pack(side="left")

        self.status_var = tk.StringVar(value="把 16 进制报文粘贴到下面的输入框，然后点【开始分割】")
        ttk.Label(btns, textvariable=self.status_var,
                  foreground="#666666").pack(side="right")

        in_frame = ttk.LabelFrame(self, text="输入的 16 进制报文", padding=(6, 4))
        in_frame.pack(fill="both", expand=True)

        self.input_text = tk.Text(in_frame, wrap="char", undo=True,
                                  font=("Consolas", 10), height=8)
        in_sb = ttk.Scrollbar(in_frame, orient="vertical", command=self.input_text.yview)
        self.input_text.configure(yscrollcommand=in_sb.set)
        in_sb.pack(side="right", fill="y")
        self.input_text.pack(side="left", fill="both", expand=True)

        out_frame = ttk.LabelFrame(self, text="分割结果", padding=(6, 4))
        out_frame.pack(fill="both", expand=True, pady=(8, 0))

        self.output_text = tk.Text(out_frame, wrap="char",
                                   font=("Consolas", 10), height=12)
        out_sb = ttk.Scrollbar(out_frame, orient="vertical", command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=out_sb.set)
        out_sb.pack(side="right", fill="y")
        self.output_text.pack(side="left", fill="both", expand=True)

    def do_split(self):
        bpg_s = self.bytes_var.get().strip()
        grp_s = self.groups_var.get().strip()

        if not bpg_s.isdigit() or not grp_s.isdigit():
            messagebox.showerror("参数错误", "「每组字节数」和「分割组数」必须是正整数")
            return

        bpg = int(bpg_s)
        stop_group = int(grp_s)
        if bpg <= 0 or stop_group <= 0:
            messagebox.showerror("参数错误", "「每组字节数」和「分割组数」必须大于 0")
            return

        raw = self.input_text.get("1.0", "end-1c")
        tokens, err = parse_hex_bytes(raw)
        if err:
            messagebox.showerror("解析失败", err)
            self.status_var.set("解析失败：" + err)
            return

        total = len(tokens)
        lines, group_count = split_bytes(tokens, bpg, stop_group)

        show_comment = self.comment_var.get()
        out_parts = []
        for content, no in lines:
            if show_comment and no is not None:
                out_parts.append(f"{content}    #第{no}组#")
            else:
                out_parts.append(content)

        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", "\n".join(out_parts))

        remaining = total - bpg * stop_group
        if remaining > 0:
            msg = (f"共 {total} 字节，已分隔 {group_count} 组"
                   f"（每组 {bpg} 字节），剩余 {remaining} 字节整体保留")
        else:
            msg = f"共 {total} 字节，已全部分隔为 {group_count} 组（每组 {bpg} 字节）"
        self.status_var.set(msg)

    def clear_all(self):
        self.input_text.delete("1.0", "end")
        self.output_text.delete("1.0", "end")
        self.status_var.set("已清空")


# ============================================================
# 页面 2：批量生成 16 进制编号（已按要求改造）
# ============================================================
class GenHexTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=10)

        # ---------- 参数区 ----------
        bar = ttk.LabelFrame(self, text="参数设置", padding=(10, 8))
        bar.pack(fill="x")

        ttk.Label(bar, text="字节数：").grid(row=0, column=0, sticky="w")
        self.bytes_var = tk.StringVar(value="1")
        ttk.Spinbox(bar, from_=1, to=64, textvariable=self.bytes_var,
                    width=8).grid(row=0, column=1, sticky="w")

        self.upper_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="大写字母",
                        variable=self.upper_var).grid(row=0, column=2, padx=(20, 0))

        self.prefix_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="加 0x 前缀",
                        variable=self.prefix_var).grid(row=0, column=3, padx=(12, 0))

        # 新增：是否显示 #原十进制# 注释
        self.comment_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="注释 #原十进制#",
                        variable=self.comment_var).grid(row=0, column=4, padx=(12, 0))

        ttk.Label(bar, text="输出分隔：").grid(row=0, column=5, sticky="w", padx=(20, 0))
        self.sep_var = tk.StringVar(value="空格")     # 默认改为空格
        ttk.Combobox(bar, textvariable=self.sep_var, state="readonly", width=6,
                     values=("空格", "换行", "逗号")).grid(row=0, column=6, sticky="w")

        # ---------- 按钮区 ----------
        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=(10, 6))

        ttk.Button(btns, text="生成 16 进制",
                   command=self.do_generate).pack(side="left")
        ttk.Button(btns, text="复制结果",
                   command=lambda: copy_widget_text(
                       self.output_text, self.status_var,
                       "还没有可复制的结果，请先点击【生成 16 进制】")).pack(side="left", padx=8)
        ttk.Button(btns, text="清空全部", command=self.clear_all).pack(side="left")

        self.status_var = tk.StringVar(
            value="在下面填写编号（每行一个），点【生成 16 进制】")
        ttk.Label(btns, textvariable=self.status_var,
                  foreground="#666666").pack(side="right")

        # ---------- 输入区 ----------
        in_frame = ttk.LabelFrame(
            self, padding=(6, 4),
            text="输入的编号（每行一个，支持十进制 10 或十六进制 0x0A）")
        in_frame.pack(fill="both", expand=True)

        self.input_text = tk.Text(in_frame, wrap="char", undo=True,
                                  font=("Consolas", 10), height=8)
        in_sb = ttk.Scrollbar(in_frame, orient="vertical", command=self.input_text.yview)
        self.input_text.configure(yscrollcommand=in_sb.set)
        in_sb.pack(side="right", fill="y")
        self.input_text.pack(side="left", fill="both", expand=True)

        # ---------- 输出区 ----------
        out_frame = ttk.LabelFrame(self, text="生成的 16 进制编号", padding=(6, 4))
        out_frame.pack(fill="both", expand=True, pady=(8, 0))

        self.output_text = tk.Text(out_frame, wrap="char",
                                   font=("Consolas", 10), height=12)
        out_sb = ttk.Scrollbar(out_frame, orient="vertical", command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=out_sb.set)
        out_sb.pack(side="right", fill="y")
        self.output_text.pack(side="left", fill="both", expand=True)

    # --------------------------------------------------------
    def do_generate(self):
        w = self.bytes_var.get().strip()
        if not w.isdigit():
            messagebox.showerror("参数错误", "「字节数」必须是正整数")
            return
        width = int(w)
        if width <= 0 or width > 64:
            messagebox.showerror("参数错误", "「字节数」取值范围为 1 ~ 64")
            return

        raw = self.input_text.get("1.0", "end-1c")
        nums, err = parse_number_list(raw)
        if err:
            messagebox.showerror("解析失败", err)
            self.status_var.set("解析失败：" + err)
            return

        lines, err = format_hex_numbers(nums, width,
                                        upper=self.upper_var.get(),
                                        prefix=self.prefix_var.get())
        if err:
            messagebox.showerror("生成失败", err)
            self.status_var.set("生成失败：" + err)
            return

        # ---------- 组装输出：每个字节 + #原十进制# 注释 ----------
        show_comment = self.comment_var.get()
        if show_comment:
            items = [f"{h} #{n}#" for h, n in zip(lines, nums)]
        else:
            items = lines

        sep = {"换行": "\n", "空格": " ", "逗号": ", "}.get(self.sep_var.get(), " ")

        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", sep.join(items))

        self.status_var.set(
            f"共 {len(nums)} 个编号，每个 {width} 字节（{width * 2} 位十六进制）")

    # --------------------------------------------------------
    def clear_all(self):
        self.input_text.delete("1.0", "end")
        self.output_text.delete("1.0", "end")
        self.status_var.set("已清空")


# ============================================================
# 主窗口
# ============================================================
class HexToolApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("字节工具集")
        root.geometry("960x740")
        root.minsize(760, 560)

        main = ttk.Frame(root, padding=10)
        main.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill="both", expand=True)

        self.split_tab = SplitTab(self.notebook)
        self.gen_tab = GenHexTab(self.notebook)

        self.notebook.add(self.split_tab, text="  字节按组分隔  ")
        self.notebook.add(self.gen_tab, text="  批量生成 16 进制编号  ")

        root.bind("<Control-Return>", lambda e: self.run_current())
        root.bind("<F5>", lambda e: self.run_current())

    def run_current(self):
        current = self.notebook.nametowidget(self.notebook.select())
        if current is self.gen_tab:
            self.gen_tab.do_generate()
        else:
            self.split_tab.do_split()
        return "break"


# ============================================================
def main():
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    HexToolApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()