# -*- coding: utf-8 -*-
"""
字节工具集（GUI 版）
功能：
  1. 字节按组分隔
  2. 批量生成 16 进制编号
  3. 设备校验：批量加后缀 + 逐条检查 + 对不上的给出具体原因
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
# 核心逻辑：设备校验辅助
# ============================================================
def parse_devices(text: str):
    """把一段文本拆成设备名列表，自动去重去空"""
    parts = re.split(r"[\r\n,;，；、\t]+", text)
    seen = set()
    out = []
    for p in parts:
        d = p.strip()
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def escape_like(s: str) -> str:
    """转义 LIKE 通配符，用 ! 作为转义符"""
    return s.replace("!", "!!").replace("%", "!%").replace("_", "!_")


def like_param(s: str) -> str:
    return "%" + escape_like(s) + "%"


def like_literal(s: str) -> str:
    return "'%" + escape_like(s).replace("'", "''") + "%'"


def build_placeholder(db_type: str, idx: int = 1) -> str:
    """生成一个占位符"""
    if db_type in ("MySQL", "PostgreSQL"):
        return "%s"
    if db_type in ("SQL Server", "SQLite"):
        return "?"
    if db_type == "Oracle":
        return f":{idx}"
    raise ValueError(f"未知数据库类型：{db_type}")


def execute_query(db_type, conn, sql, params):
    try:
        if db_type == "SQLite":
            import sqlite3
            c = sqlite3.connect(conn["database"])
            try:
                cur = c.cursor()
                cur.execute(sql, params)
                return [r[0] for r in cur.fetchall()], None
            finally:
                c.close()

        if db_type == "MySQL":
            import pymysql
            c = pymysql.connect(
                host=conn["host"], port=int(conn["port"] or 3306),
                user=conn["user"], password=conn["password"],
                database=conn["database"], charset="utf8mb4")
            try:
                cur = c.cursor()
                cur.execute(sql, params)
                return [r[0] for r in cur.fetchall()], None
            finally:
                c.close()

        if db_type == "PostgreSQL":
            import psycopg2
            c = psycopg2.connect(
                host=conn["host"], port=int(conn["port"] or 5432),
                user=conn["user"], password=conn["password"],
                dbname=conn["database"])
            try:
                cur = c.cursor()
                cur.execute(sql, params)
                return [r[0] for r in cur.fetchall()], None
            finally:
                c.close()

        if db_type == "SQL Server":
            import pyodbc
            port = conn["port"] or "1433"
            conn_str = (
                "DRIVER={ODBC Driver 17 for SQL Server};"
                f"SERVER={conn['host']},{port};"
                f"DATABASE={conn['database']};"
                f"UID={conn['user']};PWD={conn['password']};"
                "TrustServerCertificate=yes;"
            )
            c = pyodbc.connect(conn_str, timeout=10)
            try:
                cur = c.cursor()
                cur.execute(sql, params)
                return [r[0] for r in cur.fetchall()], None
            finally:
                c.close()

        if db_type == "Oracle":
            import oracledb
            dsn = f"{conn['host']}:{conn['port'] or 1521}/{conn['database']}"
            c = oracledb.connect(user=conn["user"],
                                 password=conn["password"], dsn=dsn)
            try:
                cur = c.cursor()
                cur.execute(sql, params)
                return [r[0] for r in cur.fetchall()], None
            finally:
                c.close()

        return None, f"未知数据库类型：{db_type}"

    except ImportError as e:
        pkg = {
            "MySQL": "pymysql",
            "PostgreSQL": "psycopg2-binary",
            "SQL Server": "pyodbc",
            "Oracle": "oracledb",
        }.get(db_type, "")
        tip = f"缺少数据库驱动 {pkg}，请先安装：pip install {pkg}" if pkg else ""
        return None, f"{tip}\n（原始错误：{e}）"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


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
# 页面 2：批量生成 16 进制编号
# ============================================================
class GenHexTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=10)

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

        self.comment_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="注释 #原十进制#",
                        variable=self.comment_var).grid(row=0, column=4, padx=(12, 0))

        ttk.Label(bar, text="输出分隔：").grid(row=0, column=5, sticky="w", padx=(20, 0))
        self.sep_var = tk.StringVar(value="空格")
        ttk.Combobox(bar, textvariable=self.sep_var, state="readonly", width=6,
                     values=("空格", "换行", "逗号")).grid(row=0, column=6, sticky="w")

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

        out_frame = ttk.LabelFrame(self, text="生成的 16 进制编号", padding=(6, 4))
        out_frame.pack(fill="both", expand=True, pady=(8, 0))

        self.output_text = tk.Text(out_frame, wrap="char",
                                   font=("Consolas", 10), height=12)
        out_sb = ttk.Scrollbar(out_frame, orient="vertical", command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=out_sb.set)
        out_sb.pack(side="right", fill="y")
        self.output_text.pack(side="left", fill="both", expand=True)

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

    def clear_all(self):
        self.input_text.delete("1.0", "end")
        self.output_text.delete("1.0", "end")
        self.status_var.set("已清空")


# ============================================================
# 页面 3：设备校验（批量加后缀 + 逐条检查 + 诊断）
# ============================================================
class DeviceCheckTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=10)

        # ---------- 数据库连接 ----------
        db_frame = ttk.LabelFrame(
            self,
            text="数据库连接（仅「逐个执行校验」时需要；生成 SQL 不用）",
            padding=(10, 6))
        db_frame.pack(fill="x")

        ttk.Label(db_frame, text="类型").grid(row=0, column=0, sticky="w")
        self.db_type_var = tk.StringVar(value="MySQL")
        cb = ttk.Combobox(db_frame, textvariable=self.db_type_var,
                          state="readonly", width=12,
                          values=("MySQL", "PostgreSQL", "SQL Server",
                                  "Oracle", "SQLite"))
        cb.grid(row=0, column=1, sticky="w")
        cb.bind("<<ComboboxSelected>>", self._on_db_type_change)

        ttk.Label(db_frame, text="主机").grid(row=0, column=2, sticky="w", padx=(14, 0))
        self.host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(db_frame, textvariable=self.host_var, width=16).grid(
            row=0, column=3, sticky="w")

        ttk.Label(db_frame, text="端口").grid(row=0, column=4, sticky="w", padx=(14, 0))
        self.port_var = tk.StringVar(value="3306")
        ttk.Entry(db_frame, textvariable=self.port_var, width=8).grid(
            row=0, column=5, sticky="w")

        ttk.Label(db_frame, text="库名/服务名/文件").grid(
            row=0, column=6, sticky="w", padx=(14, 0))
        self.dbname_var = tk.StringVar()
        ttk.Entry(db_frame, textvariable=self.dbname_var, width=20).grid(
            row=0, column=7, sticky="w")

        ttk.Label(db_frame, text="用户名").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.user_var = tk.StringVar()
        ttk.Entry(db_frame, textvariable=self.user_var, width=16).grid(
            row=1, column=1, sticky="w", pady=(6, 0))

        ttk.Label(db_frame, text="密码").grid(
            row=1, column=2, sticky="w", padx=(14, 0), pady=(6, 0))
        self.pwd_var = tk.StringVar()
        ttk.Entry(db_frame, textvariable=self.pwd_var, width=16, show="*").grid(
            row=1, column=3, sticky="w", pady=(6, 0))

        ttk.Button(db_frame, text="测试连接",
                   command=self.test_conn).grid(
            row=1, column=4, columnspan=2, sticky="w", padx=(14, 0), pady=(6, 0))

        # ---------- SQL 输入 ----------
        sql_frame = ttk.LabelFrame(
            self,
            text="SQL 语句（写到最后一个 and 之前；工具会为每台设备逐个补 "
                 "and 设备字段 = '列表名+后缀'）",
            padding=(6, 4))
        sql_frame.pack(fill="x", pady=(8, 0))

        self.sql_text = tk.Text(sql_frame, wrap="char", undo=True,
                                font=("Consolas", 10), height=3)
        sql_sb = ttk.Scrollbar(sql_frame, orient="vertical",
                               command=self.sql_text.yview)
        self.sql_text.configure(yscrollcommand=sql_sb.set)
        sql_sb.pack(side="right", fill="y")
        self.sql_text.pack(side="left", fill="both", expand=True)

        # ---------- 匹配参数 ----------
        params = ttk.LabelFrame(self, text="匹配参数", padding=(8, 6))
        params.pack(fill="x", pady=(6, 0))

        ttk.Label(params, text="设备字段名：").grid(row=0, column=0, sticky="w")
        self.field_var = tk.StringVar(value="device_name")
        ttk.Entry(params, textvariable=self.field_var, width=20).grid(
            row=0, column=1, sticky="w")

        ttk.Label(params, text="批量后缀：").grid(
            row=0, column=2, sticky="w", padx=(16, 0))
        self.suffix_var = tk.StringVar(value="交换机")
        ttk.Entry(params, textvariable=self.suffix_var, width=18).grid(
            row=0, column=3, sticky="w")

        ttk.Label(params, text="匹配模式：").grid(
            row=0, column=4, sticky="w", padx=(16, 0))
        self.match_var = tk.StringVar(value="精确匹配")
        ttk.Combobox(params, textvariable=self.match_var, state="readonly",
                     width=10,
                     values=("精确匹配", "包含匹配")).grid(
            row=0, column=5, sticky="w")

        ttk.Label(
            params,
            text="完整名 = 列表名 + 后缀。"
                 "「精确匹配」= 完整名与库中完全一致；"
                 "「包含匹配」= 库中名字里含完整名。"
                 "每台设备逐条查询，对不上的给出原因。",
            foreground="#888888",
            wraplength=940).grid(row=1, column=0, columnspan=6,
                                 sticky="w", pady=(4, 0))

        # ---------- 最终 SQL 预览 ----------
        preview_frame = ttk.LabelFrame(
            self, text="SQL 预览（只读，展示前 5 条，可选中复制）",
            padding=(6, 4))
        preview_frame.pack(fill="x", pady=(6, 0))

        self.preview_text = tk.Text(preview_frame, wrap="char",
                                    font=("Consolas", 9), height=5,
                                    foreground="#004080")
        preview_sb = ttk.Scrollbar(preview_frame, orient="vertical",
                                   command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=preview_sb.set)
        preview_sb.pack(side="right", fill="y")
        self.preview_text.pack(side="left", fill="both", expand=True)

        # ---------- 设备列表 ----------
        dev_frame = ttk.LabelFrame(
            self, text="设备名列表（每行一个，也支持逗号分隔）",
            padding=(6, 4))
        dev_frame.pack(fill="both", expand=True, pady=(6, 0))

        self.devices_text = tk.Text(dev_frame, wrap="char", undo=True,
                                    font=("Consolas", 10), height=5)
        dev_sb = ttk.Scrollbar(dev_frame, orient="vertical",
                               command=self.devices_text.yview)
        self.devices_text.configure(yscrollcommand=dev_sb.set)
        dev_sb.pack(side="right", fill="y")
        self.devices_text.pack(side="left", fill="both", expand=True)

        # ---------- 按钮 ----------
        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=(8, 4))

        ttk.Button(btns, text="生成 SQL（不执行）",
                   command=self.build_sql_only).pack(side="left")
        ttk.Button(btns, text="逐个执行校验",
                   command=self.do_check).pack(side="left", padx=8)
        ttk.Button(btns, text="复制结果",
                   command=lambda: copy_widget_text(
                       self.output_text, self.status_var,
                       "还没有可复制的结果，请先点击【逐个执行校验】")
                   ).pack(side="left")
        ttk.Button(btns, text="清空全部",
                   command=self.clear_all).pack(side="left", padx=8)

        self.status_var = tk.StringVar(
            value="填 SQL 前缀 + 字段名 + 后缀 + 设备列表，再点【逐个执行校验】")
        ttk.Label(btns, textvariable=self.status_var,
                  foreground="#666666").pack(side="right")

        # ---------- 结果 ----------
        out_frame = ttk.LabelFrame(
            self, text="有问题的设备（每行末尾写原因）",
            padding=(6, 4))
        out_frame.pack(fill="both", expand=True, pady=(4, 0))

        self.output_text = tk.Text(out_frame, wrap="char",
                                   font=("Consolas", 10), height=6)
        out_sb = ttk.Scrollbar(out_frame, orient="vertical",
                               command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=out_sb.set)
        out_sb.pack(side="right", fill="y")
        self.output_text.pack(side="left", fill="both", expand=True)

    # --------------------------------------------------------
    def _on_db_type_change(self, _event=None):
        default_ports = {
            "MySQL": "3306",
            "PostgreSQL": "5432",
            "SQL Server": "1433",
            "Oracle": "1521",
            "SQLite": "",
        }
        self.port_var.set(default_ports.get(self.db_type_var.get(), ""))

    def _conn_params(self):
        return {
            "host": self.host_var.get().strip(),
            "port": self.port_var.get().strip(),
            "user": self.user_var.get().strip(),
            "password": self.pwd_var.get(),
            "database": self.dbname_var.get().strip(),
        }

    def _prepare(self):
        prefix = self.sql_text.get("1.0", "end-1c").strip()
        field = self.field_var.get().strip()
        devices = parse_devices(self.devices_text.get("1.0", "end-1c"))

        if not prefix:
            return None, None, None, "SQL 语句为空"
        if not field:
            return None, None, None, "请填写设备字段名"
        if not devices:
            return None, None, None, "设备名列表为空"

        while prefix.endswith(";"):
            prefix = prefix[:-1].rstrip()

        return prefix, field, devices, None

    @staticmethod
    def _join_cond(prefix, cond):
        if re.search(r"\band\b\s*$", prefix, re.IGNORECASE):
            return f"{prefix} {cond}"
        if re.search(r"\bwhere\b", prefix, re.IGNORECASE):
            return f"{prefix} and {cond}"
        return f"{prefix} where {cond}"

    def _literal_sql_for_device(self, prefix, field, raw_name, suffix, match_mode):
        full = raw_name + suffix
        if match_mode == "精确匹配":
            cond = f"{field} = '" + full.replace("'", "''") + "'"
        else:
            cond = f"{field} like {like_literal(full)} escape '!'"
        return self._join_cond(prefix, cond)

    def _set_preview(self, text):
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)

    def _preview_lines(self, prefix, field, devices, suffix, match_mode):
        lines = [f"将逐个执行 {len(devices)} 条 SQL"
                 f"（列表名 + 后缀 '{suffix}'，{match_mode}）：", ""]
        for i, d in enumerate(devices[:5], 1):
            lines.append(f"# {i}/{len(devices)}  {d}  →  完整名 {d + suffix}")
            lines.append(self._literal_sql_for_device(
                prefix, field, d, suffix, match_mode))
            lines.append("")
        if len(devices) > 5:
            lines.append(f"...（其余 {len(devices) - 5} 条略，实际执行会逐条查询）")
        return "\n".join(lines)

    # --------------------------------------------------------
    def build_sql_only(self):
        prefix, field, devices, err = self._prepare()
        if err:
            messagebox.showerror("提示", err)
            self.status_var.set("提示：" + err)
            return

        suffix = self.suffix_var.get()
        match_mode = self.match_var.get()
        self._set_preview(
            self._preview_lines(prefix, field, devices, suffix, match_mode))
        self.status_var.set(
            f"已生成 {len(devices)} 条 SQL 模板，可复制后手动执行")

    # --------------------------------------------------------
    def test_conn(self):
        db_type = self.db_type_var.get()
        conn = self._conn_params()
        sql = "select 1 from dual" if db_type == "Oracle" else "select 1"
        self.status_var.set("正在测试连接……")
        self.update_idletasks()
        _, err = execute_query(db_type, conn, sql, [])
        if err:
            messagebox.showerror("连接失败", err)
            self.status_var.set("连接失败")
        else:
            messagebox.showinfo("连接成功", f"已成功连接 {db_type}")
            self.status_var.set(f"连接成功：{db_type}")

    # --------------------------------------------------------
    def _check_one(self, db_type, conn, prefix, field,
                   raw_name, suffix, match_mode):
        """
        逐台设备检查，返回 (status, details)
          status: "OK" / "NAME_MISMATCH" / "MISSING"
          details:
            OK        -> 命中的库中名字
            NAME_MISMATCH -> 库中相似的名字列表
            MISSING   -> []
        """
        full_name = raw_name + suffix
        placeholder = build_placeholder(db_type, 1)

        # 用原始名做模糊查询，把库里所有含原始名的候选拉回来
        cond = f"{field} like {placeholder} escape '!'"
        sql = self._join_cond(prefix, cond)
        rows, err = execute_query(db_type, conn, sql, [like_param(raw_name)])
        if err:
            raise RuntimeError(err)

        rows = [str(r) for r in rows if r is not None]
        full_lower = full_name.lower()

        # 本地判命中
        for r in rows:
            r_lower = r.lower()
            if match_mode == "精确匹配":
                if r_lower == full_lower:
                    return "OK", r
            else:  # 包含匹配
                if full_lower in r_lower:
                    return "OK", r

        if rows:
            return "NAME_MISMATCH", rows
        return "MISSING", []

    # --------------------------------------------------------
    def do_check(self):
        prefix, field, devices, err = self._prepare()
        if err:
            messagebox.showerror("提示", err)
            self.status_var.set("提示：" + err)
            return

        suffix = self.suffix_var.get()
        match_mode = self.match_var.get()
        db_type = self.db_type_var.get()
        conn = self._conn_params()

        self._set_preview(
            self._preview_lines(prefix, field, devices, suffix, match_mode))

        total = len(devices)
        self.output_text.delete("1.0", "end")

        problems = 0

        for idx, d in enumerate(devices, 1):
            self.status_var.set(f"正在检查 {idx}/{total}：{d}")
            self.update_idletasks()

            try:
                status, details = self._check_one(
                    db_type, conn, prefix, field, d, suffix, match_mode)
            except Exception as e:
                messagebox.showerror(
                    "查询失败",
                    f"设备：{d}\n{type(e).__name__}: {e}\n\n"
                    f"已中止，请检查 SQL 前缀 / 字段名。")
                self.status_var.set(f"查询失败（{idx}/{total}）")
                return

            if status != "OK":
                problems += 1
                line = self._format_problem(d, d + suffix, status, details)
                self.output_text.insert("end", line + "\n")
                self.output_text.see("end")

        ok_count = total - problems
        if problems:
            self.status_var.set(
                f"共 {total} 个：通过 {ok_count}，有问题 {problems}")
        else:
            self.status_var.set(f"共 {total} 个：全部通过")

    @staticmethod
    def _format_problem(raw_name, full_name, status, details):
        if status == "MISSING":
            return f"{raw_name} | 数据库缺失（查的是 {full_name}）"
        if status == "NAME_MISMATCH":
            shown = details[:3]
            extra = f" 等 {len(details)} 个" if len(details) > 3 else ""
            return (f"{raw_name} | 名字不一致"
                    f"（库中相似：{'、'.join(shown)}{extra}）")
        return f"{raw_name} | {status}"

    # --------------------------------------------------------
    def clear_all(self):
        self.sql_text.delete("1.0", "end")
        self.devices_text.delete("1.0", "end")
        self.preview_text.delete("1.0", "end")
        self.output_text.delete("1.0", "end")
        self.status_var.set("已清空")


# ============================================================
# 主窗口
# ============================================================
class HexToolApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("字节工具集")
        root.geometry("1020x920")
        root.minsize(860, 700)

        main = ttk.Frame(root, padding=10)
        main.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill="both", expand=True)

        self.split_tab = SplitTab(self.notebook)
        self.gen_tab = GenHexTab(self.notebook)
        self.device_tab = DeviceCheckTab(self.notebook)

        self.notebook.add(self.split_tab, text="  字节按组分隔  ")
        self.notebook.add(self.gen_tab, text="  批量生成 16 进制编号  ")
        self.notebook.add(self.device_tab, text="  设备校验  ")

        root.bind("<Control-Return>", lambda e: self.run_current())
        root.bind("<F5>", lambda e: self.run_current())

    def run_current(self):
        current = self.notebook.nametowidget(self.notebook.select())
        if current is self.gen_tab:
            self.gen_tab.do_generate()
        elif current is self.device_tab:
            self.device_tab.do_check()
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