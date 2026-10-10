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
import zlib

# ==================== PublicFunc 类 ====================
class PublicFunc:
    def deal_data(self, data, fix_hour=0, israndomtime=False, isformat=True, time_type=1, return_data_type=1):
        regex = re.compile(r'(#)(.*)(#)')
        if isinstance(data, str):
            data1 = regex.sub(r'', data)
        else:
            data1 = regex.sub(r'', data.decode('utf-8'))

        data2 = data1.upper().replace('\n', '').replace('\t', '')
        data3 = data2.replace(" ", "")

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

    def calc_crc32(self, data_hex):
        data_bytes = bytes.fromhex(data_hex)
        crc = zlib.crc32(data_bytes) & 0xFFFFFFFF
        return format(crc, '08X')


# ==================== 模拟量生成函数 ====================
def int_to_hex_orig(value, byte_len=2):
    return format(value, '0{}X'.format(byte_len * 2))

def calc_crc_orig(data_hex):
    data_bytes = bytes.fromhex(data_hex)
    crc = zlib.crc32(data_bytes) & 0xFFFFFFFF
    return format(crc, '08X')

def build_packet_orig(payload_hex, msg_id, type_id, sn, stamp=None):
    if stamp is None:
        stamp = int(time.time())
    stamp_hex = int_to_hex_orig(stamp, 4)
    sn_hex = int_to_hex_orig(sn, 4)
    station_hex = int_to_hex_orig(1, 2)
    mid_hex = int_to_hex_orig(msg_id, 1)
    tid_hex = int_to_hex_orig(type_id, 1)
    check_data_no_len = station_hex + mid_hex + tid_hex + stamp_hex + sn_hex + payload_hex
    len_bytes = 2 + 1 + 1 + 4 + 4 + len(payload_hex)//2 + 4
    len_hex = int_to_hex_orig(len_bytes, 2)
    check_data = len_hex + check_data_no_len
    crc_hex = calc_crc_orig(check_data)
    full = 'AA' + len_hex + check_data_no_len + crc_hex + '55'
    return full, stamp_hex

def format_packet_orig(full_packet, stamp_hex):
    part1 = full_packet[:14]
    stamp_part = '[' + ' '.join(stamp_hex[i:i+2] for i in range(0, 8, 2)).upper() + ']'
    part2 = full_packet[22:]
    part1_spaced = ' '.join(part1[i:i+2] for i in range(0, len(part1), 2)).upper()
    part2_spaced = ' '.join(part2[i:i+2] for i in range(0, len(part2), 2)).upper()
    return f"{part1_spaced} {stamp_part} {part2_spaced}"

# ---------- 非道岔类型生成函数 ----------
def make_cable_insulation_orig(device_no, sn):
    value_int = random.randint(0, 30000)
    item_hex = int_to_hex_orig(device_no, 2)
    analog_hex = int_to_hex_orig(value_int, 2)
    payload = item_hex + analog_hex
    full, stamp = build_packet_orig(payload, 0x40, 0x41, sn)
    show = f'设备号:{device_no}  绝缘值:{value_int/100:.2f} MΩ'
    return full, show, stamp

def make_track_voltage_orig(device_no, sn):
    analog_num = random.randint(1, 10)
    analog_num_hex = int_to_hex_orig(analog_num, 2)
    analogs_hex = ''
    for _ in range(analog_num):
        val = random.randint(150, 280)
        analogs_hex += int_to_hex_orig(val, 2)
    payload = analog_num_hex + analogs_hex
    full, stamp = build_packet_orig(payload, 0x40, 0x43, sn)
    show = f'设备号:{device_no}  轨道电压({analog_num}路)'
    return full, show, stamp

def make_temperature_orig(device_no, sn):
    analog_num = random.randint(1, 5)
    analog_num_hex = int_to_hex_orig(analog_num, 2)
    analogs_hex = ''
    for _ in range(analog_num):
        val = random.randint(0, 300)
        analogs_hex += int_to_hex_orig(val, 2)
    payload = analog_num_hex + analogs_hex
    full, stamp = build_packet_orig(payload, 0x40, 0x45, sn)
    show = f'设备号:{device_no}  温湿度({analog_num}路)'
    return full, show, stamp

def make_signal_lamp_current_orig(device_no, sn):
    analog_num = random.randint(1, 5)
    analog_num_hex = int_to_hex_orig(analog_num, 2)
    items_hex = ''
    for i in range(analog_num):
        item_no = device_no * 100 + i
        items_hex += int_to_hex_orig(item_no, 2)
        val = random.randint(0, 5000)
        items_hex += int_to_hex_orig(val, 2)
    payload = analog_num_hex + items_hex
    full, stamp = build_packet_orig(payload, 0x40, 0x47, sn)
    show = f'设备号:{device_no}  信号机点灯电流({analog_num}路)'
    return full, show, stamp

def make_platform_door_voltage_all_orig(total_devices, sn):
    analog_num = total_devices
    analog_num_hex = int_to_hex_orig(analog_num, 2)
    analogs_hex = ''
    voltages = []
    for _ in range(analog_num):
        val = random.randint(0, 5000)
        analogs_hex += int_to_hex_orig(val, 2)
        voltages.append(val / 10.0)
    payload = analog_num_hex + analogs_hex
    full, stamp = build_packet_orig(payload, 0x40, 0x51, sn)
    show = f'站台门电压 共{analog_num}路: ' + ', '.join(f'{v:.1f}V' for v in voltages)
    return full, show, stamp

def make_power_leakage_orig(device_no, sn):
    value_int = random.randint(0, 30000)
    item_hex = int_to_hex_orig(device_no, 2)
    analog_hex = int_to_hex_orig(value_int, 2)
    payload = item_hex + analog_hex
    full, stamp = build_packet_orig(payload, 0x40, 0x52, sn)
    show = f'设备号:{device_no}  漏流值:{value_int/100:.2f} mA'
    return full, show, stamp

def make_axle_counter_voltage_orig(device_no, sn):
    analog_num = 4
    analog_num_hex = int_to_hex_orig(analog_num, 2)
    analogs_hex = ''
    for _ in range(analog_num):
        val = random.randint(0, 500)
        analogs_hex += int_to_hex_orig(val, 2)
    payload = analog_num_hex + analogs_hex
    full, stamp = build_packet_orig(payload, 0x40, 0x54, sn)
    show = f'设备号:{device_no}  计轴电压(4路)'
    return full, show, stamp

def make_track_phase_angle_orig(device_no, sn):
    analog_num = 4
    analog_num_hex = int_to_hex_orig(analog_num, 2)
    analogs_hex = ''
    for _ in range(analog_num):
        val = random.randint(0, 30000)
        analogs_hex += int_to_hex_orig(val, 2)
    payload = analog_num_hex + analogs_hex
    full, stamp = build_packet_orig(payload, 0x40, 0x55, sn)
    show = f'设备号:{device_no}  轨道相位角(4路)'
    return full, show, stamp

def make_switch_machine_current_orig(device_no, sn):
    analog_num = 4
    analog_num_hex = int_to_hex_orig(analog_num, 2)
    analogs_hex = ''
    for _ in range(analog_num):
        val = random.randint(0, 1000)
        analogs_hex += int_to_hex_orig(val, 2)
    payload = analog_num_hex + analogs_hex
    full, stamp = build_packet_orig(payload, 0x40, 0x56, sn)
    show = f'设备号:{device_no}  转辙机总电流(4路)'
    return full, show, stamp

# ===== 道岔表示电压（批量模式，每个设备一个模拟量，2字节） =====
def make_switch_indication_voltage_all_orig(total_devices, sn):
    analog_num = total_devices
    analog_num_hex = int_to_hex_orig(analog_num, 2)
    analogs_hex = ''
    for _ in range(analog_num):
        val = random.randint(0, 500)
        analogs_hex += int_to_hex_orig(val, 2)
    payload = analog_num_hex + analogs_hex
    full, stamp = build_packet_orig(payload, 0x40, 0x44, sn)
    show = f'道岔表示电压 共{total_devices}个设备，每个1路'
    return full, show, stamp

# ==================== GUI 应用 ====================
class AlarmSenderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("微联5报警与模拟量发送工具")
        self.root.geometry("820x800")
        self.root.resizable(True, True)

        self.send_thread = None
        self.stop_event = threading.Event()
        self.server_socket = None
        self.client_sock = None
        self.current_mode = 'alarm'

        self.pf = PublicFunc()

        # ===== 报警映射 =====
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
        self.alarm_type_reverse = {v: k for k, v in self.alarm_type_map.items()}
        self.alarm_status_map = {"00": "正常", "55": "故障"}
        self.alarm_status_reverse = {v: k for k, v in self.alarm_status_map.items()}
        self.alarm_status_text = ["正常", "故障"]

        # ===== 模拟量类型映射 =====
        self.analog_type_map = {
            '1': ('电缆绝缘', self._make_cable_insulation),
            '2': ('道岔电流', self._make_switch_current),
            '3': ('道岔功率', self._make_switch_power),
            '4': ('轨道电压', self._make_track_voltage),
            '5': ('温湿度', self._make_temperature),
            '6': ('道岔表示电压', self._make_switch_indication_voltage_all),
            '8': ('信号机点灯电流', self._make_signal_lamp_current),
            '9': ('站台门电压', self._make_platform_door_voltage_all),
            '10': ('电源漏流', self._make_power_leakage),
            '11': ('计轴电压', self._make_axle_counter_voltage),
            '12': ('轨道相位角', self._make_track_phase_angle),
            '13': ('转辙机总电流', self._make_switch_machine_current),
        }
        self.batch_types = {'9', '6'}
        self.switch_types = {'2', '3'}

        # ===== 高级参数 =====
        self.analog_params = {
            'curve_type': 0,
            'curve_count': 3,
            'point_mode': 'fixed',
            'point_fixed': 20,
            'point_min': 10,
            'point_max': 50,
            'direction': 0,
        }
        self.power_type_var = tk.StringVar(value="0x53")

        self.create_widgets()
        self.update_preview()

    # ---------- 界面创建 ----------
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ===== 顶部网络配置 =====
        top_frame = ttk.LabelFrame(main_frame, text="网络配置", padding="5")
        top_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(top_frame, text="本机IP :").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.sourse_ip_var = tk.StringVar(value="192.168.2.131")
        ttk.Entry(top_frame, textvariable=self.sourse_ip_var, width=18).grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(top_frame, text="服务器IP :").grid(row=0, column=2, sticky=tk.W, padx=(20, 5))
        self.dest_ip_var = tk.StringVar(value="192.168.1.238")
        ttk.Entry(top_frame, textvariable=self.dest_ip_var, width=18).grid(row=0, column=3, sticky=tk.W, padx=5)

        btn_frame = ttk.Frame(top_frame)
        btn_frame.grid(row=0, column=4, padx=(30, 0))
        self.start_btn = ttk.Button(btn_frame, text="开始发送", command=self.start_sending)
        self.start_btn.pack(side=tk.LEFT, padx=2)
        self.stop_btn = ttk.Button(btn_frame, text="停止发送", command=self.stop_sending, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=2)
        self.disconnect_btn = ttk.Button(btn_frame, text="断开连接", command=self.disconnect, state=tk.NORMAL)
        self.disconnect_btn.pack(side=tk.LEFT, padx=2)

        # ===== Notebook =====
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=5)

        # --- 报警页 ---
        alarm_frame = ttk.Frame(notebook, padding="5")
        notebook.add(alarm_frame, text="报警发送")

        alarm_param_frame = ttk.LabelFrame(alarm_frame, text="报警参数", padding="5")
        alarm_param_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(alarm_param_frame, text="报警类型:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.alarm_type_text_var = tk.StringVar(value=list(self.alarm_type_map.values())[0])
        type_combo = ttk.Combobox(alarm_param_frame, textvariable=self.alarm_type_text_var,
                                  values=list(self.alarm_type_map.values()), state="readonly", width=25)
        type_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=3)
        type_combo.bind("<<ComboboxSelected>>", lambda e: self.update_preview())

        ttk.Label(alarm_param_frame, text="报警状态:").grid(row=0, column=2, sticky=tk.W, padx=(20, 5), pady=3)
        self.alarm_status_text_var = tk.StringVar(value="正常")
        status_combo = ttk.Combobox(alarm_param_frame, textvariable=self.alarm_status_text_var,
                                    values=self.alarm_status_text, state="readonly", width=10)
        status_combo.grid(row=0, column=3, sticky=tk.W, padx=5, pady=3)
        status_combo.bind("<<ComboboxSelected>>", lambda e: self.update_preview())

        ttk.Label(alarm_param_frame, text="报警设备总数:").grid(row=0, column=4, sticky=tk.W, padx=(20, 5), pady=3)
        self.alarm_device_num_var = tk.StringVar(value="29")
        device_entry = ttk.Entry(alarm_param_frame, textvariable=self.alarm_device_num_var, width=10)
        device_entry.grid(row=0, column=5, sticky=tk.W, padx=5, pady=3)
        device_entry.bind("<KeyRelease>", lambda e: self.update_preview())

        alarm_preview_frame = ttk.LabelFrame(alarm_frame, text="报文预览 (实际发送的十六进制)", padding="5")
        alarm_preview_frame.pack(fill=tk.BOTH, expand=True)
        alarm_text_frame = ttk.Frame(alarm_preview_frame)
        alarm_text_frame.pack(fill=tk.BOTH, expand=True)
        self.alarm_preview_text = tk.Text(alarm_text_frame, wrap=tk.WORD, font=("Consolas", 9))
        self.alarm_preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll_alarm = ttk.Scrollbar(alarm_text_frame, orient=tk.VERTICAL, command=self.alarm_preview_text.yview)
        v_scroll_alarm.pack(side=tk.RIGHT, fill=tk.Y)
        self.alarm_preview_text.config(yscrollcommand=v_scroll_alarm.set)
        copy_alarm_btn = ttk.Button(alarm_preview_frame, text="复制报文", command=self.copy_alarm_preview)
        copy_alarm_btn.pack(side=tk.RIGHT, padx=(5, 0), pady=(0, 5))

        # --- 模拟量页 ---
        analog_frame = ttk.Frame(notebook, padding="5")
        notebook.add(analog_frame, text="模拟量发送")

        # 基础参数
        analog_param_frame = ttk.LabelFrame(analog_frame, text="模拟量参数", padding="5")
        analog_param_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(analog_param_frame, text="模拟量类型:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.analog_type_text_var = tk.StringVar(value=list(self.analog_type_map.values())[0][0])
        analog_type_combo = ttk.Combobox(analog_param_frame, textvariable=self.analog_type_text_var,
                                         values=[desc for desc, _ in self.analog_type_map.values()],
                                         state="readonly", width=20)
        analog_type_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=3)
        analog_type_combo.bind("<<ComboboxSelected>>", self.on_analog_type_changed)

        ttk.Label(analog_param_frame, text="设备数量:").grid(row=0, column=2, sticky=tk.W, padx=(20, 5), pady=3)
        self.analog_device_num_var = tk.StringVar(value="5")
        analog_device_entry = ttk.Entry(analog_param_frame, textvariable=self.analog_device_num_var, width=10)
        analog_device_entry.grid(row=0, column=3, sticky=tk.W, padx=5, pady=3)
        analog_device_entry.bind("<KeyRelease>", lambda e: self.update_preview())

        # ===== 高级参数区域（道岔专用） =====
        self.advanced_frame = ttk.LabelFrame(analog_frame, text="道岔高级参数", padding="5")

        # 曲线类型
        ttk.Label(self.advanced_frame, text="曲线类型:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.curve_type_var = tk.StringVar(value="交流")
        curve_type_combo = ttk.Combobox(self.advanced_frame, textvariable=self.curve_type_var,
                                        values=["交流", "直流"], state="readonly", width=8)
        curve_type_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=3)
        curve_type_combo.bind("<<ComboboxSelected>>", self.on_advanced_param_changed)

        ttk.Label(self.advanced_frame, text="曲线数量:").grid(row=0, column=2, sticky=tk.W, padx=(20, 5), pady=3)
        self.curve_count_var = tk.StringVar(value="3")
        curve_count_entry = ttk.Entry(self.advanced_frame, textvariable=self.curve_count_var, width=5)
        curve_count_entry.grid(row=0, column=3, sticky=tk.W, padx=5, pady=3)
        curve_count_entry.bind("<KeyRelease>", self.on_advanced_param_changed)

        ttk.Label(self.advanced_frame, text="方向:").grid(row=0, column=4, sticky=tk.W, padx=(20, 5), pady=3)
        self.direction_var = tk.StringVar(value="定位到反位")
        direction_combo = ttk.Combobox(self.advanced_frame, textvariable=self.direction_var,
                                       values=["定位到反位", "反位到定位", "定位到定位", "反位到反位",
                                               "定位到故障位", "反位到故障位"], state="readonly", width=12)
        direction_combo.grid(row=0, column=5, sticky=tk.W, padx=5, pady=3)
        direction_combo.bind("<<ComboboxSelected>>", self.on_advanced_param_changed)

        # 采集点设置
        ttk.Label(self.advanced_frame, text="采集点:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=3)
        self.point_mode_var = tk.StringVar(value="固定")
        point_mode_combo = ttk.Combobox(self.advanced_frame, textvariable=self.point_mode_var,
                                        values=["固定", "随机范围"], state="readonly", width=8)
        point_mode_combo.grid(row=1, column=1, sticky=tk.W, padx=5, pady=3)
        point_mode_combo.bind("<<ComboboxSelected>>", self.on_advanced_param_changed)

        ttk.Label(self.advanced_frame, text="固定点数:").grid(row=1, column=2, sticky=tk.W, padx=(20, 5), pady=3)
        self.point_fixed_var = tk.StringVar(value="20")
        point_fixed_entry = ttk.Entry(self.advanced_frame, textvariable=self.point_fixed_var, width=6)
        point_fixed_entry.grid(row=1, column=3, sticky=tk.W, padx=5, pady=3)
        point_fixed_entry.bind("<KeyRelease>", self.on_advanced_param_changed)

        ttk.Label(self.advanced_frame, text="随机范围:").grid(row=1, column=4, sticky=tk.W, padx=(20, 5), pady=3)
        self.point_min_var = tk.StringVar(value="10")
        point_min_entry = ttk.Entry(self.advanced_frame, textvariable=self.point_min_var, width=5)
        point_min_entry.grid(row=1, column=5, sticky=tk.W, padx=2, pady=3)
        point_min_entry.bind("<KeyRelease>", self.on_advanced_param_changed)
        ttk.Label(self.advanced_frame, text="~").grid(row=1, column=6, padx=0)
        self.point_max_var = tk.StringVar(value="50")
        point_max_entry = ttk.Entry(self.advanced_frame, textvariable=self.point_max_var, width=5)
        point_max_entry.grid(row=1, column=7, sticky=tk.W, padx=2, pady=3)
        point_max_entry.bind("<KeyRelease>", self.on_advanced_param_changed)

        # ===== 功率类型选择（仅道岔功率） =====
        self.power_type_frame = ttk.Frame(self.advanced_frame)
        ttk.Label(self.power_type_frame, text="功率类型:").pack(side=tk.LEFT, padx=5)
        power_type_combo = ttk.Combobox(self.power_type_frame, textvariable=self.power_type_var,
                                        values=["0x48", "0x53"], state="readonly", width=8)
        power_type_combo.pack(side=tk.LEFT, padx=5)
        power_type_combo.bind("<<ComboboxSelected>>", self.on_advanced_param_changed)
        # 默认隐藏，由 on_analog_type_changed 控制显示
        self.power_type_frame.grid(row=2, column=0, columnspan=8, sticky=tk.W, padx=5, pady=3)
        self.power_type_frame.grid_remove()

        # 模拟量预览
        analog_preview_frame = ttk.LabelFrame(analog_frame, text="报文预览 (实际发送的十六进制)", padding="5")
        self.analog_preview_frame = analog_preview_frame
        analog_preview_frame.pack(fill=tk.BOTH, expand=True)

        analog_text_frame = ttk.Frame(analog_preview_frame)
        analog_text_frame.pack(fill=tk.BOTH, expand=True)
        self.analog_preview_text = tk.Text(analog_text_frame, wrap=tk.WORD, font=("Consolas", 9))
        self.analog_preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll_analog = ttk.Scrollbar(analog_text_frame, orient=tk.VERTICAL, command=self.analog_preview_text.yview)
        v_scroll_analog.pack(side=tk.RIGHT, fill=tk.Y)
        self.analog_preview_text.config(yscrollcommand=v_scroll_analog.set)
        copy_analog_btn = ttk.Button(analog_preview_frame, text="复制报文", command=self.copy_analog_preview)
        copy_analog_btn.pack(side=tk.RIGHT, padx=(5, 0), pady=(0, 5))

        notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self.notebook = notebook

        # ===== 日志 =====
        log_frame = ttk.LabelFrame(main_frame, text="运行日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.on_analog_type_changed()

    # ---------- 高级参数控制 ----------
    def on_analog_type_changed(self, event=None):
        type_desc = self.analog_type_text_var.get()
        for key, (desc, _) in self.analog_type_map.items():
            if desc == type_desc:
                if key in self.switch_types:
                    self.advanced_frame.pack(fill=tk.X, pady=(0, 5), before=self.analog_preview_frame)
                    if key == '3':  # 道岔功率
                        self.power_type_frame.grid()
                    else:
                        self.power_type_frame.grid_remove()
                else:
                    self.advanced_frame.pack_forget()
                break
        self.update_advanced_params()
        self.update_preview()

    def on_advanced_param_changed(self, event=None):
        self.update_advanced_params()
        self.update_preview()

    def update_advanced_params(self):
        curve_type_str = self.curve_type_var.get()
        self.analog_params['curve_type'] = 0 if curve_type_str == "交流" else 1

        try:
            count = int(self.curve_count_var.get())
            if count < 1 or count > 3:
                count = 3 if self.analog_params['curve_type'] == 0 else 1
        except:
            count = 3 if self.analog_params['curve_type'] == 0 else 1
        self.analog_params['curve_count'] = count
        if self.analog_params['curve_type'] == 0 and count != 3:
            self.curve_count_var.set("3")
            self.analog_params['curve_count'] = 3
        elif self.analog_params['curve_type'] == 1 and count != 1:
            self.curve_count_var.set("1")
            self.analog_params['curve_count'] = 1

        dir_str = self.direction_var.get()
        dir_map = {
            "定位到反位": 0, "反位到定位": 1, "定位到定位": 2,
            "反位到反位": 3, "定位到故障位": 4, "反位到故障位": 5
        }
        self.analog_params['direction'] = dir_map.get(dir_str, 0)

        mode_str = self.point_mode_var.get()
        self.analog_params['point_mode'] = 'fixed' if mode_str == "固定" else 'random'

        try:
            fixed = int(self.point_fixed_var.get())
            if fixed < 1: fixed = 1
        except:
            fixed = 20
        self.analog_params['point_fixed'] = fixed

        try:
            min_pt = int(self.point_min_var.get())
            if min_pt < 1: min_pt = 1
        except:
            min_pt = 10
        try:
            max_pt = int(self.point_max_var.get())
            if max_pt < min_pt: max_pt = min_pt + 1
        except:
            max_pt = 50
        self.analog_params['point_min'] = min_pt
        self.analog_params['point_max'] = max_pt

    # ---------- 日志与状态 ----------
    def log(self, msg, level="INFO"):
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] [{level}] {msg}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def set_status(self, text):
        self.status_var.set(text)
        self.root.update_idletasks()

    def on_tab_changed(self, event):
        selected = self.notebook.index(self.notebook.select())
        self.current_mode = 'alarm' if selected == 0 else 'analog'
        self.update_preview()

    def update_preview(self):
        if self.current_mode == 'alarm':
            preview = self.get_alarm_preview()
            self.alarm_preview_text.delete(1.0, tk.END)
            self.alarm_preview_text.insert(1.0, preview)
        else:
            preview = self.get_analog_preview()
            self.analog_preview_text.delete(1.0, tk.END)
            self.analog_preview_text.insert(1.0, preview)

    def get_alarm_preview(self):
        try:
            raw = self.build_alarm_frame()
            processed = self.pf.deal_data(raw, isformat=True)
            return processed
        except Exception as e:
            return f"生成失败: {str(e)}"

    def get_analog_preview(self):
        try:
            type_desc = self.analog_type_text_var.get()
            for key, (desc, func) in self.analog_type_map.items():
                if desc == type_desc:
                    break
            else:
                return "未选择有效类型"
            device_num = int(self.analog_device_num_var.get().strip())
            if device_num <= 0:
                return "设备数量必须为正整数"

            if key in self.batch_types:
                full_hex, show, stamp_hex = func(device_num, sn=0)
                formatted = format_packet_orig(full_hex, stamp_hex)
                return f"# {show} #\n{formatted}"
            else:
                full_hex, show, stamp_hex = func(0, sn=0)
                formatted = format_packet_orig(full_hex, stamp_hex)
                return f"# 设备0: {show} #\n{formatted}"
        except Exception as e:
            return f"生成失败: {str(e)}"

    def copy_alarm_preview(self):
        content = self.alarm_preview_text.get(1.0, tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.log("报警报文已复制", "INFO")
            self.set_status("报警报文已复制")
            self.root.after(2000, lambda: self.set_status("就绪" if not self.send_thread or not self.send_thread.is_alive() else "发送中"))

    def copy_analog_preview(self):
        content = self.analog_preview_text.get(1.0, tk.END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.log("模拟量报文已复制", "INFO")
            self.set_status("模拟量报文已复制")
            self.root.after(2000, lambda: self.set_status("就绪" if not self.send_thread or not self.send_thread.is_alive() else "发送中"))

    # ---------- 报警生成 ----------
    def build_alarm_frame(self):
        station_no = 20
        station_hex = self.pf.int_to_hex(station_no, 4)
        try:
            device_num = int(self.alarm_device_num_var.get().strip())
            if device_num < 0: device_num = 0
        except:
            device_num = 0
        device_num_hex = self.pf.int_to_hex(device_num, 4)

        type_text = self.alarm_type_text_var.get()
        status_text = self.alarm_status_text_var.get()
        alarm_type_hex = self.alarm_type_reverse.get(type_text, "21")
        alarm_status_hex = self.alarm_status_reverse.get(status_text, "00")

        alarm_pair = alarm_type_hex + alarm_status_hex
        values_str = ' '.join([alarm_pair for _ in range(device_num)])

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

    # ---------- 类方法：模拟量生成 ----------
    def _build_analog_packet(self, payload_hex, msg_id, type_id, sn, stamp=None):
        if stamp is None:
            stamp = int(time.time())
        stamp_hex = int_to_hex_orig(stamp, 4)
        sn_hex = int_to_hex_orig(sn, 4)
        station_hex = int_to_hex_orig(1, 2)
        mid_hex = int_to_hex_orig(msg_id, 1)
        tid_hex = int_to_hex_orig(type_id, 1)
        check_data_no_len = station_hex + mid_hex + tid_hex + stamp_hex + sn_hex + payload_hex
        len_bytes = 2 + 1 + 1 + 4 + 4 + len(payload_hex)//2 + 4
        len_hex = int_to_hex_orig(len_bytes, 2)
        check_data = len_hex + check_data_no_len
        crc_hex = calc_crc_orig(check_data)
        full = 'AA' + len_hex + check_data_no_len + crc_hex + '55'
        return full, stamp_hex

    def _make_cable_insulation(self, device_no, sn):
        return make_cable_insulation_orig(device_no, sn)
    def _make_track_voltage(self, device_no, sn):
        return make_track_voltage_orig(device_no, sn)
    def _make_temperature(self, device_no, sn):
        return make_temperature_orig(device_no, sn)
    def _make_signal_lamp_current(self, device_no, sn):
        return make_signal_lamp_current_orig(device_no, sn)
    def _make_platform_door_voltage_all(self, device_no, sn):
        return make_platform_door_voltage_all_orig(device_no, sn)
    def _make_power_leakage(self, device_no, sn):
        return make_power_leakage_orig(device_no, sn)
    def _make_axle_counter_voltage(self, device_no, sn):
        return make_axle_counter_voltage_orig(device_no, sn)
    def _make_track_phase_angle(self, device_no, sn):
        return make_track_phase_angle_orig(device_no, sn)
    def _make_switch_machine_current(self, device_no, sn):
        return make_switch_machine_current_orig(device_no, sn)
    def _make_switch_indication_voltage_all(self, total_devices, sn):
        return make_switch_indication_voltage_all_orig(total_devices, sn)

    # ----- 道岔电流 -----
    def _make_switch_current(self, device_no, sn):
        params = self.analog_params
        item_hex = int_to_hex_orig(device_no, 2)
        start_time = int(time.time()) - random.randint(10, 100)
        start_hex = int_to_hex_orig(start_time, 4)

        direction = params['direction']
        dir_hex = int_to_hex_orig(direction, 1)

        curve_type = params['curve_type']
        curve_type_hex = int_to_hex_orig(curve_type, 1)

        curve_num = params['curve_count']
        curve_num_hex = int_to_hex_orig(curve_num, 1)

        curves_hex = ''
        for _ in range(curve_num):
            if params['point_mode'] == 'fixed':
                point_num = params['point_fixed']
            else:
                point_num = random.randint(params['point_min'], params['point_max'])
            point_num_hex = int_to_hex_orig(point_num, 2)
            points_hex = ''
            for _ in range(point_num):
                pt = random.randint(0, 5000)
                points_hex += int_to_hex_orig(pt, 2)
            curves_hex += point_num_hex + points_hex

        switch_cnt = random.randint(1, 999999)
        switch_cnt_hex = int_to_hex_orig(switch_cnt, 4)

        payload = item_hex + start_hex + dir_hex + curve_type_hex + curve_num_hex + curves_hex + switch_cnt_hex
        full, stamp = self._build_analog_packet(payload, 0x40, 0x42, sn)
        show = f'设备号:{device_no}  道岔电流曲线(模拟)'
        return full, show, stamp

    # ----- 道岔功率（支持 type_id 选择） -----
    def _make_switch_power(self, device_no, sn):
        params = self.analog_params
        item_hex = int_to_hex_orig(device_no, 2)
        start_time = int(time.time()) - random.randint(10, 100)
        start_hex = int_to_hex_orig(start_time, 4)

        direction = params['direction']
        dir_hex = int_to_hex_orig(direction, 1)

        curve_type_hex = int_to_hex_orig(0, 1)
        curve_num_hex = int_to_hex_orig(1, 1)

        if params['point_mode'] == 'fixed':
            point_num = params['point_fixed']
        else:
            point_num = random.randint(params['point_min'], params['point_max'])
        point_num_hex = int_to_hex_orig(point_num, 2)
        points_hex = ''
        for _ in range(point_num):
            pt = random.randint(0, 5000)
            points_hex += int_to_hex_orig(pt, 2)
        curves_hex = point_num_hex + points_hex

        switch_cnt = random.randint(1, 999999)
        switch_cnt_hex = int_to_hex_orig(switch_cnt, 4)

        payload = item_hex + start_hex + dir_hex + curve_type_hex + curve_num_hex + curves_hex + switch_cnt_hex

        power_type_str = self.power_type_var.get()
        type_id = 0x48 if power_type_str == "0x48" else 0x53

        full, stamp = self._build_analog_packet(payload, 0x40, type_id, sn)
        show = f'设备号:{device_no}  道岔功率曲线(模拟) type_id={hex(type_id)}'
        return full, show, stamp

    # ---------- 验证 ----------
    def validate_inputs(self):
        if self.current_mode == 'alarm':
            return self._validate_alarm()
        else:
            return self._validate_analog()

    def _validate_alarm(self):
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
            device_num = int(self.alarm_device_num_var.get())
            if device_num <= 0:
                raise ValueError
        except:
            messagebox.showerror("错误", "报警设备总数必须为正整数")
            return False
        type_text = self.alarm_type_text_var.get()
        if type_text not in self.alarm_type_reverse:
            messagebox.showerror("错误", "无效的报警类型")
            return False
        status_text = self.alarm_status_text_var.get()
        if status_text not in self.alarm_status_reverse:
            messagebox.showerror("错误", "无效的报警状态")
            return False
        return True

    def _validate_analog(self):
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
            device_num = int(self.analog_device_num_var.get())
            if device_num <= 0:
                raise ValueError
        except:
            messagebox.showerror("错误", "设备数量必须为正整数")
            return False
        type_desc = self.analog_type_text_var.get()
        found = False
        for desc, _ in self.analog_type_map.values():
            if desc == type_desc:
                found = True
                break
        if not found:
            messagebox.showerror("错误", "无效的模拟量类型")
            return False
        return True

    # ---------- 发送控制 ----------
    def start_sending(self):
        if not self.validate_inputs():
            return
        if self.send_thread and self.send_thread.is_alive():
            messagebox.showwarning("警告", "发送线程已在运行中")
            return

        if self.client_sock is not None:
            try:
                self.client_sock.send(b'')
                self.log("使用已有连接", "INFO")
            except:
                self.log("已有连接无效，将重新建立", "WARNING")
                self.client_sock = None
                if self.server_socket:
                    try:
                        self.server_socket.close()
                    except:
                        pass
                    self.server_socket = None
        else:
            if self.server_socket is not None:
                try:
                    self.server_socket.close()
                except:
                    pass
                self.server_socket = None

        self.stop_event.clear()
        self.send_thread = threading.Thread(target=self.send_worker, daemon=True)
        self.send_thread.start()

        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.NORMAL)
        self.set_status("正在启动...")
        self.log(f"开始发送 {self.current_mode} 报文，休眠时间固定2秒")

    def stop_sending(self):
        self.log("正在停止发送（连接保持）...")
        self.stop_event.set()
        self.set_status("已停止发送，连接保持")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def disconnect(self):
        self.log("用户主动断开连接")
        if self.send_thread and self.send_thread.is_alive():
            self.stop_event.set()
            self.send_thread.join(timeout=2)
        if self.client_sock:
            try:
                self.client_sock.close()
            except:
                pass
            self.client_sock = None
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.set_status("连接已断开")
        self.log("TCP连接已断开")

    # ---------- 发送线程 ----------
    def send_worker(self):
        func = PublicFunc()
        sourse_ip = self.sourse_ip_var.get().strip()
        dest_ip = self.dest_ip_var.get().strip()
        port = 10060
        sleep_time = 2

        if self.client_sock is None:
            self.log("正在建立TCP连接...")
            try:
                if self.server_socket:
                    try:
                        self.server_socket.close()
                    except:
                        pass
                    self.server_socket = None
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

            while not self.stop_event.is_set():
                try:
                    client, addr = server.accept()
                    client.settimeout(2.0)
                    if addr[0] == dest_ip:
                        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        self.client_sock = client
                        self.log(f"目标服务器 {dest_ip}:{addr[1]} 已连接")
                        self.set_status(f"已连接，正在发送 {self.current_mode}...")
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
                self.root.after(0, self.on_send_finished)
                return

        send_count = 0
        sn_counter = 0
        device_index = 0

        while not self.stop_event.is_set():
            try:
                if self.current_mode == 'alarm':
                    raw_frame = self.build_alarm_frame()
                    processed_frame = func.deal_data(raw_frame)
                    send_bytes = func.str_to_bytes(processed_frame)
                    hex_preview = send_bytes.hex()[:64] + ("..." if len(send_bytes) > 32 else "")
                    self.log(f"[发送报警 #{send_count+1}] 长度={len(send_bytes)} 字节, 预览={hex_preview}")
                    sent = self.client_sock.send(send_bytes)
                    self.log(f"实际发送 {sent} 字节")
                    send_count += 1
                    self.log(f"已发送报警 #{send_count} | 类型:{self.alarm_type_text_var.get()} | 状态:{self.alarm_status_text_var.get()} | 设备数:{int(self.alarm_device_num_var.get())}")
                else:
                    type_desc = self.analog_type_text_var.get()
                    target_key = None
                    target_func = None
                    for key, (desc, func) in self.analog_type_map.items():
                        if desc == type_desc:
                            target_key = key
                            target_func = func
                            break
                    if target_func is None:
                        self.log("模拟量类型无效，停止发送", "ERROR")
                        break

                    device_num = int(self.analog_device_num_var.get())

                    if target_key in self.batch_types:
                        full_hex, show, stamp_hex = target_func(device_num, sn=sn_counter)
                        send_bytes = bytes.fromhex(full_hex)
                        hex_preview = send_bytes.hex()[:64] + ("..." if len(send_bytes) > 32 else "")
                        self.log(f"[发送模拟量 #{send_count+1}] 长度={len(send_bytes)} 字节, 预览={hex_preview}")
                        sent = self.client_sock.send(send_bytes)
                        self.log(f"实际发送 {sent} 字节")
                        send_count += 1
                        self.log(f"已发送模拟量 #{send_count} | {show}")
                        sn_counter += 1
                    else:
                        dev_no = device_index % device_num
                        full_hex, show, stamp_hex = target_func(dev_no, sn=sn_counter)
                        send_bytes = bytes.fromhex(full_hex)
                        hex_preview = send_bytes.hex()[:64] + ("..." if len(send_bytes) > 32 else "")
                        self.log(f"[发送模拟量 #{send_count+1}] 长度={len(send_bytes)} 字节, 预览={hex_preview}")
                        sent = self.client_sock.send(send_bytes)
                        self.log(f"实际发送 {sent} 字节")
                        send_count += 1
                        self.log(f"已发送模拟量 #{send_count} | 设备{dev_no}: {show}")
                        sn_counter += 1
                        device_index += 1

                for _ in range(sleep_time):
                    if self.stop_event.is_set():
                        break
                    time.sleep(1)

            except (socket.error, BrokenPipeError, ConnectionResetError) as e:
                self.log(f"发送失败，连接可能已断开: {e}", "ERROR")
                if self.client_sock:
                    try:
                        self.client_sock.close()
                    except:
                        pass
                    self.client_sock = None
                self.set_status("连接断开，重新等待目标服务器...")
                while not self.stop_event.is_set():
                    try:
                        if self.server_socket is None:
                            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                            server.bind((sourse_ip, port))
                            server.listen(5)
                            server.settimeout(1.0)
                            self.server_socket = server
                            self.log(f"重新启动TCP服务，监听 {sourse_ip}:{port}")
                        client, addr = self.server_socket.accept()
                        client.settimeout(2.0)
                        if addr[0] == dest_ip:
                            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
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
                self.log(f"发送过程未知错误: {e}\n{traceback.format_exc()}", "ERROR")
                break

        self.log("发送循环已退出，连接保持")
        self.root.after(0, self.on_send_finished)

    def on_send_finished(self):
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        if self.client_sock is not None:
            self.set_status("已停止发送，连接保持")
        else:
            self.set_status("已停止发送，连接已断开")
        self.log("发送任务已停止（连接未关闭）")


if __name__ == "__main__":
    root = tk.Tk()
    app = AlarmSenderApp(root)
    root.mainloop()