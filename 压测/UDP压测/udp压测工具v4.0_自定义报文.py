import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import socket
import threading
import re
import time
import os
import json
import random
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor


# 时间格式常量
FORMAT_LABELS = ['Unix时间戳', '日期时间(6字节)']
FORMAT_L2V = {'Unix时间戳': 'unix', '日期时间(6字节)': 'datetime'}
FORMAT_V2L = {'unix': 'Unix时间戳', 'datetime': '日期时间(6字节)'}


class PacketSender:
    def __init__(self, root):
        self.root = root
        self.root.title("UDP 发报机")
        self.root.geometry("1300x950")

        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_file = os.path.join(base_dir, "config.json")

        self.interval_var = tk.StringVar(value="0.001")
        self.target_ip_var = tk.StringVar(value="192.168.1.213")
        self.loop_var = tk.BooleanVar(value=False)
        self.verbose_logging = tk.BooleanVar(value=False)
        self.high_precision_var = tk.BooleanVar(value=True)
        self.use_high_precision_timing = True

        self.timestamp_offset_var = tk.StringVar(value="4")
        self.timestamp_length_var = tk.StringVar(value="4")
        self.timestamp_live_var = tk.BooleanVar(value=True)
        self.timestamp_reverse_var = tk.BooleanVar(value=False)
        self.timestamp_format_var = tk.StringVar(value="unix")

        self.sending = False
        self.paused = False
        self.heartbeat_listening = False
        self.loop_sending = False
        self.start_time = None
        self.total_packets_sent = 0
        self.loop_count = 0
        self.packets_lock = threading.Lock()
        self.stats_lock = threading.Lock()
        self.stop_event = threading.Event()

        self.udp_sockets = {}
        self.socket_lock = threading.Lock()
        self.receive_threads = {}

        self.executor = None
        self.futures = []

        self.sub_connections = []

        self.local_ips = self.get_local_ips()

        self.create_widgets()
        self.load_config()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def get_local_ips(self):
        ips = ["0.0.0.0"]
        try:
            hostname = socket.gethostname()
            ips.extend(socket.gethostbyname_ex(hostname)[2])
            ips.append("127.0.0.1")
            ips = list(dict.fromkeys(ips))
        except:
            pass
        return ips

    # ================== UI 构建 ==================
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        setting_frame = ttk.LabelFrame(main_frame, text="全局发送设置", padding="10")
        setting_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(setting_frame, text="默认发送间隔(秒):").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        ttk.Entry(setting_frame, textvariable=self.interval_var, width=12).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(setting_frame, text="(新子连接组的默认间隔)").grid(row=0, column=2, sticky=tk.W, padx=(5, 0))
        ttk.Checkbutton(setting_frame, text="高精度计时", variable=self.high_precision_var,
                        command=self.toggle_high_precision).grid(row=0, column=3, padx=(20, 0))
        ttk.Checkbutton(setting_frame, text="详细日志", variable=self.verbose_logging).grid(row=0, column=4, padx=(20, 0))

        ttk.Label(setting_frame, text="目标IP:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=(10, 0))
        ttk.Entry(setting_frame, textvariable=self.target_ip_var, width=15).grid(row=1, column=1, sticky=tk.W, pady=(10, 0))
        ttk.Label(setting_frame, text="(UDP 接收方 IP)").grid(row=1, column=2, columnspan=3, sticky=tk.W, padx=(10, 0), pady=(10, 0))

        ttk.Label(setting_frame, text="默认时间戳偏移(字节):").grid(row=2, column=0, sticky=tk.W, padx=(0, 10), pady=(10, 0))
        ttk.Entry(setting_frame, textvariable=self.timestamp_offset_var, width=5).grid(row=2, column=1, sticky=tk.W, pady=(10, 0))
        ttk.Label(setting_frame, text="默认时间戳长度(字节):").grid(row=2, column=2, sticky=tk.W, padx=(10, 0), pady=(10, 0))
        ttk.Entry(setting_frame, textvariable=self.timestamp_length_var, width=5).grid(row=2, column=3, sticky=tk.W, pady=(10, 0))
        ttk.Label(setting_frame, text="(日志文件模式使用)").grid(row=2, column=4, columnspan=2, sticky=tk.W, padx=(10, 0), pady=(10, 0))

        loop_frame = ttk.Frame(main_frame)
        loop_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Checkbutton(loop_frame, text="循环发送", variable=self.loop_var).pack(side=tk.LEFT)

        group_frame = ttk.LabelFrame(main_frame, text="子连接组管理", padding="10")
        group_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        global_btn_frame = ttk.Frame(group_frame)
        global_btn_frame.pack(fill=tk.X, pady=(0, 10))
        self.add_group_btn = ttk.Button(global_btn_frame, text="添加子连接组", command=self.add_sub_connection_group)
        self.add_group_btn.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(global_btn_frame, text="全部启用", command=lambda: self.global_enable_all(True)).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(global_btn_frame, text="全部禁用", command=lambda: self.global_enable_all(False)).pack(side=tk.LEFT)

        self.notebook = ttk.Notebook(group_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        self.start_btn = ttk.Button(control_frame, text="开始发送", command=self.start_sending)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.pause_btn = ttk.Button(control_frame, text="暂停", command=self.pause_sending, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.stop_btn = ttk.Button(control_frame, text="停止发送", command=self.stop_sending, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=(0, 10))

        stats_frame = ttk.Frame(main_frame)
        stats_frame.pack(fill=tk.X, pady=(0, 10))
        self.status_var = tk.StringVar(value="准备就绪")
        ttk.Label(stats_frame, textvariable=self.status_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.stats_var = tk.StringVar(value="总时长: 00:00:00 | 发送报文: 0 | 循环次数: 0")
        ttk.Label(stats_frame, textvariable=self.stats_var).pack(side=tk.RIGHT)
        self.perf_var = tk.StringVar(value="")
        ttk.Label(stats_frame, textvariable=self.perf_var).pack(side=tk.RIGHT, padx=(0, 20))

        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        send_frame = ttk.LabelFrame(paned, text="发送日志", padding="5")
        paned.add(send_frame, weight=1)
        self.send_log_text = scrolledtext.ScrolledText(send_frame, wrap=tk.WORD, height=15)
        self.send_log_text.pack(fill=tk.BOTH, expand=True)

        recv_frame = ttk.LabelFrame(paned, text="接收日志", padding="5")
        paned.add(recv_frame, weight=1)
        self.recv_log_text = scrolledtext.ScrolledText(recv_frame, wrap=tk.WORD, height=15)
        self.recv_log_text.pack(fill=tk.BOTH, expand=True)

    def toggle_high_precision(self):
        self.use_high_precision_timing = self.high_precision_var.get()
        self.log_send_message(f"高精度计时已{'启用' if self.use_high_precision_timing else '禁用'}")

    # ================== 子连接组 ==================
    def add_sub_connection_group(self, group_data=None):
        if self.sending:
            messagebox.showwarning("警告", "发送过程中不能添加子连接组")
            return

        group = {
            'name': f"子连接 {len(self.sub_connections) + 1}",
            'target_port': tk.StringVar(value="10040"),
            'interval': tk.StringVar(value=self.interval_var.get()),
            'timestamp_offset': tk.StringVar(value=self.timestamp_offset_var.get()),
            'timestamp_length': tk.StringVar(value=self.timestamp_length_var.get()),
            'timestamp_live': tk.BooleanVar(value=self.timestamp_live_var.get()),
            'timestamp_reverse': tk.BooleanVar(value=self.timestamp_reverse_var.get()),
            'timestamp_format': tk.StringVar(value=self.timestamp_format_var.get()),
            'rules': [],
            'connections': [],
            'tl_scope': tk.StringVar(value='组级'),
            't_range_lo': tk.StringVar(value='0'),
            't_range_hi': tk.StringVar(value='255'),
            'l_list_str': tk.StringVar(value=''),
            # 新增：报文列表作用域与组级报文
            'pkt_scope': tk.StringVar(value='连接级'),
            'custom_packets': [],
            'custom_count_var': tk.StringVar(value=""),
        }
        if group_data:
            group['target_port'].set(group_data.get('target_port', '10040'))
            group['interval'].set(group_data.get('interval', self.interval_var.get()))
            group['timestamp_offset'].set(group_data.get('timestamp_offset', self.timestamp_offset_var.get()))
            group['timestamp_length'].set(group_data.get('timestamp_length', self.timestamp_length_var.get()))
            group['timestamp_live'].set(group_data.get('timestamp_live', True))
            group['timestamp_reverse'].set(group_data.get('timestamp_reverse', False))
            group['timestamp_format'].set(group_data.get('timestamp_format', 'unix'))
            group['rules'] = group_data.get('rules', []) or []
            group['tl_scope'].set(group_data.get('tl_scope', '组级'))
            group['t_range_lo'].set(group_data.get('t_range_lo', '0'))
            group['t_range_hi'].set(group_data.get('t_range_hi', '255'))
            group['l_list_str'].set(group_data.get('l_list_str', ''))
            group['pkt_scope'].set(group_data.get('pkt_scope', '连接级'))
            for p in group_data.get('custom_packets', []) or []:
                content = p.get('content', '')
                tokens, _ = self.parse_packet_content(content)
                group['custom_packets'].append({
                    'content': content,
                    'remark': p.get('remark', ''),
                    'l_interval': float(p.get('l_interval', 10)),
                    'tokens': tokens,
                })

        self.sub_connections.append(group)

        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=group['name'])
        self.notebook.select(frame)

        self._build_group_ui(frame, group, len(self.sub_connections) - 1)

        if group_data:
            for conn_data in group_data.get('connections', []):
                self._add_connection_to_group(len(self.sub_connections) - 1, conn_data)

        self.log_send_message(
            f"已添加子连接组：{group['name']}，目标端口 {group['target_port'].get()}，"
            f"发送间隔 {group['interval'].get()} 秒，报文作用域 {group['pkt_scope'].get()}")

    def _build_group_ui(self, parent, group, group_index):
        config_frame = ttk.Frame(parent)
        config_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(config_frame, text="本组目标端口:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Entry(config_frame, textvariable=group['target_port'], width=10).pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(config_frame, text="本组发送间隔(秒):").pack(side=tk.LEFT, padx=(10, 5))
        ttk.Entry(config_frame, textvariable=group['interval'], width=10).pack(side=tk.LEFT, padx=(0, 15))

        live_cb = ttk.Checkbutton(config_frame, text="时间戳实时变化", variable=group['timestamp_live'],
                                  command=lambda: self._update_ts_widget_state(group))
        live_cb.pack(side=tk.LEFT, padx=(10, 15))

        ttk.Label(config_frame, text="时间格式:").pack(side=tk.LEFT, padx=(5, 5))
        group['format_label_var'] = tk.StringVar(
            value=FORMAT_V2L.get(group['timestamp_format'].get(), 'Unix时间戳'))

        def _on_format_label_changed(*args):
            label = group['format_label_var'].get()
            val = FORMAT_L2V.get(label, 'unix')
            if group['timestamp_format'].get() != val:
                group['timestamp_format'].set(val)
            self._update_ts_widget_state(group)

        group['format_label_var'].trace_add('write', _on_format_label_changed)

        format_combo = ttk.Combobox(config_frame, textvariable=group['format_label_var'],
                                    values=FORMAT_LABELS, width=18, state='readonly')
        format_combo.pack(side=tk.LEFT, padx=(0, 15))
        group['format_combo'] = format_combo

        ttk.Label(config_frame, text="时间戳偏移:").pack(side=tk.LEFT, padx=(5, 5))
        offset_entry = ttk.Entry(config_frame, textvariable=group['timestamp_offset'], width=5)
        offset_entry.pack(side=tk.LEFT, padx=(0, 10))
        group['offset_entry'] = offset_entry

        ttk.Label(config_frame, text="长度:").pack(side=tk.LEFT, padx=(5, 5))
        length_entry = ttk.Entry(config_frame, textvariable=group['timestamp_length'], width=5)
        length_entry.pack(side=tk.LEFT, padx=(0, 15))
        group['length_entry'] = length_entry

        reverse_cb = ttk.Checkbutton(config_frame, text="时间戳反转", variable=group['timestamp_reverse'])
        reverse_cb.pack(side=tk.LEFT, padx=(5, 0))
        group['reverse_cb'] = reverse_cb

        ttk.Label(parent, text="※ 上述时间戳设置仅用于【日志文件】模式；自定义报文模式请使用 [...] 占位符",
                  foreground='#888').pack(fill=tk.X, pady=(0, 5))

        self._update_ts_widget_state(group)

        # ---- T/L 作用域行 ----
        tl_frame = ttk.Frame(parent)
        tl_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(tl_frame, text="T/L作用域:").pack(side=tk.LEFT)
        ttk.Combobox(tl_frame, textvariable=group['tl_scope'],
                     values=['组级', '连接级'], state='readonly', width=10).pack(side=tk.LEFT, padx=(5, 10))

        t_group_btn = ttk.Button(tl_frame, text="编辑组级T范围",
                                 command=lambda gi=group_index: self._open_t_range_dialog(
                                     self.root, group['t_range_lo'], group['t_range_hi'],
                                     f"编辑T范围（组级）- {group['name']}"))
        t_group_btn.pack(side=tk.LEFT, padx=(0, 5))
        t_group_l_btn = ttk.Button(tl_frame, text="编辑组级L列表",
                                   command=lambda gi=group_index: self._open_l_list_dialog(
                                       self.root, group['l_list_str'],
                                       f"编辑L列表（组级）- {group['name']}"))
        t_group_l_btn.pack(side=tk.LEFT, padx=(0, 5))

        group['t_group_btn'] = t_group_btn
        group['t_group_l_btn'] = t_group_l_btn

        def update_group_tl_btn_state(*args):
            try:
                st = tk.NORMAL if group['tl_scope'].get() == '组级' else tk.DISABLED
                t_group_btn.config(state=st)
                t_group_l_btn.config(state=st)
            except:
                pass

        group['tl_scope'].trace_add('write', update_group_tl_btn_state)
        update_group_tl_btn_state()

        # ---- 报文作用域行（新增）----
        pkt_frame = ttk.Frame(parent)
        pkt_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(pkt_frame, text="报文作用域:").pack(side=tk.LEFT)
        ttk.Combobox(pkt_frame, textvariable=group['pkt_scope'],
                     values=['组级', '连接级'], state='readonly', width=10).pack(side=tk.LEFT, padx=(5, 10))

        pkt_group_btn = ttk.Button(pkt_frame, text="编辑组级报文",
                                   command=lambda gi=group_index: self.open_custom_packets_dialog(gi, None))
        pkt_group_btn.pack(side=tk.LEFT, padx=(0, 5))
        group['pkt_group_btn'] = pkt_group_btn

        group['pkt_count_label'] = ttk.Label(pkt_frame, text="", foreground='#066')
        group['pkt_count_label'].pack(side=tk.LEFT, padx=(10, 0))

        def update_pkt_scope_state(*args):
            try:
                st = tk.NORMAL if group['pkt_scope'].get() == '组级' else tk.DISABLED
                pkt_group_btn.config(state=st)
                n = len(group['custom_packets'])
                if group['pkt_scope'].get() == '组级':
                    group['pkt_count_label'].config(text=f"(共 {n} 条组级报文)")
                else:
                    group['pkt_count_label'].config(text="(每个连接各自配置报文)")
                for c in group['connections']:
                    try:
                        c['_rebuild_cell']()
                    except:
                        pass
            except:
                pass

        group['pkt_scope'].trace_add('write', update_pkt_scope_state)
        update_pkt_scope_state()

        # ---- 操作按钮行 ----
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(btn_frame, text="添加连接", command=lambda: self._add_connection_to_group(group_index)).pack(
            side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="批量生成", command=lambda: self.batch_generate_connections(group_index)).pack(
            side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="批量设置模式",
                   command=lambda: self.batch_set_mode_group(group_index)).pack(
            side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="批量设置本机端口", command=lambda: self.batch_set_ports_group(group_index)).pack(
            side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="批量设置本机IP", command=lambda: self.batch_set_ips_group(group_index)).pack(
            side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="批量选择文件", command=lambda: self.batch_select_files_group(group_index)).pack(
            side=tk.LEFT, padx=(0, 5))

        rule_btn = ttk.Button(btn_frame, text=f"偏移规则({len(group['rules'])})",
                              command=lambda: self.open_rules_dialog(group_index))
        rule_btn.pack(side=tk.LEFT, padx=(0, 5))
        group['rule_btn'] = rule_btn

        ttk.Button(btn_frame, text="删除此组", command=lambda: self.delete_sub_connection_group(group_index)).pack(
            side=tk.LEFT, padx=(0, 5))

        # ---- 滚动区域 ----
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mousewheel(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)

        ttk.Label(scrollable_frame, text="启用", width=6).grid(row=0, column=0, padx=5, pady=2)
        ttk.Label(scrollable_frame, text="本机IP", width=15).grid(row=0, column=1, padx=5, pady=2)
        ttk.Label(scrollable_frame, text="本机端口", width=10).grid(row=0, column=2, padx=5, pady=2)
        ttk.Label(scrollable_frame, text="模式", width=12).grid(row=0, column=3, padx=5, pady=2)
        ttk.Label(scrollable_frame, text="文件 / 报文", width=45).grid(row=0, column=4, padx=5, pady=2)
        ttk.Label(scrollable_frame, text="操作", width=12).grid(row=0, column=5, padx=5, pady=2)

        group['scrollable_frame'] = scrollable_frame
        group['canvas'] = canvas

    def _update_ts_widget_state(self, group):
        live = group['timestamp_live'].get()
        if not live:
            group['offset_entry'].config(state='disabled')
            group['length_entry'].config(state='disabled')
            group['reverse_cb'].config(state='disabled')
            group['format_combo'].config(state='disabled')
            return
        group['offset_entry'].config(state='normal')
        group['format_combo'].config(state='normal')
        fmt = group['timestamp_format'].get()
        if fmt == 'datetime':
            if group['timestamp_length'].get() != '6':
                group['timestamp_length'].set('6')
            group['length_entry'].config(state='disabled')
            group['reverse_cb'].config(state='disabled')
        else:
            group['length_entry'].config(state='normal')
            group['reverse_cb'].config(state='normal')

    # ================== 连接管理 ==================
    def _build_connection_row(self, sf, gi, ci, row):
        group = self.sub_connections[gi]
        conn = group['connections'][ci]

        ttk.Checkbutton(sf, variable=conn['enabled']).grid(row=row, column=0, padx=5, pady=2)
        ttk.Combobox(sf, textvariable=conn['local_ip'], values=self.local_ips, width=15).grid(
            row=row, column=1, padx=5, pady=2)
        ttk.Entry(sf, textvariable=conn['local_port'], width=10).grid(row=row, column=2, padx=5, pady=2)
        ttk.Combobox(sf, textvariable=conn['mode'], values=['日志文件', '自定义报文'],
                     state='readonly', width=12).grid(row=row, column=3, padx=5, pady=2)

        cell_frame = ttk.Frame(sf)
        cell_frame.grid(row=row, column=4, padx=5, pady=2, sticky='we')

        def rebuild_cell(*args):
            for w in cell_frame.winfo_children():
                w.destroy()
            if conn['mode'].get() == '日志文件':
                ttk.Entry(cell_frame, textvariable=conn['file_path'], width=38).pack(
                    side=tk.LEFT, fill=tk.X, expand=True)
                ttk.Button(cell_frame, text="浏览",
                           command=lambda: self.browse_conn_file(gi, ci)).pack(side=tk.LEFT, padx=(2, 0))
            else:
                if group['pkt_scope'].get() == '组级':
                    n = len(group['custom_packets'])
                    ttk.Label(cell_frame, text=f"使用组级报文（共 {n} 条）",
                              width=20, anchor='w').pack(side=tk.LEFT)
                    ttk.Button(cell_frame, text="查看/编辑组级报文",
                               command=lambda: self.open_custom_packets_dialog(gi, None)).pack(
                        side=tk.LEFT, padx=(5, 0))
                else:
                    n = len(conn['custom_packets'])
                    conn['custom_count_var'].set(f"已配置 {n} 条报文")
                    ttk.Label(cell_frame, textvariable=conn['custom_count_var'],
                              width=20, anchor='w').pack(side=tk.LEFT)
                    ttk.Button(cell_frame, text="自定义报文",
                               command=lambda: self.open_custom_packets_dialog(gi, ci)).pack(
                        side=tk.LEFT, padx=(5, 0))

        conn['_rebuild_cell'] = rebuild_cell
        rebuild_cell()

        ttk.Button(sf, text="删除",
                   command=lambda: self.delete_connection(gi, ci)).grid(row=row, column=5, padx=2, pady=2)

    def _add_connection_to_group(self, group_index, conn_data=None):
        if self.sending:
            messagebox.showwarning("警告", "发送过程中不能添加连接")
            return
        if group_index < 0 or group_index >= len(self.sub_connections):
            return

        group = self.sub_connections[group_index]

        conn = {
            'local_ip': tk.StringVar(value="0.0.0.0"),
            'local_port': tk.StringVar(value="10010"),
            'file_path': tk.StringVar(),
            'enabled': tk.BooleanVar(value=True),
            'mode': tk.StringVar(value="日志文件"),
            'custom_packets': [],
            'custom_count_var': tk.StringVar(value=""),
            't_range_lo': tk.StringVar(value='0'),
            't_range_hi': tk.StringVar(value='255'),
            'l_list_str': tk.StringVar(value=''),
            'runtime': {'p_value': {}, 'l_index': {}, 'l_last_change': {}},
            'packets_cache': None,
            'cache_time': None,
            'packet_index': 0,
            'last_send_time': 0,
            '_rebuild_cell': lambda: None,
        }
        if conn_data:
            conn['local_ip'].set(conn_data.get('local_ip', '0.0.0.0'))
            conn['local_port'].set(conn_data.get('local_port', '10010'))
            conn['file_path'].set(conn_data.get('file_path', ''))
            conn['enabled'].set(conn_data.get('enabled', True))
            conn['mode'].set(conn_data.get('mode', '日志文件'))
            conn['t_range_lo'].set(conn_data.get('t_range_lo', '0'))
            conn['t_range_hi'].set(conn_data.get('t_range_hi', '255'))
            conn['l_list_str'].set(conn_data.get('l_list_str', ''))
            raw_pkts = conn_data.get('custom_packets', []) or []
            for p in raw_pkts:
                content = p.get('content', '')
                tokens, _ = self.parse_packet_content(content)
                conn['custom_packets'].append({
                    'content': content,
                    'remark': p.get('remark', ''),
                    'l_interval': float(p.get('l_interval', 10)),
                    'tokens': tokens,
                })

        group['connections'].append(conn)

        conn['mode'].trace_add('write', lambda *a: conn['_rebuild_cell']())

        row = len(group['connections'])
        self._build_connection_row(group['scrollable_frame'], group_index, len(group['connections']) - 1, row)
        group['canvas'].configure(scrollregion=group['canvas'].bbox("all"))

    def delete_connection(self, group_index, conn_index):
        if self.sending:
            messagebox.showwarning("警告", "发送过程中不能删除连接")
            return
        if group_index < 0 or group_index >= len(self.sub_connections):
            return
        group = self.sub_connections[group_index]
        if conn_index < 0 or conn_index >= len(group['connections']):
            return
        del group['connections'][conn_index]
        self._refresh_group_ui(group_index)

    def _refresh_group_ui(self, group_index):
        group = self.sub_connections[group_index]
        sf = group['scrollable_frame']
        for widget in sf.winfo_children():
            info = widget.grid_info()
            if info and int(info.get('row', 0)) > 0:
                widget.destroy()

        for i, conn in enumerate(group['connections']):
            self._build_connection_row(sf, group_index, i, i + 1)

        group['canvas'].configure(scrollregion=group['canvas'].bbox("all"))

    def delete_sub_connection_group(self, group_index):
        if self.sending:
            messagebox.showwarning("警告", "发送过程中不能删除子连接组")
            return
        if group_index < 0 or group_index >= len(self.sub_connections):
            return
        if messagebox.askyesno("确认删除",
                               f"确定要删除子连接组 {self.sub_connections[group_index]['name']} 及其所有连接吗？"):
            del self.sub_connections[group_index]
            self.notebook.forget(group_index)
            for i in range(group_index, len(self.sub_connections)):
                self.sub_connections[i]['name'] = f"子连接 {i + 1}"
                self.notebook.tab(i, text=self.sub_connections[i]['name'])
            self.log_send_message(f"已删除子连接组，当前剩余 {len(self.sub_connections)} 个")

    # ================== 批量设置模式（新增）==================
    def batch_set_mode_group(self, group_index):
        if self.sending:
            messagebox.showwarning("警告", "发送过程中不能批量设置模式")
            return
        if group_index < 0 or group_index >= len(self.sub_connections):
            return
        group = self.sub_connections[group_index]
        if not group['connections']:
            messagebox.showinfo("提示", "该组没有连接")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("批量设置连接模式")
        dialog.geometry("320x160")
        dialog.transient(self.root)
        dialog.grab_set()

        mode_var = tk.StringVar(value="日志文件")
        ttk.Label(dialog, text="将所有连接设置为:").pack(pady=(20, 5))
        ttk.Combobox(dialog, textvariable=mode_var,
                     values=['日志文件', '自定义报文'], state='readonly', width=15).pack()

        def apply():
            for conn in group['connections']:
                conn['mode'].set(mode_var.get())
            self.log_send_message(
                f"组 {group['name']} 已将 {len(group['connections'])} 个连接模式设置为 {mode_var.get()}")
            dialog.destroy()

        ttk.Button(dialog, text="应用", command=apply).pack(pady=20)

    # ================== 时间戳偏移规则（日志模式）==================
    def open_rules_dialog(self, group_index):
        if self.sending:
            messagebox.showwarning("警告", "发送过程中不能修改规则")
            return
        if group_index < 0 or group_index >= len(self.sub_connections):
            return
        group = self.sub_connections[group_index]

        dialog = tk.Toplevel(self.root)
        dialog.title(f"组 {group['name']} - 时间戳偏移规则")
        dialog.geometry("960x540")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="规则仅用于【日志文件】模式，按顺序匹配，命中第一条后生效。",
                  foreground='#444').pack(fill=tk.X, padx=10, pady=(10, 5))

        tree_frame = ttk.Frame(dialog)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ('order', 'type', 'value', 'format', 'offset', 'length', 'reverse')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=14)
        for c, t in zip(columns, ['序号', '匹配类型', '匹配值', '时间格式', '偏移', '长度', '反转']):
            tree.heading(c, text=t)
        tree.column('order', width=50, anchor='center')
        tree.column('type', width=120, anchor='center')
        tree.column('value', width=220, anchor='w')
        tree.column('format', width=140, anchor='center')
        tree.column('offset', width=70, anchor='center')
        tree.column('length', width=70, anchor='center')
        tree.column('reverse', width=60, anchor='center')
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sb = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        TYPE_LABELS = {'length': '报文长度', 'prefix': '报文前缀(HEX)',
                       'regex': '正则表达式', 'default': '默认(兜底)'}

        def refresh_tree():
            for item in tree.get_children():
                tree.delete(item)
            for i, rule in enumerate(group['rules']):
                type_str = TYPE_LABELS.get(rule.get('match_type', 'length'), rule.get('match_type', ''))
                fmt_str = FORMAT_V2L.get(rule.get('time_format', 'unix'), 'Unix时间戳')
                if rule.get('time_format', 'unix') == 'datetime':
                    length_display, reverse_display = '6(固定)', '—'
                else:
                    length_display = rule.get('length', 4)
                    reverse_display = '是' if rule.get('reverse', False) else '否'
                tree.insert('', tk.END, iid=str(i), values=(
                    i + 1, type_str, rule.get('match_value', ''), fmt_str,
                    rule.get('offset', 0), length_display, reverse_display))
            try:
                group['rule_btn'].config(text=f"偏移规则({len(group['rules'])})")
            except:
                pass

        def add_rule():
            self._edit_rule_dialog(dialog, group, None, refresh_tree)

        def edit_rule():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("提示", "请先选择一行规则")
                return
            self._edit_rule_dialog(dialog, group, int(sel[0]), refresh_tree)

        def delete_rule():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("提示", "请先选择一行规则")
                return
            idx = int(sel[0])
            if messagebox.askyesno("确认", "确定删除该规则？"):
                del group['rules'][idx]
                refresh_tree()

        def move_up():
            sel = tree.selection()
            if not sel:
                return
            idx = int(sel[0])
            if idx > 0:
                group['rules'][idx], group['rules'][idx - 1] = group['rules'][idx - 1], group['rules'][idx]
                refresh_tree()
                tree.selection_set(str(idx - 1))

        def move_down():
            sel = tree.selection()
            if not sel:
                return
            idx = int(sel[0])
            if idx < len(group['rules']) - 1:
                group['rules'][idx], group['rules'][idx + 1] = group['rules'][idx + 1], group['rules'][idx]
                refresh_tree()
                tree.selection_set(str(idx + 1))

        tree.bind('<Double-1>', lambda e: edit_rule())

        btn_row = ttk.Frame(dialog)
        btn_row.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(btn_row, text="添加规则", command=add_rule).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="编辑选中", command=edit_rule).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="删除选中", command=delete_rule).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="上移", command=move_up).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="下移", command=move_down).pack(side=tk.LEFT, padx=(0, 5))

        close_row = ttk.Frame(dialog)
        close_row.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(close_row, text="关闭", command=dialog.destroy).pack(side=tk.RIGHT)

        refresh_tree()

    def _edit_rule_dialog(self, parent, group, rule_index, on_saved):
        dlg = tk.Toplevel(parent)
        dlg.title("编辑规则" if rule_index is not None else "添加规则")
        dlg.geometry("500x440")
        dlg.transient(parent)
        dlg.grab_set()

        if rule_index is not None:
            rule = dict(group['rules'][rule_index])
        else:
            rule = {'match_type': 'length', 'match_value': '', 'offset': 4,
                    'length': 4, 'reverse': False, 'time_format': 'unix'}

        type_var = tk.StringVar(value=rule.get('match_type', 'length'))
        value_var = tk.StringVar(value=str(rule.get('match_value', '')))
        offset_var = tk.StringVar(value=str(rule.get('offset', 4)))
        length_var = tk.StringVar(value=str(rule.get('length', 4)))
        reverse_var = tk.BooleanVar(value=rule.get('reverse', False))

        LABEL_TO_TYPE = {'报文长度': 'length', '报文前缀(HEX)': 'prefix',
                         '正则表达式': 'regex', '默认(兜底)': 'default'}
        TYPE_TO_LABEL = {v: k for k, v in LABEL_TO_TYPE.items()}

        fmt_label_var = tk.StringVar(value=FORMAT_V2L.get(rule.get('time_format', 'unix'), 'Unix时间戳'))

        ttk.Label(dlg, text="匹配类型:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=6)
        ttk.Combobox(dlg, textvariable=type_var,
                     values=['报文长度', '报文前缀(HEX)', '正则表达式', '默认(兜底)'],
                     state='readonly', width=22).grid(row=0, column=1, sticky=tk.W, padx=10, pady=6)

        ttk.Label(dlg, text="匹配值:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=6)
        value_entry = ttk.Entry(dlg, textvariable=value_var, width=32)
        value_entry.grid(row=1, column=1, sticky=tk.W, padx=10, pady=6)

        hint_label = ttk.Label(dlg, text="", foreground='#666')
        hint_label.grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=10, pady=(0, 6))

        ttk.Label(dlg, text="时间格式:").grid(row=3, column=0, sticky=tk.W, padx=10, pady=6)
        ttk.Combobox(dlg, textvariable=fmt_label_var, values=FORMAT_LABELS,
                     state='readonly', width=22).grid(row=3, column=1, sticky=tk.W, padx=10, pady=6)

        ttk.Label(dlg, text="时间戳偏移(字节):").grid(row=4, column=0, sticky=tk.W, padx=10, pady=6)
        ttk.Entry(dlg, textvariable=offset_var, width=12).grid(row=4, column=1, sticky=tk.W, padx=10, pady=6)

        ttk.Label(dlg, text="时间戳长度(字节):").grid(row=5, column=0, sticky=tk.W, padx=10, pady=6)
        length_entry = ttk.Entry(dlg, textvariable=length_var, width=12)
        length_entry.grid(row=5, column=1, sticky=tk.W, padx=10, pady=6)

        reverse_cb = ttk.Checkbutton(dlg, text="时间戳反转", variable=reverse_var)
        reverse_cb.grid(row=6, column=0, columnspan=2, sticky=tk.W, padx=10, pady=6)

        datetime_hint_label = ttk.Label(dlg, text="", foreground='#0066cc')
        datetime_hint_label.grid(row=7, column=0, columnspan=2, sticky=tk.W, padx=10, pady=(0, 6))

        type_var.set(TYPE_TO_LABEL.get(type_var.get(), '报文长度'))

        def update_match_hint(*args):
            label = type_var.get()
            if label == '报文长度':
                hint_label.config(text="示例：343（十进制字节数）")
                value_entry.config(state='normal')
            elif label == '报文前缀(HEX)':
                hint_label.config(text="示例：716B6E657402028F（忽略空格与大小写）")
                value_entry.config(state='normal')
            elif label == '正则表达式':
                hint_label.config(text="示例：^716B6E.*  （作用于去空格HEX串，自动转大写）")
                value_entry.config(state='normal')
            else:
                hint_label.config(text="该规则匹配所有报文（建议放最后作为兜底）")
                value_entry.config(state='disabled')

        def update_format_state(*args):
            label = fmt_label_var.get()
            fmt = FORMAT_L2V.get(label, 'unix')
            if fmt == 'datetime':
                length_var.set('6')
                length_entry.config(state='disabled')
                reverse_cb.config(state='disabled')
                reverse_var.set(False)
                now = datetime.now()
                example = ''.join(f'{v:02X}' for v in [
                    now.year - 2000, now.month, now.day, now.hour, now.minute, now.second])
                datetime_hint_label.config(text=f"日期时间格式固定 6 字节，当前示例：{example}")
            else:
                length_entry.config(state='normal')
                reverse_cb.config(state='normal')
                datetime_hint_label.config(text="")

        type_var.trace_add('write', update_match_hint)
        fmt_label_var.trace_add('write', update_format_state)
        update_match_hint()
        update_format_state()

        def save():
            mt = LABEL_TO_TYPE.get(type_var.get(), 'length')
            mv = value_var.get().strip() if mt != 'default' else ''
            fmt = FORMAT_L2V.get(fmt_label_var.get(), 'unix')
            try:
                off = int(offset_var.get())
                if off < 0:
                    raise ValueError("偏移必须 >= 0")
                if fmt == 'datetime':
                    ln, rev = 6, False
                else:
                    ln = int(length_var.get())
                    rev = reverse_var.get()
                    if ln < 1 or ln > 8:
                        raise ValueError("长度必须在 1-8 之间")
                if mt == 'length':
                    try:
                        int(mv)
                    except:
                        raise ValueError("报文长度必须是整数")
                if mt in ('prefix', 'regex') and not mv:
                    raise ValueError("匹配值不能为空")
                if mt == 'regex':
                    re.compile(mv.upper())
            except ValueError as e:
                messagebox.showerror("错误", f"参数无效: {str(e)}")
                return
            except re.error as e:
                messagebox.showerror("错误", f"正则表达式无效: {e}")
                return

            new_rule = {'match_type': mt, 'match_value': mv, 'offset': off,
                        'length': ln, 'reverse': rev, 'time_format': fmt}
            if rule_index is not None:
                group['rules'][rule_index] = new_rule
            else:
                group['rules'].append(new_rule)
            on_saved()
            dlg.destroy()

        ttk.Button(dlg, text="保存", command=save).grid(row=8, column=0, padx=10, pady=15)
        ttk.Button(dlg, text="取消", command=dlg.destroy).grid(row=8, column=1, padx=10, pady=15, sticky=tk.W)

    # ================== 自定义报文：解析器 ==================
    def parse_packet_content(self, content):
        if not content or not content.strip():
            return None, "报文内容为空"
        try:
            no_comment = []
            in_comment = False
            for ch in content:
                if ch == '#':
                    in_comment = not in_comment
                    continue
                if not in_comment:
                    no_comment.append(ch)
            if in_comment:
                raise ValueError("注释未闭合：存在未配对的 #")
            text = ''.join(no_comment)

            tokens = []
            i = 0
            n = len(text)
            literal = []

            def flush_literal():
                nonlocal literal
                s = re.sub(r'\s', '', ''.join(literal)).upper()
                if s:
                    if len(s) % 2 != 0:
                        raise ValueError(f"十六进制字符数为奇数: {s}")
                    try:
                        bytes.fromhex(s)
                    except ValueError:
                        raise ValueError(f"无效的十六进制内容: {s}")
                    tokens.append(('literal', s))
                literal = []

            while i < n:
                ch = text[i]
                if ch == '[':
                    flush_literal()
                    j = text.find(']', i)
                    if j < 0:
                        raise ValueError("时间戳占位符 '[' 未闭合")
                    tokens.append(self._parse_ts_token(text[i + 1:j]))
                    i = j + 1
                elif ch == '{':
                    flush_literal()
                    j = text.find('}', i)
                    if j < 0:
                        raise ValueError("变化占位符 '{' 未闭合")
                    tokens.append(self._parse_change_token(text[i + 1:j]))
                    i = j + 1
                else:
                    literal.append(ch)
                    i += 1
            flush_literal()

            if not tokens:
                raise ValueError("报文内容为空（处理注释后）")
            total_bytes = 0
            for t in tokens:
                if t[0] == 'literal':
                    total_bytes += len(t[1]) // 2
                elif t[0] == 'ts_unix':
                    total_bytes += 4
                elif t[0] == 'ts_datetime':
                    total_bytes += 6
                elif t[0] in ('random', 'random_global', 'increment', 'list', 'list_global'):
                    total_bytes += t[2]
            if total_bytes == 0:
                raise ValueError("报文内容为空")
            return tokens, None
        except ValueError as e:
            return None, str(e)

    def _parse_ts_token(self, inner):
        s = inner.strip()
        if not s:
            raise ValueError("时间戳占位符不能为空")
        offset_hours = 0
        m = re.search(r'([+-])\s*(\d+)', s)
        if m:
            offset_hours = int(m.group(2)) * (1 if m.group(1) == '+' else -1)
            s = s[:m.start()] + ' ' + s[m.end():]
        reverse = False
        if re.search(r'\bR\b', s, re.IGNORECASE):
            reverse = True
            s = re.sub(r'\bR\b', ' ', s, flags=re.IGNORECASE)
        hex_str = re.sub(r'\s', '', s).upper()
        try:
            raw = bytes.fromhex(hex_str)
        except ValueError:
            raise ValueError(f"时间戳占位符内容无效: [{inner}]")
        if len(raw) == 4:
            return ('ts_unix', hex_str, offset_hours, reverse)
        elif len(raw) == 6:
            return ('ts_datetime', hex_str, offset_hours, reverse)
        else:
            raise ValueError(f"时间戳占位符必须为 4 或 6 字节，当前 {len(raw)} 字节: [{inner}]")

    def _parse_change_token(self, inner):
        s = inner.strip()
        if not s:
            raise ValueError("变化占位符不能为空")
        m_t_range = re.search(r'T\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)', s, re.IGNORECASE)
        m_l_range = re.search(r'L\s*\(\s*([^)]+)\s*\)', s, re.IGNORECASE)
        m_t = re.search(r'\bT\b', s, re.IGNORECASE)
        m_p = re.search(r'\bP\b', s, re.IGNORECASE)
        m_l = re.search(r'\bL\b', s, re.IGNORECASE)

        hex_part = s
        hex_part = re.sub(r'T\s*\([^)]*\)', '', hex_part, flags=re.IGNORECASE)
        hex_part = re.sub(r'L\s*\([^)]*\)', '', hex_part, flags=re.IGNORECASE)
        hex_part = re.sub(r'\b[TPL]\b', '', hex_part, flags=re.IGNORECASE)
        hex_str = re.sub(r'\s', '', hex_part).upper()

        if not hex_str:
            raise ValueError(f"变化占位符缺少初始十六进制内容: {{{inner}}}")
        if len(hex_str) % 2 != 0:
            raise ValueError(f"变化占位符十六进制长度必须为偶数: {{{inner}}}")
        try:
            raw = bytes.fromhex(hex_str)
        except ValueError:
            raise ValueError(f"变化占位符十六进制内容无效: {{{inner}}}")

        nbytes = len(raw)
        max_val = (1 << (nbytes * 8)) - 1

        if m_t_range:
            lo, hi = int(m_t_range.group(1)), int(m_t_range.group(2))
            if lo > hi:
                raise ValueError(f"随机范围下限大于上限: T({lo},{hi})")
            if lo < 0 or hi > max_val:
                raise ValueError(f"随机范围超出 {nbytes} 字节允许范围 0-{max_val}: T({lo},{hi})")
            return ('random', hex_str, nbytes, lo, hi)
        if m_t:
            return ('random_global', hex_str, nbytes, 0, max_val)
        if m_p:
            return ('increment', hex_str, nbytes, 0, max_val)
        if m_l_range:
            vals = []
            for v in m_l_range.group(1).split(','):
                v = v.strip()
                if not v:
                    continue
                try:
                    val = int(v)
                except ValueError:
                    raise ValueError(f"列表值必须是十进制整数: {v}")
                if val < 0 or val > max_val:
                    raise ValueError(f"列表值 {val} 超出 {nbytes} 字节允许范围 0-{max_val}")
                vals.append(val)
            if not vals:
                raise ValueError("列表不能为空")
            return ('list', hex_str, nbytes, vals, 0, max_val)
        if m_l:
            return ('list_global', hex_str, nbytes, [], 0, max_val)
        return ('random_global', hex_str, nbytes, 0, max_val)

    # ================== 自定义报文：运行时处理 ==================
    def _process_packet(self, tokens, runtime, pkt_idx, t_range, l_list, l_interval, now):
        parts = []
        for i, t in enumerate(tokens):
            kind = t[0]
            if kind == 'literal':
                parts.append(t[1])
            elif kind == 'ts_unix':
                _, hex_str, offset_hours, reverse = t
                ts = int(time.time()) + offset_hours * 3600
                ts &= 0xFFFFFFFF
                b = ts.to_bytes(4, 'big')
                if reverse:
                    b = b[::-1]
                parts.append(b.hex().upper())
            elif kind == 'ts_datetime':
                _, hex_str, offset_hours, reverse = t
                dt = datetime.now() + timedelta(hours=offset_hours)
                b = bytes([dt.year % 100, dt.month, dt.day, dt.hour, dt.minute, dt.second])
                if reverse:
                    b = b[::-1]
                parts.append(b.hex().upper())
            elif kind == 'random':
                _, hex_str, nbytes, lo, hi = t
                parts.append(random.randint(lo, hi).to_bytes(nbytes, 'big').hex().upper())
            elif kind == 'random_global':
                _, hex_str, nbytes, _, _ = t
                max_val = (1 << (nbytes * 8)) - 1
                lo = max(0, min(t_range[0], max_val))
                hi = max(0, min(t_range[1], max_val))
                if lo > hi:
                    lo = 0
                parts.append(random.randint(lo, hi).to_bytes(nbytes, 'big').hex().upper())
            elif kind == 'increment':
                _, hex_str, nbytes, _, _ = t
                key = (pkt_idx, i)
                cur = runtime['p_value'].get(key)
                if cur is None:
                    cur = int(hex_str, 16)
                max_val = (1 << (nbytes * 8)) - 1
                parts.append(cur.to_bytes(nbytes, 'big').hex().upper())
                cur += 1
                if cur > max_val:
                    cur = 0
                runtime['p_value'][key] = cur
            elif kind == 'list':
                _, hex_str, nbytes, vals, _, _ = t
                key = (pkt_idx, i)
                if key not in runtime['l_last_change']:
                    runtime['l_last_change'][key] = now
                    runtime['l_index'][key] = 0
                last = runtime['l_last_change'][key]
                idx = runtime['l_index'][key]
                if l_interval > 0 and now - last >= l_interval:
                    steps = int((now - last) / l_interval)
                    idx = (idx + steps) % len(vals)
                    runtime['l_index'][key] = idx
                    runtime['l_last_change'][key] = last + steps * l_interval
                parts.append(vals[idx].to_bytes(nbytes, 'big').hex().upper())
            elif kind == 'list_global':
                _, hex_str, nbytes, _, _, _ = t
                if not l_list:
                    parts.append(hex_str)
                    continue
                key = (pkt_idx, i)
                if key not in runtime['l_last_change']:
                    runtime['l_last_change'][key] = now
                    runtime['l_index'][key] = 0
                last = runtime['l_last_change'][key]
                idx = runtime['l_index'][key]
                if l_interval > 0 and now - last >= l_interval:
                    steps = int((now - last) / l_interval)
                    idx = (idx + steps) % len(l_list)
                    runtime['l_index'][key] = idx
                    runtime['l_last_change'][key] = last + steps * l_interval
                max_val = (1 << (nbytes * 8)) - 1
                val = min(l_list[idx], max_val)
                parts.append(val.to_bytes(nbytes, 'big').hex().upper())
        return ''.join(parts)

    # ================== T / L 编辑弹窗 ==================
    def _open_t_range_dialog(self, owner, lo_var, hi_var, title, on_saved=None):
        dlg = tk.Toplevel(owner)
        dlg.title(title)
        dlg.geometry("340x200")
        dlg.transient(owner)
        dlg.grab_set()

        ttk.Label(dlg, text="随机范围下限:").pack(pady=(15, 2))
        ttk.Entry(dlg, textvariable=lo_var, width=15).pack()
        ttk.Label(dlg, text="随机范围上限:").pack(pady=(10, 2))
        ttk.Entry(dlg, textvariable=hi_var, width=15).pack()
        ttk.Label(dlg, text="范围 0-65535；应用到具体字节数时会自动裁剪",
                  foreground='#666').pack(pady=(8, 0))

        def save():
            try:
                lo = int(lo_var.get())
                hi = int(hi_var.get())
                if lo < 0 or hi < 0 or lo > 65535 or hi > 65535:
                    raise ValueError
                if lo > hi:
                    raise ValueError
            except ValueError:
                messagebox.showerror("错误", "范围无效：请输入 0-65535 的整数，且下限 <= 上限")
                return
            dlg.destroy()
            if on_saved:
                on_saved()

        ttk.Button(dlg, text="保存", command=save).pack(pady=15)

    def _open_l_list_dialog(self, owner, l_list_var, title, on_saved=None):
        dlg = tk.Toplevel(owner)
        dlg.title(title)
        dlg.geometry("460x200")
        dlg.transient(owner)
        dlg.grab_set()

        ttk.Label(dlg, text="列表值（十进制，用英文逗号分隔）:").pack(pady=(15, 2))
        ttk.Entry(dlg, textvariable=l_list_var, width=50).pack()
        ttk.Label(dlg, text="示例: 85, 255, 33  （每个值 0-65535，应用时会裁剪到字节范围）",
                  foreground='#666').pack(pady=(8, 0))

        def save():
            try:
                s = l_list_var.get().strip()
                if s:
                    for v in s.split(','):
                        v = v.strip()
                        if v:
                            val = int(v)
                            if val < 0 or val > 65535:
                                raise ValueError
            except ValueError:
                messagebox.showerror("错误", "列表格式无效：请输入用英文逗号分隔的 0-65535 整数")
                return
            dlg.destroy()
            if on_saved:
                on_saved()

        ttk.Button(dlg, text="保存", command=save).pack(pady=15)

    def _parse_l_list_str(self, s):
        s = (s or '').strip()
        if not s:
            return []
        vals = []
        for v in s.split(','):
            v = v.strip()
            if not v:
                continue
            vals.append(int(v))
        return vals

    # ================== 自定义报文弹窗（支持组级/连接级）==================
    def open_custom_packets_dialog(self, gi, ci):
        """
        ci=None：编辑组级报文（需 group['pkt_scope']=='组级'）
        ci>=0：编辑连接级报文
        """
        if self.sending:
            messagebox.showwarning("警告", "发送过程中不能修改自定义报文")
            return
        if gi < 0 or gi >= len(self.sub_connections):
            return
        group = self.sub_connections[gi]

        if ci is None:
            if group['pkt_scope'].get() != '组级':
                messagebox.showinfo("提示", "当前组未启用组级报文作用域")
                return
            holder = group
            title = f"组级自定义报文 - {group['name']}"
            scope_label = "组级"
        else:
            if ci < 0 or ci >= len(group['connections']):
                return
            holder = group['connections'][ci]
            title = f"自定义报文 - {group['name']} 连接 {ci + 1}（连接级）"
            scope_label = "连接级"

        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.geometry("1000x660")
        dlg.minsize(800, 500)
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="语法: [...] 时间戳(4B Unix / 6B 年月日时分秒，可 -N/+N 小时、R 反转)  "
                            "{...} 变化(T随机/P自增/L列表/无标记=T)  #...# 注释(成对)。"
                            "一条报文项可多行，最终拼接为 1 个 UDP 包。",
                  foreground='#444', wraplength=940, justify=tk.LEFT).pack(fill=tk.X, padx=10, pady=(10, 5))

        tl_frame = ttk.Frame(dlg)
        tl_frame.pack(fill=tk.X, padx=10, pady=5)

        def update_tl_buttons(*args):
            if not dlg.winfo_exists():
                return
            for w in tl_frame.winfo_children():
                w.destroy()
            scope = group['tl_scope'].get()
            if scope == '连接级':
                ttk.Button(tl_frame, text="编辑连接级T范围",
                           command=lambda: self._open_t_range_dialog(
                               dlg, holder['t_range_lo'], holder['t_range_hi'],
                               "编辑T范围（连接级）", update_tl_buttons)).pack(side=tk.LEFT, padx=(0, 5))
                ttk.Button(tl_frame, text="编辑连接级L列表",
                           command=lambda: self._open_l_list_dialog(
                               dlg, holder['l_list_str'],
                               "编辑L列表（连接级）", update_tl_buttons)).pack(side=tk.LEFT, padx=(0, 5))
                ttk.Label(tl_frame, text=f"当前 T范围: [{holder['t_range_lo'].get()}, {holder['t_range_hi'].get()}]  "
                                         f"L列表: {holder['l_list_str'].get() or '(空)'}",
                          foreground='#080').pack(side=tk.LEFT, padx=(10, 0))
            else:
                ttk.Label(tl_frame, text=f"当前使用【组级】T/L 配置  T范围: [{group['t_range_lo'].get()}, "
                                         f"{group['t_range_hi'].get()}]  L列表: {group['l_list_str'].get() or '(空)'}",
                          foreground='#066').pack(side=tk.LEFT)

        trace_id = group['tl_scope'].trace_add('write', lambda *a: update_tl_buttons())
        update_tl_buttons()

        tree_frame = ttk.Frame(dlg)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ('idx', 'content', 'remark', 'l_interval')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)
        tree.heading('idx', text='序号')
        tree.heading('content', text='报文内容（摘要）')
        tree.heading('remark', text='备注')
        tree.heading('l_interval', text='L变化间隔(秒)')
        tree.column('idx', width=50, anchor='center')
        tree.column('content', width=560, anchor='w')
        tree.column('remark', width=180, anchor='w')
        tree.column('l_interval', width=100, anchor='center')
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sb = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        def refresh():
            for item in tree.get_children():
                tree.delete(item)
            for i, pkt in enumerate(holder['custom_packets']):
                preview = pkt['content'].replace('\n', ' ')[:120]
                tree.insert('', tk.END, iid=str(i),
                            values=(i + 1, preview, pkt.get('remark', ''), pkt.get('l_interval', 10)))
            if ci is None:
                n = len(holder['custom_packets'])
                group['pkt_count_label'].config(text=f"(共 {n} 条组级报文)")
            else:
                holder['custom_count_var'].set(f"已配置 {len(holder['custom_packets'])} 条报文")
            for c in group['connections']:
                try:
                    c['_rebuild_cell']()
                except:
                    pass

        def add_packet():
            holder['custom_packets'].append({
                'content': '', 'remark': '', 'l_interval': 10.0, 'tokens': None})
            refresh()
            self._edit_custom_packet(dlg, holder, len(holder['custom_packets']) - 1, refresh)

        def edit_selected():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("提示", "请先选择一条报文")
                return
            self._edit_custom_packet(dlg, holder, int(sel[0]), refresh)

        def delete_selected():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("提示", "请先选择一条报文")
                return
            idx = int(sel[0])
            if messagebox.askyesno("确认", "确定删除该报文项？"):
                del holder['custom_packets'][idx]
                refresh()

        def move_up():
            sel = tree.selection()
            if not sel:
                return
            idx = int(sel[0])
            if idx > 0:
                holder['custom_packets'][idx], holder['custom_packets'][idx - 1] = \
                    holder['custom_packets'][idx - 1], holder['custom_packets'][idx]
                refresh()
                tree.selection_set(str(idx - 1))

        def move_down():
            sel = tree.selection()
            if not sel:
                return
            idx = int(sel[0])
            if idx < len(holder['custom_packets']) - 1:
                holder['custom_packets'][idx], holder['custom_packets'][idx + 1] = \
                    holder['custom_packets'][idx + 1], holder['custom_packets'][idx]
                refresh()
                tree.selection_set(str(idx + 1))

        tree.bind('<Double-1>', lambda e: edit_selected())

        btn_row = ttk.Frame(dlg)
        btn_row.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(btn_row, text="+ 添加报文项", command=add_packet).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="编辑选中", command=edit_selected).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="删除选中", command=delete_selected).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="上移", command=move_up).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="下移", command=move_down).pack(side=tk.LEFT, padx=(0, 5))

        def on_close():
            try:
                group['tl_scope'].trace_remove('write', trace_id)
            except:
                pass
            dlg.destroy()

        close_row = ttk.Frame(dlg)
        close_row.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(close_row, text="关闭", command=on_close).pack(side=tk.RIGHT)
        dlg.protocol("WM_DELETE_WINDOW", on_close)

        refresh()

    def _edit_custom_packet(self, parent, holder, pkt_idx, on_saved):
        """编辑报文项。窗口自适应，错误信息显示在可滚动 Text 中，不溢出。"""
        pkt = holder['custom_packets'][pkt_idx]

        dlg = tk.Toplevel(parent)
        dlg.title("编辑报文项" if pkt.get('content') else "添加报文项")
        dlg.geometry("920x740")
        dlg.minsize(720, 560)
        dlg.transient(parent)
        dlg.grab_set()

        hint_text = (
            "语法说明：\n"
            "  [xx xx xx xx]         4 字节 Unix 时间戳（int32 大端）\n"
            "  [xx xx xx xx xx xx]   6 字节日期时间（年2位/21世纪、月、日、时、分、秒）\n"
            "    后缀: -N 减N小时  +N 加N小时  R 反转字节，可组合，如 [.. R -8]\n"
            "  {xx T(下限,上限)}     随机（十进制范围，不能超出字节上限）\n"
            "  {xx T}                用全局/组级/连接级的 T 范围\n"
            "  {xx P}                自增（从初始值开始，超上限回绕到 0）\n"
            "  {xx L(85,255,33)}     列表循环（十进制值）\n"
            "  {xx L}                用全局/组级/连接级的 L 列表\n"
            "  {xx}                  无标记，默认按 T（全局范围）处理\n"
            "  #...#                 注释（成对），发送前删除，未闭合报错"
        )
        hint_label = ttk.Label(dlg, text=hint_text, foreground='#555', justify=tk.LEFT,
                               font=('Courier', 9))
        hint_label.pack(fill=tk.X, padx=10, pady=(10, 5))

        def adjust_hint_wrap(event=None):
            try:
                w = dlg.winfo_width()
                if w > 200:
                    hint_label.config(wraplength=w - 40)
            except:
                pass

        dlg.bind('<Configure>', adjust_hint_wrap)
        dlg.after(30, adjust_hint_wrap)

        ttk.Label(dlg, text="报文内容（可多行，最终拼成 1 个 UDP 包）:").pack(anchor='w', padx=10)
        text_frame = ttk.Frame(dlg)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))
        content_text = tk.Text(text_frame, height=10, width=80, wrap=tk.WORD,
                               font=('Courier', 10))
        csb = ttk.Scrollbar(text_frame, orient='vertical', command=content_text.yview)
        content_text.configure(yscrollcommand=csb.set)
        content_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        csb.pack(side=tk.RIGHT, fill=tk.Y)
        content_text.insert('1.0', pkt.get('content', ''))

        remark_frame = ttk.Frame(dlg)
        remark_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(remark_frame, text="备注:").pack(side=tk.LEFT)
        remark_var = tk.StringVar(value=pkt.get('remark', ''))
        ttk.Entry(remark_frame, textvariable=remark_var, width=60).pack(
            side=tk.LEFT, padx=(5, 0), fill=tk.X, expand=True)

        li_frame = ttk.Frame(dlg)
        li_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(li_frame, text="L变化间隔(秒):").pack(side=tk.LEFT)
        li_var = tk.StringVar(value=str(pkt.get('l_interval', 10)))
        ttk.Entry(li_frame, textvariable=li_var, width=10).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Label(li_frame, text="(仅对本报文中的 L 占位符有效)", foreground='#666').pack(side=tk.LEFT, padx=(5, 0))

        ttk.Label(dlg, text="校验结果:").pack(anchor='w', padx=10)
        err_frame = ttk.Frame(dlg)
        err_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        error_text = tk.Text(err_frame, height=4, wrap=tk.CHAR, fg='#c00',
                             bg='#fff8f8', font=('Courier', 9))
        esb = ttk.Scrollbar(err_frame, orient='vertical', command=error_text.yview)
        error_text.configure(yscrollcommand=esb.set)
        error_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        esb.pack(side=tk.RIGHT, fill=tk.Y)
        error_text.config(state='disabled')

        def set_error(msg, color='#c00'):
            error_text.config(state='normal', fg=color)
            error_text.delete('1.0', tk.END)
            error_text.insert('1.0', msg)
            error_text.config(state='disabled')

        def do_validate():
            content = content_text.get('1.0', tk.END)
            tokens, err = self.parse_packet_content(content)
            if err:
                set_error(f"错误: {err}")
                return None
            total_bytes = sum(
                len(t[1]) // 2 if t[0] == 'literal'
                else (4 if t[0] == 'ts_unix' else (6 if t[0] == 'ts_datetime' else t[2]))
                for t in tokens)
            set_error(f"解析成功：共 {len(tokens)} 个片段，{total_bytes} 字节", color='#080')
            return tokens

        def do_save():
            tokens = do_validate()
            if tokens is None:
                return
            try:
                li = float(li_var.get())
                if li < 0:
                    raise ValueError
            except ValueError:
                set_error("L变化间隔必须 >= 0")
                return
            pkt['content'] = content_text.get('1.0', tk.END).rstrip('\n')
            pkt['remark'] = remark_var.get()
            pkt['l_interval'] = li
            pkt['tokens'] = tokens
            on_saved()
            dlg.destroy()

        btn_row = ttk.Frame(dlg)
        btn_row.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_row, text="校验", command=do_validate).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="保存", command=do_save).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="取消", command=dlg.destroy).pack(side=tk.LEFT)

    # ================== 批量操作 ==================
    def batch_generate_connections(self, group_index):
        if self.sending:
            messagebox.showwarning("警告", "发送过程中不能批量生成连接")
            return
        if group_index < 0 or group_index >= len(self.sub_connections):
            return
        group = self.sub_connections[group_index]

        dialog = tk.Toplevel(self.root)
        dialog.title("批量生成连接")
        dialog.geometry("300x220")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="生成数量:").pack(pady=(20, 5))
        count_var = tk.StringVar(value="1")
        ttk.Entry(dialog, textvariable=count_var, width=15).pack()

        max_port = 0
        for conn in group['connections']:
            try:
                port = int(conn['local_port'].get())
                if port > max_port:
                    max_port = port
            except:
                pass
        default_start_port = max_port + 1 if max_port >= 10010 else 10010

        ttk.Label(dialog, text="起始本机端口:").pack(pady=(10, 5))
        start_port_var = tk.StringVar(value=str(default_start_port))
        ttk.Entry(dialog, textvariable=start_port_var, width=15).pack()

        def apply():
            try:
                count = int(count_var.get())
                start_port = int(start_port_var.get())
                if count <= 0:
                    raise ValueError("数量必须大于0")
                if start_port < 0 or start_port > 65535:
                    raise ValueError("端口必须在0-65535之间")
                if start_port + count - 1 > 65535:
                    raise ValueError("端口超出范围（最大65535）")
                for i in range(count):
                    conn = {
                        'local_ip': tk.StringVar(value="0.0.0.0"),
                        'local_port': tk.StringVar(value=str(start_port + i)),
                        'file_path': tk.StringVar(),
                        'enabled': tk.BooleanVar(value=True),
                        'mode': tk.StringVar(value="日志文件"),
                        'custom_packets': [],
                        'custom_count_var': tk.StringVar(value=""),
                        't_range_lo': tk.StringVar(value='0'),
                        't_range_hi': tk.StringVar(value='255'),
                        'l_list_str': tk.StringVar(value=''),
                        'runtime': {'p_value': {}, 'l_index': {}, 'l_last_change': {}},
                        'packets_cache': None,
                        'cache_time': None,
                        'packet_index': 0,
                        'last_send_time': 0,
                        '_rebuild_cell': lambda: None,
                    }
                    conn['mode'].trace_add('write', lambda *a, c=conn: c['_rebuild_cell']())
                    group['connections'].append(conn)
                self._refresh_group_ui(group_index)
                self.log_send_message(f"组 {group['name']} 已批量生成 {count} 个连接，端口从 {start_port} 开始")
                dialog.destroy()
            except ValueError as e:
                messagebox.showerror("错误", str(e))

        ttk.Button(dialog, text="生成", command=apply).pack(pady=20)

    def global_enable_all(self, enable):
        for group in self.sub_connections:
            for conn in group['connections']:
                conn['enabled'].set(enable)
        self.log_send_message(f"已{'启用' if enable else '禁用'}所有连接")

    def batch_set_ports_group(self, group_index):
        if group_index < 0 or group_index >= len(self.sub_connections):
            return
        group = self.sub_connections[group_index]
        if not group['connections']:
            messagebox.showinfo("提示", "该组没有连接")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("批量设置本机端口")
        dialog.geometry("300x150")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text="起始端口号:").pack(pady=(20, 5))
        start_port_var = tk.StringVar(value="10010")
        ttk.Entry(dialog, textvariable=start_port_var, width=15).pack()

        def apply():
            try:
                start = int(start_port_var.get())
                for i, conn in enumerate(group['connections']):
                    conn['local_port'].set(str(start + i))
                self.log_send_message(f"组 {group['name']} 已批量设置本机端口，从{start}开始递增")
                dialog.destroy()
            except ValueError:
                messagebox.showerror("错误", "请输入有效端口号")

        ttk.Button(dialog, text="应用", command=apply).pack(pady=20)

    def batch_set_ips_group(self, group_index):
        if group_index < 0 or group_index >= len(self.sub_connections):
            return
        group = self.sub_connections[group_index]
        if not group['connections']:
            messagebox.showinfo("提示", "该组没有连接")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("批量设置本机IP")
        dialog.geometry("350x200")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text="起始IP:").pack(pady=(20, 5))
        start_ip_var = tk.StringVar(value="192.168.1.100")
        ttk.Entry(dialog, textvariable=start_ip_var, width=20).pack()
        ttk.Label(dialog, text="数量:").pack(pady=(10, 5))
        count_var = tk.StringVar(value=str(len(group['connections'])))
        ttk.Entry(dialog, textvariable=count_var, width=10).pack()

        def apply():
            try:
                start_ip = start_ip_var.get().strip()
                count = int(count_var.get())
                if count <= 0:
                    raise ValueError("数量必须大于0")
                if count > len(group['connections']):
                    count = len(group['connections'])
                parts = start_ip.split('.')
                if len(parts) != 4:
                    raise ValueError("IP格式错误")
                nums = [int(p) for p in parts]
                for p in nums:
                    if p < 0 or p > 255:
                        raise ValueError("IP每段必须在0-255之间")
                for i in range(count):
                    conn = group['connections'][i]
                    conn['local_ip'].set(f"{nums[0]}.{nums[1]}.{nums[2]}.{nums[3]}")
                    nums[3] += 1
                    if nums[3] > 255:
                        nums[3] = 0
                        nums[2] += 1
                self.log_send_message(f"组 {group['name']} 已批量设置本机IP，从{start_ip}开始，共{count}个")
                dialog.destroy()
            except ValueError as e:
                messagebox.showerror("错误", str(e))

        ttk.Button(dialog, text="应用", command=apply).pack(pady=20)

    def batch_select_files_group(self, group_index):
        if group_index < 0 or group_index >= len(self.sub_connections):
            return
        group = self.sub_connections[group_index]
        filenames = filedialog.askopenfilenames(
            title=f"为组 {group['name']} 批量选择日志文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if filenames:
            log_conns = [c for c in group['connections'] if c['mode'].get() == '日志文件']
            for i, filename in enumerate(filenames):
                if i < len(log_conns):
                    log_conns[i]['file_path'].set(filename)
                    log_conns[i]['enabled'].set(True)
            self.log_send_message(
                f"组 {group['name']} 已批量选择 {min(len(filenames), len(log_conns))} 个文件")

    def browse_conn_file(self, group_index, conn_index):
        if group_index < 0 or group_index >= len(self.sub_connections):
            return
        group = self.sub_connections[group_index]
        if conn_index < 0 or conn_index >= len(group['connections']):
            return
        filename = filedialog.askopenfilename(
            title=f"选择日志文件 (组 {group['name']} 连接 {conn_index + 1})",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if filename:
            group['connections'][conn_index]['file_path'].set(filename)
            self.log_send_message(f"组 {group['name']} 连接 {conn_index + 1} 已选择文件")

    # ================== 日志与状态 ==================
    def log_send_message(self, message):
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        try:
            self.send_log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.send_log_text.see(tk.END)
            self.root.update_idletasks()
        except:
            pass

    def log_recv_message(self, message):
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        try:
            self.recv_log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.recv_log_text.see(tk.END)
            self.root.update_idletasks()
        except:
            pass

    def update_status(self, message):
        self.status_var.set(message)
        self.root.update_idletasks()

    def update_stats(self):
        if self.start_time:
            elapsed = datetime.now() - self.start_time
            hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            if elapsed.total_seconds() > 0:
                rate = self.total_packets_sent / elapsed.total_seconds()
                self.perf_var.set(f"速率: {rate:.1f} 包/秒")
        else:
            time_str = "00:00:00"
        self.stats_var.set(f"总时长: {time_str} | 发送报文: {self.total_packets_sent} | 循环次数: {self.loop_count}")

    def high_precision_sleep(self, seconds):
        if seconds <= 0:
            return
        if self.use_high_precision_timing and seconds < 0.01:
            start = time.perf_counter()
            while time.perf_counter() - start < seconds:
                if self.stop_event.is_set():
                    break
                time.sleep(0.000001)
        else:
            start = time.perf_counter()
            sleep_time = seconds
            while sleep_time > 0:
                if self.stop_event.is_set():
                    break
                if sleep_time > 0.01:
                    time.sleep(0.01)
                else:
                    time.sleep(sleep_time)
                elapsed = time.perf_counter() - start
                sleep_time = seconds - elapsed

    # ================== 发送控制 ==================
    def start_sending(self):
        if self.sending:
            return

        enabled_conns = []
        for gi, group in enumerate(self.sub_connections):
            try:
                interval = float(group['interval'].get())
                if interval < 0.0001:
                    raise ValueError("间隔不能小于0.0001秒")
            except ValueError as e:
                messagebox.showerror("错误", f"组 {group['name']} 的发送间隔设置不正确: {str(e)}")
                return

            try:
                target_port = int(group['target_port'].get())
            except ValueError:
                messagebox.showerror("错误", f"组 {group['name']} 的目标端口格式错误")
                return

            ts_live = group['timestamp_live'].get()
            ts_format = group['timestamp_format'].get()
            if ts_format not in ('unix', 'datetime'):
                ts_format = 'unix'
            if ts_live:
                if ts_format == 'datetime':
                    ts_length, ts_reverse = 6, False
                    try:
                        ts_offset = int(group['timestamp_offset'].get())
                        if ts_offset < 0:
                            raise ValueError("偏移必须 >= 0")
                    except ValueError as e:
                        messagebox.showerror("错误", f"组 {group['name']} 时间戳偏移设置不正确: {str(e)}")
                        return
                else:
                    ts_reverse = group['timestamp_reverse'].get()
                    try:
                        ts_offset = int(group['timestamp_offset'].get())
                        ts_length = int(group['timestamp_length'].get())
                        if ts_offset < 0 or ts_length < 1 or ts_length > 8:
                            raise ValueError("偏移不能为负，长度必须在1-8之间")
                    except ValueError as e:
                        messagebox.showerror("错误", f"组 {group['name']} 时间戳配置不正确: {str(e)}")
                        return
            else:
                ts_offset, ts_length, ts_reverse = 0, 0, False

            if ts_live:
                for ri, rule in enumerate(group['rules']):
                    mt = rule.get('match_type', '')
                    fmt = rule.get('time_format', 'unix')
                    if mt not in ('length', 'prefix', 'regex', 'default'):
                        messagebox.showerror("错误", f"组 {group['name']} 第 {ri + 1} 条规则类型无效")
                        return
                    if fmt not in ('unix', 'datetime'):
                        messagebox.showerror("错误", f"组 {group['name']} 第 {ri + 1} 条规则时间格式无效")
                        return
                    try:
                        off = int(rule.get('offset', 0))
                        if off < 0:
                            raise ValueError()
                        if fmt == 'unix':
                            ln = int(rule.get('length', 4))
                            if ln < 1 or ln > 8:
                                raise ValueError()
                    except Exception:
                        messagebox.showerror("错误", f"组 {group['name']} 第 {ri + 1} 条规则的偏移/长度无效")
                        return
                    if mt == 'length':
                        try:
                            int(rule.get('match_value', ''))
                        except:
                            messagebox.showerror("错误", f"组 {group['name']} 第 {ri + 1} 条规则的匹配值不是整数")
                            return
                    if mt == 'regex':
                        try:
                            re.compile(rule.get('match_value', '').upper())
                        except re.error as e:
                            messagebox.showerror("错误", f"组 {group['name']} 第 {ri + 1} 条规则正则无效: {e}")
                            return

            compiled_rules = self._compile_rules(group['rules']) if ts_live else []

            for ci, conn in enumerate(group['connections']):
                if not conn['enabled'].get():
                    continue

                if conn['mode'].get() == '自定义报文':
                    # 决定报文来源
                    if group['pkt_scope'].get() == '组级':
                        pkts = group['custom_packets']
                        src_label = "组级"
                    else:
                        pkts = conn['custom_packets']
                        src_label = "连接级"

                    if not pkts:
                        messagebox.showerror(
                            "错误",
                            f"组 {group['name']} 连接 {ci + 1} 自定义报文（{src_label}）为空，请先配置")
                        return

                    for pi, pkt in enumerate(pkts):
                        tokens, err = self.parse_packet_content(pkt.get('content', ''))
                        if err:
                            messagebox.showerror(
                                "错误",
                                f"组 {group['name']} 连接 {ci + 1} 报文#{pi + 1}（{src_label}）解析失败: {err}")
                            return
                        pkt['tokens'] = tokens

                    try:
                        if group['tl_scope'].get() == '组级':
                            t_lo = int(group['t_range_lo'].get())
                            t_hi = int(group['t_range_hi'].get())
                            l_list = self._parse_l_list_str(group['l_list_str'].get())
                        else:
                            t_lo = int(conn['t_range_lo'].get())
                            t_hi = int(conn['t_range_hi'].get())
                            l_list = self._parse_l_list_str(conn['l_list_str'].get())
                        if t_lo < 0 or t_hi < 0 or t_lo > 65535 or t_hi > 65535 or t_lo > t_hi:
                            raise ValueError("T范围无效")
                        for v in l_list:
                            if v < 0 or v > 65535:
                                raise ValueError("L列表值无效")
                    except ValueError as e:
                        messagebox.showerror(
                            "错误", f"组 {group['name']} 连接 {ci + 1} 的 T/L 配置无效: {e}")
                        return

                    need_l = False
                    for pkt in pkts:
                        for t in (pkt.get('tokens') or []):
                            if t[0] == 'list_global':
                                need_l = True
                                break
                        if need_l:
                            break
                    if need_l and not l_list:
                        messagebox.showerror(
                            "错误",
                            f"组 {group['name']} 连接 {ci + 1} 使用了 {{... L}} 但 L 列表为空")
                        return

                    enabled_conns.append({
                        'type': 'custom',
                        'conn': conn,
                        'group_name': group['name'],
                        'ci': ci,
                        'target_port': target_port,
                        'interval': interval,
                        't_range': (t_lo, t_hi),
                        'l_list': l_list,
                        'packets': pkts,
                    })
                else:
                    if not conn['file_path'].get():
                        messagebox.showerror(
                            "错误", f"组 {group['name']} 连接 {ci + 1} 未选择日志文件")
                        return
                    if not os.path.exists(conn['file_path'].get()):
                        messagebox.showerror(
                            "错误", f"组 {group['name']} 连接 {ci + 1} 的文件不存在")
                        return
                    enabled_conns.append({
                        'type': 'log',
                        'conn': conn,
                        'group_name': group['name'],
                        'ci': ci,
                        'target_port': target_port,
                        'ts_offset': ts_offset,
                        'ts_length': ts_length,
                        'ts_live': ts_live,
                        'ts_reverse': ts_reverse,
                        'ts_format': ts_format,
                        'interval': interval,
                        'rules': compiled_rules,
                    })

        if not enabled_conns:
            messagebox.showerror("错误", "请至少启用一个连接")
            return

        self.stop_event.clear()
        self.start_time = datetime.now()
        self.total_packets_sent = 0
        self.loop_count = 0
        self.loop_sending = self.loop_var.get()
        self.sending = True
        self.paused = False
        self.heartbeat_listening = True

        self.start_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress.start()
        self.add_group_btn.config(state=tk.DISABLED)

        if self.executor:
            self.executor.shutdown(wait=False)
        max_workers = min(len(enabled_conns), 64)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.futures = []

        target_ip = self.target_ip_var.get()
        self.log_send_message(f"开始发送，全局目标IP: {target_ip}，启用连接总数: {len(enabled_conns)}")

        for item in enabled_conns:
            if item['type'] == 'custom':
                future = self.executor.submit(
                    self.send_custom_for_connection,
                    item['conn'], item['packets'], item['interval'], item['group_name'],
                    item['ci'] + 1, target_ip, item['target_port'],
                    item['t_range'], item['l_list'])
            else:
                future = self.executor.submit(
                    self.send_packets_for_connection,
                    item['conn'], item['interval'], item['group_name'], item['ci'] + 1,
                    target_ip, item['target_port'],
                    item['ts_offset'], item['ts_length'],
                    item['ts_live'], item['ts_reverse'], item['ts_format'],
                    item['rules'])
            self.futures.append(future)

        threading.Thread(target=self.update_stats_periodically, daemon=True).start()
        threading.Thread(target=self.monitor_futures, daemon=True).start()

    def update_stats_periodically(self):
        while self.sending:
            self.update_stats()
            time.sleep(1)

    def monitor_futures(self):
        while self.sending and self.futures:
            done = sum(1 for f in self.futures if f.done())
            if done == len(self.futures) and not self.loop_sending:
                self.safe_stop_sending()
                break
            time.sleep(0.5)

    def pause_sending(self):
        if self.paused:
            self.paused = False
            self.pause_btn.config(text="暂停")
            self.update_status("继续发送...")
        else:
            self.paused = True
            self.pause_btn.config(text="继续")
            self.update_status("发送已暂停")

    def stop_sending(self):
        self.safe_stop_sending()

    def safe_stop_sending(self):
        if not self.sending:
            return
        self.log_send_message("正在停止发送...")
        self.sending = False
        self.paused = False
        self.loop_sending = False
        self.heartbeat_listening = False
        self.stop_event.set()
        threading.Thread(target=self._cleanup_resources, daemon=True).start()

    def _cleanup_resources(self):
        try:
            for key in list(self.receive_threads.keys()):
                t = self.receive_threads.get(key)
                if t and t.is_alive():
                    t.join(timeout=1.0)
            with self.socket_lock:
                for sock in list(self.udp_sockets.values()):
                    try:
                        sock.close()
                    except:
                        pass
                self.udp_sockets.clear()

            if self.executor:
                for f in self.futures:
                    if not f.done():
                        f.cancel()
                try:
                    self.executor.shutdown(wait=True, timeout=2.0)
                except:
                    pass
            self.root.after(0, self._update_ui_after_stop)
        except Exception as e:
            self.log_send_message(f"清理资源时出错: {str(e)}")
            self.root.after(0, self._update_ui_after_stop)

    def _update_ui_after_stop(self):
        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED)
        self.pause_btn.config(text="暂停")
        self.stop_btn.config(state=tk.DISABLED)
        self.progress.stop()
        self.add_group_btn.config(state=tk.NORMAL)
        self.update_status("发送已停止")
        self.update_stats()
        self.log_send_message("所有连接发送已安全停止")

    # ================== 日志模式发送线程 ==================
    def _compile_rules(self, rules):
        compiled = []
        for r in rules:
            nr = dict(r)
            if nr.get('match_type') == 'regex':
                try:
                    nr['_regex'] = re.compile(nr.get('match_value', '').upper())
                except re.error:
                    nr['_regex'] = None
            compiled.append(nr)
        return compiled

    def _match_rule(self, hex_packet, rule):
        mt = rule.get('match_type', '')
        if mt == 'default':
            return True
        mv = rule.get('match_value', '')
        if mt == 'length':
            try:
                return (len(hex_packet) // 2) == int(mv)
            except:
                return False
        elif mt == 'prefix':
            return hex_packet.upper().startswith(mv.replace(' ', '').upper())
        elif mt == 'regex':
            reg = rule.get('_regex')
            if reg is None:
                try:
                    reg = re.compile(mv.upper())
                except:
                    return False
            return reg.match(hex_packet.upper()) is not None
        return False

    def _write_timestamp(self, hex_packet, offset, length, reverse=False, time_format='unix'):
        if time_format == 'datetime':
            start_idx = offset * 2
            ts_chars = 12
            if len(hex_packet) < start_idx + ts_chars:
                return hex_packet
            now = datetime.now()
            year = now.year - 2000
            if year < 0:
                year = 0
            elif year > 99:
                year = 99
            parts = [year, now.month, now.day, now.hour, now.minute, now.second]
            ts_hex = ''.join(f'{v:02X}' for v in parts)
            return hex_packet[:start_idx] + ts_hex + hex_packet[start_idx + ts_chars:]
        else:
            if length <= 0 or length > 8:
                return hex_packet
            start_idx = offset * 2
            ts_chars = length * 2
            if len(hex_packet) < start_idx + ts_chars:
                return hex_packet
            ts = int(time.time())
            mod = 1 << (length * 8)
            ts_hex = format(ts % mod, f'0{ts_chars}X')
            if reverse:
                byte_pairs = [ts_hex[i:i + 2] for i in range(0, len(ts_hex), 2)]
                ts_hex = ''.join(reversed(byte_pairs))
            return hex_packet[:start_idx] + ts_hex + hex_packet[start_idx + ts_chars:]

    def send_packets_for_connection(self, conn, interval, group_name, conn_no, target_ip, target_port,
                                    timestamp_offset, timestamp_length, ts_live, ts_reverse, ts_format, rules):
        config_key = None
        try:
            local_ip = conn['local_ip'].get()
            local_port = int(conn['local_port'].get())
            file_path = conn['file_path'].get()
            config_key = f"{local_ip}:{local_port}"

            current = time.time()
            if conn['packets_cache'] is None or conn['cache_time'] is None or current - conn['cache_time'] > 5:
                packets = self.extract_packets_from_file(file_path)
                conn['packets_cache'] = packets
                conn['cache_time'] = current
                if not packets:
                    self.log_send_message(f"[UDP] {config_key} 无有效报文，跳过")
                    return
            else:
                packets = conn['packets_cache']

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if interval < 0.001:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
            sock.bind((local_ip, local_port))
            with self.socket_lock:
                self.udp_sockets[config_key] = sock

            recv_thread = threading.Thread(target=self.listen_udp_messages, args=(config_key,))
            recv_thread.daemon = True
            self.receive_threads[config_key] = recv_thread
            recv_thread.start()

            stat_match = {}
            stat_default = 0
            loop_local = 0
            sent_this = 0
            conn['packet_index'] = 0

            while self.sending and config_key in self.udp_sockets and not self.stop_event.is_set():
                loop_local += 1
                with self.stats_lock:
                    self.loop_count = max(self.loop_count, loop_local)

                for i in range(len(packets)):
                    if not self.sending or config_key not in self.udp_sockets or self.stop_event.is_set():
                        break
                    while self.paused and self.sending and config_key in self.udp_sockets and not self.stop_event.is_set():
                        self.high_precision_sleep(0.01)
                    if not self.sending or config_key not in self.udp_sockets or self.stop_event.is_set():
                        break

                    try:
                        hex_packet = packets[conn['packet_index']]
                        if ts_live:
                            if rules:
                                hit = None
                                for ri, rule in enumerate(rules):
                                    if self._match_rule(hex_packet, rule):
                                        hit = ri
                                        break
                                if hit is not None:
                                    stat_match[hit] = stat_match.get(hit, 0) + 1
                                    r = rules[hit]
                                    fmt = r.get('time_format', 'unix')
                                    if fmt == 'datetime':
                                        updated = self._write_timestamp(
                                            hex_packet, r['offset'], 6, False, 'datetime')
                                    else:
                                        updated = self._write_timestamp(
                                            hex_packet, r['offset'], r['length'],
                                            r.get('reverse', False), 'unix')
                                else:
                                    stat_default += 1
                                    updated = self._write_timestamp(
                                        hex_packet, timestamp_offset, timestamp_length, ts_reverse, ts_format)
                            else:
                                updated = self._write_timestamp(
                                    hex_packet, timestamp_offset, timestamp_length, ts_reverse, ts_format)
                        else:
                            updated = hex_packet

                        data = bytes.fromhex(updated)
                        with self.socket_lock:
                            s = self.udp_sockets.get(config_key)
                        if s:
                            s.sendto(data, (target_ip, target_port))
                        sent_this += 1
                        conn['packet_index'] = (conn['packet_index'] + 1) % len(packets)
                        with self.packets_lock:
                            self.total_packets_sent += 1

                        if sent_this % 1000 == 0:
                            if rules:
                                detail = ", ".join(
                                    [f"规则{ri + 1}:{cnt}" for ri, cnt in sorted(stat_match.items())])
                                if stat_default:
                                    detail += f", 默认:{stat_default}"
                                self.log_send_message(
                                    f"[UDP] {config_key} -> :{target_port} 已发送 {sent_this} 个报文（匹配 {detail}）")
                            else:
                                self.log_send_message(
                                    f"[UDP] {config_key} -> :{target_port} 已发送 {sent_this} 个报文")
                    except Exception as e:
                        if self.sending:
                            self.log_send_message(f"[UDP] {config_key} -> :{target_port} 发送出错: {str(e)}")

                    current_t = time.perf_counter()
                    last = conn.get('last_send_time', 0)
                    if i < len(packets) - 1 and last > 0:
                        wait = max(0, interval - (current_t - last))
                        if wait > 0:
                            self.high_precision_sleep(wait)
                    conn['last_send_time'] = time.perf_counter()

                if not self.loop_sending:
                    break
                conn['packet_index'] = 0
                if self.sending and self.loop_sending and config_key in self.udp_sockets and not self.stop_event.is_set():
                    self.high_precision_sleep(0.1)

        except Exception as e:
            if config_key and self.sending:
                self.log_send_message(f"组 {group_name} 连接 {conn_no} [UDP] 异常: {str(e)}")
        finally:
            if config_key:
                with self.socket_lock:
                    if config_key in self.udp_sockets:
                        try:
                            self.udp_sockets[config_key].close()
                        except:
                            pass
                        del self.udp_sockets[config_key]
                if config_key in self.receive_threads:
                    del self.receive_threads[config_key]

    # ================== 自定义报文发送线程 ==================
    def send_custom_for_connection(self, conn, packets, interval, group_name, conn_no,
                                   target_ip, target_port, t_range, l_list):
        config_key = None
        try:
            local_ip = conn['local_ip'].get()
            local_port = int(conn['local_port'].get())
            config_key = f"{local_ip}:{local_port}"

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if interval < 0.001:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
            sock.bind((local_ip, local_port))
            with self.socket_lock:
                self.udp_sockets[config_key] = sock

            recv_thread = threading.Thread(target=self.listen_udp_messages, args=(config_key,))
            recv_thread.daemon = True
            self.receive_threads[config_key] = recv_thread
            recv_thread.start()

            worker_threads = []
            for pkt_idx in range(len(packets)):
                th = threading.Thread(
                    target=self._send_custom_worker,
                    args=(conn, packets, pkt_idx, config_key, target_ip, target_port,
                          interval, t_range, l_list, group_name, conn_no))
                th.daemon = True
                th.start()
                worker_threads.append(th)

            self.log_send_message(
                f"[UDP-Custom] {config_key} -> :{target_port} 启动 {len(worker_threads)} 条报文项并行发送")

            while self.sending and not self.stop_event.is_set():
                if config_key not in self.udp_sockets:
                    break
                time.sleep(0.3)

            for th in worker_threads:
                th.join(timeout=1.0)

        except Exception as e:
            if config_key and self.sending:
                self.log_send_message(f"组 {group_name} 连接 {conn_no} 自定义发送异常: {str(e)}")
        finally:
            if config_key:
                with self.socket_lock:
                    if config_key in self.udp_sockets:
                        try:
                            self.udp_sockets[config_key].close()
                        except:
                            pass
                        del self.udp_sockets[config_key]
                if config_key in self.receive_threads:
                    del self.receive_threads[config_key]

    def _send_custom_worker(self, conn, packets, pkt_idx, config_key, target_ip, target_port,
                            interval, t_range, l_list, group_name, conn_no):
        pkt = packets[pkt_idx]
        tokens = pkt.get('tokens') or []
        l_interval = pkt.get('l_interval', 10.0)
        runtime = conn['runtime']
        sent_count = 0

        while self.sending and not self.stop_event.is_set() and config_key in self.udp_sockets:
            while self.paused and self.sending and not self.stop_event.is_set() and config_key in self.udp_sockets:
                self.high_precision_sleep(0.05)
            if not self.sending or self.stop_event.is_set() or config_key not in self.udp_sockets:
                break

            try:
                now = time.time()
                hex_str = self._process_packet(tokens, runtime, pkt_idx, t_range, l_list, l_interval, now)
                data = bytes.fromhex(hex_str)
                with self.socket_lock:
                    s = self.udp_sockets.get(config_key)
                if s:
                    s.sendto(data, (target_ip, target_port))
                sent_count += 1
                with self.packets_lock:
                    self.total_packets_sent += 1

                if sent_count % 1000 == 0:
                    self.log_send_message(
                        f"[UDP-Custom] {config_key} -> :{target_port} 报文#{pkt_idx + 1} 已发送 {sent_count} 个")
            except Exception as e:
                if self.sending:
                    self.log_send_message(
                        f"[UDP-Custom] {config_key} 报文#{pkt_idx + 1} 发送出错: {str(e)}")

            self.high_precision_sleep(interval)

    # ================== 文件读取 ==================
    def extract_packets_from_file(self, file_path):
        packets = []
        content = ""
        for enc in ["utf-8", "gbk", "gb2312", "latin-1"]:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                self.log_send_message(f"读取文件出错 ({enc}): {str(e)}")
                return packets

        if not content:
            try:
                with open(file_path, 'rb') as f:
                    raw_bytes = f.read()
                content = raw_bytes.decode('utf-8', errors='replace')
            except Exception as e:
                self.log_send_message(f"文件读取彻底失败: {str(e)}")
                return packets

        for match in re.findall(r'\{([^}]+)\}', content):
            hex_str = match.replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', '')
            try:
                bytes.fromhex(hex_str)
                packets.append(hex_str)
            except ValueError:
                if self.verbose_logging.get():
                    self.log_send_message(f"跳过无效十六进制片段: {hex_str[:50]}...")

        for line in content.splitlines():
            line = line.strip()
            if not line or ('{' in line and '}' in line):
                continue
            hex_part = line.rsplit(']', 1)[1].strip() if ']' in line else line
            hex_str = hex_part.replace(' ', '').replace('\t', '')
            if not hex_str:
                continue
            try:
                bytes.fromhex(hex_str)
                packets.append(hex_str)
            except ValueError:
                if self.verbose_logging.get():
                    self.log_send_message(f"跳过无效十六进制行: {line[:80]}...")

        return packets

    def listen_udp_messages(self, config_key):
        if config_key not in self.udp_sockets:
            return
        with self.socket_lock:
            if config_key not in self.udp_sockets:
                return
            sock = self.udp_sockets[config_key]
        try:
            sock.settimeout(0.5)
            while self.heartbeat_listening and config_key in self.udp_sockets and not self.stop_event.is_set():
                try:
                    data, addr = sock.recvfrom(1024)
                    if data:
                        if self.verbose_logging.get():
                            self.log_recv_message(
                                f"[UDP] {config_key} 收到 {addr[0]}:{addr[1]} 数据: {data.hex().upper()}")
                        else:
                            self.log_recv_message(f"[UDP] {config_key} 收到 {len(data)} 字节数据")
                except socket.timeout:
                    continue
                except OSError:
                    break
                except Exception as e:
                    if self.heartbeat_listening:
                        self.log_recv_message(f"[UDP] {config_key} 接收出错: {str(e)}")
                    break
        except Exception as e:
            if self.heartbeat_listening:
                self.log_recv_message(f"[UDP] {config_key} 接收线程初始化出错: {str(e)}")

    # ================== 配置保存/加载 ==================
    def save_config(self):
        try:
            data = {
                'target_ip': self.target_ip_var.get(),
                'interval': self.interval_var.get(),
                'loop': self.loop_var.get(),
                'verbose_logging': self.verbose_logging.get(),
                'high_precision': self.high_precision_var.get(),
                'timestamp_offset': self.timestamp_offset_var.get(),
                'timestamp_length': self.timestamp_length_var.get(),
                'timestamp_live': self.timestamp_live_var.get(),
                'timestamp_reverse': self.timestamp_reverse_var.get(),
                'timestamp_format': self.timestamp_format_var.get(),
                'sub_connections': []
            }
            for group in self.sub_connections:
                group_data = {
                    'name': group['name'],
                    'target_port': group['target_port'].get(),
                    'interval': group['interval'].get(),
                    'timestamp_offset': group['timestamp_offset'].get(),
                    'timestamp_length': group['timestamp_length'].get(),
                    'timestamp_live': group['timestamp_live'].get(),
                    'timestamp_reverse': group['timestamp_reverse'].get(),
                    'timestamp_format': group['timestamp_format'].get(),
                    'tl_scope': group['tl_scope'].get(),
                    't_range_lo': group['t_range_lo'].get(),
                    't_range_hi': group['t_range_hi'].get(),
                    'l_list_str': group['l_list_str'].get(),
                    'pkt_scope': group['pkt_scope'].get(),
                    'rules': [dict(r) for r in group['rules']],
                    'custom_packets': [
                        {'content': p.get('content', ''),
                         'remark': p.get('remark', ''),
                         'l_interval': p.get('l_interval', 10)}
                        for p in group['custom_packets']
                    ],
                    'connections': []
                }
                for r in group_data['rules']:
                    r.pop('_regex', None)
                for conn in group['connections']:
                    cpkts = []
                    for p in conn['custom_packets']:
                        cpkts.append({
                            'content': p.get('content', ''),
                            'remark': p.get('remark', ''),
                            'l_interval': p.get('l_interval', 10),
                        })
                    group_data['connections'].append({
                        'local_ip': conn['local_ip'].get(),
                        'local_port': conn['local_port'].get(),
                        'file_path': conn['file_path'].get(),
                        'enabled': conn['enabled'].get(),
                        'mode': conn['mode'].get(),
                        'custom_packets': cpkts,
                        't_range_lo': conn['t_range_lo'].get(),
                        't_range_hi': conn['t_range_hi'].get(),
                        'l_list_str': conn['l_list_str'].get(),
                    })
                data['sub_connections'].append(group_data)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            self.log_send_message(f"配置已保存到 {self.config_file}")
        except Exception as e:
            self.log_send_message(f"保存配置失败: {str(e)}")

    def load_config(self):
        if not os.path.exists(self.config_file):
            self.log_send_message("未找到配置文件，创建默认子连接组")
            self.add_sub_connection_group()
            return
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.target_ip_var.set(data.get('target_ip', '192.168.1.213'))
            self.interval_var.set(data.get('interval', '0.001'))
            self.loop_var.set(data.get('loop', False))
            self.verbose_logging.set(data.get('verbose_logging', False))
            self.high_precision_var.set(data.get('high_precision', True))
            self.use_high_precision_timing = self.high_precision_var.get()
            self.timestamp_offset_var.set(data.get('timestamp_offset', '4'))
            self.timestamp_length_var.set(data.get('timestamp_length', '4'))
            self.timestamp_live_var.set(data.get('timestamp_live', True))
            self.timestamp_reverse_var.set(data.get('timestamp_reverse', False))
            self.timestamp_format_var.set(data.get('timestamp_format', 'unix'))

            for tab in self.notebook.tabs():
                self.notebook.forget(tab)
            self.sub_connections.clear()

            sub_data = data.get('sub_connections', [])
            if sub_data:
                for group_data in sub_data:
                    self.add_sub_connection_group(group_data)
            else:
                self.add_sub_connection_group()
            self.log_send_message(f"已从配置文件加载 {len(self.sub_connections)} 个子连接组")
        except Exception as e:
            self.log_send_message(f"加载配置失败: {str(e)}")
            self.add_sub_connection_group()

    def on_closing(self):
        if self.sending:
            if messagebox.askyesno("退出确认", "正在发送报文，确定要退出吗？"):
                self.safe_stop_sending()
                time.sleep(0.5)
            else:
                return
        self.save_config()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = PacketSender(root)
    root.mainloop()