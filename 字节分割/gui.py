# -*- coding: utf-8 -*-
"""
字节按组分隔工具（GUI 版）
功能：
  1. 直接粘贴 16 进制报文，无需读取文件
  2. 自定义「每组字节数」和「分割组数」
  3. 前 N 组按设定字节数分隔，剩余数据整体保留
  4. 一键复制结果到剪贴板
"""

import re
import tkinter as tk
from tkinter import ttk, messagebox


# ============================================================
# 核心逻辑
# ============================================================
def parse_hex_bytes(text: str):
    """
    把任意格式的 16 进制文本解析成字节列表（每字节 2 个十六进制字符）
    支持：空格、换行、逗号、分号、冒号、短横线、下划线分隔，以及 0x 前缀
    返回：(字节列表, None) 或 (None, 错误信息)
    """
    s = re.sub(r"[\s,;:\-_]+", "", text)      # 去掉所有分隔符
    s = re.sub(r"0[xX]", "", s)               # 去掉 0x / 0X 前缀
    if not s:
        return None, "输入内容为空，请先粘贴 16 进制报文"

    bad = re.findall(r"[^0-9a-fA-F]", s)
    if bad:
        return None, "存在非 16 进制字符：" + "".join(sorted(set(bad)))

    if len(s) % 2:
        return None, f"16 进制字符个数为奇数（{len(s)} 个），无法两两组成字节"

    return [s[i:i + 2].upper() for i in range(0, len(s), 2)], None


def split_bytes(tokens, bytes_per_group, stop_group):
    """
    前 stop_group 组按 bytes_per_group 拆开，剩余数据整体保留
    返回：[(内容, 组号 或 None), ...]
    """
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
# 界面
# ============================================================
class HexSplitterApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("字节按组分隔工具")
        root.geometry("960x740")
        root.minsize(760, 560)

        main = ttk.Frame(root, padding=10)
        main.pack(fill="both", expand=True)

        # ---------- 参数区 ----------
        bar = ttk.LabelFrame(main, text="参数设置", padding=(10, 8))
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

        # ---------- 按钮区 ----------
        btns = ttk.Frame(main)
        btns.pack(fill="x", pady=(10, 6))

        ttk.Button(btns, text="开始分割", command=self.do_split).pack(side="left")
        ttk.Button(btns, text="复制结果", command=self.copy_result).pack(side="left", padx=8)
        ttk.Button(btns, text="清空全部", command=self.clear_all).pack(side="left")

        self.status_var = tk.StringVar(value="把 16 进制报文粘贴到下面的输入框，然后点【开始分割】")
        ttk.Label(btns, textvariable=self.status_var,
                  foreground="#666666").pack(side="right")

        # ---------- 输入区 ----------
        in_frame = ttk.LabelFrame(main, text="输入的 16 进制报文", padding=(6, 4))
        in_frame.pack(fill="both", expand=True)

        self.input_text = tk.Text(in_frame, wrap="char", undo=True,
                                  font=("Consolas", 10), height=8)
        in_sb = ttk.Scrollbar(in_frame, orient="vertical", command=self.input_text.yview)
        self.input_text.configure(yscrollcommand=in_sb.set)
        in_sb.pack(side="right", fill="y")
        self.input_text.pack(side="left", fill="both", expand=True)

        # ---------- 输出区 ----------
        out_frame = ttk.LabelFrame(main, text="分割结果", padding=(6, 4))
        out_frame.pack(fill="both", expand=True, pady=(8, 0))

        self.output_text = tk.Text(out_frame, wrap="char",
                                   font=("Consolas", 10), height=12)
        out_sb = ttk.Scrollbar(out_frame, orient="vertical", command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=out_sb.set)
        out_sb.pack(side="right", fill="y")
        self.output_text.pack(side="left", fill="both", expand=True)

        # ---------- 快捷键 ----------
        root.bind("<Control-Return>", lambda e: self.do_split())
        root.bind("<F5>", lambda e: self.do_split())

    # --------------------------------------------------------
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

    # --------------------------------------------------------
    def copy_result(self):
        content = self.output_text.get("1.0", "end-1c")
        if not content.strip():
            messagebox.showinfo("提示", "还没有可复制的结果，请先点击【开始分割】")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.root.update()          # 让剪贴板内容真正写入系统
        self.status_var.set("✔ 结果已复制到剪贴板")
        self.root.after(2500, lambda: self.status_var.set("就绪"))

    # --------------------------------------------------------
    def clear_all(self):
        self.input_text.delete("1.0", "end")
        self.output_text.delete("1.0", "end")
        self.status_var.set("已清空")


# ============================================================
def main():
    # 让界面在高分屏上不模糊（Windows）
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    HexSplitterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()