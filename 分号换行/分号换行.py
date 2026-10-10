"""
报警记录格式化工具（支持一键复制到 Excel 单个单元格）
"""
import csv
import io
import tkinter as tk
from tkinter import scrolledtext, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import pyperclip  # 需要安装：pip install pyperclip

class FormatterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("报警记录格式化工具")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)

        main_frame = ttk.Frame(root, padding=10)
        main_frame.pack(fill=BOTH, expand=YES)

        # 输入区
        ttk.Label(main_frame, text="输入（每行一条完整记录，用分号分隔）：").pack(anchor=W, pady=(0, 2))
        self.input_text = scrolledtext.ScrolledText(
            main_frame, height=10, wrap=WORD, font=("Consolas", 10)
        )
        self.input_text.pack(fill=BOTH, expand=YES, pady=(0, 10))

        # 按钮区
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=X, pady=(0, 10))

        self.btn_preview = ttk.Button(
            btn_frame, text="格式化预览", command=self.preview, style="primary.TButton"
        )
        self.btn_preview.pack(side=LEFT, padx=(0, 10))

        self.btn_copy = ttk.Button(
            btn_frame, text="复制到表格（可直接粘贴到Excel）", command=self.copy_to_clipboard, style="success.TButton"
        )
        self.btn_copy.pack(side=LEFT, padx=(0, 10))

        self.btn_clear = ttk.Button(
            btn_frame, text="清空", command=self.clear, style="secondary.TButton"
        )
        self.btn_clear.pack(side=LEFT)

        # 输出预览区
        ttk.Label(main_frame, text="预览（记录间空一行）：").pack(anchor=W, pady=(0, 2))
        self.output_text = scrolledtext.ScrolledText(
            main_frame, height=12, wrap=WORD, font=("Consolas", 10)
        )
        self.output_text.pack(fill=BOTH, expand=YES)

    def parse_records(self):
        """解析输入，返回记录列表（每条记录是一个三行字符串的列表）"""
        raw = self.input_text.get("1.0", tk.END)
        lines = raw.splitlines()
        records = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 自适应全角/半角分号拆分
            parts = [p.strip() for p in line.replace('；', ';').split(';') if p.strip()]
            if not parts:
                continue
            # 每条记录内部用换行符连接（预览用，复制时会再次处理）
            records.append(parts)
        return records

    def preview(self):
        """格式化预览：记录内换行，记录间空一行"""
        records = self.parse_records()
        blocks = ['\n'.join(rec) for rec in records]
        result = '\n\n'.join(blocks)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", result)

    def copy_to_clipboard(self):
        """将记录处理成单列 CSV 并复制到剪贴板，可直接粘贴到 Excel"""
        records = self.parse_records()
        if not records:
            messagebox.showwarning("警告", "没有可复制的内容，请先输入数据。")
            return

        # 每条记录用换行符连接成单个字段（单元格内容）
        cells = ['\n'.join(rec) for rec in records]

        # 生成 CSV 格式字符串（单列），确保包含换行的字段被双引号包围
        output = io.StringIO()
        writer = csv.writer(output, lineterminator='\n')
        for cell in cells:
            writer.writerow([cell])
        csv_text = output.getvalue()

        # 复制到剪贴板
        try:
            pyperclip.copy(csv_text)
            messagebox.showinfo("成功", "已复制到剪贴板！\n\n打开 Excel，直接粘贴（Ctrl+V）即可。\n每个报警记录会独占一个单元格，并保留内部换行。")
        except Exception as e:
            messagebox.showerror("错误", f"复制失败：{e}")

    def clear(self):
        self.input_text.delete("1.0", tk.END)
        self.output_text.delete("1.0", tk.END)

if __name__ == "__main__":
    root = ttk.Window(themename="cosmo")
    app = FormatterApp(root)
    root.mainloop()