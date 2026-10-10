# tcp_alarm_gui.py
import configparser
import copy
import datetime
import math
import os
import random
import re
import socket
import struct
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# ==================== PublicFunc 类（完整保留原功能） ====================
class PublicFunc:
    def deal_data(self, data, fix_hour=0, israndomtime=False, isformat=True, time_type=1, return_data_type=1):
        # 去掉##之间的数据,去掉空格,去掉换行符; 注意: 字符串为bytes时，要先转换为str
        regex = re.compile(r'(#)(.*)(#)')
        if isinstance(data, str):
            data1 = regex.sub(r'', data)
        else:
            data1 = regex.sub(r'', data.decode('utf-8'))

        data2 = data1.upper().replace('\n', '').replace('\t', '')
        data3 = data2.replace(" ", "")

        # 修改[ ]里面的时间,加'R'或'r'表示反转时间
        ismiddlebracket = True
        return_time = []
        while ismiddlebracket:
            if '[' in data3 and ']' in data3:
                start_index = data3.index('[')
                end_index = data3.index(']')
                old_time_hex = data3[start_index + 1:end_index]

                if time_type == 1:
                    if israndomtime:
                        hour = random.randint(0, 30 * 24)
                    else:
                        hour = fix_hour
                    ori_time = int(time.time()) - hour * 3600
                else:
                    ori_time = time.time()

                stamp_time = time.localtime(ori_time)
                time_mon = hex(stamp_time[1])[2:]
                time_day = hex(stamp_time[2])[2:]
                time_hour = hex(stamp_time[3])[2:]
                time_min = hex(stamp_time[4])[2:]
                time_second = hex(stamp_time[5])[2:]
                part_time = [self.fix_str(time_mon) + self.fix_str(time_day) + self.fix_str(time_hour) + self.fix_str(time_min) + self.fix_str(time_second)]

                if 'R' in old_time_hex.upper():
                    isreversetime = True
                else:
                    isreversetime = False

                time_hex = old_time_hex.replace('R', '')
                time_len = len(time_hex)

                if time_len == 8:
                    stamp_time = int(ori_time)
                    hex_time = hex(stamp_time)[2:]
                    if isreversetime:
                        hex_time = self.str_reverse(hex_time)
                elif time_len == 12:
                    time_year = hex(stamp_time[0] - 2000)[2:]
                    time_year = self.fix_str(time_year)
                    hex_time = time_year + part_time[0]
                    if isreversetime:
                        hex_time = self.str_reverse(hex_time)
                elif time_len == 14 or time_len == 18:
                    time_year = hex(stamp_time[0])[2:]
                    time_year = self.fix_str(time_year, 4)
                    if isreversetime:
                        time_year = self.str_reverse(time_year)
                    hex_time = time_year + part_time[0]
                    if time_len == 18:
                        millionsecond_int = int(str(ori_time - int(ori_time))[2:5])
                        millionsecond_hex1 = hex(millionsecond_int)[2:]
                        millionsecond_hex2 = self.fix_str(millionsecond_hex1, 4)
                        if isreversetime:
                            millionsecond_hex2 = self.str_reverse(millionsecond_hex2)
                        hex_time = hex_time + millionsecond_hex2
                else:
                    print('时间戳字节特殊情况！')
                    stamp_time = int(ori_time)
                    hex_time = hex(stamp_time)[2:]
                    if isreversetime:
                        hex_time = self.str_reverse(hex_time)

                return_time.append(int(ori_time))
                data3 = data3[0:start_index] + hex_time + data3[end_index + 1:]
            else:
                ismiddlebracket = False

        data4 = data3
        frame_len_int = 0
        if '{' in data4 and '}' in data4:
            start_index = data3.index('{')
            end_index = data3.index('}')
            frame1 = data3[start_index + 1:end_index]
            frame2 = frame1.replace('(', '').replace(')', '')
            frame3 = frame2.replace('R', '')
            frame_len_int = int(len(frame3) / 2)
            data4 = data4.replace('{', '').replace('}', '')

        if '<' in data4 and '>' in data4:
            start_index = data3.index('<')
            end_index = data3.index('>')
            frame1 = data3[start_index + 1:end_index]
            frame2 = frame1.replace('(', '').replace(')', '')
            frame3 = frame2.replace('R', '')
            frame_len_int = int(len(frame3) / 2)
            data4 = data4.replace('<', '').replace('>', '')

        data5 = data4.replace('（','(').replace('）',')')
        if '(' in data5 and ')' in data5:
            if frame_len_int != 0:
                start_index = data4.index('(')
                end_index = data4.index(')')
                len_part_code = data4[start_index:end_index + 1]
                new_len_part_code = len_part_code.replace('R', '')
                len_byte = int(len(new_len_part_code)-2)
                len_byte_hex = self.int_to_hex(frame_len_int, len_byte)
                if 'R' in len_part_code:
                    len_byte_hex = self.str_reverse(len_byte_hex)
                data5 = data4[0:start_index] + len_byte_hex + data4[end_index + 1:]
            else:
                data5 = data4.replace('(', '').replace(')', '')

        if isformat:
            return_data = self.data_format(data5)
        else:
            return_data = data5

        if return_data_type == 1:
            return return_data
        else:
            return return_data, return_time[0]

    def int_to_hex(self, data, num=2):
        data = int(data)
        data_hex = hex(data)[2:]
        data_hex_len = len(data_hex)
        if data_hex_len > num:
            num = math.ceil(data_hex_len/2) * 2
        data_hex = self.fix_str(data_hex, num)
        return data_hex.upper()

    def str_to_bytes(self, str_data):
        str_data = str_data.upper().replace(" ", "")
        bytes_data = bytes.fromhex(str_data)
        return bytes_data

    def data_format(self, data, num=2):
        num1 = int(num)
        return_data = ['']
        data = data.replace(" ", "")
        for i in range(len(data)):
            return_data[0] = return_data[0] + data[num1 * i:num1 * (i + 1)] + ' '
        return return_data[0].upper().strip()

    def fix_str(self, data, num=2, ishead=True, fix_character='0'):
        str_len = len(data)
        if ishead:
            if str_len < num:
                data = fix_character * (num - str_len) + data
        else:
            if str_len < num:
                data = data + fix_character * (num - str_len)
        return data

    def str_reverse(self, data, num=2):
        return_str = ['']
        deal_data = []
        data = data.replace(' ', '')
        for i in range(int(len(data) / num)):
            deal_data.append(data[num * i:num * (i + 1)])
        for d in deal_data[::-1]:
            return_str[0] = return_str[0] + d
        return return_str[0]

    # 其他可能用到的方法简单实现（避免缺失）
    def modify_code_time(self, old_time_data, time_type=1, fix_hour=0, target_time=0, is_random_time=False):
        if time_type == 1:
            if is_random_time:
                hour = random.randint(0, 30 * 24)
            else:
                hour = fix_hour
            ori_time = int(time.time()) - hour * 3600
        elif time_type == 2:
            ori_time = target_time
        else:
            ori_time = time.time()
        stamp_time = time.localtime(ori_time)
        time_year = stamp_time[0]
        time_mon = hex(stamp_time[1])[2:]
        time_day = hex(stamp_time[2])[2:]
        time_hour = hex(stamp_time[3])[2:]
        time_min = hex(stamp_time[4])[2:]
        time_second = hex(stamp_time[5])[2:]
        part_time = '{:0>2}{:0>2}{:0>2}{:0>2}{:0>2}'.format(time_mon, time_day, time_hour, time_min, time_second)
        is_reverse_time = True if 'R' in old_time_data.upper() else False
        time_hex = old_time_data.replace('R', '').replace('r', '')
        time_byte = int(len(time_hex) / 2)
        if time_byte == 4:
            stamp_time = int(ori_time)
            hex_time = hex(stamp_time)[2:]
            if is_reverse_time:
                hex_time = self.str_reverse(hex_time)
        elif time_byte == 6:
            time_year_hex = hex(time_year - 2000)[2:]
            hex_time = '{:0>2}{}'.format(time_year_hex, part_time)
            if is_reverse_time:
                hex_time = self.str_reverse(hex_time)
        elif time_byte == 7 or time_byte == 9:
            time_year_hex = '{:0>4}'.format(hex(time_year)[2:])
            if is_reverse_time:
                time_year_hex = self.str_reverse(time_year_hex)
            hex_time = time_year_hex + part_time
            if time_byte == 18:
                millionsecond_int = int(str(ori_time - int(ori_time))[2:5])
                millionsecond_hex = '{:0>4}'.format(hex(millionsecond_int)[2:])
                hex_time = hex_time + millionsecond_hex
        else:
            stamp_time = int(ori_time)
            hex_time = hex(stamp_time)[2:]
            if is_reverse_time:
                hex_time = self.str_reverse(hex_time)
        return int(ori_time), hex_time

    def calc_code_len(self, data, len_byte=2):
        if '{' in data and '}' in data:
            start_index = data.index('{')
            end_index = data.index('}')
            old_frame = data[start_index + 1:end_index]
            frame = old_frame.replace('(', '').replace(')', '')
            frame = frame.replace('R', '').replace('r', '')
            frame_int = int(len(frame) / 2)
            frame_len = self.fix_str(hex(frame_int)[2:], len_byte * 2)
            new_data = data.replace('{', '').replace('}', '')
        else:
            frame_len = False
            new_data = data
        return frame_len, new_data

    def modify_code_len(self, data, frame_len):
        if frame_len:
            if '(' in data and ')' in data:
                start_index = data.index('(')
                end_index = data.index(')')
                len_part = data[start_index:end_index + 1]
                if 'R' in len_part.upper():
                    frame_len = self.str_reverse(frame_len)
                new_data = data[0:start_index] + frame_len + data[end_index + 1:]
            else:
                new_data = data.replace('(', '').replace(')', '')
        else:
            new_data = data
        return new_data

    def deal_data_new(self, data, fix_hour=0, israndomtime=False, isformat=True, time_type=1, len_byte=4, return_data_type=1):
        regex = re.compile(r'(#)(.*)(#)')
        if isinstance(data, str):
            data1 = regex.sub(r'', data)
        else:
            data1 = regex.sub(r'', data.decode('utf-8'))
        data2 = data1.replace('\n', '').replace(' ', '')
        is_change_time = True
        return_time = []
        while is_change_time:
            if '[' in data2 and ']' in data2:
                start_index = data2.index('[')
                end_index = data2.index(']')
                head_data = data2[0: start_index]
                time_data = data2[start_index + 1:end_index]
                end_data = data2[end_index + 1:]
                ori_time, new_hex_time = self.modify_code_time(time_data, time_type, fix_hour, 0, israndomtime)
                return_time.append(ori_time)
                data2 = head_data + new_hex_time + end_data
            else:
                is_change_time = False
        frame_len, new_data = self.calc_code_len(data2, len_byte)
        new_data = self.modify_code_len(new_data, frame_len)
        if isformat:
            return_data = self.data_format(new_data)
        else:
            return_data = new_data
        if return_data_type == 1:
            return return_data
        else:
            return return_data, return_time[0]


# ==================== GUI 应用（增加报文预览功能） ====================
class AlarmSenderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("微联5报警报文发送工具")
        self.root.geometry("720x680")          # 稍微增加高度以容纳预览区
        self.root.resizable(True, True)

        # 控制变量
        self.send_thread = None
        self.stop_event = threading.Event()
        self.server_socket = None
        self.client_sock = None

        # PublicFunc 实例（用于报文生成）
        self.pf = PublicFunc()

        # 报警类型映射（十六进制代码 -> 显示描述）
        self.alarm_type_map = {
            "21": "轨道电压超限报警",
            "22": "温湿度超限报警",
            "23": "外电网报警",
            "24": "熔丝报警",
            "25": "信号灯丝断丝报警",
            "26": "信号灯点灯电流超限报警",
            "27": "电源漏流超限报警",
            "28": "电缆绝缘超限报警",
            "29": "道岔表示电压超限报警",
            "30": "站台门异常报警",
            "31": "轨道相位角超限报警",
            "34": "道岔失表示报警",
            "35": "自采继电器状态",
            "36": "板件、模块报警"
        }
        # 反向映射：描述 -> 十六进制代码
        self.alarm_type_reverse = {v: k for k, v in self.alarm_type_map.items()}

        # 报警状态映射
        self.alarm_status_map = {
            "00": "正常",
            "55": "故障"
        }
        self.alarm_status_reverse = {v: k for k, v in self.alarm_status_map.items()}
        self.alarm_status_text = ["正常", "故障"]

        self.create_widgets()

        # 初始更新一次报文预览
        self.update_preview()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ========== 参数设置区域 ==========
        param_frame = ttk.LabelFrame(main_frame, text="参数配置", padding="10")
        param_frame.pack(fill=tk.X, pady=(0, 10))

        # 源IP
        ttk.Label(param_frame, text="本机IP :").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.sourse_ip_var = tk.StringVar(value="192.168.2.131")
        ttk.Entry(param_frame, textvariable=self.sourse_ip_var, width=20).grid(row=0, column=1, sticky=tk.W, pady=5)

        # 目标IP
        ttk.Label(param_frame, text="服务器IP :").grid(row=0, column=2, sticky=tk.W, pady=5, padx=(20, 0))
        self.dest_ip_var = tk.StringVar(value="192.168.1.238")
        ttk.Entry(param_frame, textvariable=self.dest_ip_var, width=20).grid(row=0, column=3, sticky=tk.W, pady=5)

        # 报警类型
        ttk.Label(param_frame, text="报警类型:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.test_type_text_var = tk.StringVar(value=list(self.alarm_type_map.values())[0])
        type_combo = ttk.Combobox(param_frame, textvariable=self.test_type_text_var,
                                  values=list(self.alarm_type_map.values()), state="readonly", width=22)
        type_combo.grid(row=1, column=1, sticky=tk.W, pady=5, columnspan=3)
        type_combo.bind("<<ComboboxSelected>>", lambda e: self.update_preview())

        # 报警状态
        ttk.Label(param_frame, text="报警状态:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.test_status_text_var = tk.StringVar(value="正常")
        status_combo = ttk.Combobox(param_frame, textvariable=self.test_status_text_var,
                                    values=self.alarm_status_text, state="readonly", width=10)
        status_combo.grid(row=2, column=1, sticky=tk.W, pady=5)
        status_combo.bind("<<ComboboxSelected>>", lambda e: self.update_preview())

        # 设备数量
        ttk.Label(param_frame, text="报警设备总数:").grid(row=2, column=2, sticky=tk.W, pady=5, padx=(20, 0))
        self.device_num_var = tk.StringVar(value="29")
        device_entry = ttk.Entry(param_frame, textvariable=self.device_num_var, width=10)
        device_entry.grid(row=2, column=3, sticky=tk.W, pady=5)
        device_entry.bind("<KeyRelease>", lambda e: self.update_preview())

        # 休眠时间
        ttk.Label(param_frame, text="休眠时间(秒):").grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Label(param_frame, text="2 (固定)", foreground="gray").grid(row=3, column=1, sticky=tk.W, pady=5)

        # ========== 控制按钮区域 ==========
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)

        self.start_btn = ttk.Button(btn_frame, text="开始发送", command=self.start_sending)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(btn_frame, text="停止发送", command=self.stop_sending, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # ========== 可伸缩区域（PanedWindow）==========
        paned = ttk.PanedWindow(main_frame, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # ----- 报文预览区域 -----
        preview_frame = ttk.LabelFrame(paned, text="报文预览 (实际发送的十六进制)", padding="5")
        paned.add(preview_frame, weight=1)  # weight 控制伸缩比例

        # 预览文本框 + 滚动条
        text_frame = ttk.Frame(preview_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.preview_text = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 9))
        self.preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        v_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.preview_text.yview)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.preview_text.config(yscrollcommand=v_scroll.set)

        # 复制按钮放在预览区右上角（不占滚动条空间）
        copy_btn = ttk.Button(preview_frame, text="复制报文", command=self.copy_preview)
        copy_btn.pack(side=tk.RIGHT, padx=(5, 0), pady=(0, 5))

        # ----- 日志区域 -----
        log_frame = ttk.LabelFrame(paned, text="运行日志", padding="5")
        paned.add(log_frame, weight=2)  # 日志区分配更多比例

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ------------------ 日志与状态 ------------------
    def log(self, msg, level="INFO"):
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] [{level}] {msg}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def set_status(self, text):
        self.status_var.set(text)
        self.root.update_idletasks()

    # ------------------ 报文生成与预览 ------------------
    def build_alarm_frame(self):
        """构造报警数据帧（原始格式，含有#{}[]等标记）"""
        station_no = 20
        station_hex = self.pf.int_to_hex(station_no, 4)

        try:
            device_num = int(self.device_num_var.get().strip())
            if device_num < 0:
                device_num = 0
        except:
            device_num = 0

        device_num_hex = self.pf.int_to_hex(device_num, 4)

        # 获取当前选择的报警类型和状态的十六进制代码
        type_text = self.test_type_text_var.get()
        status_text = self.test_status_text_var.get()
        alarm_type_hex = self.alarm_type_reverse.get(type_text, "21")
        alarm_status_hex = self.alarm_status_reverse.get(status_text, "00")

        # 构造报警数据串: 每个设备两个字节（类型+状态）
        alarm_pair = alarm_type_hex + alarm_status_hex
        values_str = ' '.join([alarm_pair for _ in range(device_num)])

        # 帧长度计算: 每个设备2字节 + 固定17字节
        data_len_int = device_num * 2 + 17
        data_len_hex = self.pf.int_to_hex(data_len_int, 4)

        raw_data = f"""
            AA #帧开始标志#
            {data_len_hex} #帧长度(从STATIONID开始到CRC校验结束)#
            {station_hex} #站报码#
            20 #Message Type#
            [5D C2 14 13] #时间戳#
            00 94 06 22 #报文序列号#
            {device_num_hex} #报警总数#
            #报警类型，报警状态-0x00：正常 0x55：故障#
            {values_str}
            4E A5 30 EF #CRC校验#
            55 #帧的结束标识#
        """
        return raw_data

    def get_current_preview(self):
        """根据当前界面参数生成最终发送的十六进制报文（带空格）"""
        try:
            raw_frame = self.build_alarm_frame()
            # 处理原始帧，得到实际发送的十六进制字符串
            processed = self.pf.deal_data(raw_frame, isformat=True)
            return processed
        except Exception as e:
            return f"生成报文失败: {str(e)}"

    def update_preview(self):
        """刷新报文预览区"""
        preview = self.get_current_preview()
        self.preview_text.delete(1.0, tk.END)
        self.preview_text.insert(1.0, preview)
        # 自动调整文本框高度（可选）
        # lines = preview.count('\n') + 1
        # if lines < 3:
        #     lines = 3
        # elif lines > 8:
        #     lines = 8
        # self.preview_text.config(height=lines)

    def copy_preview(self):
        """复制当前预览报文到剪贴板"""
        content = self.preview_text.get(1.0, tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.log("报文已复制到剪贴板", "INFO")
            self.set_status("报文已复制")
            # 2秒后恢复状态
            self.root.after(2000, lambda: self.set_status("就绪" if not self.send_thread or not self.send_thread.is_alive() else "发送中"))
        else:
            self.log("无有效报文可复制", "WARNING")

    # ------------------ 发送相关 ------------------
    def validate_inputs(self):
        """验证输入参数并存储到实例变量中（保留原功能）"""
        sourse_ip = self.sourse_ip_var.get().strip()
        dest_ip = self.dest_ip_var.get().strip()
        if not sourse_ip or not dest_ip:
            messagebox.showerror("错误", "请填写源IP和目标IP")
            return False
        ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
        if not ip_pattern.match(sourse_ip) or not ip_pattern.match(dest_ip):
            messagebox.showerror("错误", "IP地址格式不正确")
            return False

        try:
            device_num = int(self.device_num_var.get())
            if device_num <= 0:
                raise ValueError
        except:
            messagebox.showerror("错误", "设备总数必须为正整数")
            return False

        # 获取报警类型十六进制代码
        type_text = self.test_type_text_var.get()
        if type_text not in self.alarm_type_reverse:
            messagebox.showerror("错误", "无效的报警类型")
            return False
        alarm_type_hex = self.alarm_type_reverse[type_text]

        # 获取报警状态十六进制代码
        status_text = self.test_status_text_var.get()
        if status_text not in self.alarm_status_reverse:
            messagebox.showerror("错误", "无效的报警状态")
            return False
        alarm_status_hex = self.alarm_status_reverse[status_text]

        # 存储到实例变量供发送使用
        self.alarm_type_hex = alarm_type_hex
        self.alarm_status_hex = alarm_status_hex
        self.device_num = device_num

        return True

    def send_worker(self):
        """发送线程主函数（与原逻辑一致）"""
        func = PublicFunc()
        sourse_ip = self.sourse_ip_var.get().strip()
        dest_ip = self.dest_ip_var.get().strip()
        port = 10060
        sleep_time = 2  # 固定2秒

        # 创建TCP服务器
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((sourse_ip, port))
            server.listen(5)
            server.settimeout(1.0)
            self.server_socket = server
            self.log(f"TCP服务已启动，监听 {sourse_ip}:{port}")
            self.set_status("等待客户端连接...")
        except Exception as e:
            self.log(f"启动TCP服务失败: {e}", "ERROR")
            self.root.after(0, self.on_send_finished)
            return

        # 等待正确的客户端连接
        while not self.stop_event.is_set():
            try:
                client, addr = server.accept()
                client.settimeout(2.0)
                if addr[0] == dest_ip:
                    self.client_sock = client
                    self.log(f"目标服务器 {dest_ip}:{addr[1]} 已连接")
                    self.set_status("已连接，正在发送报警...")
                    break
                else:
                    self.log(f"拒绝非目标IP连接: {addr[0]}，等待目标 {dest_ip}", "WARNING")
                    client.close()
            except socket.timeout:
                continue
            except Exception as e:
                if not self.stop_event.is_set():
                    self.log(f"接受连接异常: {e}", "ERROR")
                break
        else:
            server.close()
            self.root.after(0, self.on_send_finished)
            return

        # 发送循环
        send_count = 0
        while not self.stop_event.is_set():
            try:
                raw_frame = self.build_alarm_frame()
                processed_frame = func.deal_data(raw_frame)
                send_bytes = func.str_to_bytes(processed_frame)
                self.client_sock.send(send_bytes)
                send_count += 1
                self.log(f"已发送报警 #{send_count} | 类型:{self.test_type_text_var.get()} | 状态:{self.test_status_text_var.get()} | 设备数:{self.device_num}")
                for _ in range(sleep_time):
                    if self.stop_event.is_set():
                        break
                    time.sleep(1)
            except (socket.error, BrokenPipeError, ConnectionResetError) as e:
                self.log(f"发送失败，连接可能已断开: {e}", "ERROR")
                if self.client_sock:
                    self.client_sock.close()
                    self.client_sock = None
                self.set_status("连接断开，重新等待目标服务器...")
                while not self.stop_event.is_set():
                    try:
                        client, addr = server.accept()
                        client.settimeout(2.0)
                        if addr[0] == dest_ip:
                            self.client_sock = client
                            self.log(f"重新连接成功: {dest_ip}:{addr[1]}")
                            self.set_status("已重新连接，继续发送...")
                            break
                        else:
                            client.close()
                    except socket.timeout:
                        continue
                    except Exception as ex:
                        self.log(f"重连异常: {ex}", "ERROR")
                        break
                continue
            except Exception as e:
                self.log(f"发送过程未知错误: {e}", "ERROR")
                break

        if self.client_sock:
            self.client_sock.close()
        if self.server_socket:
            self.server_socket.close()
        self.root.after(0, self.on_send_finished)

    def on_send_finished(self):
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.set_status("已停止")
        self.log("发送任务已停止")

    def start_sending(self):
        if not self.validate_inputs():
            return
        if self.send_thread and self.send_thread.is_alive():
            messagebox.showwarning("警告", "发送线程已在运行中")
            return

        self.stop_event.clear()
        self.send_thread = threading.Thread(target=self.send_worker, daemon=True)
        self.send_thread.start()

        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.set_status("正在启动...")
        self.log("开始发送报警，休眠时间固定2秒")

    def stop_sending(self):
        self.log("正在停止发送...")
        self.stop_event.set()
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        if self.client_sock:
            try:
                self.client_sock.close()
            except:
                pass
        self.set_status("正在停止...")


if __name__ == "__main__":
    root = tk.Tk()
    app = AlarmSenderApp(root)
    root.mainloop()