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
import pymysql

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

# 非批量类型（每个设备一条）
def make_cable_insulation_orig(device_no, sn):
    value_int = random.randint(0, 30000)
    item_hex = int_to_hex_orig(device_no, 2)
    analog_hex = int_to_hex_orig(value_int, 2)
    payload = item_hex + analog_hex
    full, stamp = build_packet_orig(payload, 0x40, 0x41, sn)
    show = f'设备号:{device_no}  绝缘值:{value_int/100:.2f} MΩ'
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

# 批量类型（所有设备在一条）
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

def make_temperature_all_orig(total_devices, sn):
    analog_num = total_devices
    analog_num_hex = int_to_hex_orig(analog_num, 2)
    analogs_hex = ''
    for _ in range(analog_num):
        val = random.randint(0, 300)
        analogs_hex += int_to_hex_orig(val, 2)
    payload = analog_num_hex + analogs_hex
    full, stamp = build_packet_orig(payload, 0x40, 0x45, sn)
    show = f'温湿度 共{total_devices}个设备，每个1路'
    return full, show, stamp

def make_signal_lamp_current_all_orig(total_devices, sn):
    analog_num = total_devices
    analog_num_hex = int_to_hex_orig(analog_num, 2)
    items_hex = ''
    for dev_no in range(total_devices):
        device_id = dev_no + 1
        items_hex += int_to_hex_orig(device_id, 2)
        val = random.randint(0, 5000)
        items_hex += int_to_hex_orig(val, 2)
    payload = analog_num_hex + items_hex
    full, stamp = build_packet_orig(payload, 0x40, 0x47, sn)
    show = f'信号机点灯电流 共{total_devices}个设备'
    return full, show, stamp

# 新增批量轨道电压
def make_track_voltage_all_orig(total_devices, sn):
    analog_num = total_devices
    analog_num_hex = int_to_hex_orig(analog_num, 2)
    analogs_hex = ''
    for _ in range(analog_num):
        val = random.randint(150, 280)
        analogs_hex += int_to_hex_orig(val, 2)
    payload = analog_num_hex + analogs_hex
    full, stamp = build_packet_orig(payload, 0x40, 0x43, sn)
    show = f'轨道电压 共{total_devices}个设备，每个1路'
    return full, show, stamp


# ==================== GUI 应用 ====================
class AlarmSenderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("微联5报警与模拟量发送工具 (数据库版)")
        self.root.geometry("1100x850")
        self.root.resizable(True, True)

        self.send_threads = []
        self.stop_event = threading.Event()
        self.sub_sockets = []
        self.current_mode = 'alarm'

        self.pf = PublicFunc()

        # 报警映射
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

        # 模拟量映射
        self.analog_type_map = {
            '1': ('电缆绝缘', self._make_cable_insulation),
            '2': ('道岔电流', self._make_switch_current),
            '3': ('道岔功率', self._make_switch_power),
            '4': ('轨道电压', self._make_track_voltage_all),      # 改为批量
            '5': ('温湿度', self._make_temperature_all),
            '6': ('道岔表示电压', self._make_switch_indication_voltage_all),
            '8': ('信号机点灯电流', self._make_signal_lamp_current_all),
            '9': ('站台门电压', self._make_platform_door_voltage_all),
            '10': ('电源漏流', self._make_power_leakage),
            '11': ('计轴电压', self._make_axle_counter_voltage),
            '12': ('轨道相位角', self._make_track_phase_angle),
            '13': ('转辙机总电流', self._make_switch_machine_current),
        }
        self.batch_types = {'9', '6', '5', '8', '4'}   # 添加了 '4'
        self.switch_types = {'2', '3'}

        # 高级参数
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

    # ---------- 界面创建 ----------
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.pack(fill=tk.BOTH, expand=True)

        top_frame = ttk.LabelFrame(main_frame, text="网络与数据库配置", padding="5")
        top_frame.pack(fill=tk.X, pady=(0, 5))

        # 第一行：本机IP起始、本机端口、发送目标IP、数据库主机、数据库名、master过滤
        ttk.Label(top_frame, text="本机IP起始:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.sourse_ip_var = tk.StringVar(value="192.168.2.131")
        ttk.Entry(top_frame, textvariable=self.sourse_ip_var, width=16).grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(top_frame, text="本机端口:").grid(row=0, column=2, sticky=tk.W, padx=(20,5))
        self.port_var = tk.StringVar(value="10060")
        ttk.Entry(top_frame, textvariable=self.port_var, width=8).grid(row=0, column=3, sticky=tk.W, padx=5)

        ttk.Label(top_frame, text="发送目标IP:").grid(row=0, column=4, sticky=tk.W, padx=(20,5))
        self.target_ip_var = tk.StringVar(value="192.168.1.238")
        ttk.Entry(top_frame, textvariable=self.target_ip_var, width=16).grid(row=0, column=5, sticky=tk.W, padx=5)

        ttk.Label(top_frame, text="数据库主机:").grid(row=0, column=6, sticky=tk.W, padx=(20,5))
        self.db_host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(top_frame, textvariable=self.db_host_var, width=16).grid(row=0, column=7, sticky=tk.W, padx=5)

        ttk.Label(top_frame, text="数据库名:").grid(row=0, column=8, sticky=tk.W, padx=(20,5))
        self.db_name_var = tk.StringVar(value="base")
        ttk.Entry(top_frame, textvariable=self.db_name_var, width=10).grid(row=0, column=9, sticky=tk.W, padx=5)

        ttk.Label(top_frame, text="master过滤:").grid(row=0, column=10, sticky=tk.W, padx=(20,5))
        self.master_filter_var = tk.StringVar(value="1")
        ttk.Entry(top_frame, textvariable=self.master_filter_var, width=6).grid(row=0, column=11, sticky=tk.W, padx=5)

        # 第二行：复选框、获取按钮、控制按钮
        self.filter_192_var = tk.IntVar(value=0)
        filter_check = ttk.Checkbutton(top_frame, text="仅保留192.168网段", variable=self.filter_192_var)
        filter_check.grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)

        fetch_btn = ttk.Button(top_frame, text="从数据库中获取连接", command=self.fetch_from_database)
        fetch_btn.grid(row=1, column=2, columnspan=2, padx=5, pady=5)

        btn_frame = ttk.Frame(top_frame)
        btn_frame.grid(row=1, column=4, columnspan=8, padx=(30,0), pady=5)
        self.start_btn = ttk.Button(btn_frame, text="开始发送", command=self.start_sending)
        self.start_btn.pack(side=tk.LEFT, padx=2)
        self.stop_btn = ttk.Button(btn_frame, text="停止发送", command=self.stop_sending, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=2)
        self.disconnect_btn = ttk.Button(btn_frame, text="断开所有连接", command=self.disconnect_all, state=tk.NORMAL)
        self.disconnect_btn.pack(side=tk.LEFT, padx=2)

        # 第三行：发送间隔
        ttk.Label(top_frame, text="发送间隔(秒):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=3)
        self.interval_var = tk.StringVar(value="2.0")
        ttk.Entry(top_frame, textvariable=self.interval_var, width=8).grid(row=2, column=1, sticky=tk.W, padx=5)

        # ===== 子连接列表 =====
        sub_frame = ttk.LabelFrame(main_frame, text="子连接列表 (从数据库获取，本机IP来自数据库)", padding="5")
        sub_frame.pack(fill=tk.BOTH, expand=True, pady=(0,5))

        columns = ("序号", "站点", "本机IP", "设备数量")
        self.sub_tree = ttk.Treeview(sub_frame, columns=columns, show="headings", height=6)
        for col in columns:
            self.sub_tree.heading(col, text=col)
            if col == "序号":
                self.sub_tree.column(col, width=50, stretch=False)
            elif col == "站点":
                self.sub_tree.column(col, width=200, stretch=True)
            elif col == "本机IP":
                self.sub_tree.column(col, width=150, stretch=True)
            else:
                self.sub_tree.column(col, width=100, stretch=True)
        self.sub_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(sub_frame, orient=tk.VERTICAL, command=self.sub_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.sub_tree.configure(yscrollcommand=scrollbar.set)
        self.sub_tree.bind("<Double-1>", self.edit_device_num)

        # ===== Notebook =====
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=5)

        # 报警页
        alarm_frame = ttk.Frame(notebook, padding="5")
        notebook.add(alarm_frame, text="报警发送")

        alarm_param_frame = ttk.LabelFrame(alarm_frame, text="报警参数 (所有子连接共享)", padding="5")
        alarm_param_frame.pack(fill=tk.X, pady=(0,5))

        ttk.Label(alarm_param_frame, text="报警类型:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.alarm_type_text_var = tk.StringVar(value=list(self.alarm_type_map.values())[0])
        type_combo = ttk.Combobox(alarm_param_frame, textvariable=self.alarm_type_text_var,
                                  values=list(self.alarm_type_map.values()), state="readonly", width=25)
        type_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=3)
        type_combo.bind("<<ComboboxSelected>>", self.on_alarm_param_changed)

        ttk.Label(alarm_param_frame, text="报警状态:").grid(row=0, column=2, sticky=tk.W, padx=(20,5), pady=3)
        self.alarm_status_text_var = tk.StringVar(value="正常")
        status_combo = ttk.Combobox(alarm_param_frame, textvariable=self.alarm_status_text_var,
                                    values=self.alarm_status_text, state="readonly", width=10)
        status_combo.grid(row=0, column=3, sticky=tk.W, padx=5, pady=3)
        status_combo.bind("<<ComboboxSelected>>", self.on_alarm_param_changed)

        # 模拟量页
        analog_frame = ttk.Frame(notebook, padding="5")
        notebook.add(analog_frame, text="模拟量发送")

        analog_param_frame = ttk.LabelFrame(analog_frame, text="模拟量参数 (所有子连接共享)", padding="5")
        analog_param_frame.pack(fill=tk.X, pady=(0,5))

        ttk.Label(analog_param_frame, text="模拟量类型:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.analog_type_text_var = tk.StringVar(value=list(self.analog_type_map.values())[0][0])
        analog_type_combo = ttk.Combobox(analog_param_frame, textvariable=self.analog_type_text_var,
                                         values=[desc for desc,_ in self.analog_type_map.values()],
                                         state="readonly", width=20)
        analog_type_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=3)
        analog_type_combo.bind("<<ComboboxSelected>>", self.on_analog_type_changed)

        # 高级参数（道岔专用）
        self.advanced_frame = ttk.LabelFrame(analog_frame, text="道岔高级参数", padding="5")
        ttk.Label(self.advanced_frame, text="曲线类型:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.curve_type_var = tk.StringVar(value="交流")
        curve_type_combo = ttk.Combobox(self.advanced_frame, textvariable=self.curve_type_var,
                                        values=["交流","直流"], state="readonly", width=8)
        curve_type_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=3)
        curve_type_combo.bind("<<ComboboxSelected>>", self.on_advanced_param_changed)

        ttk.Label(self.advanced_frame, text="曲线数量:").grid(row=0, column=2, sticky=tk.W, padx=(20,5), pady=3)
        self.curve_count_var = tk.StringVar(value="3")
        ttk.Entry(self.advanced_frame, textvariable=self.curve_count_var, width=5).grid(row=0, column=3, sticky=tk.W, padx=5, pady=3)
        self.curve_count_var.trace('w', lambda *args: self.on_advanced_param_changed())

        ttk.Label(self.advanced_frame, text="方向:").grid(row=0, column=4, sticky=tk.W, padx=(20,5), pady=3)
        self.direction_var = tk.StringVar(value="定位到反位")
        direction_combo = ttk.Combobox(self.advanced_frame, textvariable=self.direction_var,
                                       values=["定位到反位","反位到定位","定位到定位","反位到反位","定位到故障位","反位到故障位"],
                                       state="readonly", width=12)
        direction_combo.grid(row=0, column=5, sticky=tk.W, padx=5, pady=3)
        direction_combo.bind("<<ComboboxSelected>>", self.on_advanced_param_changed)

        ttk.Label(self.advanced_frame, text="采集点:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=3)
        self.point_mode_var = tk.StringVar(value="固定")
        point_mode_combo = ttk.Combobox(self.advanced_frame, textvariable=self.point_mode_var,
                                        values=["固定","随机范围"], state="readonly", width=8)
        point_mode_combo.grid(row=1, column=1, sticky=tk.W, padx=5, pady=3)
        point_mode_combo.bind("<<ComboboxSelected>>", self.on_advanced_param_changed)

        ttk.Label(self.advanced_frame, text="固定点数:").grid(row=1, column=2, sticky=tk.W, padx=(20,5), pady=3)
        self.point_fixed_var = tk.StringVar(value="20")
        ttk.Entry(self.advanced_frame, textvariable=self.point_fixed_var, width=6).grid(row=1, column=3, sticky=tk.W, padx=5, pady=3)
        self.point_fixed_var.trace('w', lambda *args: self.on_advanced_param_changed())

        ttk.Label(self.advanced_frame, text="随机范围:").grid(row=1, column=4, sticky=tk.W, padx=(20,5), pady=3)
        self.point_min_var = tk.StringVar(value="10")
        ttk.Entry(self.advanced_frame, textvariable=self.point_min_var, width=5).grid(row=1, column=5, sticky=tk.W, padx=2, pady=3)
        self.point_min_var.trace('w', lambda *args: self.on_advanced_param_changed())
        ttk.Label(self.advanced_frame, text="~").grid(row=1, column=6, padx=0)
        self.point_max_var = tk.StringVar(value="50")
        ttk.Entry(self.advanced_frame, textvariable=self.point_max_var, width=5).grid(row=1, column=7, sticky=tk.W, padx=2, pady=3)
        self.point_max_var.trace('w', lambda *args: self.on_advanced_param_changed())

        self.power_type_frame = ttk.Frame(self.advanced_frame)
        ttk.Label(self.power_type_frame, text="功率类型:").pack(side=tk.LEFT, padx=5)
        power_type_combo = ttk.Combobox(self.power_type_frame, textvariable=self.power_type_var,
                                        values=["0x48","0x53"], state="readonly", width=8)
        power_type_combo.pack(side=tk.LEFT, padx=5)
        power_type_combo.bind("<<ComboboxSelected>>", self.on_advanced_param_changed)
        self.power_type_frame.grid(row=2, column=0, columnspan=8, sticky=tk.W, padx=5, pady=3)
        self.power_type_frame.grid_remove()

        notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self.notebook = notebook

        # ===== 日志 =====
        log_frame = ttk.LabelFrame(main_frame, text="运行日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(5,0))
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.on_analog_type_changed()

    # ---------- 数据库操作 ----------
    def fetch_from_database(self):
        db_host = self.db_host_var.get().strip()
        db_name = self.db_name_var.get().strip() or "base"
        master_filter = self.master_filter_var.get().strip() or "1"
        filter_192 = self.filter_192_var.get() == 1

        if not db_host:
            messagebox.showerror("错误", "请填写数据库主机")
            return

        try:
            conn = pymysql.connect(
                host=db_host,
                user='root',
                password='mysql',
                database=db_name,
                port=3306,
                charset='utf8',
                ssl=None
            )
        except Exception as e:
            messagebox.showerror("数据库连接失败", str(e))
            return

        sql = """
            SELECT a.IP, b.STATION_NAME
            FROM dic_mss_netaddress_config a
            RIGHT JOIN dic_station b ON a.STATION_NO = b.STATION_NO
            WHERE a.SYS_NO = 10 AND a.master = %s
        """
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, (master_filter,))
                results = cursor.fetchall()
        except Exception as e:
            messagebox.showerror("查询失败", str(e))
            conn.close()
            return
        finally:
            conn.close()

        if not results:
            messagebox.showinfo("提示", "没有找到匹配的记录")
            return

        if filter_192:
            results = [row for row in results if row[0].startswith('192.168.')]

        if not results:
            messagebox.showinfo("提示", "过滤后没有剩余记录")
            return

        for item in self.sub_tree.get_children():
            self.sub_tree.delete(item)

        for idx, (ip, station) in enumerate(results):
            self.sub_tree.insert("", "end", values=(idx+1, station, ip, 1))

        self.log(f"从数据库获取 {len(results)} 个连接", "INFO")
        self.set_status(f"已加载 {len(results)} 个连接")

    # ---------- 子连接表格编辑 ----------
    def edit_device_num(self, event):
        item = self.sub_tree.selection()[0] if self.sub_tree.selection() else None
        if not item:
            return
        values = self.sub_tree.item(item, "values")
        col = self.sub_tree.identify_column(event.x)
        if col != "#4":
            return
        current = values[3]
        from tkinter import simpledialog
        new_val = simpledialog.askstring("编辑设备数量", "请输入设备数量：", initialvalue=current)
        if new_val is not None:
            try:
                new_val = int(new_val)
                if new_val <= 0:
                    return
                values = list(values)
                values[3] = str(new_val)
                self.sub_tree.item(item, values=values)
            except:
                pass

    # ---------- 参数变化回调 ----------
    def on_alarm_param_changed(self, event=None):
        pass

    def on_analog_type_changed(self, event=None):
        type_desc = self.analog_type_text_var.get()
        for key, (desc, _) in self.analog_type_map.items():
            if desc == type_desc:
                if key in self.switch_types:
                    self.advanced_frame.pack(fill=tk.X, pady=(0,5))
                    if key == '3':
                        self.power_type_frame.grid()
                    else:
                        self.power_type_frame.grid_remove()
                else:
                    self.advanced_frame.pack_forget()
                break
        self.update_advanced_params()

    def on_advanced_param_changed(self, event=None):
        self.update_advanced_params()

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
        dir_map = {"定位到反位":0,"反位到定位":1,"定位到定位":2,"反位到反位":3,"定位到故障位":4,"反位到故障位":5}
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

    def on_tab_changed(self, event):
        selected = self.notebook.index(self.notebook.select())
        self.current_mode = 'alarm' if selected == 0 else 'analog'

    # ---------- 日志与状态 ----------
    def log(self, msg, level="INFO"):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] [{level}] {msg}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def set_status(self, text):
        self.status_var.set(text)
        self.root.update_idletasks()

    # ---------- 报警生成 ----------
    def build_alarm_frame(self, device_num=None):
        station_no = 20
        station_hex = self.pf.int_to_hex(station_no, 4)
        if device_num is None:
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

    # ---------- 模拟量生成方法 ----------
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
    def _make_power_leakage(self, device_no, sn):
        return make_power_leakage_orig(device_no, sn)
    def _make_axle_counter_voltage(self, device_no, sn):
        return make_axle_counter_voltage_orig(device_no, sn)
    def _make_track_phase_angle(self, device_no, sn):
        return make_track_phase_angle_orig(device_no, sn)
    def _make_switch_machine_current(self, device_no, sn):
        return make_switch_machine_current_orig(device_no, sn)

    # 批量类型封装
    def _make_platform_door_voltage_all(self, total_devices, sn):
        return make_platform_door_voltage_all_orig(total_devices, sn)
    def _make_switch_indication_voltage_all(self, total_devices, sn):
        return make_switch_indication_voltage_all_orig(total_devices, sn)
    def _make_temperature_all(self, total_devices, sn):
        return make_temperature_all_orig(total_devices, sn)
    def _make_signal_lamp_current_all(self, total_devices, sn):
        return make_signal_lamp_current_all_orig(total_devices, sn)
    def _make_track_voltage_all(self, total_devices, sn):
        return make_track_voltage_all_orig(total_devices, sn)

    # 道岔电流（非批量）
    def _make_switch_current(self, device_no, sn):
        params = self.analog_params
        item_hex = int_to_hex_orig(device_no, 2)
        start_time = int(time.time()) - random.randint(10, 100)
        start_hex = int_to_hex_orig(start_time, 4)
        dir_hex = int_to_hex_orig(params['direction'], 1)
        curve_type_hex = int_to_hex_orig(params['curve_type'], 1)
        curve_num_hex = int_to_hex_orig(params['curve_count'], 1)
        curves_hex = ''
        for _ in range(params['curve_count']):
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

    # 道岔功率（非批量）
    def _make_switch_power(self, device_no, sn):
        params = self.analog_params
        item_hex = int_to_hex_orig(device_no, 2)
        start_time = int(time.time()) - random.randint(10, 100)
        start_hex = int_to_hex_orig(start_time, 4)
        dir_hex = int_to_hex_orig(params['direction'], 1)
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
        type_id = 0x48 if self.power_type_var.get() == "0x48" else 0x53
        full, stamp = self._build_analog_packet(payload, 0x40, type_id, sn)
        show = f'设备号:{device_no}  道岔功率曲线(模拟) type_id={hex(type_id)}'
        return full, show, stamp

    # ---------- 验证 ----------
    def validate_inputs(self):
        if not self.sub_tree.get_children():
            messagebox.showerror("错误", "请先从数据库获取连接")
            return False

        for item in self.sub_tree.get_children():
            values = self.sub_tree.item(item, "values")
            try:
                dev_num = int(values[3])
                if dev_num <= 0:
                    messagebox.showerror("错误", f"子连接 {values[0]} 设备数量无效")
                    return False
            except:
                messagebox.showerror("错误", f"子连接 {values[0]} 设备数量必须为整数")
                return False

        try:
            interval = float(self.interval_var.get())
            if interval <= 0:
                raise ValueError
        except:
            messagebox.showerror("错误", "发送间隔必须为正数")
            return False

        ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
        target_ip = self.target_ip_var.get().strip()
        if not ip_pattern.match(target_ip):
            messagebox.showerror("错误", "发送目标IP格式不正确")
            return False
        try:
            port = int(self.port_var.get())
            if port <= 0 or port > 65535:
                raise ValueError
        except:
            messagebox.showerror("错误", "本机端口无效")
            return False
        for item in self.sub_tree.get_children():
            values = self.sub_tree.item(item, "values")
            if not ip_pattern.match(values[2]):
                messagebox.showerror("错误", f"子连接 {values[0]} 本机IP格式不正确")
                return False

        if self.current_mode == 'alarm':
            type_text = self.alarm_type_text_var.get()
            if type_text not in self.alarm_type_reverse:
                messagebox.showerror("错误", "无效的报警类型")
                return False
            status_text = self.alarm_status_text_var.get()
            if status_text not in self.alarm_status_reverse:
                messagebox.showerror("错误", "无效的报警状态")
                return False
        else:
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

    # ---------- 多连接发送控制 ----------
    def start_sending(self):
        if not self.validate_inputs():
            return
        if self.send_threads:
            messagebox.showwarning("警告", "已有发送线程在运行")
            return

        self.stop_event.clear()
        self.sub_sockets = []
        self.send_threads = []

        target_ip = self.target_ip_var.get().strip()
        src_port = int(self.port_var.get())

        configs = []
        for item in self.sub_tree.get_children():
            values = self.sub_tree.item(item, "values")
            config = {
                'dst_ip': target_ip,
                'src_ip': values[2],
                'src_port': src_port,
                'device_num': int(values[3]),
                'server_sock': None,
                'client_sock': None,
            }
            configs.append(config)

        for idx, cfg in enumerate(configs):
            thread = threading.Thread(target=self.sub_worker, args=(idx, cfg), daemon=True)
            thread.start()
            self.send_threads.append(thread)

        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.NORMAL)
        self.set_status(f"启动 {len(configs)} 个子连接...")
        self.log(f"启动 {len(configs)} 个子连接，目标IP: {target_ip}，发送间隔 {self.interval_var.get()} 秒")

    def stop_sending(self):
        self.log("正在停止所有子连接发送...")
        self.stop_event.set()
        self.set_status("正在停止...")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def disconnect_all(self):
        self.log("用户主动断开所有连接")
        self.stop_event.set()
        for t in self.send_threads:
            t.join(timeout=1)
        for cfg in self.sub_sockets:
            if cfg['server_sock']:
                try: cfg['server_sock'].close()
                except: pass
            if cfg['client_sock']:
                try: cfg['client_sock'].close()
                except: pass
        self.sub_sockets.clear()
        self.send_threads.clear()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.set_status("已断开所有连接")
        self.log("所有连接已断开")

    # ---------- 子连接线程 ----------
    def sub_worker(self, idx, cfg):
        thread_id = idx + 1
        src_ip = cfg['src_ip']
        src_port = cfg['src_port']
        device_num = cfg['device_num']
        dst_ip = cfg['dst_ip']

        self.log(f"[子连接{thread_id}] 启动，本机 {src_ip}:{src_port} -> 目标 {dst_ip}")

        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((src_ip, src_port))
            server.listen(5)
            server.settimeout(1.0)
            cfg['server_sock'] = server
            self.sub_sockets.append(cfg)
        except Exception as e:
            self.log(f"[子连接{thread_id}] 启动服务失败: {e}", "ERROR")
            return

        client = None
        self.log(f"[子连接{thread_id}] 等待目标 {dst_ip} 连接...")
        while not self.stop_event.is_set():
            try:
                cli, addr = server.accept()
                cli.settimeout(2.0)
                if addr[0] == dst_ip:
                    cli.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    client = cli
                    cfg['client_sock'] = client
                    self.log(f"[子连接{thread_id}] 目标 {dst_ip}:{addr[1]} 已连接")
                    break
                else:
                    cli.close()
            except socket.timeout:
                continue
            except Exception as e:
                if not self.stop_event.is_set():
                    self.log(f"[子连接{thread_id}] 接受连接异常: {e}", "ERROR")
                break
        if client is None:
            server.close()
            return

        send_count = 0
        sn_counter = 0
        device_index = 0
        interval = float(self.interval_var.get())

        while not self.stop_event.is_set():
            try:
                if self.current_mode == 'alarm':
                    raw_frame = self.build_alarm_frame(device_num=device_num)
                    processed_frame = self.pf.deal_data(raw_frame)
                    send_bytes = self.pf.str_to_bytes(processed_frame)
                    hex_str = send_bytes.hex().upper()
                    self.log(f"[子连接{thread_id}] 发送报警 #{send_count+1} 长度={len(send_bytes)} 报文={hex_str}")
                    client.send(send_bytes)
                    send_count += 1
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
                        self.log(f"[子连接{thread_id}] 模拟量类型无效", "ERROR")
                        break

                    if target_key in self.batch_types:
                        full_hex, show, stamp_hex = target_func(device_num, sn=sn_counter)
                        send_bytes = bytes.fromhex(full_hex)
                        hex_str = send_bytes.hex().upper()
                        self.log(f"[子连接{thread_id}] 发送模拟量 #{send_count+1} 长度={len(send_bytes)} 报文={hex_str}")
                        client.send(send_bytes)
                        send_count += 1
                        sn_counter += 1
                    else:
                        dev_no = device_index % device_num
                        full_hex, show, stamp_hex = target_func(dev_no, sn=sn_counter)
                        send_bytes = bytes.fromhex(full_hex)
                        hex_str = send_bytes.hex().upper()
                        self.log(f"[子连接{thread_id}] 发送模拟量 #{send_count+1} 设备{dev_no} 长度={len(send_bytes)} 报文={hex_str}")
                        client.send(send_bytes)
                        send_count += 1
                        sn_counter += 1
                        device_index += 1

                if interval > 0:
                    time.sleep(interval)

            except (socket.error, BrokenPipeError, ConnectionResetError) as e:
                self.log(f"[子连接{thread_id}] 发送失败，连接断开: {e}", "ERROR")
                client.close()
                client = None
                self.log(f"[子连接{thread_id}] 重新等待目标 {dst_ip} 连接...")
                while not self.stop_event.is_set():
                    try:
                        cli, addr = server.accept()
                        cli.settimeout(2.0)
                        if addr[0] == dst_ip:
                            cli.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                            client = cli
                            cfg['client_sock'] = client
                            self.log(f"[子连接{thread_id}] 重新连接成功")
                            break
                        else:
                            cli.close()
                    except socket.timeout:
                        continue
                    except Exception as ex:
                        self.log(f"[子连接{thread_id}] 重连异常: {ex}", "ERROR")
                        break
                if client is None:
                    break
                continue
            except Exception as e:
                self.log(f"[子连接{thread_id}] 未知错误: {e}", "ERROR")
                break

        if client:
            client.close()
        if server:
            server.close()
        self.log(f"[子连接{thread_id}] 已退出")


if __name__ == "__main__":
    root = tk.Tk()
    app = AlarmSenderApp(root)
    root.mainloop()