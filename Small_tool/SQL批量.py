#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL 批量造数工具（GUI 版）

- 表结构自动识别（information_schema）
- 自动排除自增主键 / 生成列
- 断点续跑（起点 = MAX(pk)+1）
- 后台线程执行，界面不卡，支持停止
- 配置持久化到 exe 同目录 config.ini
- 日志同时写界面和 logs/ 文件
"""

import os, sys, queue, threading, configparser, datetime
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import tkinter.font as tkfont


# ==================== 路径 & 日志目录 ====================
def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR  = app_dir()
CONF_PATH = os.path.join(BASE_DIR, "config.ini")
LOG_DIR   = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


# ==================== 数据库连接 ====================
def get_conn(db_type, conf):
    conf = dict(conf)
    timeout = conf.pop("connect_timeout", 5)
    if db_type == "postgres":
        import psycopg2
        from psycopg2.extras import RealDictCursor
        return psycopg2.connect(connect_timeout=timeout, **conf), RealDictCursor
    if db_type == "mysql":
        import pymysql
        from pymysql.cursors import DictCursor
        return pymysql.connect(charset="utf8mb4", autocommit=False,
                               connect_timeout=timeout, **conf), DictCursor
    raise ValueError(f"不支持的数据库类型: {db_type}")


# ==================== 标识符 ====================
def quote(db_type, name):
    return f"`{name}`" if db_type == "mysql" else f'"{name}"'


def split_table(table):
    if "." in table:
        s, t = table.split(".", 1)
        return s, t
    return None, table


# ==================== 表结构自省 ====================
def get_table_columns(cursor, db_type, table, default_db):
    schema, tbl = split_table(table)
    info = []

    if db_type == "mysql":
        schema = schema or default_db
        cursor.execute("""
            SELECT COLUMN_NAME AS name, DATA_TYPE AS dtype,
                   IS_NULLABLE AS nullable, COLUMN_DEFAULT AS dflt,
                   EXTRA AS extra, COLUMN_KEY AS ckey
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """, (schema, tbl))
        for r in cursor.fetchall():
            r = {k.lower(): v for k, v in r.items()}
            extra = (r["extra"] or "").lower()
            info.append(dict(
                name=r["name"], dtype=r["dtype"], nullable=r["nullable"],
                dflt=r["dflt"],
                auto=("auto_increment" in extra),
                generated=("generated" in extra),
                pk=(r["ckey"] == "PRI"),
            ))
    else:
        schema = schema or "public"
        try:
            cursor.execute("""
                SELECT column_name AS name, data_type AS dtype,
                       is_nullable AS nullable, column_default AS dflt,
                       is_identity AS is_identity, is_generated AS is_generated
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
            """, (schema, tbl))
            rows = cursor.fetchall()
            has_identity = True
        except Exception:
            # PG 9.x 没有 is_identity
            cursor.execute("""
                SELECT column_name AS name, data_type AS dtype,
                       is_nullable AS nullable, column_default AS dflt,
                       'NO' AS is_identity, is_generated AS is_generated
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
            """, (schema, tbl))
            rows = cursor.fetchall()
            has_identity = False

        cursor.execute("""
            SELECT kcu.column_name AS name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema  = kcu.table_schema
            WHERE tc.table_schema = %s AND tc.table_name = %s
              AND tc.constraint_type = 'PRIMARY KEY'
        """, (schema, tbl))
        pk_names = {r["name"] for r in cursor.fetchall()}

        for r in rows:
            r = {k.lower(): v for k, v in r.items()}
            dflt = (r["dflt"] or "").lower()
            info.append(dict(
                name=r["name"], dtype=r["dtype"], nullable=r["nullable"],
                dflt=r["dflt"],
                auto=(r["is_identity"] == "YES" or dflt.startswith("nextval(")),
                generated=(r["is_generated"] == "ALWAYS"),
                pk=(r["name"] in pk_names),
            ))

    if not info:
        raise RuntimeError(f"表 {table} 不存在或没有列（schema={schema}, table={tbl}）")

    pk_col = next((c["name"] for c in info if c["pk"] and c["auto"]), None)
    if pk_col is None:
        pk_col = next((c["name"] for c in info if c["auto"]), None)

    return info, pk_col


def build_column_lists(columns_info, pk_col):
    data_cols = [
        c["name"] for c in columns_info
        if not c["generated"] and not (pk_col and c["name"] == pk_col)
    ]
    all_cols = ([pk_col] if pk_col else []) + data_cols
    return data_cols, all_cols


# ==================== 取模板 / 生成 ====================
def fetch_templates(cursor, db_type, table, data_cols, order_col, limit):
    cols = ", ".join(quote(db_type, c) for c in data_cols)
    order_by = f"ORDER BY {quote(db_type, order_col)}" if order_col else ""
    cursor.execute(f"SELECT {cols} FROM {table} {order_by} LIMIT {limit}")
    rows = cursor.fetchall()
    if not rows:
        raise RuntimeError("表里没有模板数据，至少需要有 1 条")
    return rows


def build_rows(templates, data_cols, all_cols, pk_col,
               start_id, total, mode, cycle_col):
    base = dict(templates[0])
    n = len(templates)
    rows = []
    for i in range(total):
        new_id = start_id + i
        tpl = dict(templates[(new_id - 1) % n])
        if mode == "row_cycle":
            rec = dict(tpl)
        else:
            rec = dict(base)
            rec[cycle_col] = tpl[cycle_col]
        if pk_col:
            rec[pk_col] = new_id
        rows.append(tuple(rec[c] for c in all_cols))
    return rows, start_id + total - 1


# ==================== GUI ====================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SQL 批量造数工具")
        self.geometry("860x720")
        self.minsize(780, 620)
        self.q = queue.Queue()
        self.worker = None
        self.stop_event = threading.Event()
        self.log_fp = None
        self.inputs = []
        self._build_ui()
        self._load_conf()
        self.after(100, self._drain)

    # ---------- 构建界面 ----------
    def _build_ui(self):
        pad = dict(padx=8, pady=3)

        # 数据库连接
        box_db = ttk.LabelFrame(self, text="数据库连接")
        box_db.pack(fill=tk.X, padx=10, pady=(10, 4))

        row1 = ttk.Frame(box_db); row1.pack(fill=tk.X, **pad)
        ttk.Label(row1, text="类型").pack(side=tk.LEFT)
        self.v_db_type = tk.StringVar(value="mysql")
        cb = ttk.Combobox(row1, textvariable=self.v_db_type, width=12,
                          values=["mysql", "postgres"], state="readonly")
        cb.pack(side=tk.LEFT, padx=(4, 16))
        cb.bind("<<ComboboxSelected>>", self._on_db_type_change)

        ttk.Label(row1, text="主机").pack(side=tk.LEFT)
        self.v_host = tk.StringVar()
        e = ttk.Entry(row1, textvariable=self.v_host, width=20); e.pack(side=tk.LEFT, padx=(4, 16))
        self.inputs.append(e)

        ttk.Label(row1, text="端口").pack(side=tk.LEFT)
        self.v_port = tk.StringVar()
        e = ttk.Entry(row1, textvariable=self.v_port, width=8); e.pack(side=tk.LEFT, padx=4)
        self.inputs.append(e)

        row2 = ttk.Frame(box_db); row2.pack(fill=tk.X, **pad)
        ttk.Label(row2, text="数据库").pack(side=tk.LEFT)
        self.v_database = tk.StringVar()
        e = ttk.Entry(row2, textvariable=self.v_database, width=20); e.pack(side=tk.LEFT, padx=(4, 16))
        self.inputs.append(e)

        ttk.Label(row2, text="用户").pack(side=tk.LEFT)
        self.v_user = tk.StringVar()
        e = ttk.Entry(row2, textvariable=self.v_user, width=16); e.pack(side=tk.LEFT, padx=(4, 16))
        self.inputs.append(e)

        ttk.Label(row2, text="密码").pack(side=tk.LEFT)
        self.v_password = tk.StringVar()
        e = ttk.Entry(row2, textvariable=self.v_password, width=16, show="*"); e.pack(side=tk.LEFT, padx=4)
        self.inputs.append(e)

        row3 = ttk.Frame(box_db); row3.pack(fill=tk.X, **pad)
        ttk.Label(row3, text="连接超时(秒)").pack(side=tk.LEFT)
        self.v_timeout = tk.StringVar(value="5")
        e = ttk.Entry(row3, textvariable=self.v_timeout, width=8); e.pack(side=tk.LEFT, padx=4)
        self.inputs.append(e)

        # 任务参数
        box_task = ttk.LabelFrame(self, text="任务参数")
        box_task.pack(fill=tk.X, padx=10, pady=4)

        r1 = ttk.Frame(box_task); r1.pack(fill=tk.X, **pad)
        ttk.Label(r1, text="表名").pack(side=tk.LEFT)
        self.v_table = tk.StringVar()
        e = ttk.Entry(r1, textvariable=self.v_table, width=40); e.pack(side=tk.LEFT, padx=(4, 16))
        self.inputs.append(e)

        r2 = ttk.Frame(box_task); r2.pack(fill=tk.X, **pad)
        ttk.Label(r2, text="新增条数").pack(side=tk.LEFT)
        self.v_total = tk.StringVar(value="200000")
        e = ttk.Entry(r2, textvariable=self.v_total, width=10); e.pack(side=tk.LEFT, padx=(4, 16))
        self.inputs.append(e)

        ttk.Label(r2, text="模板数").pack(side=tk.LEFT)
        self.v_tpl = tk.StringVar(value="35")
        e = ttk.Entry(r2, textvariable=self.v_tpl, width=8); e.pack(side=tk.LEFT, padx=(4, 16))
        self.inputs.append(e)

        ttk.Label(r2, text="每批条数").pack(side=tk.LEFT)
        self.v_batch = tk.StringVar(value="1000")
        e = ttk.Entry(r2, textvariable=self.v_batch, width=8); e.pack(side=tk.LEFT, padx=4)
        self.inputs.append(e)

        r3 = ttk.Frame(box_task); r3.pack(fill=tk.X, **pad)
        ttk.Label(r3, text="模式").pack(side=tk.LEFT)
        self.v_mode = tk.StringVar(value="name_only")
        ttk.Combobox(r3, textvariable=self.v_mode, width=12,
                     values=["name_only", "row_cycle"],
                     state="readonly").pack(side=tk.LEFT, padx=(4, 16))

        ttk.Label(r3, text="循环列").pack(side=tk.LEFT)
        self.v_cycle = tk.StringVar(value="device_name")
        e = ttk.Entry(r3, textvariable=self.v_cycle, width=16); e.pack(side=tk.LEFT, padx=(4, 16))
        self.inputs.append(e)

        self.v_append = tk.BooleanVar(value=True)
        ttk.Checkbutton(r3, text="追加（不清空表）",
                        variable=self.v_append).pack(side=tk.LEFT)

        # 操作按钮
        box_btn = ttk.Frame(self)
        box_btn.pack(fill=tk.X, padx=10, pady=4)
        self.btn_test  = ttk.Button(box_btn, text="测试连接", command=self._test_conn)
        self.btn_start = ttk.Button(box_btn, text="开始生成", command=self._start)
        self.btn_stop  = ttk.Button(box_btn, text="停止", command=self._stop, state=tk.DISABLED)
        self.btn_save  = ttk.Button(box_btn, text="保存配置", command=self._save_conf)
        for b in (self.btn_test, self.btn_start, self.btn_stop, self.btn_save):
            b.pack(side=tk.LEFT, padx=4)

        # 进度
        box_prog = ttk.Frame(self)
        box_prog.pack(fill=tk.X, padx=10, pady=4)
        self.progress = ttk.Progressbar(box_prog, mode="determinate")
        self.progress.pack(fill=tk.X)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(box_prog, textvariable=self.status_var).pack(anchor=tk.W, pady=(2, 0))

        # 日志
        box_log = ttk.LabelFrame(self, text="日志")
        box_log.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 10))
        self.log_text = scrolledtext.ScrolledText(box_log, height=12, state=tk.DISABLED,
                                                  font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    # ---------- 控件状态 ----------
    def _set_running(self, running):
        st_run = tk.DISABLED if running else tk.NORMAL
        self.btn_start.configure(state=st_run)
        self.btn_test.configure(state=st_run)
        self.btn_save.configure(state=st_run)
        self.btn_stop.configure(state=tk.NORMAL if running else tk.DISABLED)

    # ---------- 日志 ----------
    def _log(self, msg, level="INFO"):
        line = f"{datetime.datetime.now():%H:%M:%S} [{level}] {msg}"
        self.q.put(("log", line))
        if self.log_fp:
            try:
                self.log_fp.write(line + "\n")
                self.log_fp.flush()
            except Exception:
                pass

    def _ui_log(self, line):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # ---------- 配置 ----------
    def _load_conf(self):
        cp = configparser.ConfigParser()
        defaults = {
            "db":  dict(db_type="mysql", host="192.168.1.134", port="3306",
                        database="base", user="root", password="mysql",
                        connect_timeout="5"),
            "task": dict(table="base.pre_alarm_history", total="200000",
                         tpl_limit="35", batch="1000", mode="name_only",
                         cycle_col="device_name", append="true"),
        }
        if os.path.exists(CONF_PATH):
            cp.read(CONF_PATH, encoding="utf-8")
            for sec, kv in defaults.items():
                if not cp.has_section(sec):
                    cp.add_section(sec)
                for k, v in kv.items():
                    if not cp.has_option(sec, k):
                        cp.set(sec, k, v)
        else:
            cp.read_dict(defaults)

        self.v_db_type.set(cp.get("db", "db_type"))
        self.v_host.set(cp.get("db", "host"))
        self.v_port.set(cp.get("db", "port"))
        self.v_database.set(cp.get("db", "database"))
        self.v_user.set(cp.get("db", "user"))
        self.v_password.set(cp.get("db", "password"))
        self.v_timeout.set(cp.get("db", "connect_timeout"))

        self.v_table.set(cp.get("task", "table"))
        self.v_total.set(cp.get("task", "total"))
        self.v_tpl.set(cp.get("task", "tpl_limit"))
        self.v_batch.set(cp.get("task", "batch"))
        self.v_mode.set(cp.get("task", "mode"))
        self.v_cycle.set(cp.get("task", "cycle_col"))
        self.v_append.set(cp.get("task", "append").lower() in ("1", "true", "yes", "y"))

    def _save_conf(self):
        cp = configparser.ConfigParser()
        cp["db"] = dict(
            db_type=self.v_db_type.get(), host=self.v_host.get().strip(),
            port=self.v_port.get().strip(), database=self.v_database.get().strip(),
            user=self.v_user.get().strip(), password=self.v_password.get(),
            connect_timeout=self.v_timeout.get().strip(),
        )
        cp["task"] = dict(
            table=self.v_table.get().strip(), total=self.v_total.get().strip(),
            tpl_limit=self.v_tpl.get().strip(), batch=self.v_batch.get().strip(),
            mode=self.v_mode.get(), cycle_col=self.v_cycle.get().strip(),
            append="true" if self.v_append.get() else "false",
        )
        with open(CONF_PATH, "w", encoding="utf-8") as f:
            cp.write(f)
        self._log(f"配置已保存到 {CONF_PATH}")

    def _on_db_type_change(self, _evt=None):
        if self.v_db_type.get() == "mysql" and self.v_port.get() in ("5432", ""):
            self.v_port.set("3306")
        elif self.v_db_type.get() == "postgres" and self.v_port.get() in ("3306", ""):
            self.v_port.set("5432")

    # ---------- 收集参数 ----------
    def _collect(self):
        d = dict(
            db_type=self.v_db_type.get(),
            host=self.v_host.get().strip(),
            port=int(self.v_port.get()),
            database=self.v_database.get().strip(),
            user=self.v_user.get().strip(),
            password=self.v_password.get(),
            connect_timeout=int(self.v_timeout.get()),
        )
        t = dict(
            table=self.v_table.get().strip(),
            total=int(self.v_total.get()),
            tpl_limit=int(self.v_tpl.get()),
            batch=int(self.v_batch.get()),
            mode=self.v_mode.get(),
            cycle_col=self.v_cycle.get().strip(),
            append=bool(self.v_append.get()),
        )
        return d, t

    # ---------- 测试连接 ----------
    def _test_conn(self):
        try:
            conf, _ = self._collect()
        except ValueError as ex:
            messagebox.showerror("参数错误", f"端口/超时必须是整数\n{ex}")
            return
        self._log(f"正在连接 {conf['host']}:{conf['port']} ...")

        def job():
            try:
                conn, _ = get_conn(conf.pop("db_type"), conf)
                conn.close()
                self._log("连接成功")
            except Exception as ex:
                self._log(f"连接失败: {ex}", "ERROR")

        threading.Thread(target=job, daemon=True).start()

    # ---------- 开始 / 停止 ----------
    def _start(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            conf, task = self._collect()
        except ValueError as ex:
            messagebox.showerror("参数错误", f"数值字段必须是整数\n{ex}")
            return

        if not task["append"]:
            if not messagebox.askyesno(
                "确认清空",
                f"未勾选『追加』，将执行 TRUNCATE 清空整张表：\n\n{task['table']}\n\n"
                f"该操作不可回滚，确定继续？"):
                return

        # 打开日志文件
        fn = os.path.join(LOG_DIR, f"run_{datetime.datetime.now():%Y%m%d_%H%M%S}.log")
        try:
            self.log_fp = open(fn, "w", encoding="utf-8")
        except Exception:
            self.log_fp = None

        self.stop_event.clear()
        self.progress.configure(maximum=max(task["total"], 1), value=0)
        self.status_var.set("运行中...")
        self._set_running(True)

        self.worker = threading.Thread(target=self._run_job,
                                       args=(conf, task), daemon=True)
        self.worker.start()

    def _stop(self):
        self.stop_event.set()
        self._log("已发送停止信号，等待当前批完成...", "WARN")

    # ---------- 后台任务 ----------
    def _run_job(self, conf, task):
        db_type = conf.pop("db_type")
        table = task["table"]
        conn = None
        try:
            self._log(f"连接 {conf['host']}:{conf['port']} / {conf['database']}")
            conn, cursor_cls = get_conn(db_type, conf)
            cursor = conn.cursor(cursor_cls)

            # 1) 结构自省
            columns_info, pk_col = get_table_columns(
                cursor, db_type, table, conf.get("database"))
            data_cols, all_cols = build_column_lists(columns_info, pk_col)
            self._log(f"表结构: 共 {len(columns_info)} 列，自增主键 = {pk_col or '无'}")
            self._log(f"写入列({len(all_cols)}): {', '.join(all_cols)}")

            if task["mode"] == "name_only" and task["cycle_col"] not in data_cols:
                raise RuntimeError(
                    f"循环列 {task['cycle_col']} 不在写入列中，请检查表名或列名")

            # 2) 起点
            if task["append"]:
                if pk_col:
                    cursor.execute(
                        f"SELECT COALESCE(MAX({quote(db_type, pk_col)}), 0) AS m FROM {table}")
                    start_id = cursor.fetchone()["m"] + 1
                else:
                    start_id = 1
            else:
                cursor.execute(f"TRUNCATE TABLE {table}")
                self._log(f"已清空表 {table}")
                start_id = 1
            if pk_col:
                self._log(f"起点: {pk_col} = {start_id}")

            # 3) 模板
            order_col = pk_col or (data_cols[0] if data_cols else None)
            templates = fetch_templates(cursor, db_type, table, data_cols,
                                        order_col, task["tpl_limit"])
            self._log(f"取到模板 {len(templates)} 条")

            # 4) 生成
            rows, max_id = build_rows(
                templates, data_cols, all_cols, pk_col,
                start_id, task["total"], task["mode"], task["cycle_col"])
            self._log(f"生成 {len(rows)} 条，"
                      + (f"{pk_col} {start_id}~{max_id}" if pk_col else ""))

            # 5) 分批写入（每批 commit，支持中途停止保留已完成）
            placeholders = ", ".join(["%s"] * len(all_cols))
            insert_sql = (
                f"INSERT INTO {table} "
                f"({', '.join(quote(db_type, c) for c in all_cols)}) "
                f"VALUES ({placeholders})"
            )
            done = 0
            batch = task["batch"]
            for i in range(0, len(rows), batch):
                if self.stop_event.is_set():
                    self._log(f"已停止，已提交 {done} 条", "WARN")
                    break
                chunk = rows[i:i + batch]
                cursor.executemany(insert_sql, chunk)
                conn.commit()
                done += len(chunk)
                self.q.put(("progress", done, len(rows)))

            # 6) 序列重置
            if pk_col and done > 0:
                if db_type == "postgres":
                    cursor.execute(
                        "SELECT setval(pg_get_serial_sequence(%s, %s), %s, true)",
                        (table, pk_col, max_id))
                else:
                    cursor.execute(
                        f"ALTER TABLE {table} AUTO_INCREMENT = {max_id + 1}")
                conn.commit()

            # 7) 校验
            cursor.execute(f"SELECT COUNT(*) AS c FROM {table}")
            total_now = cursor.fetchone()["c"]
            self._log(f"表内总条数: {total_now}")
            if task["cycle_col"] in data_cols:
                cursor.execute(
                    f"SELECT COUNT(DISTINCT {quote(db_type, task['cycle_col'])}) AS c FROM {table}")
                self._log(f"不同 {task['cycle_col']} 数: {cursor.fetchone()['c']}")

            cursor.close()
            self.q.put(("done", f"完成，本次插入 {done} 条"))

        except Exception as ex:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self._log(f"失败: {ex}", "ERROR")
            self.q.put(("done", f"失败: {ex}"))
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # ---------- 主线程轮询队列 ----------
    def _drain(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._ui_log(msg[1])
                elif kind == "progress":
                    done, total = msg[1], msg[2]
                    self.progress.configure(value=done)
                    pct = done * 100 // total if total else 0
                    self.status_var.set(f"{done}/{total} ({pct}%)")
                elif kind == "done":
                    self._ui_log(msg[1])
                    self.status_var.set(msg[1])
                    self._set_running(False)
                    if self.log_fp:
                        try:
                            self.log_fp.close()
                        except Exception:
                            pass
                        self.log_fp = None
        except queue.Empty:
            pass
        self.after(100, self._drain)


# ==================== 入口 ====================
def main():
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = App()
    try:
        f = tkfont.nametofont("TkDefaultFont")
        f.configure(family="Microsoft YaHei UI", size=9)
    except Exception:
        pass
    app.mainloop()


if __name__ == "__main__":
    main()