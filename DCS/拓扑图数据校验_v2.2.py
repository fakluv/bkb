# -*- coding: utf-8 -*-
"""
拓扑表 ↔ API 数据比对工具 v2.6.2 轻量加速版（无日志落盘）

相对 v2.6.1：
  - 新增 IP 格式校验（IPv4）：Excel / JSON 任一侧 IP 格式非法 → 记为「IP格式错误」
  - 新增状态 ST_INVALID_IP，独立过滤项、独立底色、计入失败统计
  - 其余保持 v2.6.1：去掉日志落盘、保留 UI 日志队列、端口重复检测
"""
import os
import sys
import queue
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime


def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = _app_dir()


def _show_fatal(msg, title="启动失败"):
    """无控制台也能弹框提示的兜底"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, str(msg), str(title), 0x10)  # MB_ICONERROR
    except Exception:
        pass


# ============================================================
# 1. 依赖导入（失败要可见、可提示）
# ============================================================
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext
except Exception as e:
    _show_fatal(f"tkinter 不可用：\n{e}\n\n请确认 Python 安装时勾选了 tcl/tk。")
    raise

try:
    # 轻量版：
    #   - 不用 pandas/numpy（Excel 用 openpyxl）
    #   - HTTP 用 requests（比 urllib.request 快几倍，内网高频请求场景尤为明显）
    import requests
    import pymysql
    from openpyxl import load_workbook, Workbook
except Exception as e:
    _show_fatal(
        f"依赖库导入失败：\n{e}\n\n"
        f"当前轻量版只需要：requests、pymysql、openpyxl。\n"
        f"请先执行：pip install requests pymysql openpyxl"
    )
    raise

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

import json
import csv


# ============================================================
# 2. 工具函数
# ============================================================
def clean_val(v):
    if v is None:
        return ""
    if isinstance(v, float):
        if v != v:  # NaN
            return ""
        if v == int(v):
            return str(int(v))
        return str(v)
    s = str(v).strip()
    if s.lower() in ("nan", "none", "nat"):
        return ""
    if s.endswith(".0") and s[:-2].replace("-", "").isdigit():
        s = s[:-2]
    return s


def is_valid_ipv4(ip):
    """★ 新增：严格校验 IPv4 地址格式。

    规则：
      - 必须是 4 段，以 "." 分隔
      - 每段只能是纯数字，且 0 <= n <= 255
      - 空字符串返回 False（由调用方决定是否视为“未填写”）
    注意：0.0.0.0 属于合法 IPv4 格式，比对阶段会单独特殊处理。
    """
    if ip is None:
        return False
    s = str(ip).strip()
    if not s:
        return False
    parts = s.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit():
            return False
        if len(p) > 1 and p[0] == "0":
            # 拒绝前导零（如 192.168.01.1），避免与八进制/字符串比较混淆
            return False
        if not (0 <= int(p) <= 255):
            return False
    return True


def build_api_url(base, station_no):
    base = (base or "").strip()
    if not base:
        return ""
    if base.endswith("stationNo="):
        return f"{base}{station_no}"
    if base.endswith("stationNo"):
        return f"{base}={station_no}"
    if "getDcsSwitchLink" in base:
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}stationNo={station_no}"
    base = base.rstrip("/")
    return f"{base}/bdms/isim-backend/isim/indoorDevice/getDcsSwitchLink?stationNo={station_no}"


# 状态常量
ST_SUCCESS       = "success"
ST_MISMATCH      = "mismatch"
ST_MISSING_JSON  = "missing_json"
ST_MISSING_EXCEL = "missing_excel"
ST_ERROR         = "error"
ST_DUPLICATE     = "duplicate"
ST_INVALID_IP    = "invalid_ip"   # ★ 新增

STATUS_LABEL = {
    ST_SUCCESS: "一致",
    ST_MISMATCH: "值不一致",
    ST_MISSING_JSON: "JSON 缺失",
    ST_MISSING_EXCEL: "Excel 缺失",
    ST_ERROR: "错误",
    ST_DUPLICATE: "端口重复",
    ST_INVALID_IP: "IP格式错误",   # ★ 新增
}
FAIL_STATUSES = {ST_MISMATCH, ST_MISSING_JSON, ST_MISSING_EXCEL,
                 ST_ERROR, ST_DUPLICATE, ST_INVALID_IP}   # ★ 新增

# ============================================================
# 3. 主界面
# ============================================================
class NMSCompareApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DCS拓扑表 ↔ API 数据比对工具 v2.2")
        self.root.geometry("1560x980")
        self.set_window_icon()

        self.base_url_var = tk.StringVar(
            value="http://192.168.1.237/bdms/isim-backend/isim/indoorDevice/getDcsSwitchLink?stationNo=")
        self.excel_path_var = tk.StringVar()
        self.db_host_var = tk.StringVar(value="192.168.1.237")
        self.db_port_var = tk.StringVar(value="3306")
        self.db_name_var = tk.StringVar(value="base")
        self.db_user_var = tk.StringVar(value="root")
        self.db_pass_var = tk.StringVar(value="mysql")
        self.status_var = tk.StringVar(value="就绪")

        self.show_success_var        = tk.BooleanVar(value=True)
        self.show_fail_var           = tk.BooleanVar(value=True)
        self.show_mismatch_var       = tk.BooleanVar(value=True)
        self.show_missing_json_var   = tk.BooleanVar(value=True)
        self.show_missing_excel_var  = tk.BooleanVar(value=True)
        self.show_error_var          = tk.BooleanVar(value=True)
        self.show_duplicate_var      = tk.BooleanVar(value=True)
        self.show_invalid_ip_var     = tk.BooleanVar(value=True)   # ★ 新增

        self.stations = []
        self.excel_data = {}
        # 比对性能参数：API 请求彼此独立，使用线程池并发请求。
        # 内网环境通常 6~12 个并发比较合适，默认 8。
        self.compare_workers = 8
        self._excel_station_index = {}
        # ★ 每个 sheet 下检测到的重复端口键集合 {(switch, port), ...}
        self._excel_dups = {}
        # 每线程一个 requests.Session（复用 TCP 连接；Session 本身非线程安全）
        self._thread_local = threading.local()

        self.results = []
        self.visible_results = []
        self._running = False

        # UI 日志队列：工作线程往里丢，主线程每 200ms 批量取出刷 UI
        self._ui_log_queue = queue.Queue(maxsize=20000)

        self._build_ui()

        # 启动 UI 日志刷新循环
        self.root.after(200, self._drain_ui_log)

    # ---------- 线程安全 UI 调度 ----------
    def _ui(self, fn, *args, **kwargs):
        """从任意线程安全地把 UI 操作调度到主线程。"""
        try:
            self.root.after(0, lambda: fn(*args, **kwargs))
        except Exception:
            # 窗口可能已销毁
            pass

    def _set_status(self, text):
        self._ui(self.status_var.set, text)

    def _set_progress(self, value=None, maximum=None):
        def _do():
            try:
                if maximum is not None:
                    self.progress.configure(maximum=maximum)
                if value is not None:
                    self.progress.configure(value=value)
            except Exception:
                pass
        self._ui(_do)

    # ---------- HTTP Session（线程本地） ----------
    def _get_session(self):
        s = getattr(self._thread_local, "session", None)
        if s is None:
            s = requests.Session()
            s.verify = False
            s.headers.update({"User-Agent": "TopologyCheck/2.6.2"})
            self._thread_local.session = s
        return s

    # ---------- UI ----------
    def set_window_icon(self):
        """设置窗口左上角图标（兼容 onefile / onedir）"""
        candidates = []
        if hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, "Cjdowner-Cryptocurrency-Verify.ico"))
        candidates.append(os.path.join(APP_DIR, "Cjdowner-Cryptocurrency-Verify.ico"))
        candidates.append(os.path.join(os.path.abspath("."), "Cjdowner-Cryptocurrency-Verify.ico"))

        for p in candidates:
            try:
                if os.path.exists(p):
                    self.root.iconbitmap(p)
                    return
            except Exception:
                pass

    def _build_ui(self):
        # ===== 配置区 =====
        top = ttk.LabelFrame(self.root, text="配置", padding=10)
        top.pack(fill="x", padx=10, pady=5)
        top.columnconfigure(1, weight=1)
        top.columnconfigure(3, weight=1)

        ttk.Label(top, text="API 基础地址:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(top, textvariable=self.base_url_var).grid(
            row=0, column=1, columnspan=3, sticky="we", padx=5, pady=3)

        ttk.Label(top, text="拓扑表 Excel:").grid(row=1, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(top, textvariable=self.excel_path_var).grid(
            row=1, column=1, columnspan=2, sticky="we", padx=5, pady=3)
        ttk.Button(top, text="浏览...", command=self._browse_excel).grid(
            row=1, column=3, sticky="e", padx=5, pady=3)

        ttk.Label(top, text="数据库主机:").grid(row=2, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(top, textvariable=self.db_host_var, width=20).grid(
            row=2, column=1, sticky="w", padx=5, pady=3)
        ttk.Label(top, text="端口:").grid(row=2, column=2, sticky="e", padx=5, pady=3)
        ttk.Entry(top, textvariable=self.db_port_var, width=10).grid(
            row=2, column=3, sticky="w", padx=5, pady=3)

        ttk.Label(top, text="数据库名:").grid(row=3, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(top, textvariable=self.db_name_var, width=20).grid(
            row=3, column=1, sticky="w", padx=5, pady=3)
        ttk.Label(top, text="用户名:").grid(row=3, column=2, sticky="e", padx=5, pady=3)
        ttk.Entry(top, textvariable=self.db_user_var, width=20).grid(
            row=3, column=3, sticky="w", padx=5, pady=3)

        ttk.Label(top, text="密码:").grid(row=4, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(top, textvariable=self.db_pass_var, width=20, show="*").grid(
            row=4, column=1, sticky="w", padx=5, pady=3)

        # ===== 按钮 =====
        btn = ttk.Frame(self.root)
        btn.pack(fill="x", padx=10, pady=5)
        ttk.Button(btn, text="① 加载站点",   command=self._load_stations_thread).pack(side="left", padx=5)
        ttk.Button(btn, text="② 加载拓扑表", command=self._load_excel_thread).pack(side="left", padx=5)
        ttk.Button(btn, text="③ 开始比对",   command=self._start_compare_thread).pack(side="left", padx=5)
        ttk.Button(btn, text="导出当前显示", command=self._export_results).pack(side="left", padx=5)
        ttk.Button(btn, text="清空日志",     command=self._clear_log).pack(side="left", padx=5)

        # ===== 显示过滤勾选区 =====
        filt = ttk.LabelFrame(self.root, text="显示过滤（影响界面显示与导出）", padding=6)
        filt.pack(fill="x", padx=10, pady=3)

        ttk.Checkbutton(filt, text="显示成功（一致）",
                        variable=self.show_success_var,
                        command=self._refresh_view).pack(side="left", padx=8)
        ttk.Separator(filt, orient="vertical").pack(side="left", fill="y", padx=5)
        ttk.Checkbutton(filt, text="显示失败",
                        variable=self.show_fail_var,
                        command=self._refresh_view).pack(side="left", padx=8)
        ttk.Checkbutton(filt, text="└ 值不一致",
                        variable=self.show_mismatch_var,
                        command=self._refresh_view).pack(side="left", padx=8)
        ttk.Checkbutton(filt, text="└ JSON 缺失",
                        variable=self.show_missing_json_var,
                        command=self._refresh_view).pack(side="left", padx=8)
        ttk.Checkbutton(filt, text="└ Excel 缺失",
                        variable=self.show_missing_excel_var,
                        command=self._refresh_view).pack(side="left", padx=8)
        ttk.Checkbutton(filt, text="└ 错误",
                        variable=self.show_error_var,
                        command=self._refresh_view).pack(side="left", padx=8)
        ttk.Checkbutton(filt, text="└ 端口重复",
                        variable=self.show_duplicate_var,
                        command=self._refresh_view).pack(side="left", padx=8)
        # ★ 新增：IP 格式错误
        ttk.Checkbutton(filt, text="└ IP格式错误",
                        variable=self.show_invalid_ip_var,
                        command=self._refresh_view).pack(side="left", padx=8)

        ttk.Button(filt, text="全选",   command=self._select_all_filters).pack(side="right", padx=3)
        ttk.Button(filt, text="仅失败", command=self._only_fail_filters).pack(side="right", padx=3)
        ttk.Button(filt, text="仅成功", command=self._only_success_filters).pack(side="right", padx=3)

        # ===== 进度 =====
        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=(5, 0))
        ttk.Label(self.root, textvariable=self.status_var).pack(anchor="w", padx=10)

        # ===== 标签页 =====
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=10, pady=5)

        f1 = ttk.Frame(nb); nb.add(f1, text="日志")
        self.log_text = scrolledtext.ScrolledText(f1, wrap="word")
        self.log_text.pack(fill="both", expand=True)

        f2 = ttk.Frame(nb); nb.add(f2, text="站点列表")
        self.station_tree = ttk.Treeview(f2, columns=("no", "name"), show="headings")
        self.station_tree.heading("no", text="站点编号")
        self.station_tree.heading("name", text="站点名称")
        self.station_tree.column("no", width=140)
        self.station_tree.column("name", width=320)
        self.station_tree.pack(fill="both", expand=True)

        f3 = ttk.Frame(nb); nb.add(f3, text="比对结果")
        rcols = ("station", "switch", "port", "type", "excel", "json", "status")
        headers = ["站点", "交换机", "端口", "对比项", "Excel 值", "JSON 值", "结果"]
        widths  = [110, 200, 60, 100, 260, 260, 100]
        self.result_tree = ttk.Treeview(f3, columns=rcols, show="headings")
        for c, h, w in zip(rcols, headers, widths):
            self.result_tree.heading(c, text=h)
            self.result_tree.column(c, width=w, anchor="w")
        vsb = ttk.Scrollbar(f3, orient="vertical", command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.result_tree.pack(fill="both", expand=True)

        self.result_tree.tag_configure(ST_SUCCESS,       background="#e6ffe6")
        self.result_tree.tag_configure(ST_MISMATCH,      background="#ffd9d9")
        self.result_tree.tag_configure(ST_MISSING_JSON,  background="#ffe9b3")
        self.result_tree.tag_configure(ST_MISSING_EXCEL, background="#d9e6ff")
        self.result_tree.tag_configure(ST_ERROR,         background="#f0c0f0")
        # ★ 端口重复：鲜红底 + 白字
        self.result_tree.tag_configure(ST_DUPLICATE,     background="#ff4d4d",
                                                         foreground="#ffffff")
        # ★ IP 格式错误：橙色底 + 深棕字（区别于端口重复的鲜红）
        self.result_tree.tag_configure(ST_INVALID_IP,    background="#ffc000",
                                                         foreground="#4d2600")

        self.summary_var = tk.StringVar(value="比对结果：尚未执行")
        ttk.Label(self.root, textvariable=self.summary_var).pack(anchor="w", padx=10, pady=(0, 5))

    # ---------- 过滤 ----------
    def _select_all_filters(self):
        for v in (self.show_success_var, self.show_fail_var, self.show_mismatch_var,
                  self.show_missing_json_var, self.show_missing_excel_var,
                  self.show_error_var, self.show_duplicate_var,
                  self.show_invalid_ip_var):   # ★ 新增
            v.set(True)
        self._refresh_view()

    def _only_fail_filters(self):
        self.show_success_var.set(False)
        self.show_fail_var.set(True)
        self.show_mismatch_var.set(True)
        self.show_missing_json_var.set(True)
        self.show_missing_excel_var.set(True)
        self.show_error_var.set(True)
        self.show_duplicate_var.set(True)
        self.show_invalid_ip_var.set(True)   # ★ 新增
        self._refresh_view()

    def _only_success_filters(self):
        self.show_success_var.set(True)
        self.show_fail_var.set(False)
        self._refresh_view()

    def _pass_filter(self, status):
        if status == ST_SUCCESS:
            return self.show_success_var.get()
        if not self.show_fail_var.get():
            return False
        if status == ST_MISMATCH:       return self.show_mismatch_var.get()
        if status == ST_MISSING_JSON:   return self.show_missing_json_var.get()
        if status == ST_MISSING_EXCEL:  return self.show_missing_excel_var.get()
        if status == ST_ERROR:          return self.show_error_var.get()
        if status == ST_DUPLICATE:      return self.show_duplicate_var.get()
        if status == ST_INVALID_IP:     return self.show_invalid_ip_var.get()   # ★ 新增
        return True

    def _refresh_view(self):
        try:
            for i in self.result_tree.get_children():
                self.result_tree.delete(i)

            self.visible_results = []
            for r in self.results:
                if not self._pass_filter(r.get("status", ST_SUCCESS)):
                    continue
                self.visible_results.append(r)
                tag = r.get("status", ST_SUCCESS)
                self.result_tree.insert(
                    "", "end",
                    values=(r["station"], r["switch"], r.get("port", ""),
                            r["type"], r["excel"], r["json"],
                            STATUS_LABEL.get(tag, tag)),
                    tags=(tag,))

            cnt = {ST_SUCCESS: 0, ST_MISMATCH: 0, ST_MISSING_JSON: 0,
                   ST_MISSING_EXCEL: 0, ST_ERROR: 0, ST_DUPLICATE: 0,
                   ST_INVALID_IP: 0}   # ★ 新增
            for r in self.results:
                s = r.get("status", ST_SUCCESS)
                cnt[s] = cnt.get(s, 0) + 1

            total = len(self.results)
            fail_total = sum(cnt[s] for s in FAIL_STATUSES)
            self.summary_var.set(
                f"全部 {total} 条  |  一致 {cnt[ST_SUCCESS]}  |  失败 {fail_total}  "
                f"（不一致 {cnt[ST_MISMATCH]}，JSON缺失 {cnt[ST_MISSING_JSON]}，"
                f"Excel缺失 {cnt[ST_MISSING_EXCEL]}，端口重复 {cnt[ST_DUPLICATE]}，"
                f"IP格式错误 {cnt[ST_INVALID_IP]}，"
                f"错误 {cnt[ST_ERROR]}）  "
                f"|  当前显示 {len(self.visible_results)} 条"
            )
        except Exception:
            pass

    # ---------- 日志（仅 UI 文本框，不落盘） ----------
    def _log(self, msg):
        """线程安全，可从任意线程调用。仅入队，由主线程定期取出刷新。"""
        try:
            self._ui_log_queue.put_nowait(msg)
        except Exception:
            pass

    def _drain_ui_log(self):
        """在主线程中运行：批量取日志，更新 UI 文本框。"""
        batch = []
        try:
            while True:
                try:
                    batch.append(self._ui_log_queue.get_nowait())
                except queue.Empty:
                    break
        except Exception:
            pass

        if batch:
            ts = datetime.now().strftime("%H:%M:%S")
            text = "".join(f"[{ts}] {m}\n" for m in batch)
            try:
                self.log_text.insert("end", text)
                self.log_text.see("end")
            except Exception:
                pass

        try:
            self.root.after(200, self._drain_ui_log)
        except Exception:
            pass

    def _clear_log(self):
        try:
            self.log_text.delete("1.0", "end")
        except Exception:
            pass

    def _browse_excel(self):
        p = filedialog.askopenfilename(
            title="选择拓扑表 Excel",
            filetypes=[("Excel 文件", "*.xlsx")])
        if p:
            self.excel_path_var.set(p)
            self._load_excel_thread()

    # ---------- 站点 ----------
    def _load_stations_thread(self):
        if self._running:
            messagebox.showwarning("提示", "当前有任务正在执行")
            return
        threading.Thread(target=self._load_stations, daemon=True).start()

    def _load_stations(self):
        self._running = True
        try:
            self._set_status("正在读取站点...")
            self._log("连接数据库读取 dic_station ...")
            conn = pymysql.connect(
                host=self.db_host_var.get().strip(),
                port=int(self.db_port_var.get().strip() or "3306"),
                user=self.db_user_var.get().strip(),
                password=self.db_pass_var.get().strip(),
                database=self.db_name_var.get().strip(),
                charset="utf8mb4",
                connect_timeout=10,
            )
            try:
                with conn.cursor() as cur:
                    cur.execute("select station_no, station_name from dic_station")
                    rows = cur.fetchall()
            finally:
                conn.close()

            self.stations = [(str(r[0]), str(r[1])) for r in rows]
            self._log(f"共读取到 {len(self.stations)} 个站点")

            def _fill():
                try:
                    for i in self.station_tree.get_children():
                        self.station_tree.delete(i)
                    for no, name in self.stations:
                        self.station_tree.insert("", "end", values=(no, name))
                except Exception:
                    pass
            self._ui(_fill)
            self._set_status(f"站点加载完成：{len(self.stations)} 个")
        except Exception as e:
            self._log(f"读取站点失败：{e}")
            self._ui(messagebox.showerror, "数据库错误", str(e))
        finally:
            self._running = False

    # ---------- 拓扑表 ----------
    def _load_excel_thread(self):
        path = self.excel_path_var.get().strip()
        if not path:
            p = filedialog.askopenfilename(
                title="选择拓扑表 Excel",
                filetypes=[("Excel 文件", "*.xlsx")])
            if not p:
                return
            self.excel_path_var.set(p)
            path = p
        if not os.path.exists(path):
            messagebox.showerror("错误", f"文件不存在：{path}")
            return
        threading.Thread(target=self._load_excel, args=(path,), daemon=True).start()

    def _load_excel(self, path):
        self._running = True
        try:
            self._set_status("正在读取拓扑表...")
            self._log(f"读取拓扑表：{path}")
            if not path.lower().endswith(".xlsx"):
                raise ValueError("轻量版仅支持 .xlsx 拓扑表，请将 .xls 另存为 .xlsx 后再加载。")

            wb = load_workbook(path, read_only=True, data_only=True)
            excel_data = {}
            # ★ 记录每个 sheet 中检测到的重复端口键
            excel_dups = {}
            # ★ 记录每个 sheet 中检测到的格式非法 IP（用于日志提示）
            excel_bad_ip = {}

            try:
                for ws in wb.worksheets:
                    sheet_name = ws.title.strip()
                    if sheet_name in ("设备类型状态表", "NMSConfig"):
                        continue

                    ports = {}
                    dups = set()   # ★ 本 sheet 的重复键集合
                    bad_ips = set()  # ★ 本 sheet 的非法 IP
                    for row in ws.iter_rows(values_only=True):
                        if len(row) < 9:
                            continue

                        sw1 = clean_val(row[0]); ip1 = clean_val(row[1])
                        p1  = clean_val(row[2]); c1  = clean_val(row[3])
                        dev = clean_val(row[4]); c2  = clean_val(row[5])
                        sw2 = clean_val(row[6]); ip2 = clean_val(row[7])
                        p2  = clean_val(row[8])

                        if sw1 == "交换机1":
                            continue

                        # ★ 交换机1侧
                        if c1 == "1" and sw1 and p1:
                            key = (sw1, p1)
                            if key in ports:
                                dups.add(key)   # 已存在 → 重复
                            else:
                                ports[key] = {"dev": dev, "ip": ip1}
                            # ★ IP 格式校验（空值跳过，交由比对阶段处理）
                            if ip1 and not is_valid_ipv4(ip1):
                                bad_ips.add((sw1, p1, ip1))

                        # ★ 交换机2侧
                        if c2 == "1" and sw2 and p2:
                            key = (sw2, p2)
                            if key in ports:
                                dups.add(key)
                            else:
                                ports[key] = {"dev": dev, "ip": ip2}
                            if ip2 and not is_valid_ipv4(ip2):
                                bad_ips.add((sw2, p2, ip2))

                    if ports:
                        excel_data[sheet_name] = ports
                        if dups:
                            excel_dups[sheet_name] = dups
                            self._log(f"  · {sheet_name}：{len(ports)} 个端口，"
                                      f"发现 {len(dups)} 个重复端口")
                        else:
                            self._log(f"  · {sheet_name}：{len(ports)} 个端口")
                        if bad_ips:
                            excel_bad_ip[sheet_name] = bad_ips
                            self._log(f"    ⚠ {sheet_name}：发现 {len(bad_ips)} 个"
                                      f"格式非法的 IP（将在比对结果中标记为「IP格式错误」）")
            finally:
                wb.close()

            self.excel_data = excel_data

            # 预计算站点匹配索引，避免比对每个站点时反复遍历全部 Excel sheet。
            index = {}
            dup_index = {}
            for k, v in excel_data.items():
                k0 = k.strip()
                k_alt = k0.replace("站", "")
                index[k0] = v
                index[k_alt] = v
                d = excel_dups.get(k)
                if d:
                    dup_index[k0] = d
                    dup_index[k_alt] = d
            self._excel_station_index = index
            self._excel_dups = dup_index

            dup_total = sum(len(d) for d in excel_dups.values())
            bad_ip_total = sum(len(d) for d in excel_bad_ip.values())

            msg_parts = [f"共 {len(excel_data)} 个站点"]
            if dup_total:
                msg_parts.append(f"{len(excel_dups)} 个 sheet 存在重复端口（合计 {dup_total} 个）")
            if bad_ip_total:
                msg_parts.append(f"{len(excel_bad_ip)} 个 sheet 存在非法 IP（合计 {bad_ip_total} 个）")

            summary = "，".join(msg_parts)
            self._log(f"拓扑表加载完成：{summary}")
            self._set_status(f"拓扑表加载完成：{summary}")
        except Exception as e:
            self._log(f"读取拓扑表失败：{e}")
            self._ui(messagebox.showerror, "Excel 错误", str(e))
        finally:
            self._running = False

    # ---------- 比对 ----------
    def _start_compare_thread(self):
        if self._running:
            messagebox.showwarning("提示", "当前有任务正在执行")
            return
        if not self.stations:
            messagebox.showwarning("提示", "请先加载站点")
            return
        if not self.excel_data:
            messagebox.showwarning("提示", "请先加载拓扑表")
            return
        if not self.base_url_var.get().strip():
            messagebox.showwarning("提示", "请填写 API 基础地址")
            return
        threading.Thread(target=self._compare_all, daemon=True).start()

    def _compare_all(self):
        self._running = True
        self.results = []
        total = len(self.stations)
        self._set_progress(value=0, maximum=total)

        # 关键：在派发工作线程之前一次性读取 Tk 变量。
        # 工作线程绝不能再调用 self.base_url_var.get()。
        base_url = self.base_url_var.get().strip()

        def _clear_tree():
            try:
                for i in self.result_tree.get_children():
                    self.result_tree.delete(i)
            except Exception:
                pass
        self._ui(_clear_tree)

        try:
            self._log(f"开始比对，共 {total} 个站点；并发数 {self.compare_workers}")

            completed = 0

            def worker(item):
                no, name = item
                try:
                    res, log_msg = self._compare_one_station(no, name, base_url)
                    return no, name, res, log_msg, None
                except Exception as e:
                    return no, name, [{
                        "station": name, "switch": "", "port": "",
                        "type": "异常", "excel": "", "json": str(e),
                        "status": ST_ERROR,
                    }], f"[{name}] 比对异常：{e}", e

            workers = min(max(1, self.compare_workers), max(1, total))

            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="compare") as executor:
                futures = [executor.submit(worker, item) for item in self.stations]

                for future in as_completed(futures):
                    no, name, res, log_msg, exc = future.result()
                    self.results.extend(res)
                    completed += 1

                    # 日志只入队，不刷 Tk
                    if log_msg:
                        self._log(log_msg)

                    if exc is not None:
                        self._log(f"[{name}] 比对异常：{exc}")

                    # 降频更新进度/状态栏，避免大量 root.after 排队
                    if completed == total or completed == 1 or completed % 5 == 0:
                        self._set_progress(value=completed)
                        self._set_status(f"正在比对 [{completed}/{total}]，并发 {workers}")

            self._ui(self._refresh_view)
            self._log(f"比对完成，全部记录 {len(self.results)} 条")
            self._set_status(f"比对完成：{total} 个站点，全部记录 {len(self.results)} 条")

        except Exception as e:
            self._log(f"批量比对异常：{e}")
            self._ui(messagebox.showerror, "比对错误", str(e))
        finally:
            self._running = False

    def _find_excel_station(self, station_name):
        # 第一阶段 O(1) 精确/去“站”匹配。
        index = self._excel_station_index
        if station_name in index:
            return station_name, index[station_name]

        alt = station_name.replace("站", "")
        if alt in index:
            return alt, index[alt]

        # 仅在确实没有精确匹配时才执行模糊匹配。
        for k, v in self.excel_data.items():
            kk = k.replace("站", "")
            if kk and (kk in alt or alt in kk):
                return k, v
        return None, None

    def _compare_one_station(self, station_no, station_name, base_url):
        """纯逻辑：发请求 + 解析 + 比对。
        不碰 Tk、不写文件。返回 (results, log_msg)。"""
        results = []
        url = build_api_url(base_url, station_no)

        # ---- 调接口 ----
        try:
            session = self._get_session()
            resp = session.get(url, timeout=30)
            resp.encoding = "utf-8"
            data = resp.json()
        except Exception as e:
            results.append({
                "station": station_name, "switch": "", "port": "", "type": "API请求",
                "excel": "", "json": f"请求失败: {e}", "status": ST_ERROR,
            })
            return results, ""

        if data.get("code") != 200:
            results.append({
                "station": station_name, "switch": "", "port": "", "type": "API返回",
                "excel": "", "json": f"code={data.get('code')} msg={data.get('msg')}",
                "status": ST_ERROR,
            })
            return results, ""

        # ---- JSON 端口映射（★ 同时检测重复） ----
        json_ports = {}
        json_dups = set()
        for group in (data.get("data") or []):
            for child in (group.get("child") or []):
                dev_name = child.get("name", "")
                link_to = str(child.get("linkTo", ""))

                if "1" in link_to:
                    sw = clean_val(child.get("switch1Name", ""))
                    p  = clean_val(child.get("port1", ""))
                    ip = clean_val(child.get("ip1", ""))
                    if sw and p:
                        key = (sw, p)
                        if key in json_ports:
                            json_dups.add(key)
                        else:
                            json_ports[key] = {"dev": dev_name, "ip": ip}

                if "2" in link_to:
                    sw = clean_val(child.get("switch2Name", ""))
                    p  = clean_val(child.get("port2", ""))
                    ip = clean_val(child.get("ip2", ""))
                    if sw and p:
                        key = (sw, p)
                        if key in json_ports:
                            json_dups.add(key)
                        else:
                            json_ports[key] = {"dev": dev_name, "ip": ip}

        # ---- 匹配 Excel 站点 ----
        matched_name, excel_ports = self._find_excel_station(station_name)
        excel_dups = self._excel_dups.get(matched_name, set()) if matched_name else set()

        if excel_ports is None:
            results.append({
                "station": station_name, "switch": "", "port": "", "type": "站点",
                "excel": "Excel 无此站点", "json": "", "status": ST_MISSING_EXCEL,
            })
            # 即便 Excel 中没有该站点，JSON 侧的重复 / 非法 IP 仍应报出
            for key in sorted(json_dups, key=lambda x: (x[0], self._port_sort(x[1]))):
                sw, port = key
                results.append({
                    "station": station_name, "switch": sw, "port": port,
                    "type": "端口重复(JSON)",
                    "excel": "",
                    "json": f"端口 {port} 在交换机 {sw} 下重复出现",
                    "status": ST_DUPLICATE,
                })
            for key, jp in sorted(json_ports.items(),
                                  key=lambda x: (x[0][0], self._port_sort(x[0][1]))):
                sw, port = key
                j_ip = jp.get("ip", "")
                if j_ip and not is_valid_ipv4(j_ip):
                    results.append({
                        "station": station_name, "switch": sw, "port": port,
                        "type": "IP格式(JSON)",
                        "excel": "",
                        "json": j_ip,
                        "status": ST_INVALID_IP,
                    })
            return results, ""

        # ---- 逐端口比对 ----
        all_keys = set(excel_ports.keys()) | set(json_ports.keys())
        diff_count = 0
        ok_count = 0
        bad_ip_count = 0

        for key in sorted(all_keys, key=lambda x: (x[0], self._port_sort(x[1]))):
            sw, port = key
            ep = excel_ports.get(key)
            jp = json_ports.get(key)

            if ep and not jp:
                results.append({
                    "station": station_name, "switch": sw, "port": port,
                    "type": "端口/设备",
                    "excel": f"{ep['dev']} ({ep['ip']})",
                    "json": "缺失",
                    "status": ST_MISSING_JSON,
                })
                diff_count += 1
                continue

            if jp and not ep:
                results.append({
                    "station": station_name, "switch": sw, "port": port,
                    "type": "端口/设备",
                    "excel": "缺失",
                    "json": f"{jp['dev']} ({jp['ip']})",
                    "status": ST_MISSING_EXCEL,
                })
                diff_count += 1
                continue

            port_ok = True

            # ① 设备名比对
            if ep["dev"] != jp["dev"]:
                results.append({
                    "station": station_name, "switch": sw, "port": port,
                    "type": "设备名",
                    "excel": ep["dev"], "json": jp["dev"],
                    "status": ST_MISMATCH,
                })
                diff_count += 1
                port_ok = False

            # ② ★ 新增：IP 格式校验（任一侧非法即报错，且不再做数值比对）
            e_ip, j_ip = ep["ip"], jp["ip"]
            e_ip_bad = bool(e_ip) and not is_valid_ipv4(e_ip)
            j_ip_bad = bool(j_ip) and not is_valid_ipv4(j_ip)

            if e_ip_bad or j_ip_bad:
                bad_sides = []
                if e_ip_bad:
                    bad_sides.append("Excel")
                if j_ip_bad:
                    bad_sides.append("JSON")
                results.append({
                    "station": station_name, "switch": sw, "port": port,
                    "type": f"IP格式({'+'.join(bad_sides)})",
                    "excel": e_ip,
                    "json": j_ip,
                    "status": ST_INVALID_IP,
                })
                diff_count += 1
                bad_ip_count += 1
                port_ok = False
            # ③ IP 值比对（只在两侧格式都合法时进行）
            elif (e_ip and j_ip and e_ip != j_ip
                    and e_ip != "0.0.0.0" and j_ip != "0.0.0.0"):
                results.append({
                    "station": station_name, "switch": sw, "port": port,
                    "type": "IP",
                    "excel": e_ip, "json": j_ip,
                    "status": ST_MISMATCH,
                })
                diff_count += 1
                port_ok = False

            if port_ok:
                results.append({
                    "station": station_name, "switch": sw, "port": port,
                    "type": "端口/设备",
                    "excel": f"{ep['dev']} ({ep['ip']})",
                    "json": f"{jp['dev']} ({jp['ip']})",
                    "status": ST_SUCCESS,
                })
                ok_count += 1

        # ---- 同一交换机下端口不能重复（Excel 侧） ----
        for key in sorted(excel_dups, key=lambda x: (x[0], self._port_sort(x[1]))):
            sw, port = key
            results.append({
                "station": station_name, "switch": sw, "port": port,
                "type": "端口重复(Excel)",
                "excel": f"端口 {port} 在交换机 {sw} 下重复出现",
                "json": "",
                "status": ST_DUPLICATE,
            })
            diff_count += 1

        # ---- 同一交换机下端口不能重复（JSON 侧） ----
        for key in sorted(json_dups, key=lambda x: (x[0], self._port_sort(x[1]))):
            sw, port = key
            results.append({
                "station": station_name, "switch": sw, "port": port,
                "type": "端口重复(JSON)",
                "excel": "",
                "json": f"端口 {port} 在交换机 {sw} 下重复出现",
                "status": ST_DUPLICATE,
            })
            diff_count += 1

        log_msg = f"[{station_name}] 一致 {ok_count} 条，差异 {diff_count} 条"
        if bad_ip_count:
            log_msg += f"，其中 IP 格式错误 {bad_ip_count} 条"
        return results, log_msg

    @staticmethod
    def _port_sort(p):
        try:
            return (0, int(p))
        except Exception:
            return (1, str(p))

    # ---------- 导出 ----------
    def _export_results(self):
        if not self.visible_results:
            messagebox.showinfo("提示", "当前显示为空，无内容可导出")
            return
        p = filedialog.asksaveasfilename(
            title="导出当前显示结果",
            defaultextension=".xlsx",
            filetypes=[("Excel 文件", "*.xlsx"), ("CSV 文件", "*.csv")],
            initialfile=f"拓扑比对结果_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        )
        if not p:
            return
        try:
            headers = ["站点", "交换机", "端口", "对比项", "Excel 值", "JSON 值", "结果"]

            if p.lower().endswith(".csv"):
                with open(p, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    for r in self.visible_results:
                        writer.writerow([
                            r.get("station", ""),
                            r.get("switch", ""),
                            r.get("port", ""),
                            r.get("type", ""),
                            r.get("excel", ""),
                            r.get("json", ""),
                            STATUS_LABEL.get(r.get("status", ""), r.get("status", "")),
                        ])
            else:
                wb = Workbook()
                ws = wb.active
                ws.title = "比对结果"
                ws.append(headers)
                for r in self.visible_results:
                    ws.append([
                        r.get("station", ""),
                        r.get("switch", ""),
                        r.get("port", ""),
                        r.get("type", ""),
                        r.get("excel", ""),
                        r.get("json", ""),
                        STATUS_LABEL.get(r.get("status", ""), r.get("status", "")),
                    ])
                wb.save(p)
                wb.close()
            self._log(f"结果已导出（{len(self.visible_results)} 条）：{p}")
            messagebox.showinfo("导出成功", f"已导出 {len(self.visible_results)} 条到：\n{p}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))


# ============================================================
# 4. 入口
# ============================================================
def main():
    # DPI（Win8.1+ 才有 shcore，Win7 会 AttributeError，忽略即可）
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    # 创建 Tk
    try:
        root = tk.Tk()
    except Exception as e:
        _show_fatal(
            f"Tk() 初始化失败：\n{e}\n\n"
            f"常见原因：\n"
            f"  1) 打包时 tcl/tk 数据未收集，加 --collect-data tk\n"
            f"  2) 杀软拦截了临时解包目录"
        )
        return

    # Tk 回调未捕获异常：打印到 stderr（不再落盘）
    def _tk_exc_hook(exc_type, exc_val, exc_tb):
        try:
            traceback.print_exception(exc_type, exc_val, exc_tb, file=sys.__stderr__)
        except Exception:
            pass
    root.report_callback_exception = _tk_exc_hook

    # 创建主界面
    try:
        app = NMSCompareApp(root)
    except Exception as e:
        _show_fatal(f"界面初始化失败：\n{e}")
        return

    try:
        root.mainloop()
    except Exception:
        pass


if __name__ == "__main__":
    main()