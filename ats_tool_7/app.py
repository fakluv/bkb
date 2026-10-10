# app.py
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, messagebox
import threading
import socket
import time
import struct
import json
import os
import re
import sys
from common import float_to_hex, data_format, fix_str, str_reverse, int_to_hex, deal_data, calculate_crc, calculate_crc_with_version
from data_reader import (
    read_ats_device_table, read_platform_table, read_generic_device_table,
    read_excel_data_perf, read_signal_table, read_logic_section_table,
    read_switch_table, filter_test_track, read_psd_table, read_emergency_brake_table
)
from packet_builder import (
    get_next_sequence, build_alarm_packet,
    build_alarm_base_packet, get_default_thresholds, generate_value,
    generate_perf_packet_by_version, build_full_perf_packet_raw,
    build_full_perf_packet_clean, build_full_perf_packet_raw_bytes,
    build_perf_base_packet, compute_signal_status_byte,
    compute_section_status_bytes, compute_switch_status_byte,
    build_station_status_packet_full, build_station_base_packet,
    build_track_base_packet
)
from widgets import CheckboxTreeview


class IntegratedApp:
    def __init__(self, root):
        self.root = root
        root.title("ATS 协议工具v2.2")
        root.geometry("1400x850")
        root.minsize(1200, 700)

        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))
        self.layout_file = os.path.join(app_dir, "integrated_layout.json")
        self.config_file = os.path.join(app_dir, "app_config.json")

        style = ttk.Style()
        style.configure('TLabel', font=('微软雅黑', 9))
        style.configure('TButton', font=('微软雅黑', 9))
        style.configure('TRadiobutton', font=('微软雅黑', 9))
        style.configure('TEntry', font=('微软雅黑', 9))
        style.configure('TLabelframe.Label', font=('微软雅黑', 9, 'bold'))

        self.mode = tk.StringVar(value="alarm")

        self.alarm_devices_data = {}
        self.perf_devices = []
        self.signal_devices = []
        self.section_devices = []
        self.switch_devices = []
        self.psd_devices = []
        self.em_brake_devices = []

        self.log_text = None
        self.right_pane = None
        self.send_thread = None
        self.server_thread = None
        self.stop_event = threading.Event()
        self.send_stop_event = threading.Event()
        self.server_socket = None
        self.client_sock = None
        self.send_counter = 0
        self.alarm_sending = False
        self.perf_sending = False
        self.station_sending = False
        self.track_sending = False
        self.track_data_cache = None
        self.track_random_time = tk.BooleanVar(value=False)

        self.connected = False

        self.tcp_local_ip = tk.StringVar(value="0.0.0.0")
        self.tcp_port = tk.StringVar(value="10050")
        self.tcp_target_ip = tk.StringVar(value="192.168.1.238")

        self._preview_after_id = None

        self.load_config()
        self.create_widgets()
        self.load_layout()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.perf_panel_ready = False
        self.global_version.trace('w', self.on_global_version_changed)

        self.tree.check_callback = self.on_device_check_changed
        self._bind_param_events()

    # ---------- 配置管理 ----------
    def update_device_count(self):
        count = 0
        def count_leaves(item):
            nonlocal count
            if not self.tree.get_children(item):
                count += 1
            else:
                for child in self.tree.get_children(item):
                    count_leaves(child)
        for root_item in self.tree.get_children():
            count_leaves(root_item)
        self.device_count_label.config(text=f"设备总数: {count}")

    def load_config(self):
        default_config = {
            "local_ip": "0.0.0.0",
            "port": "10050",
            "target_ip": "192.168.1.238",
            "global_version": "11.0"
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                for key in default_config:
                    if key in saved:
                        default_config[key] = saved[key]
            except:
                pass
        self.config = default_config
        self._global_version_value = default_config.get("global_version", "11.0")
        self.tcp_local_ip.set(self.config.get("local_ip", "0.0.0.0"))
        self.tcp_port.set(self.config.get("port", "10050"))
        self.tcp_target_ip.set(self.config.get("target_ip", "192.168.1.238"))

    def save_config(self):
        config_to_save = {
            "local_ip": self.tcp_local_ip.get(),
            "port": self.tcp_port.get(),
            "target_ip": self.tcp_target_ip.get(),
            "global_version": self.global_version.get()
        }
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_to_save, f, indent=2)
        except:
            pass

    # ---------- 界面搭建 ----------
    def create_widgets(self):
        root = self.root
        mode_frame = ttk.LabelFrame(root, text="工作模式", padding=5)
        mode_frame.pack(fill=tk.X, padx=8, pady=5)

        ttk.Radiobutton(mode_frame, text="设备运行状态报文模式", variable=self.mode, value="alarm",
                        command=self.on_mode_changed).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(mode_frame, text="设备性能状态报文模式", variable=self.mode, value="performance",
                        command=self.on_mode_changed).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(mode_frame, text="站场状态报文模式", variable=self.mode, value="station",
                        command=self.on_mode_changed).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(mode_frame, text="早晚点模式", variable=self.mode, value="track",
                        command=self.on_mode_changed).pack(side=tk.LEFT, padx=10)

        ttk.Label(mode_frame, text="协议版本:").pack(side=tk.LEFT, padx=(20, 5))
        self.global_version = tk.StringVar(value=self._global_version_value)
        version_combo = ttk.Combobox(mode_frame, textvariable=self.global_version,
                                     values=["7.0", "8.0", "9.0", "10.0", "11.0", "12.0"],
                                     state="readonly", width=6)
        version_combo.pack(side=tk.LEFT, padx=5)

        tcp_frame = ttk.LabelFrame(root, text="TCP 发送设置（所有模式共用）", padding=5)
        tcp_frame.pack(fill=tk.X, padx=8, pady=5)

        ttk.Label(tcp_frame, text="本机监听IP:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        ttk.Entry(tcp_frame, textvariable=self.tcp_local_ip, width=15).grid(row=0, column=1, padx=5, pady=2)
        ttk.Label(tcp_frame, text="监听端口:").grid(row=0, column=2, sticky='w', padx=5, pady=2)
        ttk.Entry(tcp_frame, textvariable=self.tcp_port, width=8).grid(row=0, column=3, padx=5, pady=2)
        ttk.Label(tcp_frame, text="目标客户端IP:").grid(row=0, column=4, sticky='w', padx=5, pady=2)
        ttk.Entry(tcp_frame, textvariable=self.tcp_target_ip, width=15).grid(row=0, column=5, padx=5, pady=2)

        self.open_server_btn = ttk.Button(tcp_frame, text="开启TCP服务器", command=self.open_tcp_server)
        self.open_server_btn.grid(row=0, column=6, padx=5, pady=2)
        self.close_server_btn = ttk.Button(tcp_frame, text="关闭TCP服务器", command=self.close_tcp_server, state=tk.DISABLED)
        self.close_server_btn.grid(row=0, column=7, padx=5, pady=2)

        self.send_btn = ttk.Button(tcp_frame, text="▶ 开始发送", command=self.toggle_send)
        self.send_btn.grid(row=0, column=8, padx=5, pady=2)
        self.stop_btn = ttk.Button(tcp_frame, text="⏹ 停止发送", command=self.stop_sending, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=9, padx=5, pady=2)

        folder_frame = ttk.Frame(root)
        folder_frame.pack(fill=tk.X, padx=8, pady=5)
        ttk.Label(folder_frame, text="工作文件夹:").pack(side=tk.LEFT, padx=5)
        self.folder_path = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.folder_path, width=60).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(folder_frame, text="浏览", command=self.select_folder).pack(side=tk.LEFT, padx=5)

        self.main_pane = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        left_frame = ttk.LabelFrame(self.main_pane, text="设备列表", padding=5)
        self.main_pane.add(left_frame, weight=40)

        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(btn_frame, text="全选", command=self.select_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="清空勾选", command=self.clear_all).pack(side=tk.LEFT, padx=2)

        tree_container = ttk.Frame(left_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)
        tree_container.grid_columnconfigure(1, weight=0)

        self.tree = CheckboxTreeview(tree_container, show='tree', height=25)
        tree_scroll = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll.grid(row=0, column=1, sticky="ns")

        self.device_count_label = ttk.Label(left_frame, text="设备总数: 0", font=('微软雅黑', 9))
        self.device_count_label.pack(fill=tk.X, padx=5, pady=(2, 0))

        self.right_pane = ttk.PanedWindow(self.main_pane, orient=tk.HORIZONTAL)
        self.main_pane.add(self.right_pane, weight=60)

        op_log_frame = ttk.Frame(self.right_pane)
        self.right_pane.add(op_log_frame, weight=3)

        op_frame = ttk.LabelFrame(op_log_frame, text="操作", padding="5")
        op_frame.pack(side=tk.TOP, fill=tk.X, expand=False, pady=(0, 5))

        self.op_content = ttk.Frame(op_frame)
        self.op_content.pack(fill=tk.BOTH, expand=True)

        self.alarm_op_frame = ttk.Frame(self.op_content)
        self.perf_op_frame = ttk.Frame(self.op_content)
        self.station_op_frame = ttk.Frame(self.op_content)
        self.track_op_frame = ttk.Frame(self.op_content)

        log_frame = ttk.LabelFrame(op_log_frame, text="日志", padding=5)
        log_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, font=("Consolas", 9), relief=tk.FLAT)
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        preview_frame = ttk.LabelFrame(self.right_pane, text="报文预览 (实时更新)", padding="5")
        self.right_pane.add(preview_frame, weight=2)
        preview_frame.grid_rowconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(1, weight=0)
        self.result_text = tk.Text(preview_frame, wrap=tk.WORD, font=("Consolas", 9), relief=tk.FLAT)
        scroll_preview = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=scroll_preview.set)
        self.result_text.grid(row=0, column=0, sticky="nsew")
        scroll_preview.grid(row=0, column=1, sticky="ns")

        self.init_alarm_panel()
        self.init_perf_panel()
        self.init_station_panel()
        self.init_track_panel()
        self.on_mode_changed()

    # ---------- 报警模式面板 ----------
    def init_alarm_panel(self):
        type_frame = ttk.LabelFrame(self.alarm_op_frame, text="设备类型", padding=5)
        type_frame.pack(fill=tk.X, pady=5)

        self.alarm_dev_type = tk.StringVar(value="05")
        types = [
            ("01 - CI通信状态", "01"),
            ("02 - ZC通信状态", "02"),
            ("03 - DSU通信状态", "03"),
            ("04 - 主备维护态", "04"),
            ("05 - ATS设备报警", "05"),
            ("通信前置机相关报警（0x14~0x19）", "comm_group"),
            ("20 - 站台设备状态", "20"),
        ]
        row, col = 0, 0
        for text, val in types:
            rb = ttk.Radiobutton(type_frame, text=text, variable=self.alarm_dev_type, value=val,
                                 command=self.on_alarm_type_changed)
            rb.grid(row=row, column=col, sticky='w', padx=5, pady=2)
            col += 1
            if col > 3:
                col = 0
                row += 1

        self.alarm_status_frame = ttk.Frame(self.alarm_op_frame)
        self.alarm_status_frame.pack(fill=tk.X, pady=5)

        # 通信前置机子类型面板（下拉选择）
        self.comm_frame = ttk.Frame(self.alarm_op_frame)
        self.comm_vars = {}
        sub_types = [
            ("乘客信息系统", "14"),
            ("时钟系统", "15"),
            ("广播系统", "16"),
            ("无线系统", "17"),
            ("综合监控", "18"),
            ("TCC", "19")
        ]
        for idx, (label, code) in enumerate(sub_types):
            var = tk.StringVar(value="0x55")
            self.comm_vars[code] = var
            frame = ttk.Frame(self.comm_frame)
            frame.pack(fill=tk.X, pady=2)
            ttk.Label(frame, text=f"{label}:").pack(side=tk.LEFT, padx=5)
            combo = ttk.Combobox(frame, textvariable=var, values=["正常 (0x55)", "中断 (0xAA)", "未知 (0x33)"],
                                 state="readonly", width=15)
            combo.pack(side=tk.LEFT, padx=5)
            var.trace('w', lambda *a: self.update_preview_if_needed())

        self.comm_frame.pack_forget()
        self.on_alarm_type_changed()

    # ---------- 性能模式面板 ----------
    def init_perf_panel(self):
        param_frame = ttk.LabelFrame(self.perf_op_frame, text="参数设置", padding=5)
        param_frame.pack(fill=tk.X, pady=5)

        ttk.Label(param_frame, text="阈值模式:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        self.perf_threshold_mode = tk.StringVar(value="default")
        mode_combo = ttk.Combobox(param_frame, textvariable=self.perf_threshold_mode,
                                  values=["默认", "自定义"], state="readonly", width=10)
        mode_combo.grid(row=0, column=1, sticky='w', padx=5, pady=2)
        mode_combo.bind("<<ComboboxSelected>>", self.on_perf_threshold_mode_changed)

        ttk.Label(param_frame, text="报文模式:").grid(row=0, column=2, sticky='w', padx=5, pady=2)
        self.perf_mode = tk.StringVar(value="recovery")
        mode_frame2 = ttk.Frame(param_frame)
        mode_frame2.grid(row=0, column=3, sticky='w', padx=5, pady=2)
        ttk.Radiobutton(mode_frame2, text="恢复模式", variable=self.perf_mode, value="recovery").pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(mode_frame2, text="报警模式", variable=self.perf_mode, value="alarm").pack(side=tk.LEFT, padx=2)

        self.perf_custom_canvas = tk.Canvas(param_frame, height=120, highlightthickness=0)
        self.perf_custom_scrollbar = ttk.Scrollbar(param_frame, orient="vertical", command=self.perf_custom_canvas.yview)
        self.perf_custom_inner = ttk.Frame(self.perf_custom_canvas)
        self.perf_custom_canvas.configure(yscrollcommand=self.perf_custom_scrollbar.set)
        self.perf_custom_canvas.create_window((0, 0), window=self.perf_custom_inner, anchor='nw')
        self.perf_custom_canvas.grid(row=1, column=0, columnspan=4, sticky='ew', pady=5)
        self.perf_custom_scrollbar.grid(row=1, column=4, sticky='ns')
        self.perf_custom_canvas.grid_remove()
        self.perf_custom_scrollbar.grid_remove()
        self.perf_custom_entries = {}
        self.perf_extra_entries = {}

        self.build_perf_custom_inputs()
        self.perf_panel_ready = True

    # ---------- 站场模式面板 ----------
    def init_station_panel(self):
        scroll_frame = ttk.Frame(self.station_op_frame)
        scroll_frame.pack(fill=tk.X, pady=5)

        self.station_canvas = tk.Canvas(scroll_frame, height=200, highlightthickness=0)
        h_scroll = ttk.Scrollbar(scroll_frame, orient="horizontal", command=self.station_canvas.xview)
        v_scroll = ttk.Scrollbar(scroll_frame, orient="vertical", command=self.station_canvas.yview)
        self.station_canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)

        self.station_canvas.grid(row=0, column=0, sticky="nsew")
        h_scroll.grid(row=1, column=0, sticky="ew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        scroll_frame.grid_rowconfigure(0, weight=1)
        scroll_frame.grid_columnconfigure(0, weight=1)

        status_container = ttk.Frame(self.station_canvas)
        self.station_canvas.create_window((0, 0), window=status_container, anchor='nw')
        status_container.bind("<Configure>",
                              lambda e: self.station_canvas.configure(scrollregion=self.station_canvas.bbox("all")))

        signal_frame = ttk.LabelFrame(status_container, text="信号机状态设置", padding=5)
        signal_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=2)

        self.block_var = tk.StringVar(value="未封锁")
        self.light_var = tk.StringVar(value="亮")
        self.filament_var = tk.StringVar(value="未断丝")
        self.speed_limit_var = tk.StringVar(value="未限速")
        self.lamp_var = tk.StringVar(value="单红")

        row = 0
        ttk.Label(signal_frame, text="封锁状态:").grid(row=row, column=0, sticky='w', padx=5)
        f = ttk.Frame(signal_frame); f.grid(row=row, column=1, sticky='w')
        ttk.Radiobutton(f, text="未封锁", variable=self.block_var, value="未封锁").pack(side=tk.LEFT)
        ttk.Radiobutton(f, text="封锁", variable=self.block_var, value="封锁").pack(side=tk.LEFT)
        row += 1
        ttk.Label(signal_frame, text="亮灭状态:").grid(row=row, column=0, sticky='w', padx=5)
        f = ttk.Frame(signal_frame); f.grid(row=row, column=1, sticky='w')
        ttk.Radiobutton(f, text="亮", variable=self.light_var, value="亮").pack(side=tk.LEFT)
        ttk.Radiobutton(f, text="灭", variable=self.light_var, value="灭").pack(side=tk.LEFT)
        row += 1
        ttk.Label(signal_frame, text="灯丝断丝状态:").grid(row=row, column=0, sticky='w', padx=5)
        f = ttk.Frame(signal_frame); f.grid(row=row, column=1, sticky='w')
        ttk.Radiobutton(f, text="未断丝", variable=self.filament_var, value="未断丝").pack(side=tk.LEFT)
        ttk.Radiobutton(f, text="断丝", variable=self.filament_var, value="断丝").pack(side=tk.LEFT)
        row += 1
        ttk.Label(signal_frame, text="限速状态:").grid(row=row, column=0, sticky='w', padx=5)
        f = ttk.Frame(signal_frame); f.grid(row=row, column=1, sticky='w')
        ttk.Radiobutton(f, text="未限速", variable=self.speed_limit_var, value="未限速").pack(side=tk.LEFT)
        ttk.Radiobutton(f, text="限速", variable=self.speed_limit_var, value="限速").pack(side=tk.LEFT)
        row += 1
        ttk.Label(signal_frame, text="灯位状态:").grid(row=row, column=0, sticky='w', padx=5)
        f = ttk.Frame(signal_frame); f.grid(row=row, column=1, sticky='w')
        for opt in ["单红", "单绿", "单黄", "单白", "红黄", "单蓝", "未知"]:
            ttk.Radiobutton(f, text=opt, variable=self.lamp_var, value=opt).pack(side=tk.LEFT)

        section_frame = ttk.LabelFrame(status_container, text="逻辑区段状态设置", padding=5)
        section_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=2)

        self.section_speed_limit_var = tk.StringVar(value="无限速")
        self.section_block_var = tk.StringVar(value="未封锁")
        self.section_arb_var = tk.StringVar(value="无ARB")
        self.section_occupy_var = tk.StringVar(value="未占用")
        self.section_lock_var = tk.StringVar(value="空闲")
        self.section_valid_var = tk.StringVar(value="有效")
        self.section_cut_var = tk.StringVar(value="未切除")

        row = 0
        ttk.Label(section_frame, text="联锁限速:").grid(row=row, column=0, sticky='w', padx=5)
        f = ttk.Frame(section_frame); f.grid(row=row, column=1, sticky='w')
        ttk.Radiobutton(f, text="无限速", variable=self.section_speed_limit_var, value="无限速").pack(side=tk.LEFT)
        ttk.Radiobutton(f, text="有限速", variable=self.section_speed_limit_var, value="有限速").pack(side=tk.LEFT)
        row += 1
        ttk.Label(section_frame, text="封锁状态:").grid(row=row, column=0, sticky='w', padx=5)
        f = ttk.Frame(section_frame); f.grid(row=row, column=1, sticky='w')
        ttk.Radiobutton(f, text="未封锁", variable=self.section_block_var, value="未封锁").pack(side=tk.LEFT)
        ttk.Radiobutton(f, text="封锁", variable=self.section_block_var, value="封锁").pack(side=tk.LEFT)
        row += 1
        ttk.Label(section_frame, text="ARB状态:").grid(row=row, column=0, sticky='w', padx=5)
        f = ttk.Frame(section_frame); f.grid(row=row, column=1, sticky='w')
        ttk.Radiobutton(f, text="无ARB", variable=self.section_arb_var, value="无ARB").pack(side=tk.LEFT)
        ttk.Radiobutton(f, text="有ARB", variable=self.section_arb_var, value="有ARB").pack(side=tk.LEFT)
        row += 1
        ttk.Label(section_frame, text="占用状态:").grid(row=row, column=0, sticky='w', padx=5)
        f = ttk.Frame(section_frame); f.grid(row=row, column=1, sticky='w')
        for opt in ["未占用", "通信车占用", "非通信车占用", "通信车占用和非通信车占用"]:
            ttk.Radiobutton(f, text=opt, variable=self.section_occupy_var, value=opt).pack(side=tk.LEFT)
        row += 1
        ttk.Label(section_frame, text="锁闭状态:").grid(row=row, column=0, sticky='w', padx=5)
        f = ttk.Frame(section_frame); f.grid(row=row, column=1, sticky='w')
        for opt in ["空闲", "上电锁闭", "进路锁闭", "故障锁闭", "保护锁闭", "跳跃锁闭"]:
            ttk.Radiobutton(f, text=opt, variable=self.section_lock_var, value=opt).pack(side=tk.LEFT)
        row += 1
        ttk.Label(section_frame, text="逻辑区段是否有效:").grid(row=row, column=0, sticky='w', padx=5)
        f = ttk.Frame(section_frame); f.grid(row=row, column=1, sticky='w')
        ttk.Radiobutton(f, text="有效", variable=self.section_valid_var, value="有效").pack(side=tk.LEFT)
        ttk.Radiobutton(f, text="无效", variable=self.section_valid_var, value="无效").pack(side=tk.LEFT)
        row += 1
        ttk.Label(section_frame, text="区段切除:").grid(row=row, column=0, sticky='w', padx=5)
        f = ttk.Frame(section_frame); f.grid(row=row, column=1, sticky='w')
        ttk.Radiobutton(f, text="未切除", variable=self.section_cut_var, value="未切除").pack(side=tk.LEFT)
        ttk.Radiobutton(f, text="切除", variable=self.section_cut_var, value="切除").pack(side=tk.LEFT)

        switch_frame = ttk.LabelFrame(status_container, text="道岔状态设置", padding=5)
        switch_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=2)

        self.switch_pos_var = tk.StringVar(value="四开")
        self.switch_lock_var = tk.StringVar(value="未单锁")
        self.switch_block_var = tk.StringVar(value="未封锁")
        self.switch_guide_var = tk.StringVar(value="未引导总锁")

        row = 0
        ttk.Label(switch_frame, text="道岔位置:").grid(row=row, column=0, sticky='w', padx=5)
        f = ttk.Frame(switch_frame); f.grid(row=row, column=1, sticky='w')
        for opt in ["四开", "定位", "反位", "挤岔"]:
            ttk.Radiobutton(f, text=opt, variable=self.switch_pos_var, value=opt).pack(side=tk.LEFT)
        row += 1
        ttk.Label(switch_frame, text="单锁状态:").grid(row=row, column=0, sticky='w', padx=5)
        f = ttk.Frame(switch_frame); f.grid(row=row, column=1, sticky='w')
        ttk.Radiobutton(f, text="单锁", variable=self.switch_lock_var, value="单锁").pack(side=tk.LEFT)
        ttk.Radiobutton(f, text="未单锁", variable=self.switch_lock_var, value="未单锁").pack(side=tk.LEFT)
        row += 1
        ttk.Label(switch_frame, text="封锁状态:").grid(row=row, column=0, sticky='w', padx=5)
        f = ttk.Frame(switch_frame); f.grid(row=row, column=1, sticky='w')
        ttk.Radiobutton(f, text="封锁", variable=self.switch_block_var, value="封锁").pack(side=tk.LEFT)
        ttk.Radiobutton(f, text="未封锁", variable=self.switch_block_var, value="未封锁").pack(side=tk.LEFT)
        row += 1
        ttk.Label(switch_frame, text="引导总锁:").grid(row=row, column=0, sticky='w', padx=5)
        f = ttk.Frame(switch_frame); f.grid(row=row, column=1, sticky='w')
        ttk.Radiobutton(f, text="引导总锁", variable=self.switch_guide_var, value="引导总锁").pack(side=tk.LEFT)
        ttk.Radiobutton(f, text="未引导总锁", variable=self.switch_guide_var, value="未引导总锁").pack(side=tk.LEFT)

        reg_frame = ttk.LabelFrame(status_container, text="调控权状态设置", padding=5)
        reg_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=2)

        self.regulation_var = tk.StringVar(value="1")
        ttk.Label(reg_frame, text="调控权状态:").pack(anchor='w', pady=2)
        ttk.Radiobutton(reg_frame, text="未知 (0)", variable=self.regulation_var, value="0").pack(anchor='w')
        ttk.Radiobutton(reg_frame, text="遥控 (1)", variable=self.regulation_var, value="1").pack(anchor='w')
        ttk.Radiobutton(reg_frame, text="站控 (2)", variable=self.regulation_var, value="2").pack(anchor='w')
        ttk.Radiobutton(reg_frame, text="紧急站控 (4)", variable=self.regulation_var, value="4").pack(anchor='w')

        psd_frame = ttk.LabelFrame(status_container, text="屏蔽门状态设置", padding=5)
        psd_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=2)
        self.psd_status_var = tk.StringVar(value="0x55")
        ttk.Label(psd_frame, text="屏蔽门状态:").pack(anchor='w', pady=2)
        ttk.Radiobutton(psd_frame, text="关 (0x55)", variable=self.psd_status_var, value="0x55").pack(anchor='w')
        ttk.Radiobutton(psd_frame, text="开 (0xAA)", variable=self.psd_status_var, value="0xAA").pack(anchor='w')
        ttk.Radiobutton(psd_frame, text="互锁解除 (0xFF)", variable=self.psd_status_var, value="0xFF").pack(anchor='w')

        eb_frame = ttk.LabelFrame(status_container, text="紧急停车按钮状态设置", padding=5)
        eb_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=2)
        self.eb_status_var = tk.StringVar(value="0xAA")
        ttk.Label(eb_frame, text="紧急停车按钮状态:").pack(anchor='w', pady=2)
        ttk.Radiobutton(eb_frame, text="按钮被按下 (0x55)", variable=self.eb_status_var, value="0x55").pack(anchor='w')
        ttk.Radiobutton(eb_frame, text="按钮处于释放状态 (0xAA)", variable=self.eb_status_var, value="0xAA").pack(anchor='w')

    # ---------- 早晚点模式面板 ----------
    def init_track_panel(self):
        param_frame = ttk.LabelFrame(self.track_op_frame, text="参数设置", padding=5)
        param_frame.pack(fill=tk.X, pady=5)
        ttk.Checkbutton(param_frame, text="时间戳随机偏移 (0~720小时)",
                        variable=self.track_random_time).pack(anchor=tk.W, padx=5, pady=2)

    # ---------- 参数事件绑定 ----------
    def _bind_param_events(self):
        self.alarm_dev_type.trace('w', lambda *a: self.update_preview_if_needed())
        for var in self.comm_vars.values():
            var.trace('w', lambda *a: self.update_preview_if_needed())
        self.perf_mode.trace('w', lambda *a: self.update_preview_if_needed())
        self.perf_threshold_mode.trace('w', lambda *a: self.update_preview_if_needed())
        station_vars = [
            self.block_var, self.light_var, self.filament_var, self.speed_limit_var, self.lamp_var,
            self.section_speed_limit_var, self.section_block_var, self.section_arb_var, self.section_occupy_var,
            self.section_lock_var, self.section_valid_var, self.section_cut_var,
            self.switch_pos_var, self.switch_lock_var, self.switch_block_var, self.switch_guide_var,
            self.regulation_var, self.psd_status_var, self.eb_status_var
        ]
        for var in station_vars:
            var.trace('w', lambda *a: self.update_preview_if_needed())

    # ---------- 设备勾选回调 ----------
    def on_device_check_changed(self):
        self.update_preview_if_needed()

    # ---------- 预览更新 ----------
    def update_preview_if_needed(self):
        if self._preview_after_id:
            self.root.after_cancel(self._preview_after_id)
        self._preview_after_id = self.root.after(500, self.update_preview)

    def update_preview(self):
        self._preview_after_id = None
        mode = self.mode.get()
        result = ""
        try:
            if mode == "alarm":
                selected, status_byte, version, device_statuses = self._get_alarm_selected_devices_status()
                if selected is not None:
                    _, result = build_alarm_packet(selected, status_byte, version, device_statuses=device_statuses)
                else:
                    result = "请勾选设备或配置通信状态"
            elif mode == "performance":
                selected_dicts, version, mode_val, thresholds, extra = self._get_perf_selected_and_params()
                if selected_dicts is not None:
                    raw = build_full_perf_packet_raw(selected_dicts, mode_val, version, thresholds, extra)
                    result = raw if raw else "生成失败"
                else:
                    result = "请勾选设备"
            elif mode == "station":
                data = self._collect_station_data()
                if data is None:
                    result = "请勾选至少一个设备"
                else:
                    (selected_signals, selected_sections, selected_switches, selected_psds, selected_em_brakes,
                     signal_status, section_status, switch_status, regulation_status, psd_status, eb_status) = data
                    version = self.global_version.get()
                    _, result = build_station_status_packet_full(
                        selected_signals, signal_status,
                        selected_sections, section_status,
                        selected_switches, switch_status,
                        regulation_status,
                        selected_psds, psd_status,
                        selected_em_brakes, eb_status,
                        version=version
                    )
            elif mode == "track":
                result = "早晚点模式报文动态生成，预览暂不支持。点击「开始发送」即开始循环发送。"
        except Exception as e:
            result = f"预览生成错误: {e}"
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, result)

    # ---------- 全局版本变化 ----------
    def on_global_version_changed(self, *args):
        if hasattr(self, 'perf_panel_ready') and self.perf_panel_ready:
            self.build_perf_custom_inputs()
        self.update_preview()

    # ---------- 模式切换 ----------
    def on_mode_changed(self):
        mode = self.mode.get()
        if mode == "alarm":
            self.alarm_op_frame.pack(fill=tk.BOTH, expand=True)
            self.perf_op_frame.pack_forget()
            self.station_op_frame.pack_forget()
            self.track_op_frame.pack_forget()
            self.update_alarm_tree()
        elif mode == "performance":
            self.alarm_op_frame.pack_forget()
            self.perf_op_frame.pack(fill=tk.BOTH, expand=True)
            self.station_op_frame.pack_forget()
            self.track_op_frame.pack_forget()
            self.tree.load_perf_devices(self.perf_devices)
        elif mode == "station":
            self.alarm_op_frame.pack_forget()
            self.perf_op_frame.pack_forget()
            self.station_op_frame.pack(fill=tk.BOTH, expand=True)
            self.track_op_frame.pack_forget()
            self.update_station_tree()
        elif mode == "track":
            self.alarm_op_frame.pack_forget()
            self.perf_op_frame.pack_forget()
            self.station_op_frame.pack_forget()
            self.track_op_frame.pack(fill=tk.BOTH, expand=True)
            self.update_track_tree()
            self.load_track_data()
        self.update_device_count()
        self.update_preview()

    # ---------- 全选/清空 ----------
    def select_all(self):
        self.tree.set_all_checked(True)

    def clear_all(self):
        self.tree.set_all_checked(False)

    # ---------- 数据加载 ----------
    def select_folder(self):
        folder = filedialog.askdirectory(title="选择工作文件夹")
        if folder:
            self.folder_path.set(folder)
            self.load_all_data()
            self.update_preview()

    def load_all_data(self):
        folder = self.folder_path.get().strip()
        if not folder:
            return
        if not os.path.exists(folder):
            messagebox.showerror("错误", "文件夹不存在")
            return

        ats_file = None
        ci_file = None
        mss_file = None
        for f in os.listdir(folder):
            lower_f = f.lower()
            if lower_f.startswith("设备") and (lower_f.endswith(".xlsx") or lower_f.endswith(".xls")):
                ats_file = os.path.join(folder, f)
            elif lower_f.startswith("ci_zc_dsu") and (lower_f.endswith(".xlsx") or lower_f.endswith(".xls")):
                ci_file = os.path.join(folder, f)
            elif lower_f.startswith("ats-mss数据") and (lower_f.endswith(".xlsx") or lower_f.endswith(".xls")):
                mss_file = os.path.join(folder, f)

        self.alarm_devices_data = {}
        if ats_file:
            try:
                devices = read_ats_device_table(ats_file)
                self.alarm_devices_data["04"] = [{'inner_id': d['inner_id'], 'name': d['name'], 'site': d['site']} for d
                                                 in devices]
                self.alarm_devices_data["05"] = [{'inner_id': d['inner_id'], 'name': d['name'], 'site': d['site']} for d
                                                 in devices]
                self.perf_devices = [{'id': d['inner_id'], 'name': d['name'], 'station': d['site']} for d in devices]
                self.perf_devices.sort(key=lambda x: x['id'])
                self.log_status(f"ATS设备表读取成功，设备数: {len(devices)}")
            except Exception as e:
                messagebox.showerror("错误", f"读取设备文件失败: {e}")

        if ci_file:
            try:
                ci_dev = read_generic_device_table(ci_file, "CI", "索引编号", "名称", "集中区")
                ci_dev = filter_test_track(ci_dev, "试车线")
                self.alarm_devices_data["01"] = [{'inner_id': d['inner_id'], 'name': d['name'], 'site': d['site']} for d
                                                 in ci_dev]
                self.log_status(f"CI设备读取成功，数量: {len(ci_dev)}")

                zc_dev = read_generic_device_table(ci_file, "ZC", "索引编号", "名称", "站名称")
                zc_dev = filter_test_track(zc_dev, "试车线")
                self.alarm_devices_data["02"] = [{'inner_id': d['inner_id'], 'name': d['name'], 'site': d['site']} for d
                                                 in zc_dev]
                self.log_status(f"ZC设备读取成功，数量: {len(zc_dev)}")

                dsu_dev = read_generic_device_table(ci_file, "DSU", "索引编号", "名称", "设备位置")
                dsu_dev = filter_test_track(dsu_dev, "试车线")
                self.alarm_devices_data["03"] = [{'inner_id': d['inner_id'], 'name': d['name'], 'site': d['site']} for d
                                                 in dsu_dev]
                self.log_status(f"DSU设备读取成功，数量: {len(dsu_dev)}")
            except Exception as e:
                messagebox.showerror("错误", f"读取CI_ZC_DSU文件失败: {e}")
        else:
            self.log_status("未找到 CI_ZC_DSU 文件（文件名需以 'ci_zc_dsu' 开头）", "WARNING")

        if mss_file:
            try:
                plat_dev = read_platform_table(mss_file)
                self.alarm_devices_data["20"] = [{'inner_id': d['inner_id'], 'name': d['name'], 'site': d['site']} for d
                                                 in plat_dev]
                self.signal_devices = read_signal_table(mss_file)
                self.section_devices = read_logic_section_table(mss_file)
                self.switch_devices = read_switch_table(mss_file)
                self.psd_devices = read_psd_table(mss_file)
                self.em_brake_devices = read_emergency_brake_table(mss_file)
                self.log_status(
                    f"站台设备: {len(plat_dev)}，信号机: {len(self.signal_devices)}，区段: {len(self.section_devices)}，道岔: {len(self.switch_devices)}，屏蔽门: {len(self.psd_devices)}，紧急停车按钮: {len(self.em_brake_devices)}")
            except Exception as e:
                messagebox.showerror("错误", f"读取ATS-MSS数据文件失败: {e}")

        if self.mode.get() == "alarm":
            self.update_alarm_tree()
        elif self.mode.get() == "performance":
            self.tree.load_perf_devices(self.perf_devices)
        elif self.mode.get() == "station":
            self.update_station_tree()
        self.update_device_count()
        self.update_preview()

    # ---------- 报警模式辅助 ----------
    def _get_alarm_selected_devices_status(self):
        dt = self.alarm_dev_type.get()
        if dt == "comm_group":
            selected_devices = []
            device_statuses = {}
            name_map = {"14":"乘客信息系统","15":"时钟系统","16":"广播系统","17":"无线系统","18":"综合监控","19":"TCC"}
            for idx, (code, var) in enumerate(self.comm_vars.items()):
                status_str = var.get()
                match = re.search(r'0x([0-9A-Fa-f]{2})', status_str)
                if match:
                    status_byte = int(match.group(1), 16)
                else:
                    status_byte = 0x55
                selected_devices.append((1, name_map.get(code, code), "通信前置机", code))
                device_statuses[idx] = status_byte
            return selected_devices, 0x55, self.global_version.get(), device_statuses
        else:
            selected = self.tree.get_checked_devices()
            if not selected:
                return None, None, None, None
            selected_devices = [(dev_id, name, site, dt) for (dev_id, name, site) in selected]
            if dt == "05":
                recovery = getattr(self, 'alarm_recovery_var', None)
                if recovery is not None and recovery.get():
                    status_byte = 0x0F
                else:
                    status_byte = 0x0F
                    yellow = getattr(self, 'alarm_yellow_var', None)
                    purple = getattr(self, 'alarm_purple_var', None)
                    d_yellow = getattr(self, 'alarm_direct_yellow_var', None)
                    d_purple = getattr(self, 'alarm_direct_purple_var', None)
                    if yellow is not None and yellow.get():
                        status_byte &= ~0x01
                    if purple is not None and purple.get():
                        status_byte &= ~0x02
                    if d_yellow is not None and d_yellow.get():
                        status_byte &= ~0x04
                    if d_purple is not None and d_purple.get():
                        status_byte &= ~0x08
            elif dt == "04":
                status_byte = self.alarm_type04_var.get() if hasattr(self, 'alarm_type04_var') else 0x55
            elif dt in ("01", "02", "03", "20"):
                status_byte = self.alarm_simple_var.get() if hasattr(self, 'alarm_simple_var') else 0x55
            else:
                status_byte = 0x55
            selected_devices.sort(key=lambda x: x[0])
            return selected_devices, status_byte, self.global_version.get(), None

    def on_alarm_type_changed(self):
        dt = self.alarm_dev_type.get()
        if dt == "comm_group":
            self.comm_frame.pack(fill=tk.X, pady=5)
        else:
            self.comm_frame.pack_forget()
        for child in self.alarm_status_frame.winfo_children():
            child.destroy()

        if dt == "05":
            self.alarm_recovery_var = tk.BooleanVar(value=True)
            self.alarm_yellow_var = tk.BooleanVar(value=False)
            self.alarm_purple_var = tk.BooleanVar(value=False)
            self.alarm_direct_yellow_var = tk.BooleanVar(value=False)
            self.alarm_direct_purple_var = tk.BooleanVar(value=False)

            def on_recovery_changed(*args):
                if self.alarm_recovery_var.get():
                    self.alarm_yellow_var.set(False)
                    self.alarm_purple_var.set(False)
                    self.alarm_direct_yellow_var.set(False)
                    self.alarm_direct_purple_var.set(False)
                self.update_preview_if_needed()

            def on_any_unconnect_changed(*args):
                if (self.alarm_yellow_var.get() or self.alarm_purple_var.get() or
                        self.alarm_direct_yellow_var.get() or self.alarm_direct_purple_var.get()):
                    self.alarm_recovery_var.set(False)
                else:
                    self.alarm_recovery_var.set(True)
                self.update_preview_if_needed()

            self.alarm_recovery_var.trace('w', on_recovery_changed)
            self.alarm_yellow_var.trace('w', on_any_unconnect_changed)
            self.alarm_purple_var.trace('w', on_any_unconnect_changed)
            self.alarm_direct_yellow_var.trace('w', on_any_unconnect_changed)
            self.alarm_direct_purple_var.trace('w', on_any_unconnect_changed)

            recovery_frame = ttk.Frame(self.alarm_status_frame)
            recovery_frame.pack(fill=tk.X, pady=2)
            ttk.Checkbutton(recovery_frame, text="报警恢复（所有连接正常）",
                            variable=self.alarm_recovery_var).pack(anchor=tk.W)

            unconnect_frame = ttk.LabelFrame(self.alarm_status_frame,
                                             text="未连接状态（可多选）", padding=5)
            unconnect_frame.pack(fill=tk.X, pady=5)
            ttk.Checkbutton(unconnect_frame, text="黄网未连接",
                            variable=self.alarm_yellow_var).pack(anchor=tk.W)
            ttk.Checkbutton(unconnect_frame, text="紫网未连接",
                            variable=self.alarm_purple_var).pack(anchor=tk.W)
            ttk.Checkbutton(unconnect_frame, text="直连黄网未连接",
                            variable=self.alarm_direct_yellow_var).pack(anchor=tk.W)
            ttk.Checkbutton(unconnect_frame, text="直连紫网未连接",
                            variable=self.alarm_direct_purple_var).pack(anchor=tk.W)

        elif dt == "04":
            ttk.Label(self.alarm_status_frame, text="设备状态：").pack(anchor=tk.W)
            self.alarm_type04_var = tk.IntVar(value=0x55)
            for text, val in [("主状态 (0x55)", 0x55), ("备状态 (0x33)", 0x33),
                              ("维护态 (0xAA)", 0xaa), ("与维护工作站通信中断 (0x00)", 0x00)]:
                ttk.Radiobutton(self.alarm_status_frame, text=text,
                                variable=self.alarm_type04_var, value=val).pack(anchor=tk.W)
            self.alarm_type04_var.trace('w', lambda *a: self.update_preview_if_needed())

        elif dt in ("01", "02", "03", "20"):
            ttk.Label(self.alarm_status_frame, text="通信状态：").pack(anchor=tk.W)
            self.alarm_simple_var = tk.IntVar(value=0x55)
            for text, val in [("正常 (0x55)", 0x55), ("中断 (0xAA)", 0xaa), ("未知 (0x33)", 0x33)]:
                ttk.Radiobutton(self.alarm_status_frame, text=text,
                                variable=self.alarm_simple_var, value=val).pack(anchor=tk.W)
            self.alarm_simple_var.trace('w', lambda *a: self.update_preview_if_needed())

        self.update_alarm_tree()
        self.update_preview()

    def toggle_comm_all(self):
        pass

    def update_alarm_tree(self):
        dt = self.alarm_dev_type.get()
        if dt == "comm_group":
            self.tree.delete(*self.tree.get_children())
            self.tree.checked.clear()
            self.tree.insert('', 'end', text="通信前置机报警无需选择设备", open=True)
            return
        devices = self.alarm_devices_data.get(dt, [])
        if not devices:
            self.tree.delete(*self.tree.get_children())
            self.tree.checked.clear()
            self.tree.insert('', 'end', text="无设备数据", open=True)
            return
        if dt in ("04", "05"):
            self.tree.load_alarm_devices(devices, use_tree=True)
        else:
            self.tree.load_alarm_devices(devices, use_tree=False)
        self.update_device_count()

    # ---------- 性能模式辅助 ----------
    def _get_perf_selected_and_params(self):
        selected = self.tree.get_checked_devices()
        if not selected:
            return None, None, None, None, None
        selected_dicts = [{'id': dev_id, 'name': name, 'station': site} for (dev_id, name, site) in selected]
        version = self.global_version.get()
        mode = self.perf_mode.get()
        thresholds, extra = self.get_perf_thresholds()
        return selected_dicts, version, mode, thresholds, extra

    def build_perf_custom_inputs(self):
        for widget in self.perf_custom_inner.winfo_children():
            widget.destroy()
        self.perf_custom_entries.clear()
        self.perf_extra_entries.clear()
        version = self.global_version.get()
        labels = [
            ("硬盘空闲报警阈值(GB):", "disk_free", "float"),
            ("CPU使用率报警阈值(%):", "cpu", "int"),
            ("物理内存报警阈值(MB):", "memory", "int"),
            ("句柄数报警阈值:", "handles", "int"),
            ("线程数报警阈值:", "threads", "int"),
            ("DMP数量报警阈值:", "dmp", "int")
        ]
        row = 0
        for label_text, key, typ in labels:
            ttk.Label(self.perf_custom_inner, text=label_text).grid(row=row, column=0, sticky='w', padx=5, pady=2)
            var = tk.DoubleVar() if typ == "float" else tk.IntVar()
            var.set(get_default_thresholds(version)[key])
            entry = ttk.Entry(self.perf_custom_inner, textvariable=var, width=12)
            entry.grid(row=row, column=1, sticky='w', padx=5, pady=2)
            self.perf_custom_entries[key] = var
            var.trace('w', lambda *a: self.update_preview_if_needed())
            row += 1
        if version in ['10.0', '11.0', '12.0']:
            ttk.Label(self.perf_custom_inner, text="硬盘总空间范围(GB):").grid(row=row, column=0, sticky='w', padx=5, pady=2)
            frame = ttk.Frame(self.perf_custom_inner)
            frame.grid(row=row, column=1, sticky='w', padx=5, pady=2)
            min_var = tk.DoubleVar(value=10.1)
            max_var = tk.DoubleVar(value=20.0)
            ttk.Entry(frame, textvariable=min_var, width=8).pack(side=tk.LEFT, padx=2)
            ttk.Label(frame, text="~").pack(side=tk.LEFT)
            ttk.Entry(frame, textvariable=max_var, width=8).pack(side=tk.LEFT, padx=2)
            self.perf_extra_entries['disk_total'] = (min_var, max_var)
            min_var.trace('w', lambda *a: self.update_preview_if_needed())
            max_var.trace('w', lambda *a: self.update_preview_if_needed())
            row += 1
        if version in ['11.0', '12.0']:
            ranges = [
                ("恢复模式运行时间范围(秒):", "run_time_recovery", (0, 100)),
                ("报警模式运行时间范围(秒):", "run_time_alarm", (7776001, 155520000)),
                ("恢复模式CPU温度范围(℃):", "cpu_temp_recovery", (0, 84)),
                ("报警模式CPU温度范围(℃):", "cpu_temp_alarm", (86, 100))
            ]
            for label_text, key, default in ranges:
                ttk.Label(self.perf_custom_inner, text=label_text).grid(row=row, column=0, sticky='w', padx=5, pady=2)
                frame = ttk.Frame(self.perf_custom_inner)
                frame.grid(row=row, column=1, sticky='w', padx=5, pady=2)
                min_var = tk.IntVar(value=default[0])
                max_var = tk.IntVar(value=default[1])
                ttk.Entry(frame, textvariable=min_var, width=10).pack(side=tk.LEFT, padx=2)
                ttk.Label(frame, text="~").pack(side=tk.LEFT)
                ttk.Entry(frame, textvariable=max_var, width=10).pack(side=tk.LEFT, padx=2)
                self.perf_extra_entries[key] = (min_var, max_var)
                min_var.trace('w', lambda *a: self.update_preview_if_needed())
                max_var.trace('w', lambda *a: self.update_preview_if_needed())
                row += 1
        self.perf_custom_inner.update_idletasks()
        self.perf_custom_canvas.configure(scrollregion=self.perf_custom_canvas.bbox('all'))

    def on_perf_threshold_mode_changed(self, event=None):
        if self.perf_threshold_mode.get() == "自定义":
            self.perf_custom_canvas.grid()
            self.perf_custom_scrollbar.grid()
        else:
            self.perf_custom_canvas.grid_remove()
            self.perf_custom_scrollbar.grid_remove()
        self.update_preview_if_needed()

    def get_perf_thresholds(self):
        if self.perf_threshold_mode.get() == "自定义":
            thresholds = {k: v.get() for k, v in self.perf_custom_entries.items()}
            extra = {}
            for k, (v1, v2) in self.perf_extra_entries.items():
                extra[k] = (v1.get(), v2.get())
            return thresholds, extra
        else:
            return None, None

    # ---------- 站场模式辅助 ----------
    def update_station_tree(self):
        self.tree.load_station_devices(self.signal_devices, self.section_devices,
                                       self.switch_devices, self.psd_devices, self.em_brake_devices)

    def _collect_station_data(self):
        selected_signals = self.get_selected_signals()
        selected_sections = self.get_selected_sections()
        selected_switches = self.get_selected_switches()
        selected_psds = self.get_selected_psds()
        selected_em_brakes = self.get_selected_em_brakes()

        if not selected_signals and not selected_sections and not selected_switches and not selected_psds and not selected_em_brakes:
            return None

        selected_signals.sort(key=lambda x: x['signal_id'])
        selected_sections.sort(key=lambda x: x['section_id'])
        selected_switches.sort(key=lambda x: x['switch_id'])

        signal_status = {
            '封锁状态': self.block_var.get(),
            '亮灭状态': self.light_var.get(),
            '灯丝断丝状态': self.filament_var.get(),
            '限速状态': self.speed_limit_var.get(),
            '灯位状态': self.lamp_var.get()
        }
        section_status = {
            '联锁限速': self.section_speed_limit_var.get(),
            '封锁状态': self.section_block_var.get(),
            'ARB状态': self.section_arb_var.get(),
            '占用状态': self.section_occupy_var.get(),
            '锁闭状态': self.section_lock_var.get(),
            '逻辑区段是否有效': self.section_valid_var.get(),
            '区段切除': self.section_cut_var.get()
        }
        switch_status = {
            '道岔位置': self.switch_pos_var.get(),
            '单锁状态': self.switch_lock_var.get(),
            '封锁状态': self.switch_block_var.get(),
            '引导总锁': self.switch_guide_var.get()
        }
        regulation_status = int(self.regulation_var.get())
        psd_status = int(self.psd_status_var.get(), 16)
        eb_status = int(self.eb_status_var.get(), 16)

        return (selected_signals, selected_sections, selected_switches, selected_psds, selected_em_brakes,
                signal_status, section_status, switch_status, regulation_status, psd_status, eb_status)

    def get_selected_signals(self):
        selected = []
        for item in self.tree.checked:
            if not self.tree.get_children(item):
                root = item
                while self.tree.parent(root):
                    root = self.tree.parent(root)
                if "信号机设备" in self.tree.item(root, 'text'):
                    text = self.tree.item(item, 'text')
                    if text.startswith('☑ ') or text.startswith('☐ '):
                        text = text[2:]
                    match = re.search(r'(.+) \(ID:(\d+)\)', text)
                    if match:
                        name = match.group(1)
                        dev_id = int(match.group(2))
                        station = self.tree.item(self.tree.parent(item), 'text')
                        if station.startswith('☑ ') or station.startswith('☐ '):
                            station = station[2:]
                        selected.append({'signal_id': dev_id, 'name': name, 'station': station})
        return selected

    def get_selected_sections(self):
        selected = []
        for item in self.tree.checked:
            if not self.tree.get_children(item):
                root = item
                while self.tree.parent(root):
                    root = self.tree.parent(root)
                if "逻辑区段设备" in self.tree.item(root, 'text'):
                    text = self.tree.item(item, 'text')
                    if text.startswith('☑ ') or text.startswith('☐ '):
                        text = text[2:]
                    match = re.search(r'(.+) \(ID:(\d+)\)', text)
                    if match:
                        name = match.group(1)
                        dev_id = int(match.group(2))
                        station = self.tree.item(self.tree.parent(item), 'text')
                        if station.startswith('☑ ') or station.startswith('☐ '):
                            station = station[2:]
                        selected.append({'section_id': dev_id, 'name': name, 'station': station})
        return selected

    def get_selected_switches(self):
        selected = []
        for item in self.tree.checked:
            if not self.tree.get_children(item):
                root = item
                while self.tree.parent(root):
                    root = self.tree.parent(root)
                if "道岔设备" in self.tree.item(root, 'text'):
                    text = self.tree.item(item, 'text')
                    if text.startswith('☑ ') or text.startswith('☐ '):
                        text = text[2:]
                    match = re.search(r'(.+) \(ID:(\d+)\)', text)
                    if match:
                        name = match.group(1)
                        dev_id = int(match.group(2))
                        station = self.tree.item(self.tree.parent(item), 'text')
                        if station.startswith('☑ ') or station.startswith('☐ '):
                            station = station[2:]
                        selected.append({'switch_id': dev_id, 'name': name, 'station': station})
        return selected

    def get_selected_psds(self):
        selected_ids = set()
        for item in self.tree.checked:
            if not self.tree.get_children(item):
                root = item
                while self.tree.parent(root):
                    root = self.tree.parent(root)
                if "屏蔽门设备" in self.tree.item(root, 'text'):
                    text = self.tree.item(item, 'text')
                    if text.startswith('☑ ') or text.startswith('☐ '):
                        text = text[2:]
                    match = re.search(r'ID[：:]\s*(\d+)', text)
                    if match:
                        dev_id = int(match.group(1))
                        selected_ids.add(dev_id)
        result = []
        for psd in self.psd_devices:
            if psd['psd_id'] in selected_ids:
                result.append({
                    'psd_id': psd['psd_id'],
                    'station': psd.get('station', ''),
                    'name': psd.get('name')
                })
        result.sort(key=lambda x: x['psd_id'])
        return result

    def get_selected_em_brakes(self):
        selected = []
        for item in self.tree.checked:
            if not self.tree.get_children(item):
                root = item
                while self.tree.parent(root):
                    root = self.tree.parent(root)
                if "紧急停车按钮设备" in self.tree.item(root, 'text'):
                    text = self.tree.item(item, 'text')
                    if text.startswith('☑ ') or text.startswith('☐ '):
                        text = text[2:]
                    match = re.search(r'ID：(\d+)\s*（所属站台：(.+)）', text)
                    if match:
                        dev_id = int(match.group(1))
                        station = match.group(2)
                        selected.append({'eb_id': dev_id, 'station': station})
        seen = set()
        unique = []
        for d in selected:
            if d['eb_id'] not in seen:
                seen.add(d['eb_id'])
                unique.append(d)
        unique.sort(key=lambda x: x['eb_id'])
        return unique

    # ---------- 早晚点模式辅助 ----------
    def update_track_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.tree.insert('', 'end', text="早晚点模式无需选择设备", open=True)
        self.device_count_label.config(text="设备总数: 0")

    def load_track_data(self):
        import pymysql
        target_ip = self.tcp_target_ip.get().strip()
        if not target_ip:
            self.log_status("未设置目标客户端 IP，无法连接数据库", "ERROR")
            return False
        try:
            conn = pymysql.connect(host=target_ip, user='root', password='mysql',
                                   database='base', port=3306, charset='utf8')
            cursor = conn.cursor()
            sql = '''
                SELECT a.index_no, b.station_name
                FROM dic_map_logic_section a
                LEFT JOIN dic_map_stop_area b ON a.begin_link_no = b.parking_region_no
                WHERE b.station_name IS NOT NULL
            '''
            cursor.execute(sql)
            section_data = cursor.fetchall()
            cursor.execute("SELECT MIN(index_no), MAX(index_no) FROM dic_map_stop_area")
            row = cursor.fetchone()
            min_index, max_index = row if row else (0, 0)
            conn.close()
            self.track_data_cache = (section_data, min_index, max_index)
            self.log_status(f"数据库连接成功，获取 {len(section_data)} 条区段记录，停车索引范围 {min_index}~{max_index}")
            return True
        except Exception as e:
            self.log_status(f"数据库连接失败: {e}", "ERROR")
            self.track_data_cache = None
            return False

    # ---------- TCP 连接管理 ----------
    def open_tcp_server(self):
        if self.connected:
            messagebox.showinfo("提示", "服务器已开启")
            return
        if self.server_thread and self.server_thread.is_alive():
            return

        local_ip = self.tcp_local_ip.get().strip()
        port_str = self.tcp_port.get().strip()
        try:
            port = int(port_str)
        except:
            messagebox.showerror("错误", "端口必须是整数")
            return

        self.stop_event.clear()
        self.server_thread = threading.Thread(target=self._listen_worker,
                                              args=(local_ip, port), daemon=True)
        self.server_thread.start()
        self.open_server_btn.config(state=tk.DISABLED)
        self.close_server_btn.config(state=tk.NORMAL)
        self.log_status("正在启动 TCP 服务器...")

    def _listen_worker(self, local_ip, port):
        target_ip = self.tcp_target_ip.get().strip()
        server = None
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((local_ip, port))
            server.listen(5)
            server.settimeout(1.0)
            self.server_socket = server
            self.log_status(f"TCP 服务器监听 {local_ip}:{port}，等待目标 {target_ip}...")

            while not self.stop_event.is_set():
                try:
                    client, addr = server.accept()
                    client.settimeout(2.0)
                    if addr[0] == target_ip:
                        with threading.Lock():
                            self.client_sock = client
                            self.connected = True
                        self.root.after(0, self._update_ui_connected, True)
                        self.log_status(f"目标客户端 {target_ip}:{addr[1]} 已连接")
                        while not self.stop_event.is_set():
                            time.sleep(0.5)
                            try:
                                client.getpeername()
                            except:
                                self.log_status("客户端连接已断开", "WARNING")
                                self.root.after(0, self._on_client_disconnected)
                                break
                    else:
                        client.close()
                        self.log_status(f"拒绝非目标 IP 连接: {addr[0]}", "WARNING")
                except socket.timeout:
                    continue
                except Exception as e:
                    if not self.stop_event.is_set():
                        self.log_status(f"监听异常: {e}", "ERROR")
                    break
        except Exception as e:
            self.log_status(f"启动 TCP 服务器失败: {e}", "ERROR")
        finally:
            self._cleanup_connection()
            if server:
                server.close()
                self.server_socket = None
            self.root.after(0, self._update_ui_connected, False)

    def _on_client_disconnected(self):
        if self.connected:
            self.connected = False
            if self.client_sock:
                try:
                    self.client_sock.close()
                except:
                    pass
                self.client_sock = None
            self._update_ui_connected(False)
            self.log_status("连接断开，等待客户端重新连接...")

    def _cleanup_connection(self):
        if self.client_sock:
            try:
                self.client_sock.close()
            except:
                pass
            self.client_sock = None
        self.connected = False

    def _update_ui_connected(self, state):
        if state:
            self.open_server_btn.config(state=tk.DISABLED)
            self.close_server_btn.config(state=tk.NORMAL)
        else:
            self.open_server_btn.config(state=tk.NORMAL)
            self.close_server_btn.config(state=tk.DISABLED)
            if self.send_thread and self.send_thread.is_alive():
                self.stop_sending()

    def close_tcp_server(self):
        if not self.connected and self.server_socket is None:
            messagebox.showinfo("提示", "服务器未开启")
            return
        self.log_status("正在关闭 TCP 服务器...")
        self.send_stop_event.set()
        self.stop_event.set()
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        if self.client_sock:
            try:
                self.client_sock.close()
            except:
                pass
            self.client_sock = None
        self.connected = False
        self._update_ui_connected(False)
        self.send_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.log_status("TCP 服务器已关闭")

    # ---------- 发送控制 ----------
    def toggle_send(self):
        if self.send_thread and self.send_thread.is_alive():
            messagebox.showinfo("提示", "已有发送任务正在进行")
            return

        if not self.connected:
            messagebox.showwarning("警告", "请先点击「开启TCP服务器」建立连接")
            return

        mode = self.mode.get()
        if mode == "alarm":
            self._start_alarm_send()
        elif mode == "performance":
            self._start_perf_send()
        elif mode == "station":
            self._start_station_send()
        elif mode == "track":
            self._start_track_send()

    def _start_alarm_send(self):
        selected, status_byte, version, device_statuses = self._get_alarm_selected_devices_status()
        if selected is None:
            messagebox.showwarning("警告", "请勾选设备或配置通信状态")
            return
        base_packet, timestamp_pos = build_alarm_base_packet(selected, status_byte, version, device_statuses=device_statuses)
        if base_packet is None:
            messagebox.showwarning("警告", "生成基础报文失败")
            return
        self._start_sending(base_packet, timestamp_pos, "alarm", version)

    def _start_perf_send(self):
        selected_dicts, version, mode_val, thresholds, extra = self._get_perf_selected_and_params()
        if selected_dicts is None:
            messagebox.showwarning("警告", "请勾选设备")
            return
        base_packet, timestamp_indices = build_perf_base_packet(selected_dicts, mode_val, version, thresholds, extra)
        if base_packet is None:
            messagebox.showwarning("警告", "生成基础报文失败")
            return
        self._start_sending(base_packet, timestamp_indices, "performance", version)

    def _start_station_send(self):
        data = self._collect_station_data()
        if data is None:
            messagebox.showwarning("警告", "请勾选设备")
            return
        (selected_signals, selected_sections, selected_switches, selected_psds, selected_em_brakes,
         signal_status, section_status, switch_status, regulation_status, psd_status, eb_status) = data
        version = self.global_version.get()
        base_packet, timestamp_pos = build_station_base_packet(
            selected_signals, signal_status,
            selected_sections, section_status,
            selected_switches, switch_status,
            regulation_status,
            selected_psds, psd_status,
            selected_em_brakes, eb_status,
            version=version
        )
        if base_packet is None:
            messagebox.showwarning("警告", "生成基础报文失败")
            return
        self._start_sending(base_packet, timestamp_pos, "station", version)

    def _start_track_send(self):
        if self.track_data_cache is None:
            if not self.load_track_data():
                messagebox.showerror("错误", "无法连接数据库，请检查目标 IP 和数据库服务")
                return
        self.send_stop_event.clear()
        self.track_sending = True
        self.send_thread = threading.Thread(target=self._track_send_worker, daemon=True)
        self.send_thread.start()
        self.send_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.log_status("开始发送早晚点报文...")

    def _start_sending(self, base_packet, timestamp_indices, mode_name, version):
        self.header = base_packet[:5]
        self.body_template = base_packet[5:-5]

        if isinstance(timestamp_indices, int):
            self.timestamp_indices = [timestamp_indices]
        else:
            self.timestamp_indices = timestamp_indices
        self.version = version

        self.send_stop_event.clear()
        self.alarm_sending = (mode_name == "alarm")
        self.perf_sending = (mode_name == "performance")
        self.station_sending = (mode_name == "station")
        self.send_thread = threading.Thread(target=self._send_worker,
                                            args=(mode_name,), daemon=True)
        self.send_thread.start()
        self.send_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.log_status(f"开始发送 {mode_name} 报文...")

    def _send_worker(self, mode_name):
        if not self.connected or self.client_sock is None:
            self.log_status("错误：未建立连接，无法发送", "ERROR")
            self.root.after(0, self.on_send_finished)
            return

        send_count = 0
        last_log_time = time.time()
        header = self.header
        body_template = self.body_template
        timestamp_indices = self.timestamp_indices
        version = self.version

        while not self.send_stop_event.is_set():
            try:
                body = bytearray(body_template)
                current_timestamp = int(time.time())
                for idx in timestamp_indices:
                    struct.pack_into('>I', body, idx, current_timestamp)
                crc = calculate_crc_with_version(body, version)
                packet = header + body + crc + b'\x55'
                self.client_sock.send(packet)
                send_count += 1
                self.send_counter += 1
                now = time.time()
                if now - last_log_time >= 10:
                    self.log_status(f"已发送 {mode_name} 报文 #{send_count} (总第{self.send_counter}次)，持续发送中...")
                    last_log_time = now
                time.sleep(1)
            except (socket.error, BrokenPipeError, ConnectionResetError) as e:
                self.log_status(f"发送失败，连接可能已断开: {e}", "ERROR")
                self.root.after(0, self._on_client_disconnected)
                break
            except Exception as e:
                self.log_status(f"发送过程未知错误: {e}", "ERROR")
                break
        self.root.after(0, self.on_send_finished)

    def _track_send_worker(self):
        if not self.connected or self.client_sock is None:
            self.log_status("错误：未建立连接，无法发送", "ERROR")
            self.root.after(0, self.on_send_finished)
            return

        version = self.global_version.get()
        random_time = self.track_random_time.get()
        section_data, min_idx, max_idx = self.track_data_cache

        while not self.send_stop_event.is_set():
            try:
                packet, _ = build_track_base_packet(section_data, min_idx, max_idx,
                                                    version, random_time, timestamp=int(time.time()))
                self.client_sock.send(packet)
                self.send_counter += 1
                time.sleep(1)
            except (socket.error, BrokenPipeError, ConnectionResetError) as e:
                self.log_status(f"发送失败，连接已断开: {e}", "ERROR")
                self.root.after(0, self._on_client_disconnected)
                break
            except Exception as e:
                self.log_status(f"发送过程未知错误: {e}", "ERROR")
                break
        self.root.after(0, self.on_send_finished)

    def stop_sending(self):
        if not self.send_thread or not self.send_thread.is_alive():
            return
        self.log_status("正在停止发送...")
        self.send_stop_event.set()
        self.send_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.alarm_sending = False
        self.perf_sending = False
        self.station_sending = False
        self.track_sending = False
        self.log_status("报文发送已停止")

    def on_send_finished(self):
        self.send_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.track_sending = False
        self.log_status("发送线程已退出")
        if not self.connected:
            self._update_ui_connected(False)

    # ---------- 日志 ----------
    def log_status(self, msg, level="INFO"):
        timestamp = time.strftime("%H:%M:%S")
        full_msg = f"[{timestamp}][{level}] {msg}\n"
        if self.log_text:
            self.log_text.insert(tk.END, full_msg)
            self.log_text.see(tk.END)
        print(full_msg.strip())

    # ---------- 布局保存 ----------
    def save_layout(self):
        try:
            config = {'geometry': self.root.geometry()}
            if hasattr(self, 'main_pane'):
                config['main_sash'] = self.main_pane.sashpos(0)
            if hasattr(self, 'right_pane'):
                config['right_sash'] = self.right_pane.sashpos(0)
            with open(self.layout_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"保存布局失败: {e}")

    def load_layout(self):
        if not os.path.exists(self.layout_file):
            return
        try:
            with open(self.layout_file, 'r') as f:
                config = json.load(f)
            if 'geometry' in config:
                self.root.geometry(config['geometry'])
            if 'main_sash' in config and hasattr(self, 'main_pane'):
                self.root.after(100, lambda: self.main_pane.sashpos(0, config['main_sash']))
            if 'right_sash' in config and hasattr(self, 'right_pane'):
                self.root.after(100, lambda: self.right_pane.sashpos(0, config['right_sash']))
        except Exception as e:
            print(f"加载布局失败: {e}")

    def on_closing(self):
        self.save_config()
        self.save_layout()
        if self.connected or self.server_socket:
            self.close_tcp_server()
        self.root.destroy()