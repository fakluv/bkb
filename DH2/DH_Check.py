# -*- coding: utf-8 -*-
"""
PowerDH 点表处理工具
勾选控制报文数据内容（告警置位 / 模拟量赋值），报文结构始终全量
"""

import os
import re
import math
import time
import random
import struct
import threading
import traceback
import sys
import queue
import socket
import difflib
import tkinter as tk
from tkinter import *
from tkinter import ttk
from tkinter import filedialog, scrolledtext
import chardet

try:
    import pymysql
    PYMYSQL_AVAILABLE = True
except ImportError:
    pymysql = None
    PYMYSQL_AVAILABLE = False


# ============================================================
# 一、公共工具类
# ============================================================
class PublicFunc:
    def crc32_ccitt(self, data: bytes) -> int:
        crc = 0x00000000
        poly = 0x04C11DB7
        for byte in data:
            crc ^= byte << 24
            for _ in range(8):
                if crc & 0x80000000:
                    crc = (crc << 1) ^ poly
                else:
                    crc <<= 1
                crc &= 0xFFFFFFFF
        return crc

    def deal_data(self, data, fix_hour=0, israndomtime=False, isformat=True,
                  time_type=1, return_data_type=1):
        return_time = []
        regex = re.compile(r'(#)(.*?)(#)')
        if isinstance(data, str):
            data1 = regex.sub(r'', data)
        else:
            data1 = regex.sub(r'', data.decode('utf-8'))

        data2 = data1.upper().replace('\n', '').replace('\t', '')
        data3 = data2.replace(" ", "")

        ismiddlebracket = True
        while ismiddlebracket:
            if '[' in data3 and ']' in data3:
                start_index = data3.index('[')
                end_index = data3.index(']')
                old_time_hex = data3[start_index + 1:end_index]

                if time_type == 1:
                    hour = random.randint(0, 30 * 24) if israndomtime else fix_hour
                    ori_time = int(time.time()) - hour * 3600
                else:
                    ori_time = time.time()

                stamp_time = time.localtime(ori_time)
                time_mon = hex(stamp_time[1])[2:]
                time_day = hex(stamp_time[2])[2:]
                time_hour = hex(stamp_time[3])[2:]
                time_min = hex(stamp_time[4])[2:]
                time_second = hex(stamp_time[5])[2:]
                part_time = [self.fix_str(time_mon) + self.fix_str(time_day) +
                             self.fix_str(time_hour) + self.fix_str(time_min) +
                             self.fix_str(time_second)]

                isreversetime = 'R' in old_time_hex.upper()
                time_hex = old_time_hex.replace('R', '')
                time_len = len(time_hex)

                if time_len == 8:
                    hex_time = hex(int(ori_time))[2:]
                    if isreversetime:
                        hex_time = self.str_reverse(hex_time)
                elif time_len == 12:
                    time_year = self.fix_str(hex(stamp_time[0] - 2000)[2:])
                    hex_time = time_year + part_time[0]
                    if isreversetime:
                        hex_time = self.str_reverse(hex_time)
                elif time_len == 14 or time_len == 18:
                    time_year = self.fix_str(hex(stamp_time[0])[2:], 4)
                    if isreversetime:
                        time_year = self.str_reverse(time_year)
                    hex_time = time_year + part_time[0]
                    if time_len == 18:
                        ms_int = int(str(ori_time - int(ori_time))[2:5])
                        ms_hex = self.fix_str(hex(ms_int)[2:], 4)
                        if isreversetime:
                            ms_hex = self.str_reverse(ms_hex)
                        hex_time += ms_hex
                else:
                    hex_time = hex(int(ori_time))[2:]
                    if isreversetime:
                        hex_time = self.str_reverse(hex_time)

                return_time.append(int(ori_time))
                data3 = data3[:start_index] + hex_time + data3[end_index + 1:]
            else:
                ismiddlebracket = False

        data4 = data3
        frame_len_int = 0
        if '{' in data4 and '}' in data4:
            start_idx = data3.index('{')
            end_idx = data3.index('}')
            frame = data3[start_idx + 1:end_idx]
            frame_clean = re.sub(r'\(.*?\)', '', frame)
            frame_len_int = int(len(frame_clean) / 2)
            data4 = data4.replace('{', '').replace('}', '')

        if '<' in data4 and '>' in data4:
            start_idx = data3.index('<')
            end_idx = data3.index('>')
            frame = data3[start_idx + 1:end_idx]
            frame_clean = re.sub(r'\(.*?\)', '', frame)
            frame_len_int = int(len(frame_clean) / 2)
            data4 = data4.replace('<', '').replace('>', '')

        data5 = data4.replace('（', '(').replace('）', ')')
        if '(' in data5 and ')' in data5:
            if frame_len_int != 0:
                start_idx = data4.index('(')
                end_idx = data4.index(')')
                len_part = data4[start_idx:end_idx + 1]
                len_byte = int(len(len_part.replace('R', '')) - 2)
                len_hex = self.int_to_hex(frame_len_int, len_byte)
                if 'R' in len_part:
                    len_hex = self.str_reverse(len_hex)
                data5 = data4[:start_idx] + len_hex + data4[end_idx + 1:]
            else:
                data5 = data4.replace('(', '').replace(')', '')

        hex_clean = data5.replace(' ', '').upper()
        if len(hex_clean) >= 16:
            try:
                raw_bytes = bytes.fromhex(hex_clean)
                crc_data = raw_bytes[3:-4]
                crc_val = self.crc32_ccitt(crc_data)
                crc_hex = crc_val.to_bytes(4, 'big').hex().upper()
                hex_clean = hex_clean[:-8] + crc_hex
            except Exception:
                pass
        data5 = hex_clean

        return_data = self.data_format(data5) if isformat else data5
        time_val = return_time[0] if return_time else 0
        return return_data if return_data_type == 1 else (return_data, time_val)

    def data_format(self, data, num=2):
        num = int(num)
        result = ''
        data = data.replace(" ", "")
        for i in range(0, len(data), num):
            result += data[i:i + num] + ' '
        return result.upper().strip()

    def fix_str(self, data, num=2, ishead=True, fix_char='0'):
        str_len = len(data)
        if str_len < num:
            pad = fix_char * (num - str_len)
            data = pad + data if ishead else data + pad
        return data

    def str_reverse(self, data, num=2):
        data = data.replace(' ', '')
        parts = [data[i * num: (i + 1) * num] for i in range(int(len(data) / num))]
        return ''.join(reversed(parts))

    def int_to_hex(self, data, num=2):
        data = int(data)
        hex_str = hex(data)[2:]
        if len(hex_str) > num:
            num = math.ceil(len(hex_str) / 2) * 2
        return self.fix_str(hex_str, num).upper()

    def int_to_bin(self, data, num=8):
        bin_str = bin(data)[2:]
        if len(bin_str) > num:
            num = math.ceil(len(bin_str) / 8) * 8
        return self.fix_str(bin_str, num)

    def float_to_hex(self, f):
        if '.' in str(f):
            val = struct.unpack('<I', struct.pack('<f', float(f)))[0]
            return hex(val)[2:]
        else:
            f_int = int(f)
            f_hex = self.int_to_hex(abs(f_int))
            if f_int >= 0:
                return f_hex
            byte_num = int(len(f_hex) / 2)
            boundary = int('80' + '00' * (byte_num - 1), 16)
            real_val = float(f) + boundary
            bin_str = '1' + self.int_to_bin(int(real_val))[1:]
            return self.int_to_hex(int(bin_str, 2))

    def get_file_charset(self, file_path):
        """读取完整文件进行编码探测，避免只检测文件头导致中文点位误判。"""
        with open(file_path, 'rb') as f:
            raw = f.read()
        return chardet.detect(raw).get('encoding')

    def decode_text_file(self, file_path):
        """尽量可靠地识别常见点表编码；优先处理 BOM 和 UTF-8。"""
        with open(file_path, 'rb') as f:
            raw = f.read()
        if not raw:
            return ''
        # BOM 必须优先处理，特别是 UTF-16 导出的点表。
        if raw.startswith(b'\xef\xbb\xbf'):
            return raw.decode('utf-8-sig')
        if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
            return raw.decode('utf-16')

        # UTF-8 严格解码成功时优先采用，避免 UTF-8 中文被 GBK“成功但错误”地解码。
        try:
            return raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            pass

        detected = chardet.detect(raw) or {}
        enc = detected.get('encoding')
        confidence = float(detected.get('confidence') or 0)
        candidates = []
        if enc and confidence >= 0.75 and not any(x in enc.lower() for x in ('1252', 'latin', 'ascii')):
            candidates.append(enc)
        # GB18030 是 GBK/GB2312 的超集，适合中文 Windows 点表。
        candidates.extend(['gb18030', 'gbk', 'gb2312', 'big5'])
        if enc and confidence >= 0.60:
            candidates.append(enc)
        tried = set()
        for encoding in candidates:
            key = encoding.lower().replace('-', '').replace('_', '')
            if key in tried:
                continue
            tried.add(key)
            try:
                text = raw.decode(encoding)
                # 解码结果中出现大量替换字符或 NUL，通常代表编码判断错误。
                if text.count('\ufffd') or ('\x00' in text and not encoding.lower().startswith('utf-16')):
                    continue
                return text
            except (UnicodeDecodeError, LookupError):
                continue
        raise UnicodeError(f'无法可靠识别文件编码：{file_path}；请将点表另存为 UTF-8 或 GB18030')

    def get_text_data(self, dir_path, file_name, return_type=1):
        deal_files = []
        result = []
        try:
            available = os.listdir(dir_path)
        except Exception:
            available = []
        # 优先读取文件名完全对应的单个点表，避免“东站”误把“东站备份.txt”合并进来。
        exact = [f for f in available if os.path.splitext(f)[0].casefold() == os.path.splitext(str(file_name))[0].casefold()]
        if exact:
            deal_files = sorted(exact)
        else:
            deal_files = sorted(f for f in available if str(file_name) in f)

        for file in deal_files:
            file_path = os.path.join(dir_path, file)
            try:
                text = self.decode_text_file(file_path)
                result.extend(line.rstrip('\r\n') for line in text.splitlines() if line.strip())
            except Exception as e:
                print(f"读取文件{file}失败: {e}")
        return result


# ============================================================
# 二、辅助函数
# ============================================================
def pack_alarms_to_hex(alarm_count, is_alarm):
    if alarm_count <= 0:
        return ''
    byte_num = (alarm_count + 7) // 8
    mask = (1 << alarm_count) - 1 if is_alarm else 0
    return mask.to_bytes(byte_num, 'little').hex().upper()


def clean_point_name(line):
    line = line.strip()
    line = re.sub(r'^\d+\s*[:：]\s*', '', line)
    line = re.sub(r'^---.*?---', '', line)
    line = line.split(';')[0].strip()
    return line if line else '未命名点位'


def find_section_index(lines, keyword):
    def normalize(s):
        return re.sub(r'[^A-Za-z0-9]', '', s).upper()
    keyword_norm = normalize(keyword)
    for i, line in enumerate(lines):
        if normalize(line) == keyword_norm:
            return i
    return -1


def is_in_data(in_data, filter_data_list):
    in_data_lower = in_data.lower()
    for data in filter_data_list:
        if data.lower() in in_data_lower:
            return True
    return False


def find_title_index(module_data, keyword):
    for idx, line in enumerate(module_data):
        cleaned = re.sub(r'[-]+', '', line).strip()
        if cleaned == keyword or keyword in cleaned:
            return idx
    return -1


def detect_protocol_from_lines(files_data):
    for line in files_data or []:
        if '[' in line and ']' in line:
            match = re.search(r'\[(.*?)\]', line)
            if match and 'BAT' in match.group(1).upper():
                return 'DH2'
        if 'BAT-' in line.upper() or 'BAT1' in line.upper():
            return 'DH2'
    return 'DH1'


def detect_protocol_from_file(folder, station_name, func):
    files_data = func.get_text_data(folder, station_name)
    if not files_data:
        return 'DH1'
    for line in files_data:
        if '[' in line and ']' in line:
            match = re.search(r'\[(.*?)\]', line)
            if match:
                bracket_content = match.group(1).upper()
                if 'BAT' in bracket_content:
                    return 'DH2'
        if 'BAT-' in line.upper() or 'BAT1' in line.upper():
            return 'DH2'
    return 'DH1'


# ============================================================
# 三、结构化解析
# ============================================================
def parse_modules(module_data):
    type_count = 0
    modules = []
    current = None
    flags = {'analog': False, 'state': False, 'alarm': False}

    for line in module_data:
        line_strip = line.strip()

        if 'PWR_MODULE_TYPE_NUM' in line_strip.replace(' ', '').upper():
            try:
                type_count = int(line_strip.split('=')[1].strip())
            except Exception:
                type_count = 0
            continue

        if '[' in line_strip and ']' in line_strip and '模块个数' in line_strip:
            try:
                name = line_strip.split('[')[1].split(']')[0]
                m_count = int(line_strip.split('=')[1])
                current = {
                    'name': name, 'count': m_count,
                    'analog': [], 'state': [], 'alarm': []
                }
                modules.append(current)
                flags = {'analog': False, 'state': False, 'alarm': False}
            except Exception:
                pass
            continue

        if 'Module_Analog' in line_strip:
            flags = {'analog': True, 'state': False, 'alarm': False}
            continue
        if 'Module_State' in line_strip:
            flags = {'analog': False, 'state': True, 'alarm': False}
            continue
        if 'Module_Alarm' in line_strip:
            flags = {'analog': False, 'state': False, 'alarm': True}
            continue

        if current:
            point_name = clean_point_name(line_strip)
            if not point_name or point_name == '未命名点位':
                continue
            if flags['analog']:
                current['analog'].append(point_name)
            if flags['state']:
                current['state'].append(point_name)
            if flags['alarm']:
                current['alarm'].append(point_name)

    return type_count, modules


def parse_power_data(files_data):
    result = {
        'input_analog': [], 'state': [], 'alarm': [], 'output_analog': [],
        'modules': [], 'module_type_count': 0,
        'section_indices': {}, 'has_ups_section': False
    }

    ups_section_idx = find_section_index(files_data, 'UPS&BAT_Info')
    if ups_section_idx == -1:
        ups_section_idx = len(files_data)
    else:
        result['has_ups_section'] = True

    power_data = files_data[:ups_section_idx]

    input_analog_idx = find_section_index(power_data, 'PMS_INPUT_ANALOG')
    state_idx = find_section_index(power_data, 'PMS_SWITCH_STATE')

    idx_input_alarm = find_section_index(power_data, 'PMS_INPUT_ALARM')
    idx_alarm = find_section_index(power_data, 'PMS_ALARM')
    if idx_input_alarm != -1 and idx_alarm != -1:
        alarm_idx = min(idx_input_alarm, idx_alarm)
    else:
        alarm_idx = idx_input_alarm if idx_input_alarm != -1 else idx_alarm

    out_term_idx = find_section_index(power_data, 'PMS_输出端子表')
    output_analog_idx = find_section_index(power_data, 'PMS_OUTPUT_ANALOG')
    module_info_idx = find_section_index(power_data, 'PMS_Module_Info')

    result['section_indices'] = {
        'PMS_INPUT_ANALOG': input_analog_idx,
        'PMS_SWITCH_STATE': state_idx,
        'PMS_ALARM': alarm_idx,
        'PMS_输出端子表': out_term_idx,
        'PMS_OUTPUT_ANALOG': output_analog_idx,
        'PMS_Module_Info': module_info_idx,
        'UPS&BAT_Info': ups_section_idx if ups_section_idx != len(files_data) else -1,
    }

    def extract_points(start_idx, end_idx):
        if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
            return []
        points = []
        skip_titles = [
            'PMS_INPUT_ANALOG', 'PMS_SWITCH_STATE', 'PMS_ALARM', 'PMS_INPUT_ALARM',
            'PMS_OUTPUT_ANALOG', 'PMS_MODULE_INFO', 'PMS_输出端子表', 'UPS&BAT_INFO'
        ]
        for line in power_data[start_idx + 1:end_idx]:
            raw_line = line.strip()
            if raw_line.startswith('-----') and any(
                    kw.upper() in raw_line.upper() for kw in skip_titles):
                continue
            name = clean_point_name(line)
            if not name or name == '未命名点位':
                continue
            points.append(name)
        return points

    result['input_analog'] = extract_points(input_analog_idx, state_idx)
    result['state'] = extract_points(state_idx, alarm_idx)

    alarm_end_idx = out_term_idx if out_term_idx != -1 else output_analog_idx
    if alarm_end_idx == -1:
        alarm_end_idx = len(power_data)
    result['alarm'] = extract_points(alarm_idx, alarm_end_idx)

    output_end_idx = module_info_idx if module_info_idx != -1 else len(power_data)
    result['output_analog'] = extract_points(output_analog_idx, output_end_idx)

    module_data = power_data[module_info_idx + 1:ups_section_idx] \
        if module_info_idx != -1 else []
    type_count, modules = parse_modules(module_data)
    result['modules'] = modules
    result['module_type_count'] = type_count

    return result


def parse_ups_bat_data(files):
    module_starts = []
    for i, line in enumerate(files):
        if '[' in line and ']' in line:
            upper_line = line.upper()
            if 'UPS' in upper_line and 'BAT' not in upper_line:
                module_starts.append((i, 'ups'))
            elif 'BAT' in upper_line:
                module_starts.append((i, 'bat'))

    ups_modules, bat_modules = [], []

    for idx, (start_idx, kind) in enumerate(module_starts):
        end_idx = module_starts[idx + 1][0] if idx + 1 < len(module_starts) else len(files)
        module_data = files[start_idx:end_idx]

        analog_idx = find_title_index(module_data, '模拟量')
        alarm_idx = find_title_index(module_data, '告警量')

        if analog_idx == -1 or alarm_idx == -1:
            continue

        first_line = module_data[0]
        if '[' in first_line:
            name = first_line.split('[')[1].split(']')[0]
        else:
            name = f"Module{idx + 1}"

        analog_names = [clean_point_name(l) for l in module_data[analog_idx + 1:alarm_idx]]
        alarm_names = [clean_point_name(l) for l in module_data[alarm_idx + 1:]]
        analog_names = [n for n in analog_names if n and n != '未命名点位']
        alarm_names = [n for n in alarm_names if n and n != '未命名点位']

        mod = {'name': name, 'analog': analog_names, 'alarm': alarm_names}
        if kind == 'ups':
            ups_modules.append(mod)
        else:
            bat_modules.append(mod)

    return {'ups': ups_modules, 'bat': bat_modules}


# ============================================================
# 三-2、汇总（按实例展开）
# ============================================================
def _expand_module_instances(mod, points_key):
    count = mod.get('count', 1)
    points = mod.get(points_key, [])
    out = []
    if count <= 1:
        src = f"模块-{mod['name']}"
        prefix = mod['name']
        for pt in points:
            out.append((src, f"{prefix}{pt}"))
    else:
        for inst in range(1, count + 1):
            inst_name = f"{mod['name']}-{inst}"
            src = f"模块-{inst_name}"
            for pt in points:
                out.append((src, f"{inst_name}{pt}"))
    return out


def collect_all_analogs(power_result, ups_bat_result):
    items = []
    for pt in power_result['input_analog']:
        items.append(('电源屏-输入模拟量', pt))
    for pt in power_result['output_analog']:
        items.append(('电源屏-输出模拟量', pt))
    for mod in power_result['modules']:
        items.extend(_expand_module_instances(mod, 'analog'))
    for ups in ups_bat_result['ups']:
        for pt in ups['analog']:
            items.append((f"UPS-{ups['name']}", pt))
    for bat in ups_bat_result['bat']:
        for pt in bat['analog']:
            items.append((f"BAT-{bat['name']}", pt))
    return items


def collect_all_alarms(power_result, ups_bat_result):
    items = []
    for pt in power_result['alarm']:
        items.append(('电源屏-输入告警', pt))
    for mod in power_result['modules']:
        items.extend(_expand_module_instances(mod, 'alarm'))
    for ups in ups_bat_result['ups']:
        for pt in ups['alarm']:
            items.append((f"UPS-{ups['name']}", pt))
    for bat in ups_bat_result['bat']:
        for pt in bat['alarm']:
            items.append((f"BAT-{bat['name']}", pt))
    return items


# ============================================================
# 四、报文生成（支持勾选控制数据内容）
# ============================================================
def get_analog_value_int(analog_name, zero_analog=False):
    if zero_analog:
        return 0
    min_val = 0
    max_val = 500
    return random.randint(min_val * 100, max_val * 100)


def get_analog_code(analog_data, is_use_analog, func, data_type=1, ex_info='',
                    zero_analog=False, checked_keys=None, source_label='',
                    point_prefix=''):
    """
    checked_keys=None  → 原行为（全部随机值；zero_analog=True 时全 0）
    checked_keys=set   → 勾选的点生成随机值，未勾选的置 0
    zero_analog=True 优先级最高，直接全 0
    """
    count = len(analog_data)
    count_hex = func.int_to_hex(count, 4)
    type_name = {1: '输入', 2: '输出'}.get(data_type, '模块输出')

    value_str = ''
    for i in range(count):
        name = analog_data[i]
        full_name = point_prefix + name if point_prefix else name
        key = f"{source_label}|{full_name}"

        if zero_analog:
            val_int = 0
        elif checked_keys is None:
            # 原行为：全随机
            if '电压' in name:
                val_int = get_analog_value_int(name, False)
            else:
                val_int = random.randint(0, 4000)
        else:
            # 勾选控制：勾选生成值，未勾选置0
            if key in checked_keys:
                if '电压' in name:
                    val_int = get_analog_value_int(name, False)
                else:
                    val_int = random.randint(0, 4000)
            else:
                val_int = 0

        value_str += func.int_to_hex(val_int, 4) + ' '
        if i != 0 and (i + 1) % 10 == 0:
            value_str += '\n'

    code = f'{count_hex} #{type_name}模拟量个数 {count}个#\n{value_str}'
    return code.replace(' ', '').strip('\n')


def get_state_code(state_data, is_use_state, func, ex_info=''):
    count = len(state_data)
    count_hex = func.int_to_hex(count, 4)
    value_str = ''
    for i in range(count):
        idx = random.randint(0, 1)
        value_str += f'0{idx} '
    code = f'{count_hex} #开关状态量个数 {count}个#\n{value_str}'
    return code.replace(' ', '').strip('\n')


def get_alarm_code(alarm_data, is_use_alarm, is_alarm, func, data_type=1,
                   ex_info='', protocol='DH2', checked_keys=None,
                   source_label='', point_prefix=''):
    """
    checked_keys=None  → 原行为（is_alarm=True 全 FF/全1；False 全 00/全0）
    checked_keys=set   → 勾选的告警置 1，未勾选置 0
    """
    count = len(alarm_data)
    count_hex = func.int_to_hex(count, 4)
    type_name = '输入输出' if data_type == 1 else '模块'

    if checked_keys is None:
        # 原行为
        if protocol == 'DH1':
            value_str = pack_alarms_to_hex(count, is_alarm)
        else:
            byte_num = math.ceil(count / 8) if count > 0 else 0
            value_str = ''
            for _ in range(byte_num):
                value_str += 'FF ' if is_alarm else '00 '
            value_str = value_str.strip()
    else:
        # 按勾选构造位图（bit order: 点位 i → 字节 i//8 的第 i%8 位）
        byte_num = math.ceil(count / 8) if count > 0 else 0
        packed = bytearray(byte_num)
        for i, name in enumerate(alarm_data):
            full_name = point_prefix + name if point_prefix else name
            key = f"{source_label}|{full_name}"
            # 勾选点位表示本次处理的目标点；全局“报警/恢复”决定其置位或清零。
            # 未勾选点位保持正常（0），避免随机抽取和全局处理选项互相覆盖。
            if key in checked_keys and is_alarm:
                packed[i // 8] |= (1 << (i % 8))
        value_str = ' '.join(f"{b:02X}" for b in packed)

    code = f'{count_hex} #{type_name}告警个数 {count}个#\n{value_str}'
    return code.replace(' ', '').strip('\n')


def get_module_code(module_data, name_code_map, is_use_analog, is_use_state,
                    is_use_alarm, is_alarm, func, protocol='DH2', zero_analog=False,
                    analog_checked_keys=None, alarm_checked_keys=None):
    type_count = 0
    module_data_dict = {}
    module_names = []
    current_name = ''
    current_count = 0
    flags = {'analog': False, 'state': False, 'alarm': False}

    for line in module_data:
        line_strip = line.strip()

        if 'PWR_MODULE_TYPE_NUM' in line_strip.replace(' ', '').upper():
            try:
                type_count = int(line_strip.split('=')[1].strip())
            except Exception:
                type_count = 0
            continue

        if '[' in line_strip and ']' in line_strip and '模块个数' in line_strip:
            try:
                name = line_strip.split('[')[1].split(']')[0]
                m_count = int(line_strip.split('=')[1])
                code = name_code_map.get(name.upper(), '00')
                current_name = name
                current_count = m_count
                module_names.append(name)
                module_data_dict[name] = {
                    'count': m_count, 'code': code,
                    'analog': [], 'state': [], 'alarm': []
                }
                flags = {'analog': False, 'state': False, 'alarm': False}
            except Exception:
                pass
            continue

        if 'Module_Analog' in line_strip:
            flags = {'analog': True, 'state': False, 'alarm': False}
            continue
        if 'Module_State' in line_strip:
            flags = {'analog': False, 'state': True, 'alarm': False}
            continue
        if 'Module_Alarm' in line_strip:
            flags = {'analog': False, 'state': False, 'alarm': True}
            continue

        if current_name and current_name in module_data_dict:
            point_name = clean_point_name(line_strip)
            if not point_name or point_name == '未命名点位':
                continue
            if flags['analog']:
                module_data_dict[current_name]['analog'].append(point_name)
            if flags['state']:
                module_data_dict[current_name]['state'].append(point_name)
            if flags['alarm']:
                module_data_dict[current_name]['alarm'].append(point_name)

    all_code = f'{func.int_to_hex(type_count)} #模块类型总数{type_count}#'
    for idx, name in enumerate(module_names, 1):
        info = module_data_dict[name]
        count = info['count']
        m_code = info['code']
        value_code = ''
        for i in range(count):
            if count > 1:
                inst_name = f"{name}-{i + 1}"
            else:
                inst_name = name
            src = f"模块-{inst_name}"
            idx_hex = func.int_to_hex(i + 1)

            a_code = get_analog_code(
                info['analog'], is_use_analog, func, 3, '', zero_analog,
                checked_keys=analog_checked_keys,
                source_label=src, point_prefix=inst_name)
            s_code = get_state_code(info['state'], is_use_state, func)
            al_code = get_alarm_code(
                info['alarm'], is_use_alarm, is_alarm, func, 2, '', protocol,
                checked_keys=alarm_checked_keys,
                source_label=src, point_prefix=inst_name)

            block = f'{idx_hex} #模块{name}序号{idx}-{i + 1}#\n{a_code}\n{s_code}\n{al_code}'
            value_code += '\n' + block.replace(' ', '').strip('\n')

        part_code = (f'{m_code} #类型{idx}的模块{name}类型码#\n'
                     f'{func.int_to_hex(count)} #类型{idx}的模块数量{count}#\n{value_code}')
        all_code += '\n' + part_code.replace(' ', '').strip('\n')

    return all_code


def get_powerdh_code(file_path, file_name, is_use_analog, is_use_state,
                     is_use_alarm, is_alarm, func, station_index=1, sn=1,
                     protocol='DH2', zero_analog=False,
                     analog_checked_keys=None, alarm_checked_keys=None):
    module_name_code = {
        'TH1': '00', 'TC1': '01', 'TE1': '04', 'TE2': '05', 'TE3': '07',
        'DHXDD1': '08', 'DHXDD2': '09', 'DHXDE': '0A', 'DHXDF2': '0C',
        'DHXDF3': '0D', 'DHXDH4': '15', 'TU1': '16', 'SC1': '20', 'SD1': '21',
        'SD2': '22', 'SD3': '23', 'SE1': '24', 'SE2': '25', 'SE3': '26',
        'SE4': '27', 'SE5': '28', 'SH1': '29', 'SF1': '2a', 'SF2': '2b',
        'SF3': '2c', 'SC2': '2d', 'SW1': '2e', 'SD4': '2f', 'SD5': '30',
        'SE6': '31', 'SD7': '32', 'SC3': '33', 'HD11010(20)': '34', 'TH5': '0F'
    }

    files_data = func.get_text_data(file_path, file_name)
    if not files_data:
        return 'AA (0000) {30 [00000000] 01 00000001 0000 0000 0000 0000 00 55 00000000}'

    ups_section_idx = find_section_index(files_data, 'UPS&BAT_Info')
    if ups_section_idx == -1:
        ups_section_idx = len(files_data)
    power_data = files_data[:ups_section_idx]

    input_analog_idx = find_section_index(power_data, 'PMS_INPUT_ANALOG')
    state_idx = find_section_index(power_data, 'PMS_SWITCH_STATE')

    idx_input_alarm = find_section_index(power_data, 'PMS_INPUT_ALARM')
    idx_alarm = find_section_index(power_data, 'PMS_ALARM')
    if idx_input_alarm != -1 and idx_alarm != -1:
        alarm_idx = min(idx_input_alarm, idx_alarm)
    else:
        alarm_idx = idx_input_alarm if idx_input_alarm != -1 else idx_alarm

    out_term_idx = find_section_index(power_data, 'PMS_输出端子表')
    output_analog_idx = find_section_index(power_data, 'PMS_OUTPUT_ANALOG')
    module_info_idx = find_section_index(power_data, 'PMS_Module_Info')

    def extract_points(start_idx, end_idx):
        if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
            return []
        points = []
        skip_titles = [
            'PMS_INPUT_ANALOG', 'PMS_SWITCH_STATE', 'PMS_ALARM', 'PMS_INPUT_ALARM',
            'PMS_OUTPUT_ANALOG', 'PMS_MODULE_INFO', 'PMS_输出端子表', 'UPS&BAT_INFO'
        ]
        for line in power_data[start_idx + 1:end_idx]:
            raw_line = line.strip()
            if raw_line.startswith('-----') and any(
                    kw.upper() in raw_line.upper() for kw in skip_titles):
                continue
            name = clean_point_name(line)
            if not name or name == '未命名点位':
                continue
            points.append(name)
        return points

    input_analog = extract_points(input_analog_idx, state_idx)
    state_data = extract_points(state_idx, alarm_idx)
    alarm_end_idx = out_term_idx if out_term_idx != -1 else output_analog_idx
    if alarm_end_idx == -1:
        alarm_end_idx = len(power_data)
    alarm_data = extract_points(alarm_idx, alarm_end_idx)
    output_end_idx = module_info_idx if module_info_idx != -1 else len(power_data)
    output_analog = extract_points(output_analog_idx, output_end_idx)
    module_data = power_data[module_info_idx + 1:ups_section_idx] if module_info_idx != -1 else []

    input_code = get_analog_code(
        input_analog, is_use_analog, func, 1, zero_analog=zero_analog,
        checked_keys=analog_checked_keys,
        source_label='电源屏-输入模拟量', point_prefix='')
    state_code = get_state_code(state_data, is_use_state, func)
    alarm_code = get_alarm_code(
        alarm_data, is_use_alarm, is_alarm, func, 1, '', protocol,
        checked_keys=alarm_checked_keys,
        source_label='电源屏-输入告警', point_prefix='')
    output_code = get_analog_code(
        output_analog, is_use_analog, func, 2, zero_analog=zero_analog,
        checked_keys=analog_checked_keys,
        source_label='电源屏-输出模拟量', point_prefix='')
    module_code = get_module_code(
        module_data, module_name_code, is_use_analog,
        is_use_state, is_use_alarm, is_alarm, func,
        protocol, zero_analog,
        analog_checked_keys=analog_checked_keys,
        alarm_checked_keys=alarm_checked_keys)

    return f'''
        aa #帧开始标志#
        (01 f1) #帧长度#
        {{30 #Message Type#
        [5e426a31] #时间戳#
        {func.int_to_hex(station_index, 2)} #站点编号#
        {func.int_to_hex(sn, 8)} #报文序列号#
        {input_code}
        {state_code}
        {alarm_code}
        {output_code}
        {module_code}
        55 #结束标识#
        64a4aca2 #CRC校验#}}
    '''


def _build_dh2_ups_bat_data(files, is_alarm, is_use_alarm, is_use_analog, func,
                            zero_analog=False,
                            analog_checked_keys=None, alarm_checked_keys=None):
    ups_all_data, ups_module_name, ups_module_index = [], [], []
    bat_all_data, bat_module_name, bat_module_index = [], [], []

    ups_start_name = ''
    bat_start_name = ''
    for data in files:
        if '[' not in data or ']' not in data:
            continue
        if is_in_data(data, ['ups1', 'ups-1', '1[UPS_UL33_Modbus]']):
            ups_start_name = data
        if is_in_data(data, ['BAT-1', 'BAT1']):
            bat_start_name = data

    if not ups_start_name:
        return 0, 0, '', ''

    ups_index = files.index(ups_start_name)
    bat_start_index = files.index(bat_start_name) if bat_start_name else len(files)

    for i in range(ups_index, bat_start_index):
        data = files[i]
        ups_all_data.append(data)
        if '[' in data and ']' in data and 'ups' in data.lower():
            ups_module_name.append(data)
            ups_module_index.append(len(ups_all_data) - 1)

    if bat_start_index < len(files):
        for i in range(bat_start_index, len(files)):
            data = files[i]
            bat_all_data.append(data)
            if '[' in data and ']' in data and 'bat' in data.lower():
                bat_module_name.append(data)
                bat_module_index.append(len(bat_all_data) - 1)

    def find_title_idx(module_data, keyword):
        for idx, line in enumerate(module_data):
            cleaned = re.sub(r'[-]+', '', line).strip()
            if cleaned == keyword or keyword in cleaned:
                return idx
        return -1

    def build_module_code(all_data, mod_index, mod_name, kind_prefix):
        code = ''
        actual_count = 0
        for i in range(len(mod_name)):
            end_idx = mod_index[i + 1] if i < len(mod_name) - 1 else len(all_data)
            single = all_data[mod_index[i]:end_idx]
            a_idx = find_title_idx(single, '模拟量')
            al_idx = find_title_idx(single, '告警量')
            if a_idx == -1 or al_idx == -1:
                continue

            # 提取设备名
            first = mod_name[i]
            if '[' in first and ']' in first:
                dev_name = first.split('[')[1].split(']')[0]
            else:
                dev_name = f"Dev{actual_count + 1}"
            src = f"{kind_prefix}-{dev_name}"

            # 提取点位名称
            analog_names = [clean_point_name(l)
                            for l in single[a_idx + 1:al_idx]]
            analog_names = [n for n in analog_names if n and n != '未命名点位']
            alarm_names = [clean_point_name(l)
                           for l in single[al_idx + 1:]]
            alarm_names = [n for n in alarm_names if n and n != '未命名点位']

            analog_num = len(analog_names)
            alarm_num = len(alarm_names)

            module_no = func.int_to_hex(actual_count + 1)
            single_code = f'\n            {module_no} \n            '
            single_code += f'{func.int_to_hex(analog_num, 4)} \n            '

            # 模拟量
            for name in analog_names:
                key = f"{src}|{name}"
                if zero_analog:
                    val = 0.0
                elif analog_checked_keys is None:
                    val = round(random.uniform(0, 50), 2)
                else:
                    val = round(random.uniform(0, 50), 2) if key in analog_checked_keys else 0.0
                single_code += f'{func.str_reverse(func.float_to_hex(val))} '

            single_code += f'\n            {func.int_to_hex(alarm_num, 4)} \n            '

            # 告警
            byte_num = math.ceil(alarm_num / 8) if alarm_num > 0 else 0
            if alarm_checked_keys is None:
                for _ in range(byte_num):
                    single_code += f'{"FF" if is_alarm else "00"} '
            else:
                packed = bytearray(byte_num)
                for j, name in enumerate(alarm_names):
                    key = f"{src}|{name}"
                    if key in alarm_checked_keys:
                        packed[j // 8] |= (1 << (j % 8))
                for b in packed:
                    single_code += f'{b:02X} '

            code += single_code
            actual_count += 1
        return actual_count, code

    ups_count, ups_code = build_module_code(
        ups_all_data, ups_module_index, ups_module_name, 'UPS')
    bat_count, bat_code = build_module_code(
        bat_all_data, bat_module_index, bat_module_name, 'BAT')

    return ups_count, bat_count, ups_code, bat_code


def get_powerdh_anolog(file_path, file_name, is_alarm, is_use_alarm, is_use_analog,
                       func, station_index=1, sn=1, protocol='DH2', zero_analog=False,
                       analog_checked_keys=None, alarm_checked_keys=None):
    files = func.get_text_data(file_path, file_name)
    if not files:
        return 'AA (0000) <33 [00000000] 01 00000001 00 55 00000000>'

    if protocol == 'DH1':
        ups_section_start = find_section_index(files, 'UPS&BAT_Info')
        if ups_section_start == -1:
            return f'AA (0000) <33 [00000000] {func.int_to_hex(station_index, 2)} {func.int_to_hex(sn, 8)} 00 55 00000000>'

        ups_section = files[ups_section_start + 1:]
        ups_start_lines = []
        for i, line in enumerate(ups_section):
            if '[' in line and ']' in line and 'UPS' in line.upper():
                ups_start_lines.append((i, line))

        ups_len = len(ups_start_lines)
        ups_code = ''
        for i in range(ups_len):
            start_idx, start_line = ups_start_lines[i]
            end_idx = ups_start_lines[i + 1][0] if i < ups_len - 1 else len(ups_section)
            single_data = ups_section[start_idx:end_idx]
            a_idx = find_title_index(single_data, '模拟量')
            al_idx = find_title_index(single_data, '告警量')
            if a_idx is not None and al_idx is not None and a_idx != -1 and al_idx != -1:
                # 设备名
                if '[' in start_line and ']' in start_line:
                    dev_name = start_line.split('[')[1].split(']')[0]
                else:
                    dev_name = f"UPS{i + 1}"
                src = f"UPS-{dev_name}"

                analog_names = [clean_point_name(l)
                                for l in single_data[a_idx + 1:al_idx]]
                analog_names = [n for n in analog_names if n and n != '未命名点位']
                alarm_names = [clean_point_name(l)
                               for l in single_data[al_idx + 1:]]
                alarm_names = [n for n in alarm_names if n and n != '未命名点位']

                analog_num = len(analog_names)
                alarm_num = len(alarm_names)

                code = func.int_to_hex(analog_num, 4) + '\n'
                for name in analog_names:
                    key = f"{src}|{name}"
                    if zero_analog:
                        val = 0.0
                    elif analog_checked_keys is None:
                        val = round(random.uniform(0, 50), 2)
                    else:
                        val = round(random.uniform(0, 50), 2) if key in analog_checked_keys else 0.0
                    code += func.str_reverse(func.float_to_hex(val)) + ' '
                code += '\n' + func.int_to_hex(alarm_num, 4) + '\n'

                byte_num = math.ceil(alarm_num / 8) if alarm_num > 0 else 0
                if alarm_checked_keys is None:
                    for _ in range(byte_num):
                        code += 'FF ' if is_alarm else '00 '
                else:
                    packed = bytearray(byte_num)
                    for j, name in enumerate(alarm_names):
                        key = f"{src}|{name}"
                        if key in alarm_checked_keys:
                            packed[j // 8] |= (1 << (j % 8))
                    for b in packed:
                        code += f'{b:02X} '

                ups_code += f'{func.int_to_hex(i + 1, 2)} #UPS{i + 1}序号#\n{code}\n'
        return f'''AA (0000) <33 [00000000] {func.int_to_hex(station_index, 2)} {func.int_to_hex(sn, 8)} {func.int_to_hex(ups_len, 2)} {ups_code} 55 00000000>'''

    ups_count, bat_count, ups_code, bat_code = _build_dh2_ups_bat_data(
        files, is_alarm, is_use_alarm, is_use_analog, func, zero_analog,
        analog_checked_keys=analog_checked_keys,
        alarm_checked_keys=alarm_checked_keys
    )
    return f'''AA (01 C2) <33 [5C B4 79 D7] {func.int_to_hex(station_index, 2)} {func.int_to_hex(sn, 8)} {func.int_to_hex(ups_count, 2)} {func.int_to_hex(bat_count, 2)} {ups_code} {bat_code} 55 00000000>'''


# ============================================================
# 五、GUI
# ============================================================
class PointTableApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PowerDH 协议报文工具v1.0")
        self.root.geometry("1350x820")
        self.set_window_icon()

        self.func = PublicFunc()
        self.folder_path = tk.StringVar()
        self.selected_station = tk.StringVar()
        self.selected_files = []
        self.file_contexts = []
        self.site_info_list = []
        self.site_by_name = {}
        self.selected_site = None
        self.db_host = tk.StringVar(value="192.168.1.238")
        self.db_port = tk.IntVar(value=3306)
        self.db_user = tk.StringVar(value="root")
        self.db_pass = tk.StringVar(value="mysql")
        self.db_name = tk.StringVar(value="base")
        self.send_mode = tk.StringVar(value="单站发送")
        self.random_percent = tk.StringVar(value="30")
        self.time_offset = tk.StringVar(value="0")
        self.target_port = tk.IntVar(value=10030)
        self.source_ip = tk.StringVar(value="")
        self.send_interval = tk.DoubleVar(value=1.0)
        self._send_running = False
        self._send_thread = None
        self._send_stop = threading.Event()
        self._last_sent = []
        self._sent_point_names = {'analog': [], 'alarm': []}
        self.protocol = tk.StringVar(value="DH1")
        self.zero_analog = tk.BooleanVar(value=False)
        self.is_alarm = tk.BooleanVar(value=True)

        self.log_queue = queue.Queue()
        self.after_id = None
        self.original_stdout = sys.stdout

        self._last_context = None
        self._regen_after_id = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        sys.stdout = self
        self._start_log_consumer()

    def _get_app_icon_path(self):
        """查找 power.ico，兼容源码运行和 PyInstaller 打包运行。"""
        candidates = []
        if getattr(sys, "_MEIPASS", None):
            candidates.append(os.path.join(sys._MEIPASS, "power.ico"))
        # 源码所在目录优先，避免从其他工作目录启动时找不到图标
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "power.ico"))
        candidates.append(os.path.join(os.path.abspath(os.getcwd()), "power.ico"))
        for path in candidates:
            if os.path.isfile(path):
                return path
        return None

    def apply_window_icon(self, window):
        """将 power.ico 应用到指定 Tk/Toplevel 窗口。"""
        icon_path = getattr(self, "_app_icon_path", None) or self._get_app_icon_path()
        if not icon_path:
            return False
        try:
            window.iconbitmap(icon_path)
            return True
        except Exception as e:
            # 某些系统/主题不支持 iconbitmap 时不影响主程序运行
            print(f"设置窗口图标失败：{e}")
            return False

    def set_window_icon(self):
        """设置主窗口图标，并设置后续顶层窗口的默认图标。"""
        self._app_icon_path = self._get_app_icon_path()
        if not self._app_icon_path:
            print("未找到 power.ico，请将 power.ico 放在程序同目录，或打包时添加到程序根目录。")
            return
        try:
            # 设置 Tk 的默认顶层窗口图标，后续创建的 Toplevel 也会继承
            try:
                self.root.iconbitmap(default=self._app_icon_path)
            except Exception:
                pass
            self.apply_window_icon(self.root)
        except Exception as e:
            print(f"设置主窗口图标失败：{e}")

    def _start_log_consumer(self):
        self.after_id = self.root.after(100, self._process_log_queue)

    def _process_log_queue(self):
        try:
            messages = []
            while True:
                try:
                    msg = self.log_queue.get_nowait()
                    messages.append(msg)
                except queue.Empty:
                    break
            if messages:
                ts = time.strftime("%H:%M:%S")
                batch_text = "\n".join(f"[{ts}] {msg}" for msg in messages) + "\n"
                self.log_text.insert(tk.END, batch_text)
                self.log_text.see(tk.END)
                line_count = int(self.log_text.index('end-1c').split('.')[0])
                if line_count > 500:
                    self.log_text.delete('1.0', f'{line_count - 500}.0')
        except Exception:
            pass
        if not self.root.winfo_exists():
            return
        self.after_id = self.root.after(100, self._process_log_queue)

    def write(self, msg):
        if msg.strip():
            self._log(msg.strip())

    def flush(self):
        pass

    def _log(self, msg):
        if self.log_queue.qsize() > 1000:
            try:
                self.log_queue.get_nowait()
            except queue.Empty:
                pass
        self.log_queue.put(msg)

    # -------------------- UI --------------------
    def _build_ui(self):
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=BOTH, expand=True, padx=5, pady=5)

        left_panel = ttk.Frame(main_container, width=320)
        left_panel.pack(side=LEFT, fill=Y, padx=(0, 5))
        left_panel.pack_propagate(False)

        frame_folder = ttk.LabelFrame(left_panel, text="点表文件（支持多选）")
        frame_folder.pack(fill=X, pady=(0, 5))
        inner_folder = ttk.Frame(frame_folder, padding=8)
        inner_folder.pack(fill=BOTH, expand=True)
        ttk.Button(inner_folder, text="选择多个文件", command=self.select_files).pack(side=LEFT)
        ttk.Button(inner_folder, text="清除文件", command=self.clear_files).pack(side=LEFT, padx=5)

        frame_single = ttk.LabelFrame(left_panel, text="已选择文件 / 站点")
        frame_single.pack(fill=BOTH, expand=True, pady=(0, 5))
        inner_single = ttk.Frame(frame_single, padding=8)
        inner_single.pack(fill=BOTH, expand=True)
        list_frame = ttk.Frame(inner_single)
        list_frame.pack(fill=BOTH, expand=True)
        sb = ttk.Scrollbar(list_frame, orient="vertical")
        self.station_list = tk.Listbox(list_frame, height=12, selectmode=tk.SINGLE, yscrollcommand=sb.set)
        sb.config(command=self.station_list.yview)
        self.station_list.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)
        self.station_list.bind("<<ListboxSelect>>", self._on_station_select)

        frame_opt = ttk.LabelFrame(left_panel, text="处理选项")
        frame_opt.pack(fill=X, pady=(0, 5))
        inner_opt = ttk.Frame(frame_opt, padding=8)
        inner_opt.pack(fill=BOTH, expand=True)

        ttk.Checkbutton(inner_opt, text="模拟量为0（强制全部为0）",
                        variable=self.zero_analog).pack(anchor=W, pady=2)

        alarm_row = ttk.Frame(inner_opt)
        alarm_row.pack(fill=X, pady=2)
        ttk.Label(alarm_row, text="全局报警:").pack(side=LEFT)
        ttk.Radiobutton(alarm_row, text="报警",
                        variable=self.is_alarm, value=True).pack(side=LEFT, padx=2)
        ttk.Radiobutton(alarm_row, text="恢复",
                        variable=self.is_alarm, value=False).pack(side=LEFT, padx=2)
        ttk.Label(inner_opt, text="(无勾选时按此全局设置生成)",
                  foreground="#888").pack(anchor=W, pady=2)

        proto_row = ttk.Frame(inner_opt)
        proto_row.pack(fill=X, pady=2)
        ttk.Label(proto_row, text="检测协议:").pack(side=LEFT)
        ttk.Label(proto_row, textvariable=self.protocol,
                  foreground="blue", font=("", 10, "bold")).pack(side=LEFT, padx=5)

        btn_row = ttk.Frame(left_panel)
        btn_row.pack(fill=X, pady=(0, 5))
        ttk.Button(btn_row, text="解析并展示",
                   command=self.process_station).pack(side=LEFT, padx=5)
        ttk.Button(btn_row, text="清空日志",
                   command=self.clear_log).pack(side=LEFT, padx=5)

        right_panel = ttk.Frame(main_container)
        right_panel.pack(side=LEFT, fill=BOTH, expand=True)

        self.notebook = ttk.Notebook(right_panel)
        self.notebook.pack(fill=BOTH, expand=True)

        self.tab_overview = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_overview, text="解析概览")
        self._build_overview_tab()

        self.tab_power = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_power, text="电源屏点位")
        self.power_tree = self._build_tree_tab(self.tab_power)

        self.tab_module = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_module, text="模块信息")
        self.module_tree = self._build_tree_tab(self.tab_module)

        self.tab_ups = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_ups, text="UPS/BAT")
        self.ups_tree = self._build_tree_tab(self.tab_ups)

        self.tab_all_analog = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_all_analog, text="全部模拟量")
        self.all_analog_tree = self._build_table_tab(self.tab_all_analog)

        self.tab_all_alarm = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_all_alarm, text="全部告警量")
        self.all_alarm_tree = self._build_table_tab(self.tab_all_alarm)

        self.tab_message = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_message, text="生成报文")
        self._build_message_tab()

        self.tab_send = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_send, text="发送报文")
        self._build_send_tab()

        self.tab_log = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_log, text="运行日志")
        self.log_text = self._build_text_tab(self.tab_log)

    def _build_overview_tab(self):
        frame = ttk.Frame(self.tab_overview, padding=5)
        frame.pack(fill=BOTH, expand=True)
        self.overview_text = scrolledtext.ScrolledText(
            frame, font=("Consolas", 10), wrap=tk.WORD)
        self.overview_text.pack(fill=BOTH, expand=True)

    def _build_tree_tab(self, parent):
        frame = ttk.Frame(parent, padding=5)
        frame.pack(fill=BOTH, expand=True)
        sb = ttk.Scrollbar(frame, orient="vertical")
        tree = ttk.Treeview(frame, show="tree", yscrollcommand=sb.set)
        sb.config(command=tree.yview)
        sb.pack(side=RIGHT, fill=Y)
        tree.pack(side=LEFT, fill=BOTH, expand=True)
        tree.tag_configure('header', background='#e8f0fe',
                           font=('', 10, 'bold'))
        tree.tag_configure('section', foreground='#0066cc',
                           font=('', 10, 'bold'))
        tree.tag_configure('sub', foreground='#0b7a0b',
                           font=('', 9, 'bold'))
        tree.tag_configure('point', foreground='#333333')
        return tree

    def _build_table_tab(self, parent):
        frame = ttk.Frame(parent, padding=5)
        frame.pack(fill=BOTH, expand=True)

        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=X, pady=(0, 5))

        count_var = tk.StringVar(value="共 0 条")
        ttk.Label(toolbar, textvariable=count_var,
                  foreground="#0066cc", font=('', 10, 'bold')).pack(side=LEFT, padx=5)

        ttk.Label(toolbar, text="搜索:").pack(side=LEFT, padx=(20, 2))
        search_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=search_var, width=25).pack(side=LEFT, padx=2)

        ttk.Button(toolbar, text="全选",
                   command=lambda: tree._select_all(True)).pack(side=LEFT, padx=(15, 2))
        ttk.Button(toolbar, text="取消全选",
                   command=lambda: tree._select_all(False)).pack(side=LEFT, padx=2)

        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill=BOTH, expand=True)

        columns = ('勾选', '序号', '文件/站点', '来源', '点位名称')
        sb_y = ttk.Scrollbar(tree_frame, orient="vertical")
        sb_x = ttk.Scrollbar(tree_frame, orient="horizontal")
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings',
                            yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        for col, width, anchor in [
            ('勾选', 60, 'center'),
            ('序号', 60, 'w'),
            ('文件/站点', 180, 'w'),
            ('来源', 200, 'w'),
            ('点位名称', 500, 'w'),
        ]:
            tree.heading(col, text=col)
            tree.column(col, width=width, anchor=anchor,
                        stretch=(col != '勾选'))

        tree.tag_configure('odd', background='#f7f9fc')
        tree.tag_configure('even', background='#ffffff')
        tree.tag_configure('checked', background='#fff5cc')

        sb_y.config(command=tree.yview)
        sb_x.config(command=tree.xview)
        sb_y.pack(side=RIGHT, fill=Y)
        sb_x.pack(side=BOTTOM, fill=X)
        tree.pack(side=LEFT, fill=BOTH, expand=True)

        tree._count_var = count_var
        tree._search_var = search_var
        tree._all_items = []
        tree._checked_ids = set()
        tree._items_data = {}

        def _update_count():
            total = len(tree._all_items)
            checked = len(tree._checked_ids)
            shown = len(tree.get_children())
            count_var.set(f"共 {shown} 条  (全部 {total}, 已勾选 {checked})")

        def _filter(*_):
            keyword = search_var.get().strip().lower()
            for item in tree.get_children():
                tree.delete(item)
            tree._items_data = {}
            shown = 0
            for i, entry in enumerate(tree._all_items):
                if len(entry) == 3:
                    station, src, pt = entry
                else:
                    station, (src, pt) = "", entry
                if keyword and (keyword not in station.lower() and keyword not in src.lower()
                                and keyword not in pt.lower()):
                    continue
                shown += 1
                is_checked = i in tree._checked_ids
                mark = '☑' if is_checked else '☐'
                if is_checked:
                    tag = 'checked'
                else:
                    tag = 'odd' if shown % 2 else 'even'
                item = tree.insert('', 'end',
                                   values=(mark, shown, station, src, pt),
                                   tags=(tag,))
                tree._items_data[item] = i
            _update_count()

        def _select_all(state):
            if state:
                for i in range(len(tree._all_items)):
                    tree._checked_ids.add(i)
            else:
                tree._checked_ids.clear()
            _filter()
            self._schedule_regen()

        def _on_click(event):
            region = tree.identify('region', event.x, event.y)
            if region != 'cell':
                return
            col = tree.identify_column(event.x)
            if col != '#1':
                return
            item = tree.identify_row(event.y)
            if not item:
                return
            global_idx = tree._items_data.get(item)
            if global_idx is None:
                return
            if global_idx in tree._checked_ids:
                tree._checked_ids.discard(global_idx)
                new_mark = '☐'
                is_checked = False
            else:
                tree._checked_ids.add(global_idx)
                new_mark = '☑'
                is_checked = True
            tree.set(item, '勾选', new_mark)
            values = tree.item(item, 'values')
            try:
                shown = int(values[1])
            except Exception:
                shown = 1
            tag = 'checked' if is_checked else ('odd' if shown % 2 else 'even')
            tree.item(item, tags=(tag,))
            _update_count()
            self._schedule_regen()

        search_var.trace_add('write', _filter)
        tree.bind('<Button-1>', _on_click)
        tree._filter = _filter
        tree._select_all = _select_all
        tree._update_count = _update_count
        return tree

    def _build_message_tab(self):
        frame = ttk.Frame(self.tab_message, padding=5)
        frame.pack(fill=BOTH, expand=True)

        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=X, pady=(0, 5))
        ttk.Button(toolbar, text="重新生成报文",
                   command=self._regen_message).pack(side=LEFT, padx=5)
        ttk.Label(toolbar,
                  text="报文结构始终全量；勾选仅决定每个点位的数据内容（告警置位/模拟量赋值）",
                  foreground="#666").pack(side=LEFT, padx=10)

        text_frame = ttk.Frame(frame)
        text_frame.pack(fill=BOTH, expand=True)
        self.message_text = scrolledtext.ScrolledText(
            text_frame, font=("Consolas", 9))
        self.message_text.pack(fill=BOTH, expand=True)

    def _build_text_tab(self, parent):
        frame = ttk.Frame(parent, padding=5)
        frame.pack(fill=BOTH, expand=True)
        text = scrolledtext.ScrolledText(frame, font=("Consolas", 9))
        text.pack(fill=BOTH, expand=True)
        return text

    # -------------------- 事件 --------------------
    def select_files(self):
        paths = filedialog.askopenfilenames(
            title="选择一个或多个站点点表文件",
            filetypes=[("点表文本", "*.txt"), ("所有文件", "*.*")])
        if not paths:
            return
        self.selected_files = list(paths)
        # 新文件集需要重新解析，避免旧解析结果与新列表索引错位。
        self.file_contexts = []
        self._refresh_file_list()
        self._clear_displayed_results()
        if self.selected_files:
            self.station_list.selection_set(0)
            self.station_list.activate(0)
            self._on_station_select(None)
        self._log(f"已选择 {len(self.selected_files)} 个文件；点击“解析并展示”后会一次性解析全部文件")

    def clear_files(self):
        self.selected_files = []
        self.file_contexts = []
        self.station_list.delete(0, tk.END)
        self._clear_displayed_results()
        self._log("已清除文件列表")

    def _clear_displayed_results(self):
        """清空当前展示，避免更换文件后仍显示上一次的内容。"""
        for tree_name in ("power_tree", "module_tree", "ups_tree"):
            tree = getattr(self, tree_name, None)
            if tree is not None:
                for item in tree.get_children():
                    tree.delete(item)
        for tree_name in ("all_analog_tree", "all_alarm_tree"):
            tree = getattr(self, tree_name, None)
            if tree is not None:
                tree._all_items = []
                tree._checked_ids.clear()
                tree._filter()
        if hasattr(self, "overview_text"):
            self.overview_text.delete("1.0", tk.END)
        if hasattr(self, "message_text"):
            self.message_text.delete("1.0", tk.END)
        self._last_context = None
        self._displayed_context = None

    def _refresh_file_list(self):
        """左侧统一管理文件/站点；数据库连接成功后在同一列表补充站点信息。"""
        self.station_list.delete(0, tk.END)
        contexts = {os.path.abspath(c['path']): c for c in self.file_contexts}
        for path in self.selected_files:
            file_name = os.path.basename(path)
            ctx = contexts.get(os.path.abspath(path))
            station = (ctx.get('station') if ctx else None) or self._find_site_for_name(os.path.splitext(file_name)[0])
            if station:
                suffix = f" | IP:{station.get('ip') or '无'} | 站点号:{station.get('station_no')}"
                if ctx.get('station_match_type') == 'similar':
                    suffix += ' | 相似匹配'
            else:
                suffix = ' | 数据库站点：未匹配'
            self.station_list.insert(tk.END, file_name + suffix)

    def _selected_file_paths(self):
        # 解析按钮始终解析全部已选择文件；左侧列表只用于切换查看对象。
        return list(self.selected_files)

    def _read_exact_file(self, path):
        text = self.func.decode_text_file(path)
        return [line.rstrip("\r\n") for line in text.splitlines() if line.strip()]

    def _on_station_select(self, _):
        sel = self.station_list.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self.selected_files):
            return
        path = self.selected_files[idx]
        file = os.path.basename(path)
        self.selected_station.set(file)
        station_name = os.path.splitext(file)[0]
        # 左侧文件/站点列表同时承担站点选择：单站发送直接使用当前选中文件匹配的站点。
        ctx = next((c for c in self.file_contexts if os.path.abspath(c['path']) == os.path.abspath(path)), None)
        site = (ctx.get('station') if ctx else None) or self._find_site_for_name(station_name)
        self.selected_site = site
        self.source_ip.set(site.get('ip', '') if site else '')
        if ctx:
            self._display_file_context(ctx)
            self._log(f"当前选择站点：{site['name']} | IP:{site.get('ip') or '无'} | 站点号:{site['station_no']}" if site else f"文件 {file} 暂无匹配数据库站点")
            self._log(f"当前展示文件：{file}（仅显示该文件的数据）")
            return
        if self.file_contexts:
            self._clear_displayed_results()
            self._log(f"文件 {file} 未成功解析，已清空旧展示内容；请检查文件后重新点击“解析并展示”")
            return
        try:
            lines = self._read_exact_file(path)
            detected = detect_protocol_from_lines(lines)
            self.protocol.set(detected)
            self._log(f"已选择站点文件: {file} | 自动检测协议: {detected}；请点击“解析并展示”完成批量解析")
        except Exception as e:
            self._log(f"读取文件失败 {file}: {e}")

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    # -------------------- 核心 --------------------
    def process_station(self):
        """一次性解析全部已选择文件；解析后由左侧文件列表切换展示内容。"""
        paths = self._selected_file_paths()
        if not paths:
            self._log("请先选择一个或多个点表文件！")
            return
        self.file_contexts = []
        overview_parts = []
        for path in paths:
            station_name = os.path.splitext(os.path.basename(path))[0]
            folder = os.path.dirname(path) or "."
            try:
                files_data = self._read_exact_file(path)
                if not files_data:
                    self._log(f"文件无有效数据，跳过：{path}")
                    continue
                protocol = detect_protocol_from_lines(files_data)
                power_result = parse_power_data(files_data)
                ups_bat_result = parse_ups_bat_data(files_data)
                analog_items = [(station_name, src, pt) for src, pt in collect_all_analogs(power_result, ups_bat_result)]
                alarm_items = [(station_name, src, pt) for src, pt in collect_all_alarms(power_result, ups_bat_result)]
                self.file_contexts.append({
                    'path': path, 'folder': folder, 'station_name': station_name,
                    'file_name': os.path.basename(path), 'protocol': protocol,
                    'power': power_result, 'ups': ups_bat_result,
                    'analogs': analog_items, 'alarms': alarm_items,
                    'analog_checked_ids': set(), 'alarm_checked_ids': set(),
                    'station': None,
                })
                overview_parts.append(f"{station_name}: 协议 {protocol}，模拟量 {len(analog_items)}，告警量 {len(alarm_items)}")
            except Exception as e:
                self._log(f"解析文件失败 {path}: {e}")
                traceback.print_exc()
        if not self.file_contexts:
            self._log("没有成功解析的文件")
            return
        self._match_selected_files_to_sites(log_only=False)
        self._refresh_file_list()
        # 解析完成后选中第一个成功解析的文件并展示；后续点击文件名只切换展示。
        first_path = self.file_contexts[0]['path']
        try:
            first_index = next(i for i, p in enumerate(self.selected_files) if os.path.abspath(p) == os.path.abspath(first_path))
            self.station_list.selection_clear(0, tk.END)
            self.station_list.selection_set(first_index)
            self.station_list.activate(first_index)
        except Exception:
            pass
        self._display_file_context(self.file_contexts[0])
        self._log(f"全部文件解析完成：成功 {len(self.file_contexts)} 个；" + "；".join(overview_parts))

    def _save_current_file_checks(self):
        """切换文件前，将当前两个点位表的勾选状态保存回对应文件上下文。"""
        ctx = getattr(self, '_displayed_context', None)
        if not ctx:
            return
        ctx['analog_checked_ids'] = set(self.all_analog_tree._checked_ids)
        ctx['alarm_checked_ids'] = set(self.all_alarm_tree._checked_ids)

    def _display_file_context(self, ctx):
        """仅展示当前选中文件的解析数据，绝不将多个文件汇总到同一界面。"""
        if getattr(self, '_displayed_context', None) is ctx:
            # 同一文件重复选择也刷新一次，保持界面状态一致。
            pass
        else:
            self._save_current_file_checks()
        self._displayed_context = ctx
        self.protocol.set(ctx['protocol'])
        self._update_overview(ctx['power'], ctx['ups'], ctx['protocol'])
        self._update_power_tree(ctx['power'])
        self._update_module_tree(ctx['power']['modules'], ctx['power']['module_type_count'])
        self._update_ups_tree(ctx['ups'])
        self.all_analog_tree._all_items = list(ctx['analogs'])
        self.all_analog_tree._checked_ids = set(ctx.get('analog_checked_ids', set()))
        self.all_analog_tree._filter()
        self.all_alarm_tree._all_items = list(ctx['alarms'])
        self.all_alarm_tree._checked_ids = set(ctx.get('alarm_checked_ids', set()))
        self.all_alarm_tree._filter()
        self.notebook.tab(self.tab_all_analog, text=f"全部模拟量 ({len(ctx['analogs'])})")
        self.notebook.tab(self.tab_all_alarm, text=f"全部告警量 ({len(ctx['alarms'])})")
        self._last_context = (ctx['folder'], ctx['station_name'], ctx['protocol'])
        self._regen_message()

    def _update_overview(self, power_result, ups_bat_result, protocol):
        lines = []
        lines.append("=" * 60)
        lines.append(f"  协议版本: {protocol}")
        lines.append(f"  UPS&BAT 分区: {'存在' if power_result['has_ups_section'] else '不存在'}")
        lines.append("=" * 60)
        lines.append("")
        lines.append("【电源屏点位统计】")
        lines.append(f"  输入模拟量:   {len(power_result['input_analog']):>4} 个")
        lines.append(f"  开关状态量:   {len(power_result['state']):>4} 个")
        lines.append(f"  告警量:       {len(power_result['alarm']):>4} 个")
        lines.append(f"  输出模拟量:   {len(power_result['output_analog']):>4} 个")
        lines.append(f"  模块类型数:   {power_result['module_type_count']:>4} 个")
        lines.append(f"  模块实例数:   {sum(m['count'] for m in power_result['modules']):>4} 个")
        lines.append("")

        all_analogs = collect_all_analogs(power_result, ups_bat_result)
        all_alarms = collect_all_alarms(power_result, ups_bat_result)
        lines.append("【当前文件点位汇总（按实例展开）】")
        lines.append(f"  全部模拟量:   {len(all_analogs):>4} 条")
        lines.append(f"  全部告警量:   {len(all_alarms):>4} 条")
        lines.append("")
        n_an = len(self.all_analog_tree._checked_ids)
        n_al = len(self.all_alarm_tree._checked_ids)
        lines.append("【勾选关注点（决定报文数据内容）】")
        lines.append(f"  已勾选模拟量: {n_an} / {len(all_analogs)}  (勾选=有值, 未勾选=0)")
        lines.append(f"  已勾选告警:   {n_al} / {len(all_alarms)}  (勾选=报警, 未勾选=正常)")
        if n_an == 0 and n_al == 0:
            lines.append("  → 无勾选，按左侧【全局报警】设置全量生成")
        lines.append("")

        lines.append("【UPS/BAT 统计】")
        lines.append(f"  UPS 设备数: {len(ups_bat_result['ups'])} 台")
        for ups in ups_bat_result['ups']:
            lines.append(f"    - {ups['name']}: 模拟量 {len(ups['analog'])} 个, "
                         f"告警量 {len(ups['alarm'])} 个")
        lines.append(f"  BAT 设备数: {len(ups_bat_result['bat'])} 台")
        for bat in ups_bat_result['bat']:
            lines.append(f"    - {bat['name']}: 模拟量 {len(bat['analog'])} 个, "
                         f"告警量 {len(bat['alarm'])} 个")
        lines.append("")
        lines.append("【分区定位（行索引）】")
        for name, idx in power_result['section_indices'].items():
            label = "未找到" if idx == -1 else f"行 {idx}"
            lines.append(f"  {name:<22}: {label}")

        self.overview_text.delete(1.0, tk.END)
        self.overview_text.insert(tk.END, "\n".join(lines))

    def _update_power_tree(self, power_result):
        tree = self.power_tree
        for item in tree.get_children():
            tree.delete(item)

        sections = [
            ('输入模拟量', power_result['input_analog']),
            ('开关状态量', power_result['state']),
            ('告警量', power_result['alarm']),
            ('输出模拟量', power_result['output_analog']),
        ]
        for name, points in sections:
            node = tree.insert("", "end",
                               text=f"{name}  ({len(points)} 个)",
                               open=True, tags=('section',))
            for i, point in enumerate(points, 1):
                tree.insert(node, "end", text=f"{i:>3}.  {point}", tags=('point',))
            if not points:
                tree.insert(node, "end", text="（无点位）", tags=('point',))

    def _update_module_tree(self, modules, type_count):
        tree = self.module_tree
        for item in tree.get_children():
            tree.delete(item)

        root = tree.insert("", "end",
                           text=f"模块类型总数: {type_count}",
                           open=True, tags=('header',))

        if not modules:
            tree.insert(root, "end", text="（无模块信息）", tags=('point',))
            return

        for i, mod in enumerate(modules, 1):
            mod_node = tree.insert(
                root, "end",
                text=f"{i}. 模块 {mod['name']}   数量: {mod['count']} 个",
                open=True, tags=('header',))

            for sub_name, sub_points, tag in [
                ('模拟量', mod['analog'], 'section'),
                ('状态量', mod['state'], 'sub'),
                ('告警量', mod['alarm'], 'sub'),
            ]:
                sub_node = tree.insert(
                    mod_node, "end",
                    text=f"{sub_name}  ({len(sub_points)} 个)",
                    open=False, tags=(tag,))
                for j, pt in enumerate(sub_points, 1):
                    tree.insert(sub_node, "end",
                                text=f"{j:>3}.  {pt}", tags=('point',))
                if not sub_points:
                    tree.insert(sub_node, "end", text="（无点位）", tags=('point',))

    def _update_ups_tree(self, ups_bat_result):
        tree = self.ups_tree
        for item in tree.get_children():
            tree.delete(item)

        for kind, label, modules in [
            ('ups', 'UPS 设备', ups_bat_result['ups']),
            ('bat', 'BAT 设备', ups_bat_result['bat']),
        ]:
            kind_node = tree.insert(
                "", "end",
                text=f"{label}  ({len(modules)} 台)",
                open=True, tags=('header',))
            if not modules:
                tree.insert(kind_node, "end", text="（未识别到设备）", tags=('point',))
                continue
            for i, mod in enumerate(modules, 1):
                mod_node = tree.insert(
                    kind_node, "end",
                    text=f"{i}. {mod['name']}",
                    open=True, tags=('header',))
                a_node = tree.insert(
                    mod_node, "end",
                    text=f"模拟量 ({len(mod['analog'])} 个)",
                    open=False, tags=('section',))
                for j, pt in enumerate(mod['analog'], 1):
                    tree.insert(a_node, "end", text=f"{j:>3}.  {pt}", tags=('point',))
                al_node = tree.insert(
                    mod_node, "end",
                    text=f"告警量 ({len(mod['alarm'])} 个)",
                    open=False, tags=('sub',))
                for j, pt in enumerate(mod['alarm'], 1):
                    tree.insert(al_node, "end", text=f"{j:>3}.  {pt}", tags=('point',))

    def _update_all_analog_tree(self, power_result, ups_bat_result):
        tree = self.all_analog_tree
        items = collect_all_analogs(power_result, ups_bat_result)
        tree._all_items = items
        tree._checked_ids.clear()
        tree._filter()
        self.notebook.tab(self.tab_all_analog,
                          text=f"全部模拟量 ({len(items)})")

    def _update_all_alarm_tree(self, power_result, ups_bat_result):
        tree = self.all_alarm_tree
        items = collect_all_alarms(power_result, ups_bat_result)
        tree._all_items = items
        tree._checked_ids.clear()
        tree._filter()
        self.notebook.tab(self.tab_all_alarm,
                          text=f"全部告警量 ({len(items)})")

    # -------------------- 报文生成 --------------------
    def _build_checked_keys(self, station_name=None):
        analog_keys, alarm_keys = set(), set()
        an_items = getattr(self.all_analog_tree, '_all_items', [])
        for gid in getattr(self.all_analog_tree, '_checked_ids', set()):
            if 0 <= gid < len(an_items):
                entry = an_items[gid]
                if len(entry) == 3:
                    station, src, pt = entry
                    if station_name is not None and station != station_name:
                        continue
                else:
                    src, pt = entry
                analog_keys.add(f"{src}|{pt}")
        al_items = getattr(self.all_alarm_tree, '_all_items', [])
        for gid in getattr(self.all_alarm_tree, '_checked_ids', set()):
            if 0 <= gid < len(al_items):
                entry = al_items[gid]
                if len(entry) == 3:
                    station, src, pt = entry
                    if station_name is not None and station != station_name:
                        continue
                else:
                    src, pt = entry
                alarm_keys.add(f"{src}|{pt}")
        return analog_keys, alarm_keys

    def _build_checked_keys_for_context(self, ctx):
        """根据每个文件独立保存的勾选状态构建发送点位集合。"""
        analog_keys, alarm_keys = set(), set()
        for idx in ctx.get('analog_checked_ids', set()):
            if 0 <= idx < len(ctx.get('analogs', [])):
                entry = ctx['analogs'][idx]
                analog_keys.add(f"{entry[1]}|{entry[2]}")
        for idx in ctx.get('alarm_checked_ids', set()):
            if 0 <= idx < len(ctx.get('alarms', [])):
                entry = ctx['alarms'][idx]
                alarm_keys.add(f"{entry[1]}|{entry[2]}")
        return analog_keys, alarm_keys

    def _schedule_regen(self):
        """勾选变化后自动重新生成报文（带防抖）。"""
        if self._regen_after_id:
            try:
                self.root.after_cancel(self._regen_after_id)
            except Exception:
                pass
        self._regen_after_id = self.root.after(400, self._do_regen)

    def _do_regen(self):
        self._regen_after_id = None
        if self._last_context:
            self._regen_message()

    def _regen_message(self):
        contexts = getattr(self, 'file_contexts', [])
        ctx = getattr(self, '_displayed_context', None)
        if not contexts or not ctx:
            self.message_text.delete(1.0, tk.END)
            self.message_text.insert(tk.END, "请先点击“解析并展示”，然后在左侧点击要查看的文件。")
            return
        self._save_current_file_checks()
        station_name = ctx['station_name']
        analog_keys, alarm_keys = self._build_checked_keys(station_name)
        # 预览只显示当前文件；未勾选时保持原程序的全量默认行为。
        any_checked = bool(analog_keys or alarm_keys)
        analog_arg = analog_keys if any_checked else None
        alarm_arg = alarm_keys if any_checked else None
        try:
            power_msg = get_powerdh_code(
                ctx['folder'], station_name, True, True, True,
                self.is_alarm.get(), self.func, station_index=1, sn=1,
                protocol=ctx['protocol'], zero_analog=self.zero_analog.get(),
                analog_checked_keys=analog_arg, alarm_checked_keys=alarm_arg)
            formatted_power = self.func.deal_data(power_msg, fix_hour=-int(self.time_offset.get()), isformat=True)
        except Exception as e:
            formatted_power = f"生成失败: {e}"
        try:
            ups_msg = get_powerdh_anolog(
                ctx['folder'], station_name, self.is_alarm.get(), True, True,
                self.func, station_index=1, sn=1, protocol=ctx['protocol'],
                zero_analog=self.zero_analog.get(), analog_checked_keys=analog_arg,
                alarm_checked_keys=alarm_arg)
            formatted_ups = self.func.deal_data(ups_msg, fix_hour=-int(self.time_offset.get()), isformat=True)
        except Exception as e:
            formatted_ups = f"生成失败: {e}"
        station = ctx.get('station')
        station_desc = (f"数据库站点：{station['name']} | 站点号：{station['station_no']}"
                        if station else "数据库站点：未匹配（允许预览，禁止发送和校验）")
        summary = (f"当前文件：{ctx['file_name']} | 协议：{ctx['protocol']}\n{station_desc}\n"
                   f"当前文件模拟量勾选：{len(analog_keys)}；告警量勾选：{len(alarm_keys)}\n"
                   "提示：这里只显示当前选中文件的报文预览；预览不会发送。\n\n")
        chunk = ("=" * 68 + f"\n站点：{station_name} | 文件：{ctx['file_name']} | 协议：{ctx['protocol']}\n" + "=" * 68 +
                 "\n【电源屏报文 (Message Type 0x30)】\n" + formatted_power +
                 "\n\n【UPS/BAT 报文 (Message Type 0x33)】\n" + formatted_ups + "\n")
        self.message_text.delete(1.0, tk.END)
        self.message_text.insert(tk.END, summary + chunk)

    # -------------------- 数据库、发送、校验 --------------------
    def _build_send_tab(self):
        outer = ttk.Frame(self.tab_send, padding=8)
        outer.pack(fill=BOTH, expand=True)
        db = ttk.LabelFrame(outer, text="数据库连接（与站点获取、校验共用）", padding=8)
        db.pack(fill=X, pady=(0, 8))
        row1 = ttk.Frame(db); row1.pack(fill=X, pady=2)
        ttk.Label(row1, text="主机").pack(side=LEFT)
        ttk.Entry(row1, textvariable=self.db_host, width=16).pack(side=LEFT, padx=4)
        ttk.Label(row1, text="端口").pack(side=LEFT, padx=(8, 0))
        ttk.Entry(row1, textvariable=self.db_port, width=7).pack(side=LEFT, padx=4)
        ttk.Label(row1, text="数据库").pack(side=LEFT, padx=(8, 0))
        ttk.Entry(row1, textvariable=self.db_name, width=12).pack(side=LEFT, padx=4)
        row2 = ttk.Frame(db); row2.pack(fill=X, pady=2)
        ttk.Label(row2, text="用户名").pack(side=LEFT)
        ttk.Entry(row2, textvariable=self.db_user, width=16).pack(side=LEFT, padx=4)
        ttk.Label(row2, text="密码").pack(side=LEFT, padx=(8, 0))
        ttk.Entry(row2, textvariable=self.db_pass, width=16, show="*").pack(side=LEFT, padx=4)
        ttk.Button(row2, text="获取数据连接并更新左侧站点", command=self.fetch_sites_from_db).pack(side=LEFT, padx=8)
        send = ttk.LabelFrame(outer, text="网络配置与发送", padding=8)
        send.pack(fill=X, pady=(0, 8))
        r1 = ttk.Frame(send); r1.pack(fill=X, pady=3)
        ttk.Label(r1, text="发送模式").pack(side=LEFT)
        ttk.Combobox(r1, textvariable=self.send_mode, values=["单站发送", "全站发送"], state="readonly", width=12).pack(side=LEFT, padx=4)
        ttk.Label(r1, text="源 IP（在左侧已选择文件/站点中选择）").pack(side=LEFT, padx=(8, 2))
        ttk.Entry(r1, textvariable=self.source_ip, width=14, state="readonly").pack(side=LEFT, padx=3)
        ttk.Label(r1, text="统一目标 IP（默认 db_host）").pack(side=LEFT, padx=(8, 2))
        ttk.Entry(r1, textvariable=self.db_host, width=16, state="readonly").pack(side=LEFT, padx=4)
        ttk.Label(r1, text="目标端口").pack(side=LEFT, padx=(8, 0))
        ttk.Entry(r1, textvariable=self.target_port, width=7).pack(side=LEFT, padx=4)
        r2 = ttk.Frame(send); r2.pack(fill=X, pady=3)
        ttk.Label(r2, text="报文时间").pack(side=LEFT)
        ttk.Combobox(r2, textvariable=self.time_offset, values=["-8", "0", "+8"], state="readonly", width=8).pack(side=LEFT, padx=4)
        ttk.Label(r2, text="小时（默认 0） 发送间隔秒").pack(side=LEFT, padx=(8, 2))
        ttk.Entry(r2, textvariable=self.send_interval, width=8).pack(side=LEFT, padx=4)
        r3 = ttk.Frame(send); r3.pack(fill=X, pady=3)
        ttk.Label(r3, text="随机抽取比例").pack(side=LEFT)
        ttk.Combobox(r3, textvariable=self.random_percent, values=["10", "30", "50", "70", "100"], state="readonly", width=8).pack(side=LEFT, padx=4)
        ttk.Button(r3, text="随机抽取模拟和报警", command=self.random_select_points).pack(side=LEFT, padx=8)
        ttk.Button(r3, text="生成报文预览", command=self._regen_message).pack(side=LEFT, padx=4)
        r4 = ttk.Frame(send); r4.pack(fill=X, pady=5)
        ttk.Button(r4, text="开始发送", command=self.start_send).pack(side=LEFT, padx=4)
        ttk.Button(r4, text="停止发送", command=self.stop_send).pack(side=LEFT, padx=4)
        ttk.Button(r4, text="校验所选模拟量和报警", command=self.validate_sent_points).pack(side=LEFT, padx=12)
        self.send_result_text = scrolledtext.ScrolledText(outer, height=8, font=("Consolas", 9))
        self.send_result_text.pack(fill=BOTH, expand=True, pady=(5, 0))

    def _db_connect(self):
        if not PYMYSQL_AVAILABLE:
            raise RuntimeError("未安装 pymysql，请运行 pip install pymysql")
        return pymysql.connect(host=self.db_host.get().strip(), port=int(self.db_port.get()),
            user=self.db_user.get().strip(), password=self.db_pass.get(),
            database=self.db_name.get().strip(), charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor, connect_timeout=8)

    @staticmethod
    def _name_similarity(a, b):
        return difflib.SequenceMatcher(None, str(a or "").casefold(), str(b or "").casefold()).ratio()

    @staticmethod
    def _digits_signature(name):
        return re.findall(r"\d+", str(name or ""))

    def _safe_name_match(self, a, b):
        # 保护设备编号：数字序列不一致时，不自动认定为同一个设备。
        if self._digits_signature(a) != self._digits_signature(b):
            return False
        return self._name_similarity(a, b) >= 0.8

    def fetch_sites_from_db(self):
        try:
            conn = self._db_connect()
            try:
                with conn.cursor() as cur:
                    cur.execute("""SELECT a.IP, b.STATION_NAME, b.STATION_NO
                        FROM dic_mss_netaddress_config a
                        RIGHT JOIN dic_station b ON a.STATION_NO=b.STATION_NO
                        WHERE (a.sys_no=6 AND a.master=1) OR a.IP IS NULL""")
                    rows = cur.fetchall()
            finally:
                conn.close()
            self.site_info_list = []
            for row in rows:
                name = str(row.get("STATION_NAME") or "").strip()
                ip = str(row.get("IP") or "").strip()
                no = row.get("STATION_NO")
                if name and no is not None:
                    self.site_info_list.append({'name': name, 'ip': ip, 'station_no': no, 'target_ip': self.db_host.get().strip()})
            self.site_by_name = {x['name']: x for x in self.site_info_list}
            self._match_selected_files_to_sites(log_only=False)
            self._refresh_file_list()
            # 保持当前文件选择，并同步选中站点及源 IP。
            sel = self.station_list.curselection()
            if sel:
                self._on_station_select(None)
            self._send_log(f"数据库连接成功，获取站点 {len(self.site_info_list)} 个；站点信息已更新到左侧“已选择文件 / 站点”列表")
        except Exception as e:
            self._send_log(f"获取数据连接/站点失败：{e}")
            traceback.print_exc()

    def _find_site_for_name(self, name):
        exact = [site for site in self.site_info_list if site['name'].casefold() == str(name).casefold()]
        if len(exact) == 1:
            return exact[0]
        candidates = [site for site in self.site_info_list if self._safe_name_match(name, site['name'])]
        return candidates[0] if len(candidates) == 1 else None

    def _match_selected_files_to_sites(self, log_only=False):
        if not self.site_info_list:
            return
        for ctx in getattr(self, 'file_contexts', []):
            name = ctx['station_name']
            exact = [s for s in self.site_info_list if s['name'].casefold() == name.casefold()]
            if len(exact) == 1:
                ctx['station'] = exact[0]
                ctx['station_match_type'] = 'exact'
                continue
            candidates = [s for s in self.site_info_list if self._safe_name_match(name, s['name'])]
            if len(candidates) == 1:
                ctx['station'] = candidates[0]
                ctx['station_match_type'] = 'similar'
                if not log_only:
                    self._send_log(f"文件站点 {name} 使用相似匹配：{candidates[0]['name']}")
            else:
                ctx['station'] = None
                ctx['station_match_type'] = None
                if not log_only:
                    msg = "未匹配到站点" if not candidates else "存在多个相似站点"
                    self._send_log(f"警告：文件 {name} {msg}；可解析预览，但禁止发送和校验")

    def _send_log(self, msg):
        try:
            self.send_result_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            self.send_result_text.see(tk.END)
        except Exception:
            self._log(msg)

    def random_select_points(self):
        if not self.file_contexts or not getattr(self, '_displayed_context', None):
            self._send_log("请先选择文件并点击“解析并展示”")
            return
        try:
            ratio = max(0.0, min(1.0, int(self.random_percent.get()) / 100.0))
        except Exception:
            self._send_log("随机抽取比例无效")
            return

        if self.send_mode.get() == "全站发送":
            targets = [ctx for ctx in self.file_contexts if ctx.get('station')]
            if not targets:
                self._send_log("没有匹配数据库站点的文件，无法按全站随机抽取")
                return
        else:
            targets = [self._displayed_context]

        total_a = total_l = 0
        for ctx in targets:
            for items_key, checked_key in (("analogs", "analog_checked_ids"), ("alarms", "alarm_checked_ids")):
                count = len(ctx.get(items_key, []))
                n = max(1, int(math.floor(count * ratio + 0.5))) if count else 0
                ctx[checked_key] = set(random.sample(range(count), min(n, count))) if n else set()
            total_a += len(ctx.get('analog_checked_ids', set()))
            total_l += len(ctx.get('alarm_checked_ids', set()))

        # 将当前展示文件的抽取结果同步回表格；其他站点的勾选状态保存在各自上下文。
        current = self._displayed_context
        self.all_analog_tree._checked_ids = set(current.get('analog_checked_ids', set()))
        self.all_analog_tree._filter()
        self.all_alarm_tree._checked_ids = set(current.get('alarm_checked_ids', set()))
        self.all_alarm_tree._filter()
        self._schedule_regen()
        mode_desc = "全站" if self.send_mode.get() == "全站发送" else "当前单站"
        self._send_log(f"{mode_desc}随机抽取完成：比例 {int(ratio*100)}%，覆盖站点 {len(targets)} 个，模拟量共 {total_a} 个，告警量共 {total_l} 个。各站点独立抽取；报警/恢复由左侧处理选项统一控制。")

    def _selected_contexts_for_send(self):
        if self.send_mode.get() == "单站发送":
            if not self.selected_site:
                raise RuntimeError("请先在左侧“已选择文件 / 站点”列表中选择一个已匹配站点")
            contexts = [c for c in self.file_contexts if c.get('station') and c['station']['station_no'] == self.selected_site['station_no']]
            if not contexts:
                # 文件名与所选站点名称可精确/模糊匹配；不能把未匹配文件用于发送。
                contexts = [c for c in self.file_contexts if c['station_name'].casefold() == self.selected_site['name'].casefold()]
            if not contexts:
                raise RuntimeError("当前选中站点没有匹配的已解析文件，禁止发送")
            return contexts
        contexts = [c for c in self.file_contexts if c.get('station')]
        if not contexts:
            raise RuntimeError("没有匹配数据库站点的文件，禁止全站发送")
        return contexts

    def _generate_raw(self, ctx, kind, analog_keys, alarm_keys):
        station = ctx['station']
        if not station:
            raise RuntimeError(f"文件 {ctx['file_name']} 未匹配站点，禁止发送")
        kwargs = dict(station_index=station['station_no'], sn=1, protocol=ctx['protocol'],
                      zero_analog=self.zero_analog.get(), analog_checked_keys=analog_keys,
                      alarm_checked_keys=alarm_keys)
        if kind == 'power':
            msg = get_powerdh_code(ctx['folder'], ctx['station_name'], True, True, True,
                                   self.is_alarm.get(), self.func, **kwargs)
        else:
            msg = get_powerdh_anolog(ctx['folder'], ctx['station_name'], self.is_alarm.get(),
                                     True, True, self.func, **kwargs)
        offset = int(self.time_offset.get())
        # deal_data 的 fix_hour 采用“当前时间 - fix_hour小时”，传入负值实现明确的加减偏移。
        raw_hex, stamp = self.func.deal_data(msg, fix_hour=-offset, isformat=False, return_data_type=2)
        raw_hex = re.sub(r'[^0-9A-Fa-f]', '', raw_hex)
        if len(raw_hex) % 2:
            raw_hex = raw_hex[:-1]
        return bytes.fromhex(raw_hex), int(stamp), self.func.data_format(raw_hex)

    def start_send(self):
        self._save_current_file_checks()
        if self._send_running:
            self._send_log("发送任务已经在运行")
            return
        try:
            contexts = self._selected_contexts_for_send()
            if not self.site_info_list:
                raise RuntimeError("请先点击“获取数据连接并更新左侧站点”")
            # 发送前确认所选点位范围；空选择在发送场景下代表没有选中点位，不扩展为全量。
            self._send_running = True
            self._last_sent.clear()
            self._send_stop.clear()
            self._send_thread = threading.Thread(target=self._send_loop_once_or_repeat, args=(contexts,), daemon=True)
            self._send_thread.start()
            self._send_log(f"发送线程已启动，站点数 {len(contexts)}")
        except Exception as e:
            self._send_log(str(e))

    def _send_loop_once_or_repeat(self, contexts):
        try:
            while not self._send_stop.is_set():
                for ctx in contexts:
                    if self._send_stop.is_set():
                        break
                    station = ctx['station']
                    if not station or not station.get('ip'):
                        self._send_log(f"站点 {ctx['station_name']} 缺少源 IP，跳过")
                        continue
                    analog_keys, alarm_keys = self._build_checked_keys_for_context(ctx)
                    sock = None
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        sock.bind((station['ip'], 10000))
                        target = (self.db_host.get().strip(), int(self.target_port.get()))
                        sent_stamps = []
                        for kind in ('power', 'ups'):
                            packet, stamp, formatted = self._generate_raw(ctx, kind, analog_keys, alarm_keys)
                            sock.sendto(packet, target)
                            sent_stamps.append(stamp)
                            self._send_log(f"已发送 {ctx['station_name']} {kind} 报文，源 {station['ip']}:10000 -> 目标 {target[0]}:{target[1]}，时间戳 {stamp}，长度 {len(packet)} 字节")
                        self._last_sent = [x for x in self._last_sent if x['context']['station_name'] != ctx['station_name']] + [{'context': ctx, 'timestamps': sent_stamps, 'analog_keys': set(analog_keys), 'alarm_keys': set(alarm_keys)}]
                        self._sent_point_names['analog'] = [ctx['analogs'][i][2] for i in ctx.get('analog_checked_ids', set()) if 0 <= i < len(ctx.get('analogs', []))]
                        self._sent_point_names['alarm'] = [ctx['alarms'][i][2] for i in ctx.get('alarm_checked_ids', set()) if 0 <= i < len(ctx.get('alarms', []))]
                    except Exception as e:
                        self._send_log(f"站点 {ctx['station_name']} 发送失败：{e}")
                    finally:
                        if sock:
                            sock.close()
                # 沿用 DH_TTK 的循环发送方式；设置为 0 或负数时只发送一轮。
                interval = float(self.send_interval.get())
                if interval <= 0 or self._send_stop.wait(interval):
                    break
        finally:
            self._send_running = False
            self._send_log("发送任务结束")

    def stop_send(self):
        self._send_stop.set()
        self._send_running = False
        self._send_log("已请求停止发送")

    def validate_sent_points(self):
        if not self._last_sent:
            self._send_log("没有本次发送记录，请先发送报文")
            return
        analog_results, alarm_results = [], []
        try:
            conn = self._db_connect()
            try:
                for sent in self._last_sent:
                    ctx = sent['context']; site = ctx.get('station')
                    if not site:
                        continue
                    station_no = site['station_no']
                    analog_keys = list(sent['analog_keys'])
                    alarm_keys = list(sent['alarm_keys'])
                    # 同一站点按报文来源分组查询，避免每个点位都重复访问数据库。
                    analog_rows_by_stamp = {}
                    for key in analog_keys:
                        source_name, point_name = key.split('|', 1)
                        stamp_index = 1 if source_name.startswith(('UPS-', 'BAT-')) else 0
                        stamp = sent['timestamps'][stamp_index] if len(sent['timestamps']) > stamp_index else int(time.time())
                        if stamp not in analog_rows_by_stamp:
                            with conn.cursor() as cur:
                                cur.execute("""SELECT b.DEVICE_NAME,b.STATION_NO,c.STATION_NAME
                                    FROM ftp_db.t_mq_powerquantity_currentvalue a
                                    LEFT JOIN base.dic_device b ON a.DeviceNo=b.device_no
                                    LEFT JOIN base.dic_station c ON b.STATION_NO=c.STATION_NO
                                    WHERE b.STATION_NO=%s AND a.Stamp BETWEEN %s AND %s""",
                                    (station_no, stamp - 5, stamp + 5))
                                analog_rows_by_stamp[stamp] = cur.fetchall()
                        analog_results.append(self._match_validation_row(point_name, site, analog_rows_by_stamp[stamp], '模拟量'))
                    alarm_rows = None
                    if alarm_keys:
                        with conn.cursor() as cur:
                            cur.execute("""SELECT DEVICE_NAME,STATION_NO,STATION_NAME
                                FROM base.alarm_history
                                WHERE sys_no=6 AND STATION_NO=%s AND RECOVER_TIME IS NULL""", (station_no,))
                            alarm_rows = cur.fetchall()
                    for key in alarm_keys:
                        point_name = key.split('|', 1)[-1]
                        alarm_results.append(self._match_validation_row(point_name, site, alarm_rows or [], '告警量'))
            finally:
                conn.close()
            self._show_validation_results(analog_results, alarm_results)
        except Exception as e:
            self._send_log(f"数据库校验异常：{e}")
            traceback.print_exc()

    def _match_validation_row(self, point_name, site, rows, kind):
        exact = next((r for r in rows if str(r.get('DEVICE_NAME') or '').strip().casefold() == point_name.casefold()), None)
        if exact:
            return {'point': point_name, 'db_name': exact.get('DEVICE_NAME'), 'station': exact.get('STATION_NAME') or site['name'], 'status': '通过'}
        similar = [r for r in rows if self._safe_name_match(point_name, r.get('DEVICE_NAME'))]
        if similar:
            best = max(similar, key=lambda r: self._name_similarity(point_name, r.get('DEVICE_NAME')))
            return {'point': point_name, 'db_name': best.get('DEVICE_NAME'), 'station': best.get('STATION_NAME') or site['name'], 'status': '通过（相似）'}
        return {'point': point_name, 'db_name': '未找到', 'station': site['name'], 'status': '失败：数据库未找到'}

    def _show_validation_results(self, analog_rows, alarm_rows):
        """在同一个窗口中用 Notebook 分页展示模拟量、告警量校验结果。"""
        win = tk.Toplevel(self.root)
        self.apply_window_icon(win)
        win.title("报文点位校验结果")
        win.geometry("1120x680")
        win.minsize(850, 480)

        notebook = ttk.Notebook(win)
        notebook.pack(fill=BOTH, expand=True, padx=8, pady=8)

        def build_page(tab_title, rows):
            page = ttk.Frame(notebook)
            notebook.add(page, text=tab_title)

            filter_frame = ttk.Frame(page)
            filter_frame.pack(fill=X, padx=8, pady=(8, 4))
            ttk.Label(filter_frame, text="站点：").pack(side=LEFT)
            station_var = tk.StringVar(value="全部站点")
            station_values = ["全部站点"] + sorted({str(r.get('station') or '') for r in rows if r.get('station')})
            station_box = ttk.Combobox(filter_frame, textvariable=station_var,
                                       values=station_values, state="readonly", width=24)
            station_box.pack(side=LEFT, padx=(0, 12))

            ttk.Label(filter_frame, text="结果：").pack(side=LEFT)
            result_var = tk.StringVar(value="全部结果")
            result_values = ["全部结果", "通过", "通过（相似）", "失败"]
            result_box = ttk.Combobox(filter_frame, textvariable=result_var,
                                      values=result_values, state="readonly", width=16)
            result_box.pack(side=LEFT, padx=(0, 12))

            ttk.Label(filter_frame, text="点位搜索：").pack(side=LEFT)
            search_var = tk.StringVar()
            search_entry = ttk.Entry(filter_frame, textvariable=search_var, width=24)
            search_entry.pack(side=LEFT, padx=(0, 8))
            reset_btn = ttk.Button(filter_frame, text="重置筛选")
            reset_btn.pack(side=LEFT)

            table_frame = ttk.Frame(page)
            table_frame.pack(fill=BOTH, expand=True, padx=8, pady=4)
            cols = ('点表点位名称', '数据库设备名称', '站点', '结果')
            tree = ttk.Treeview(table_frame, columns=cols, show='headings')
            widths = (340, 340, 190, 150)
            for col, width in zip(cols, widths):
                tree.heading(col, text=col)
                tree.column(col, width=width, minwidth=100, anchor=W, stretch=True)
            ybar = ttk.Scrollbar(table_frame, orient=VERTICAL, command=tree.yview)
            xbar = ttk.Scrollbar(table_frame, orient=HORIZONTAL, command=tree.xview)
            tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
            tree.grid(row=0, column=0, sticky='nsew')
            ybar.grid(row=0, column=1, sticky='ns')
            xbar.grid(row=1, column=0, sticky='ew')
            table_frame.rowconfigure(0, weight=1)
            table_frame.columnconfigure(0, weight=1)

            summary = ttk.Label(page, anchor=W)
            summary.pack(fill=X, padx=10, pady=(2, 8))

            def refresh(*_):
                selected_station = station_var.get()
                selected_result = result_var.get()
                keyword = search_var.get().strip().casefold()
                filtered = []
                for row in rows:
                    status = str(row.get('status') or '')
                    if selected_station != '全部站点' and row.get('station') != selected_station:
                        continue
                    if selected_result == '通过' and status != '通过':
                        continue
                    if selected_result == '通过（相似）' and status != '通过（相似）':
                        continue
                    if selected_result == '失败' and '失败' not in status:
                        continue
                    if keyword and keyword not in (str(row.get('point') or '') + ' ' + str(row.get('db_name') or '')).casefold():
                        continue
                    filtered.append(row)
                tree.delete(*tree.get_children())
                for row in filtered:
                    tree.insert('', 'end', values=(row.get('point', ''), row.get('db_name', ''),
                                                   row.get('station', ''), row.get('status', '')))
                passed = sum('通过' in str(r.get('status', '')) for r in filtered)
                failed = sum('失败' in str(r.get('status', '')) for r in filtered)
                summary.config(text=f"当前显示 {len(filtered)} / {len(rows)} 个点位；通过 {passed} 个；失败 {failed} 个")

            station_box.bind('<<ComboboxSelected>>', refresh)
            result_box.bind('<<ComboboxSelected>>', refresh)
            search_var.trace_add('write', refresh)
            reset_btn.config(command=lambda: (station_var.set('全部站点'), result_var.set('全部结果'), search_var.set('')))
            refresh()
            return page

        build_page("模拟量校验", analog_rows)
        build_page("报警校验", alarm_rows)

        bottom = ttk.Frame(win)
        bottom.pack(fill=X, padx=8, pady=(0, 8))
        ttk.Label(bottom, text=f"模拟量 {len(analog_rows)} 条；报警 {len(alarm_rows)} 条").pack(side=LEFT)
        ttk.Button(bottom, text="关闭", command=win.destroy).pack(side=RIGHT)

    # -------------------- 关闭 --------------------
    def on_close(self):
        self.stop_send()
        if self._regen_after_id:
            try:
                self.root.after_cancel(self._regen_after_id)
            except Exception:
                pass
        if self.after_id:
            self.root.after_cancel(self.after_id)
        sys.stdout = self.original_stdout
        self.root.destroy()


def main():
    try:
        root = tk.Tk()
        style = ttk.Style(root)
        style.theme_use('classic')
        app = PointTableApp(root)
        root.protocol("WM_DELETE_WINDOW", app.on_close)
        root.mainloop()
    except Exception:
        with open("error.log", "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        try:
            import tkinter.messagebox as msgbox
            msgbox.showerror("程序启动失败", "请查看 error.log 获取详细信息")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()