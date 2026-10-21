import json
import os
import re
import socket
import sys
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from tkinter import ttk, filedialog, messagebox, scrolledtext

# 规则模式
RULE_MODE_GROUP = "组级规则"
RULE_MODE_CONN = "连接级规则"
RULE_MODE_VALUES = [RULE_MODE_GROUP, RULE_MODE_CONN]
RULE_MODE_GROUP_KEY = 'group'
RULE_MODE_CONN_KEY = 'conn'


class PacketSender:
    def __init__(self, root):
        self.root = root
        self.root.title("UDP 压测工具 v3.0")
        self.root.geometry("1300x950")
        self.set_window_icon()

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

    def set_window_icon(self):
        """设置窗口左上角图标"""
        try:
            # 获取资源路径（兼容 PyInstaller 打包）
            if hasattr(sys, '_MEIPASS'):
                # 打包后的临时目录
                base_path = sys._MEIPASS
            else:
                base_path = os.path.abspath(".")
            icon_path = os.path.join(base_path, "udp.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
                # self.log(f"窗口图标已加载：{icon_path}")
            else:
                # 如果找不到图标文件，可以使用默认图标（无图标）
                pass
        except Exception as e:
            print(f"设置图标失败：{e}")

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

    # ------------------ UI 构建 ------------------
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
        ttk.Label(setting_frame, text="(作为规则都不命中时的兜底)").grid(row=2, column=4, columnspan=2, sticky=tk.W, padx=(10, 0), pady=(10, 0))

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

    # ------------------ 子连接组 ------------------
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
            'rule_mode': tk.StringVar(value=RULE_MODE_GROUP),  # 规则模式
            'rules': [],    # 组级规则
            'connections': []
        }
        if group_data:
            group['target_port'].set(group_data.get('target_port', '10040'))
            group['interval'].set(group_data.get('interval', self.interval_var.get()))
            group['timestamp_offset'].set(group_data.get('timestamp_offset', self.timestamp_offset_var.get()))
            group['timestamp_length'].set(group_data.get('timestamp_length', self.timestamp_length_var.get()))
            group['timestamp_live'].set(group_data.get('timestamp_live', True))
            group['timestamp_reverse'].set(group_data.get('timestamp_reverse', False))
            rm = group_data.get('rule_mode', RULE_MODE_GROUP_KEY)
            group['rule_mode'].set(RULE_MODE_CONN if rm == RULE_MODE_CONN_KEY else RULE_MODE_GROUP)
            group['rules'] = group_data.get('group_rules', []) or group_data.get('rules', []) or []

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
            f"规则模式={group['rule_mode'].get()}")

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

        offset_label = ttk.Label(config_frame, text="默认偏移:")
        offset_label.pack(side=tk.LEFT, padx=(5, 3))
        offset_entry = ttk.Entry(config_frame, textvariable=group['timestamp_offset'], width=5)
        offset_entry.pack(side=tk.LEFT, padx=(0, 10))

        length_label = ttk.Label(config_frame, text="默认长度:")
        length_label.pack(side=tk.LEFT, padx=(5, 3))
        length_entry = ttk.Entry(config_frame, textvariable=group['timestamp_length'], width=5)
        length_entry.pack(side=tk.LEFT, padx=(0, 10))

        reverse_cb = ttk.Checkbutton(config_frame, text="默认反转", variable=group['timestamp_reverse'])
        reverse_cb.pack(side=tk.LEFT, padx=(5, 0))

        group['offset_entry'] = offset_entry
        group['length_entry'] = length_entry
        group['reverse_cb'] = reverse_cb
        self._update_ts_widget_state(group)

        # 规则模式选择行
        mode_frame = ttk.Frame(parent)
        mode_frame.pack(fill=tk.X, pady=(3, 3))
        ttk.Label(mode_frame, text="规则模式:").pack(side=tk.LEFT, padx=(0, 5))
        mode_combo = ttk.Combobox(mode_frame, textvariable=group['rule_mode'],
                                  values=RULE_MODE_VALUES, state='readonly', width=14)
        mode_combo.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(mode_frame, text="（组级：所有连接共用一套规则；连接级：每条连接独立配置）",
                  foreground='#666').pack(side=tk.LEFT)
        group['mode_combo'] = mode_combo
        # 切换模式时刷新按钮状态
        mode_combo.bind('<<ComboboxSelected>>',
                        lambda e, gi=group_index: self._apply_rule_mode(gi))

        # 操作按钮行
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(btn_frame, text="添加连接", command=lambda: self._add_connection_to_group(group_index)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="批量生成", command=lambda: self.batch_generate_connections(group_index)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="批量设置本机端口", command=lambda: self.batch_set_ports_group(group_index)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="批量设置本机IP", command=lambda: self.batch_set_ips_group(group_index)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="批量选择文件", command=lambda: self.batch_select_files_group(group_index)).pack(side=tk.LEFT, padx=(0, 5))

        group_rule_btn = ttk.Button(btn_frame, text=f"组级规则({len(group['rules'])})",
                                    command=lambda: self.open_group_rules_dialog(group_index))
        group_rule_btn.pack(side=tk.LEFT, padx=(0, 5))
        group['group_rule_btn'] = group_rule_btn

        ttk.Button(btn_frame, text="删除此组", command=lambda: self.delete_sub_connection_group(group_index)).pack(side=tk.LEFT, padx=(0, 5))

        # 滚动区
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

        def _bind_mw(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mw(event):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _bind_mw)
        canvas.bind("<Leave>", _unbind_mw)

        ttk.Label(scrollable_frame, text="启用", width=6).grid(row=0, column=0, padx=5, pady=2)
        ttk.Label(scrollable_frame, text="本机IP", width=15).grid(row=0, column=1, padx=5, pady=2)
        ttk.Label(scrollable_frame, text="本机端口", width=10).grid(row=0, column=2, padx=5, pady=2)
        ttk.Label(scrollable_frame, text="日志文件", width=45).grid(row=0, column=3, padx=5, pady=2)
        ttk.Label(scrollable_frame, text="操作", width=24).grid(row=0, column=4, padx=5, pady=2)

        group['scrollable_frame'] = scrollable_frame
        group['canvas'] = canvas

        # 初始应用一次规则模式
        self._apply_rule_mode(group_index)

    def _update_ts_widget_state(self, group):
        if group['timestamp_live'].get():
            group['offset_entry'].config(state='normal')
            group['length_entry'].config(state='normal')
            group['reverse_cb'].config(state='normal')
        else:
            group['offset_entry'].config(state='disabled')
            group['length_entry'].config(state='disabled')
            group['reverse_cb'].config(state='disabled')

    def _apply_rule_mode(self, group_index):
        """根据规则模式，启用/禁用组级、连接级规则按钮"""
        if group_index < 0 or group_index >= len(self.sub_connections):
            return
        group = self.sub_connections[group_index]
        is_group_mode = (group['rule_mode'].get() == RULE_MODE_GROUP)

        # 组级规则按钮
        try:
            group['group_rule_btn'].config(
                state='normal' if is_group_mode else 'disabled'
            )
        except:
            pass

        # 连接级规则按钮
        for conn in group['connections']:
            try:
                conn['rule_btn'].config(
                    state='normal' if not is_group_mode else 'disabled'
                )
            except:
                pass

    # ------------------ 规则弹窗 ------------------
    def _open_rules_dialog(self, title, rules_list, rule_btn=None, is_group_mode=True):
        """通用规则编辑弹窗；rules_list 为直接操作的列表"""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("880x520")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(
            dialog,
            text="规则按顺序匹配，命中第一条即写入时间戳。建议把“默认(兜底)”规则放在最后。"
                 "若一条规则都未命中，则使用本组“默认偏移/默认长度/默认反转”。",
            foreground='#444'
        ).pack(fill=tk.X, padx=10, pady=(10, 5))

        tree_frame = ttk.Frame(dialog)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ('order', 'type', 'value', 'offset', 'length', 'reverse')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=14)
        tree.heading('order', text='序号')
        tree.heading('type', text='匹配类型')
        tree.heading('value', text='匹配值')
        tree.heading('offset', text='偏移(字节)')
        tree.heading('length', text='长度(字节)')
        tree.heading('reverse', text='反转')
        tree.column('order', width=60, anchor='center')
        tree.column('type', width=140, anchor='center')
        tree.column('value', width=280, anchor='w')
        tree.column('offset', width=100, anchor='center')
        tree.column('length', width=100, anchor='center')
        tree.column('reverse', width=80, anchor='center')
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sb = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        TYPE_LABELS = {
            'length': '报文长度',
            'prefix': '报文前缀(HEX)',
            'regex': '正则表达式',
            'default': '默认(兜底)'
        }

        def refresh_tree():
            for item in tree.get_children():
                tree.delete(item)
            for i, rule in enumerate(rules_list):
                type_str = TYPE_LABELS.get(rule.get('match_type', 'length'), rule.get('match_type', ''))
                tree.insert('', tk.END, iid=str(i), values=(
                    i + 1, type_str,
                    rule.get('match_value', ''),
                    rule.get('offset', 0),
                    rule.get('length', 4),
                    '是' if rule.get('reverse', False) else '否'
                ))
            if rule_btn is not None:
                try:
                    if is_group_mode:
                        rule_btn.config(text=f"组级规则({len(rules_list)})")
                    else:
                        rule_btn.config(text=f"规则({len(rules_list)})")
                except:
                    pass

        def add_rule():
            self._edit_rule_dialog(dialog, rules_list, None, refresh_tree)

        def edit_rule():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("提示", "请先选择一行规则")
                return
            idx = int(sel[0])
            self._edit_rule_dialog(dialog, rules_list, idx, refresh_tree)

        def delete_rule():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("提示", "请先选择一行规则")
                return
            idx = int(sel[0])
            if messagebox.askyesno("确认", "确定删除该规则？"):
                del rules_list[idx]
                refresh_tree()

        def move_up():
            sel = tree.selection()
            if not sel:
                return
            idx = int(sel[0])
            if idx > 0:
                rules_list[idx], rules_list[idx - 1] = rules_list[idx - 1], rules_list[idx]
                refresh_tree()
                tree.selection_set(str(idx - 1))

        def move_down():
            sel = tree.selection()
            if not sel:
                return
            idx = int(sel[0])
            if idx < len(rules_list) - 1:
                rules_list[idx], rules_list[idx + 1] = rules_list[idx + 1], rules_list[idx]
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

    def open_group_rules_dialog(self, group_index):
        if self.sending:
            messagebox.showwarning("警告", "发送过程中不能修改规则")
            return
        if group_index < 0 or group_index >= len(self.sub_connections):
            return
        group = self.sub_connections[group_index]
        self._open_rules_dialog(
            f"组 {group['name']} - 组级偏移规则（所有连接共用）",
            group['rules'],
            rule_btn=group.get('group_rule_btn'),
            is_group_mode=True
        )

    def open_conn_rules_dialog(self, group_index, conn_index):
        if self.sending:
            messagebox.showwarning("警告", "发送过程中不能修改规则")
            return
        if group_index < 0 or group_index >= len(self.sub_connections):
            return
        group = self.sub_connections[group_index]
        if conn_index < 0 or conn_index >= len(group['connections']):
            return
        conn = group['connections'][conn_index]
        fname = os.path.basename(conn['file_path'].get()) or '未选文件'
        self._open_rules_dialog(
            f"组 {group['name']} - 连接 {conn_index + 1} ({fname}) 独立规则",
            conn['rules'],
            rule_btn=conn.get('rule_btn'),
            is_group_mode=False
        )

    def _edit_rule_dialog(self, parent, rules_list, rule_index, on_saved):
        dlg = tk.Toplevel(parent)
        dlg.title("编辑规则" if rule_index is not None else "添加规则")
        dlg.geometry("460x360")
        dlg.transient(parent)
        dlg.grab_set()

        if rule_index is not None:
            rule = dict(rules_list[rule_index])
        else:
            rule = {'match_type': 'length', 'match_value': '', 'offset': 4, 'length': 4, 'reverse': False}

        type_var = tk.StringVar(value=rule.get('match_type', 'length'))
        value_var = tk.StringVar(value=str(rule.get('match_value', '')))
        offset_var = tk.StringVar(value=str(rule.get('offset', 4)))
        length_var = tk.StringVar(value=str(rule.get('length', 4)))
        reverse_var = tk.BooleanVar(value=rule.get('reverse', False))

        ttk.Label(dlg, text="匹配类型:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=8)
        type_combo = ttk.Combobox(dlg, textvariable=type_var,
                                  values=['报文长度', '报文前缀(HEX)', '正则表达式', '默认(兜底)'],
                                  state='readonly', width=22)
        type_combo.grid(row=0, column=1, sticky=tk.W, padx=10, pady=8)

        ttk.Label(dlg, text="匹配值:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=8)
        value_entry = ttk.Entry(dlg, textvariable=value_var, width=32)
        value_entry.grid(row=1, column=1, sticky=tk.W, padx=10, pady=8)

        hint_label = ttk.Label(dlg, text="", foreground='#666')
        hint_label.grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=10, pady=(0, 8))

        ttk.Label(dlg, text="时间戳偏移(字节):").grid(row=3, column=0, sticky=tk.W, padx=10, pady=8)
        ttk.Entry(dlg, textvariable=offset_var, width=12).grid(row=3, column=1, sticky=tk.W, padx=10, pady=8)

        ttk.Label(dlg, text="时间戳长度(字节):").grid(row=4, column=0, sticky=tk.W, padx=10, pady=8)
        ttk.Entry(dlg, textvariable=length_var, width=12).grid(row=4, column=1, sticky=tk.W, padx=10, pady=8)

        ttk.Checkbutton(dlg, text="时间戳反转", variable=reverse_var).grid(row=5, column=0, columnspan=2, sticky=tk.W, padx=10, pady=8)

        LABEL_TO_TYPE = {'报文长度': 'length', '报文前缀(HEX)': 'prefix', '正则表达式': 'regex', '默认(兜底)': 'default'}
        TYPE_TO_LABEL = {v: k for k, v in LABEL_TO_TYPE.items()}

        def update_hint(*args):
            label = type_var.get()
            if label == '报文长度':
                hint_label.config(text="示例：32（十进制字节数）")
                value_entry.config(state='normal')
            elif label == '报文前缀(HEX)':
                hint_label.config(text="示例：AA55 或 AA55BB（忽略空格与大小写）")
                value_entry.config(state='normal')
            elif label == '正则表达式':
                hint_label.config(text="示例：^AA55.*  （作用于去空格的HEX串，自动转大写）")
                value_entry.config(state='normal')
            else:
                hint_label.config(text="该规则匹配所有报文（建议放最后作为兜底）")
                value_entry.config(state='disabled')

        label_init = TYPE_TO_LABEL.get(type_var.get(), '报文长度')
        type_var.set(label_init)
        type_var.trace_add('write', update_hint)
        update_hint()

        def save():
            label = type_var.get()
            mt = LABEL_TO_TYPE.get(label, 'length')
            mv = value_var.get().strip() if mt != 'default' else ''

            try:
                off = int(offset_var.get())
                ln = int(length_var.get())
                if off < 0:
                    raise ValueError("偏移必须 >= 0")
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
                    try:
                        re.compile(mv.upper())
                    except re.error as e:
                        raise ValueError(f"正则表达式无效: {e}")
            except ValueError as e:
                messagebox.showerror("错误", f"参数无效: {str(e)}")
                return

            new_rule = {'match_type': mt, 'match_value': mv, 'offset': off, 'length': ln, 'reverse': reverse_var.get()}
            if rule_index is not None:
                rules_list[rule_index] = new_rule
            else:
                rules_list.append(new_rule)
            on_saved()
            dlg.destroy()

        ttk.Button(dlg, text="保存", command=save).grid(row=6, column=0, padx=10, pady=15)
        ttk.Button(dlg, text="取消", command=dlg.destroy).grid(row=6, column=1, padx=10, pady=15, sticky=tk.W)

    # ------------------ 规则匹配 / 时间戳写入 ------------------
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
            clean = mv.replace(' ', '').upper()
            return hex_packet.upper().startswith(clean)
        elif mt == 'regex':
            reg = rule.get('_regex')
            if reg is None:
                try:
                    reg = re.compile(mv.upper())
                except:
                    return False
            return reg.match(hex_packet.upper()) is not None
        return False

    def _write_timestamp(self, hex_packet, offset, length, reverse=False):
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

    # ------------------ 连接管理 ------------------
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
            'rules': [],   # 连接级规则
            'packets_cache': None,
            'cache_time': None,
            'packet_index': 0,
            'last_send_time': 0
        }
        if conn_data:
            conn['local_ip'].set(conn_data.get('local_ip', '0.0.0.0'))
            conn['local_port'].set(conn_data.get('local_port', '10010'))
            conn['file_path'].set(conn_data.get('file_path', ''))
            conn['enabled'].set(conn_data.get('enabled', True))
            conn['rules'] = conn_data.get('rules', []) or []

        group['connections'].append(conn)
        self._render_connection_row(group, group_index, len(group['connections']) - 1)

    def _render_connection_row(self, group, group_index, conn_index):
        conn = group['connections'][conn_index]
        row = conn_index + 1
        sf = group['scrollable_frame']

        ttk.Checkbutton(sf, variable=conn['enabled']).grid(row=row, column=0, padx=5, pady=2)
        ip_combo = ttk.Combobox(sf, textvariable=conn['local_ip'], values=self.local_ips, width=15)
        ip_combo.grid(row=row, column=1, padx=5, pady=2)
        ttk.Entry(sf, textvariable=conn['local_port'], width=10).grid(row=row, column=2, padx=5, pady=2)
        ttk.Entry(sf, textvariable=conn['file_path'], width=45).grid(row=row, column=3, padx=5, pady=2)

        op_frame = ttk.Frame(sf)
        op_frame.grid(row=row, column=4, padx=2, pady=2, sticky=tk.W)

        ttk.Button(op_frame, text="浏览",
                   command=lambda gi=group_index, ci=conn_index: self.browse_conn_file(gi, ci)).pack(side=tk.LEFT, padx=1)

        rule_btn = ttk.Button(op_frame, text=f"规则({len(conn['rules'])})",
                              command=lambda gi=group_index, ci=conn_index: self.open_conn_rules_dialog(gi, ci))
        rule_btn.pack(side=tk.LEFT, padx=1)
        conn['rule_btn'] = rule_btn

        ttk.Button(op_frame, text="删除",
                   command=lambda gi=group_index, ci=conn_index: self.delete_connection(gi, ci)).pack(side=tk.LEFT, padx=1)

        group['canvas'].configure(scrollregion=group['canvas'].bbox("all"))

        # 按当前模式设置按钮状态
        is_group_mode = (group['rule_mode'].get() == RULE_MODE_GROUP)
        try:
            rule_btn.config(state='disabled' if is_group_mode else 'normal')
        except:
            pass

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
            if int(widget.grid_info()['row']) > 0:
                widget.destroy()
        for i in range(len(group['connections'])):
            self._render_connection_row(group, group_index, i)

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

    # ------------------ 批量生成 ------------------
    def batch_generate_connections(self, group_index):
        if self.sending:
            messagebox.showwarning("警告", "发送过程中不能批量生成连接")
            return
        if group_index < 0 or group_index >= len(self.sub_connections):
            return
        group = self.sub_connections[group_index]

        dialog = tk.Toplevel(self.root)
        dialog.title("批量生成连接")
        dialog.geometry("340x200")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="生成数量:").pack(pady=(20, 5))
        count_var = tk.StringVar(value="1")
        ttk.Entry(dialog, textvariable=count_var, width=15).pack()

        default_port = "10010"
        if group['connections']:
            default_port = group['connections'][0]['local_port'].get()

        ttk.Label(dialog, text="本机端口（所有新连接使用相同端口）:").pack(pady=(10, 5))
        port_var = tk.StringVar(value=default_port)
        ttk.Entry(dialog, textvariable=port_var, width=15).pack()

        def apply():
            try:
                count = int(count_var.get())
                port = int(port_var.get())
                if count <= 0:
                    raise ValueError("数量必须大于0")
                if port < 0 or port > 65535:
                    raise ValueError("端口必须在0-65535之间")
                for _ in range(count):
                    conn = {
                        'local_ip': tk.StringVar(value="0.0.0.0"),
                        'local_port': tk.StringVar(value=str(port)),
                        'file_path': tk.StringVar(),
                        'enabled': tk.BooleanVar(value=True),
                        'rules': [],
                        'packets_cache': None,
                        'cache_time': None,
                        'packet_index': 0,
                        'last_send_time': 0
                    }
                    group['connections'].append(conn)
                self._refresh_group_ui(group_index)
                self.log_send_message(f"组 {group['name']} 已批量生成 {count} 个连接，端口均为 {port}")
                dialog.destroy()
            except ValueError as e:
                messagebox.showerror("错误", str(e))

        ttk.Button(dialog, text="生成", command=apply).pack(pady=20)

    # ------------------ 批量操作 ------------------
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
                self.log_send_message(f"组 {group['name']} 已批量设置本机IP")
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
            for i, filename in enumerate(filenames):
                if i < len(group['connections']):
                    group['connections'][i]['file_path'].set(filename)
                    group['connections'][i]['enabled'].set(True)
            self.log_send_message(f"组 {group['name']} 已批量选择 {min(len(filenames), len(group['connections']))} 个文件")

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

    # ------------------ 日志/状态 ------------------
    def log_send_message(self, message):
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        self.send_log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.send_log_text.see(tk.END)
        self.root.update_idletasks()

    def log_recv_message(self, message):
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        self.recv_log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.recv_log_text.see(tk.END)
        self.root.update_idletasks()

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

    # ------------------ 发送控制 ------------------
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

            ts_live = group['timestamp_live'].get()
            ts_reverse = group['timestamp_reverse'].get() if ts_live else False
            rule_mode_label = group['rule_mode'].get()
            use_conn_rules = (rule_mode_label == RULE_MODE_CONN)

            if ts_live:
                try:
                    ts_offset = int(group['timestamp_offset'].get())
                    ts_length = int(group['timestamp_length'].get())
                    if ts_offset < 0 or ts_length < 1 or ts_length > 8:
                        raise ValueError("偏移不能为负，长度必须在1-8之间")
                except ValueError as e:
                    messagebox.showerror("错误", f"组 {group['name']} 默认时间戳配置不正确: {str(e)}")
                    return

                # 校验规则（组级 or 连接级）
                rules_to_check = []
                if use_conn_rules:
                    for ci, conn in enumerate(group['connections']):
                        for ri, rule in enumerate(conn['rules']):
                            rules_to_check.append((f"连接{ci+1} 第{ri+1}条", rule))
                else:
                    for ri, rule in enumerate(group['rules']):
                        rules_to_check.append((f"第{ri+1}条", rule))

                for tag, rule in rules_to_check:
                    mt = rule.get('match_type', '')
                    if mt not in ('length', 'prefix', 'regex', 'default'):
                        messagebox.showerror("错误", f"组 {group['name']} {tag} 规则类型无效")
                        return
                    try:
                        off = int(rule.get('offset', 0))
                        ln = int(rule.get('length', 4))
                        if off < 0 or ln < 1 or ln > 8:
                            raise ValueError
                    except:
                        messagebox.showerror("错误", f"组 {group['name']} {tag} 规则偏移/长度无效")
                        return
                    if mt == 'length':
                        try:
                            int(rule.get('match_value', ''))
                        except:
                            messagebox.showerror("错误", f"组 {group['name']} {tag} 长度规则值无效")
                            return
                    if mt == 'regex':
                        try:
                            re.compile(rule.get('match_value', '').upper())
                        except re.error as e:
                            messagebox.showerror("错误", f"组 {group['name']} {tag} 正则无效: {e}")
                            return
            else:
                ts_offset = 0
                ts_length = 0

            # 组级规则快照（连接级模式下为空）
            group_rules_compiled = self._compile_rules(group['rules']) if (ts_live and not use_conn_rules) else []

            try:
                target_port = int(group['target_port'].get())
            except ValueError:
                messagebox.showerror("错误", f"组 {group['name']} 的目标端口格式错误")
                return

            for ci, conn in enumerate(group['connections']):
                if conn['enabled'].get():
                    if use_conn_rules:
                        conn_rules = self._compile_rules(conn['rules']) if ts_live else []
                    else:
                        conn_rules = group_rules_compiled
                    enabled_conns.append({
                        'conn': conn,
                        'group_name': group['name'],
                        'ci': ci,
                        'target_port': target_port,
                        'ts_offset': ts_offset,
                        'ts_length': ts_length,
                        'ts_live': ts_live,
                        'ts_reverse': ts_reverse,
                        'interval': interval,
                        'rules': conn_rules,
                    })

        if not enabled_conns:
            messagebox.showerror("错误", "请至少启用一个连接")
            return

        for item in enabled_conns:
            conn = item['conn']
            if not conn['file_path'].get():
                messagebox.showerror("错误", f"组 {item['group_name']} 连接 {item['ci'] + 1} 未选择日志文件")
                return
            if not os.path.exists(conn['file_path'].get()):
                messagebox.showerror("错误", f"组 {item['group_name']} 连接 {item['ci'] + 1} 的文件不存在")
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
        max_workers = len(enabled_conns)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.futures = []

        target_ip = self.target_ip_var.get()
        self.log_send_message(f"开始发送，全局目标IP: {target_ip}，启用连接总数: {len(enabled_conns)}")

        for item in enabled_conns:
            future = self.executor.submit(
                self.send_packets_for_connection,
                item['conn'], item['interval'], item['group_name'], item['ci'] + 1,
                target_ip, item['target_port'],
                item['ts_offset'], item['ts_length'],
                item['ts_live'], item['ts_reverse'],
                item['rules']
            )
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

    # ------------------ UDP 发送线程 ------------------
    def send_packets_for_connection(self, conn, interval, group_name, conn_no, target_ip, target_port,
                                    timestamp_offset, timestamp_length, ts_live, ts_reverse, rules):
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
                                    updated = self._write_timestamp(
                                        hex_packet, r['offset'], r['length'], r.get('reverse', False))
                                else:
                                    stat_default += 1
                                    updated = self._write_timestamp(
                                        hex_packet, timestamp_offset, timestamp_length, ts_reverse)
                            else:
                                updated = self._write_timestamp(
                                    hex_packet, timestamp_offset, timestamp_length, ts_reverse)
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
                                detail = ", ".join([f"规则{ri+1}:{cnt}" for ri, cnt in sorted(stat_match.items())])
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

    # ------------------ 文件读取 ------------------
    def extract_packets_from_file(self, file_path):
        packets = []
        content = ""
        encodings = ["utf-8", "gbk", "gb2312", "latin-1"]
        for enc in encodings:
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
            hex_part = line.rsplit(']', 1)[1].strip() if ']' in line else line.strip()
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
                            hex_data = data.hex().upper()
                            self.log_recv_message(f"[UDP] {config_key} 收到 {addr[0]}:{addr[1]} 数据: {hex_data}")
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

    # ------------------ 配置保存/加载 ------------------
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
                'sub_connections': []
            }
            for group in self.sub_connections:
                rm = RULE_MODE_CONN_KEY if group['rule_mode'].get() == RULE_MODE_CONN else RULE_MODE_GROUP_KEY
                group_data = {
                    'name': group['name'],
                    'target_port': group['target_port'].get(),
                    'interval': group['interval'].get(),
                    'timestamp_offset': group['timestamp_offset'].get(),
                    'timestamp_length': group['timestamp_length'].get(),
                    'timestamp_live': group['timestamp_live'].get(),
                    'timestamp_reverse': group['timestamp_reverse'].get(),
                    'rule_mode': rm,
                    'group_rules': [dict(r) for r in group['rules']],
                    'connections': []
                }
                for r in group_data['group_rules']:
                    r.pop('_regex', None)
                for conn in group['connections']:
                    conn_rules = []
                    for r in conn['rules']:
                        nr = dict(r)
                        nr.pop('_regex', None)
                        conn_rules.append(nr)
                    group_data['connections'].append({
                        'local_ip': conn['local_ip'].get(),
                        'local_port': conn['local_port'].get(),
                        'file_path': conn['file_path'].get(),
                        'enabled': conn['enabled'].get(),
                        'rules': conn_rules
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