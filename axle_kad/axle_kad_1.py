"""
计轴报文发送工具（增强版）
- 支持独立选择报警类型（24V故障、12V故障、传感器通道故障、板卡不在位、通信故障、下位机告警）
- 报文预览（带注释）
- 运行日志显示
- 设备统计
- UDP 循环发送
"""

import os
import re
import socket
import sys
import threading
import time
import random
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
import xlrd

# ===================== 精简公共函数 =====================

class PublicFunc:
    def fix_str(self, data, num=2, ishead=True, fix_character='0'):
        str_len = len(data)
        if ishead:
            if str_len < num:
                data = fix_character * (num - str_len) + data
        else:
            if str_len < num:
                data = data + fix_character * (num - str_len)
        return data

    def int_to_hex(self, data, num=2):
        data = int(data)
        data_hex = hex(data)[2:]
        data_hex_len = len(data_hex)
        if data_hex_len > num:
            num = (data_hex_len // 2 + 1) * 2
        data_hex = self.fix_str(data_hex, num)
        return data_hex.upper()

    def data_format(self, data, num=2):
        data = data.replace(" ", "")
        result = []
        for i in range(0, len(data), num):
            result.append(data[i:i+num])
        return ' '.join(result).upper()

    def str_reverse(self, data, num=2):
        data = data.replace(' ', '')
        parts = [data[i:i+num] for i in range(0, len(data), num)]
        return ''.join(parts[::-1])

    def letter_to_number(self, letter):
        letter = letter.upper()
        num = 0
        for c in letter:
            num = num * 26 + (ord(c) - ord('A') + 1)
        return num

    def get_excel_data(self, dir_path, file_name, sheet_name, row_col_name='', start_index=1, end_index=None, isint=True):
        deal_files = []
        return_data = []
        dir_files = os.listdir(dir_path)
        for file in dir_files:
            if file_name in file:
                deal_files.append(file)

        for file in deal_files:
            file_path = os.path.join(dir_path, file)
            if not file_path.lower().endswith(('.xls', '.xlsx')):
                continue
            workbook = xlrd.open_workbook(file_path)
            sheet = workbook.sheet_by_name(sheet_name)

            col_index = self.letter_to_number(row_col_name) - 1
            values = sheet.col(col_index)

            if start_index < 1:
                start_index = 1
            start_row = start_index - 1
            if end_index is not None:
                end_row = end_index + 1
            else:
                end_row = len(values)

            for i in range(start_row, end_row):
                cell = values[i]
                if cell.ctype == 0:
                    continue
                data = cell.value
                if isinstance(data, str):
                    data = data.replace('\n', '').replace('\r', '').strip()
                    if data == '':
                        continue
                if isint:
                    try:
                        return_data.append(int(float(data)))
                    except:
                        continue
                else:
                    return_data.append(data)
        return return_data

    def deal_data(self, data, fix_hour=0, israndomtime=False, isformat=True, time_type=1, return_data_type=1):
        return_time = []
        regex = re.compile(r'(#)(.*)(#)')
        if isinstance(data, str):
            data1 = regex.sub(r'', data)
        else:
            data1 = regex.sub(r'', data.decode('utf-8'))

        data2 = data1.upper().replace('\n', '').replace('\t', '').replace(' ', '')

        while '[' in data2 and ']' in data2:
            start = data2.index('[')
            end = data2.index(']')
            old_time_hex = data2[start+1:end]

            if time_type == 1:
                hour = random.randint(0, 30*24) if israndomtime else fix_hour
                ori_time = int(time.time()) - hour * 3600
            else:
                ori_time = time.time()

            stamp = time.localtime(ori_time)
            mon = hex(stamp[1])[2:]
            day = hex(stamp[2])[2:]
            hour_h = hex(stamp[3])[2:]
            minu = hex(stamp[4])[2:]
            sec = hex(stamp[5])[2:]
            part_time = (self.fix_str(mon) + self.fix_str(day) + self.fix_str(hour_h) + self.fix_str(minu) + self.fix_str(sec))

            is_reverse = 'R' in old_time_hex.upper()
            time_hex = old_time_hex.replace('R', '').replace('r', '')
            time_len = len(time_hex)

            if time_len == 8:
                stamp = int(ori_time)
                hex_time = hex(stamp)[2:]
                if is_reverse:
                    hex_time = self.str_reverse(hex_time)
            elif time_len == 12:
                year = hex(stamp[0] - 2000)[2:]
                hex_time = self.fix_str(year) + part_time
                if is_reverse:
                    hex_time = self.str_reverse(hex_time)
            elif time_len in (14, 18):
                year = hex(stamp[0])[2:]
                year = self.fix_str(year, 4)
                if is_reverse:
                    year = self.str_reverse(year)
                hex_time = year + part_time
                if time_len == 18:
                    ms = int(str(ori_time - int(ori_time))[2:5])
                    ms_hex = self.fix_str(hex(ms)[2:], 4)
                    if is_reverse:
                        ms_hex = self.str_reverse(ms_hex)
                    hex_time += ms_hex
            else:
                stamp = int(ori_time)
                hex_time = hex(stamp)[2:]
                if is_reverse:
                    hex_time = self.str_reverse(hex_time)

            return_time.append(int(ori_time))
            data2 = data2[:start] + hex_time + data2[end+1:]

        if '{' in data2 and '}' in data2:
            start = data2.index('{')
            end = data2.index('}')
            frame_content = data2[start+1:end].replace('(', '').replace(')', '').replace('R', '').replace('r', '')
            frame_len_int = int(len(frame_content) / 2)
            data2 = data2.replace('{', '').replace('}', '')
        else:
            frame_len_int = 0

        if '<' in data2 and '>' in data2:
            start = data2.index('<')
            end = data2.index('>')
            frame_content = data2[start+1:end].replace('(', '').replace(')', '').replace('R', '').replace('r', '')
            frame_len_int = int(len(frame_content) / 2)
            data2 = data2.replace('<', '').replace('>', '')

        if '(' in data2 and ')' in data2:
            if frame_len_int:
                start = data2.index('(')
                end = data2.index(')')
                len_part = data2[start:end+1]
                len_byte = len(len_part.replace('R', '').replace('r', '')) - 2
                len_hex = self.int_to_hex(frame_len_int, len_byte)
                if 'R' in len_part.upper():
                    len_hex = self.str_reverse(len_hex)
                data2 = data2[:start] + len_hex + data2[end+1:]
            else:
                data2 = data2.replace('(', '').replace(')', '')

        if isformat:
            return_data = self.data_format(data2)
        else:
            return_data = data2

        if return_data_type == 1:
            return return_data
        else:
            return return_data, return_time[0]

    def send_to_mss(self, sourse_ip, dest_ip, dest_port, data, time_out=0.1, hour=0, time_type=1, sourse_port=10000, is_show_rec=True):
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_socket.settimeout(time_out)

        data1 = self.deal_data(data, hour, time_type=time_type)
        data1 = data1.upper()
        print('发送报文:', data1)
        postdata = bytes.fromhex(data1)

        host_address = (sourse_ip, sourse_port)
        server_address = (dest_ip, dest_port)
        client_socket.bind(host_address)
        client_socket.sendto(postdata, server_address)

        if is_show_rec:
            try:
                recv_data, addr = client_socket.recvfrom(10240)
                client_socket.close()
                return_data = self.data_format(recv_data.hex())
                print('接收数据：', addr, return_data, '\n')
                return addr, return_data
            except socket.timeout:
                print("无返回数据\n")
                return '', '没有接收到返回报文!'


# ===================== 报文生成函数 =====================

func = PublicFunc()

def make_code(path, file, hour, alarm_config, raw=False):
    '''
    制造axleKAD的报警报文
    alarm_config: dict，包含以下键，值为True表示报警（故障态），False表示正常
        '24v'       - 24V电源故障（区段）
        '12v'       - 12V电源故障（传感器）
        'sensor_ch' - 传感器通道故障
        'board'     - 板卡不在位（放大板、计轴板、输出板）
        'comm'      - 机柜监测主机箱通信故障
        'error'     - 下位机告警驱动
    raw=True 时返回原始模板（含注释），否则返回格式化后的十六进制数据
    '''
    name = '计轴机柜0_ETH板配置'
    start_index = 4

    section_no = func.get_excel_data(path, file, name, 'N', start_index)
    section_name = func.get_excel_data(path, file, name, 'P', start_index, isint=False)
    sensor_no = func.get_excel_data(path, file, name, 'X', start_index)
    sensor_name = func.get_excel_data(path, file, name, 'Z', start_index, isint=False)
    fangdaban = func.get_excel_data(path, file, name, 'D', start_index, 6)
    jizhouban = func.get_excel_data(path, file, name, 'E', start_index, 6)
    jigui_no = func.get_excel_data(path, file, name, 'C', start_index, 6)

    section_no_len = len(section_no)
    section_name_len = len(section_name)
    section_len = min(section_no_len, section_name_len)

    sensor_no_len = len(sensor_no)
    sensor_name_len = len(sensor_name)
    sensor_len = min(sensor_no_len, sensor_name_len)

    fangdaban_len = [0]
    jizhouban_len = [0]
    for i in range(len(fangdaban)):
        fangdaban_len[0] += fangdaban[i]
        jizhouban_len[0] += jizhouban[i]
    fangdaban_len[0] = int(fangdaban_len[0])
    shuchuban_len = jizhouban_len

    # ----- 根据alarm_config生成各状态字节 -----
    # 区段：D7~D6 = 24V (01故障/10正常), D5~D4=00, D3~D2=00, D1~D0=区段占用(随机01或10)
    v24_status = '01' if alarm_config.get('24v', True) else '10'
    quduan_status = random.choice(['01', '10'])  # 保留随机占用/空闲
    section_byte_template = v24_status + '00' + '00' + quduan_status
    section_hex = func.int_to_hex(int(section_byte_template, 2))
    # 传感器：D7~D4=00, D3~D2=12V (01故障/10正常), D1~D0=通道 (01故障/10正常)
    v12_status = '01' if alarm_config.get('12v', True) else '10'
    ch_status = '01' if alarm_config.get('sensor_ch', True) else '10'
    sensor_byte_template = '00' + v12_status + ch_status  # 共8位
    sensor_hex = func.int_to_hex(int(sensor_byte_template, 2))
    # 板卡
    board_status = '02' if alarm_config.get('board', True) else '01'
    # 机柜通信
    comm_status = '02' if alarm_config.get('comm', True) else '01'
    # 下位机告警
    error_status = '01' if alarm_config.get('error', True) else '02'

    section_part = [section_hex + ' ' for _ in range(section_len)]
    sensor_part = [sensor_hex + ' ' for _ in range(sensor_len)]
    fangdaban_part = [board_status + ' ' for _ in range(fangdaban_len[0])]
    jizhouban_part = [board_status + ' ' for _ in range(jizhouban_len[0])]
    shuchuban_part = [board_status + ' ' for _ in range(shuchuban_len[0])]
    zhuji_part = [comm_status + ' ' for _ in range(len(jigui_no))]
    xiaweiji_part = error_status

    baowen = '''
            {AA #帧开始标志#
            (10 B6) #帧长度(从帧头到帧尾)#
            70 #Message Type#
            [5D 88 6D 70] #时间戳#
            00 00 AA AF #报文序列号#
            00 05 #计轴子系统的车站编号#
            #计轴区段 状态: 0x%02X (24V故障=%d, 占用=%d)#
            %s 
            #传感器 状态: 0x%02X (12V故障=%d, 通道故障=%d)#
            %s 
            #放大板 0:初始化 1:板在位 2:板不在位(故障态)#
            %s 
            #计轴板 0:初始化 1:板在位 2:板不在位(故障态)#
            %s 
            #输出板 0:初始化 1:板在位 2:板不在位(故障态)#
            %s
            %s #计轴机柜监测主机箱状态 0:初始化 1:通信正常 2:通信故障(故障态)#
            %s #下位机告警驱动状态 0:初始化 1:有告警(故障态) 2:无告警#
            AA #帧结束标识#}
            ''' % (
                int(section_hex,16), 1 if alarm_config.get('24v', True) else 0, 1 if quduan_status=='01' else 0,
                ''.join(section_part),
                int(sensor_hex,16), 1 if alarm_config.get('12v', True) else 0, 1 if alarm_config.get('sensor_ch', True) else 0,
                ''.join(sensor_part),
                ''.join(fangdaban_part),
                ''.join(jizhouban_part),
                ''.join(shuchuban_part),
                ''.join(zhuji_part),
                xiaweiji_part
            )

    if raw:
        return baowen
    else:
        send_data = func.deal_data(baowen, hour)
        return send_data

def get_station_summary(path, station_name):
    """读取站点配置摘要（只显示设备数量，不依赖报警状态）"""
    name = '计轴机柜0_ETH板配置'
    start_index = 4
    try:
        section_no = func.get_excel_data(path, station_name, name, 'N', start_index)
        section_name = func.get_excel_data(path, station_name, name, 'P', start_index, isint=False)
        sensor_no = func.get_excel_data(path, station_name, name, 'X', start_index)
        sensor_name = func.get_excel_data(path, station_name, name, 'Z', start_index, isint=False)
        fangdaban = func.get_excel_data(path, station_name, name, 'D', start_index, 6)
        jizhouban = func.get_excel_data(path, station_name, name, 'E', start_index, 6)
        jigui_no = func.get_excel_data(path, station_name, name, 'C', start_index, 6)

        section_len = min(len(section_no), len(section_name))
        sensor_len = min(len(sensor_no), len(sensor_name))
        fangdaban_total = sum(fangdaban)
        jizhouban_total = sum(jizhouban)
        shuchuban_total = jizhouban_total
        jigui_count = len(jigui_no)

        summary = f"站点: {station_name}\n\n"
        summary += "【设备配置统计】\n"
        summary += f"  计轴区段数量: {section_len}\n"
        summary += f"  传感器数量:   {sensor_len}\n"
        summary += f"  放大板总数:   {fangdaban_total}\n"
        summary += f"  计轴板总数:   {jizhouban_total}\n"
        summary += f"  输出板总数:   {shuchuban_total}\n"
        summary += f"  机柜数量:     {jigui_count}\n"
        summary += f"  下位机:       1\n"
        summary += "-" * 30 + "\n"
        summary += f"状态点总数: {section_len + sensor_len*2 + fangdaban_total + jizhouban_total + shuchuban_total + jigui_count + 1}"
        return summary
    except Exception as e:
        return f"读取失败: {str(e)}"


# ===================== 日志重定向 =====================

class TextRedirector:
    """将 print 输出重定向到 tkinter Text 控件"""
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, message):
        self.text_widget.after(0, self._insert, message)

    def _insert(self, message):
        self.text_widget.insert(tk.END, message)
        self.text_widget.see(tk.END)

    def flush(self):
        pass


# ===================== GUI 界面 =====================

class AxleSenderGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("计轴KAD报文发送工具")
        self.root.geometry("950x750")
        self.root.minsize(800, 600)

        self.send_thread = None
        self.stop_event = threading.Event()

        # 界面变量
        self.folder_path = tk.StringVar()
        self.sourse_ip = tk.StringVar(value="192.168.2.133")
        self.dest_ip = tk.StringVar(value="192.168.1.249")
        self.dest_port = tk.StringVar(value="10070")
        self.station_var = tk.StringVar()

        # 报警选项（默认全部报警）
        self.alarm_24v = tk.BooleanVar(value=True)
        self.alarm_12v = tk.BooleanVar(value=True)
        self.alarm_sensor_ch = tk.BooleanVar(value=True)
        self.alarm_board = tk.BooleanVar(value=True)
        self.alarm_comm = tk.BooleanVar(value=True)
        self.alarm_error = tk.BooleanVar(value=True)

        self.create_widgets()

        # 绑定事件
        self.station_var.trace_add('write', self.on_config_changed)
        # 所有报警复选框变化时更新预览
        for var in [self.alarm_24v, self.alarm_12v, self.alarm_sensor_ch,
                    self.alarm_board, self.alarm_comm, self.alarm_error]:
            var.trace_add('write', self.on_config_changed)

        # 重定向标准输出到日志区
        sys.stdout = TextRedirector(self.log_text)

    def create_widgets(self):
        # 主布局：垂直 PanedWindow，上方为操作+预览，下方为日志
        main_pw = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        main_pw.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 上方框架
        top_frame = ttk.Frame(main_pw)
        main_pw.add(top_frame, weight=3)

        # 水平分割：左侧控制，右侧预览
        h_pw = ttk.PanedWindow(top_frame, orient=tk.HORIZONTAL)
        h_pw.pack(fill=tk.BOTH, expand=True)

        # ---------- 左侧控制面板 ----------
        left_frame = ttk.Frame(h_pw, width=400)
        h_pw.add(left_frame, weight=1)

        # 站点配置
        frame1 = ttk.LabelFrame(left_frame, text="站点配置")
        frame1.pack(fill="x", padx=5, pady=5)

        ttk.Button(frame1, text="选择文件夹", command=self.select_folder).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Label(frame1, textvariable=self.folder_path, width=35).grid(row=0, column=1, padx=5, pady=5, sticky="w")
        ttk.Label(frame1, text="选择站点:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.station_combo = ttk.Combobox(frame1, textvariable=self.station_var, state="readonly", width=25)
        self.station_combo.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        # 网络参数
        frame2 = ttk.LabelFrame(left_frame, text="网络参数")
        frame2.pack(fill="x", padx=5, pady=5)

        ttk.Label(frame2, text="本机 IP:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        ttk.Entry(frame2, textvariable=self.sourse_ip, width=18).grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(frame2, text="目标 IP:").grid(row=0, column=2, padx=5, pady=5, sticky="e")
        ttk.Entry(frame2, textvariable=self.dest_ip, width=18).grid(row=0, column=3, padx=5, pady=5)
        ttk.Label(frame2, text="目标端口:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        ttk.Entry(frame2, textvariable=self.dest_port, width=8).grid(row=1, column=1, padx=5, pady=5, sticky="w")

        # 报警选项（取代原来的“报文类型”）
        frame3 = ttk.LabelFrame(left_frame, text="报警选项（勾选表示触发该故障）")
        frame3.pack(fill="x", padx=5, pady=5)

        # 使用网格布局排列复选框
        ttk.Checkbutton(frame3, text="24V电源故障", variable=self.alarm_24v).grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Checkbutton(frame3, text="12V电源故障", variable=self.alarm_12v).grid(row=0, column=1, sticky="w", padx=5, pady=2)
        ttk.Checkbutton(frame3, text="传感器通道故障", variable=self.alarm_sensor_ch).grid(row=1, column=0, sticky="w", padx=5, pady=2)
        ttk.Checkbutton(frame3, text="板卡不在位", variable=self.alarm_board).grid(row=1, column=1, sticky="w", padx=5, pady=2)
        ttk.Checkbutton(frame3, text="机柜通信故障", variable=self.alarm_comm).grid(row=2, column=0, sticky="w", padx=5, pady=2)
        ttk.Checkbutton(frame3, text="下位机告警", variable=self.alarm_error).grid(row=2, column=1, sticky="w", padx=5, pady=2)

        # 控制按钮
        frame4 = ttk.Frame(left_frame)
        frame4.pack(pady=10)
        self.send_button = ttk.Button(frame4, text="开始发送", command=self.start_send)
        self.send_button.pack(side="left", padx=10)
        self.stop_button = ttk.Button(frame4, text="停止发送", command=self.stop_send, state=tk.DISABLED)
        self.stop_button.pack(side="left", padx=10)

        # ---------- 右侧预览区（选项卡） ----------
        right_frame = ttk.Frame(h_pw)
        h_pw.add(right_frame, weight=2)

        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # 设备统计标签页
        self.stats_text = scrolledtext.ScrolledText(self.notebook, wrap=tk.WORD, width=50, height=15, font=("Consolas", 10))
        self.notebook.add(self.stats_text, text="设备统计")

        # 报文预览标签页
        self.code_preview = scrolledtext.ScrolledText(self.notebook, wrap=tk.WORD, width=50, height=15, font=("Consolas", 10))
        self.notebook.add(self.code_preview, text="报文预览")

        # ---------- 下方日志区 ----------
        log_frame = ttk.LabelFrame(main_pw, text="运行日志")
        main_pw.add(log_frame, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=8, font=("Consolas", 9), state=tk.NORMAL)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        print("工具已启动，请选择文件夹和站点。")

    def select_folder(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        self.folder_path.set(folder)
        self.scan_stations(folder)

    def scan_stations(self, folder):
        stations = []
        for f in os.listdir(folder):
            if f.endswith('.xls') or f.endswith('.xlsx'):
                base = os.path.splitext(f)[0]
                if '_' in base:
                    parts = base.rsplit('_', 1)
                    station = parts[-1]
                else:
                    station = base
                stations.append(station)
        stations = sorted(set(stations))
        self.station_combo['values'] = stations
        if stations:
            self.station_var.set(stations[0])
            print(f"已加载 {len(stations)} 个站点。")
        else:
            self.station_var.set('')
            print("未找到站点文件。")

    def on_config_changed(self, *args):
        station = self.station_var.get()
        if not station or not self.folder_path.get():
            return
        # 更新设备统计（不依赖报警选项）
        summary = get_station_summary(self.folder_path.get(), station)
        self.stats_text.delete(1.0, tk.END)
        self.stats_text.insert(tk.END, summary)

        # 更新报文预览（根据当前报警选项）
        alarm_config = {
            '24v': self.alarm_24v.get(),
            '12v': self.alarm_12v.get(),
            'sensor_ch': self.alarm_sensor_ch.get(),
            'board': self.alarm_board.get(),
            'comm': self.alarm_comm.get(),
            'error': self.alarm_error.get()
        }
        try:
            raw_code = make_code(self.folder_path.get(), station, 0, alarm_config, raw=True)
        except Exception as e:
            raw_code = f"生成报文失败: {str(e)}"
        self.code_preview.delete(1.0, tk.END)
        self.code_preview.insert(tk.END, raw_code)

    def start_send(self):
        if not self.folder_path.get():
            messagebox.showerror("错误", "请先选择文件夹")
            return
        station = self.station_var.get()
        if not station:
            messagebox.showerror("错误", "请选择站点")
            return

        sourse_ip = self.sourse_ip.get().strip()
        dest_ip = self.dest_ip.get().strip()
        try:
            dest_port = int(self.dest_port.get().strip())
        except ValueError:
            messagebox.showerror("错误", "端口必须是整数")
            return

        # 收集当前报警配置
        alarm_config = {
            '24v': self.alarm_24v.get(),
            '12v': self.alarm_12v.get(),
            'sensor_ch': self.alarm_sensor_ch.get(),
            'board': self.alarm_board.get(),
            'comm': self.alarm_comm.get(),
            'error': self.alarm_error.get()
        }

        self.send_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

        self.stop_event.clear()
        self.send_thread = threading.Thread(
            target=self.send_loop,
            args=(self.folder_path.get(), station, sourse_ip, dest_ip, dest_port, alarm_config),
            daemon=True
        )
        self.send_thread.start()
        # 显示简要的报警状态
        status_str = "，".join([k for k,v in alarm_config.items() if v]) or "无报警"
        print(f"开始发送报文（触发报警: {status_str}），目标 {dest_ip}:{dest_port}")

    def send_loop(self, path, station, sourse_ip, dest_ip, dest_port, alarm_config):
        index = 1
        func_send = PublicFunc()
        while not self.stop_event.is_set():
            print(f"[{index}] 发送报文 -> 站点: {station}")
            try:
                send_data = make_code(path, station, 0, alarm_config)
                func_send.send_to_mss(sourse_ip, dest_ip, dest_port, send_data)
            except Exception as e:
                print(f"发送失败: {e}")
            index += 1
            self.stop_event.wait(1)
        self.root.after(0, self.on_send_stopped)

    def stop_send(self):
        self.stop_event.set()
        self.stop_button.config(state=tk.DISABLED)
        if self.send_thread and self.send_thread.is_alive():
            self.send_thread.join(timeout=2)
        print("发送已停止")

    def on_send_stopped(self):
        self.send_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = AxleSenderGUI()
    app.run()