import os
import re
import math
import time
import random
import socket
import struct
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, scrolledtext
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
import chardet

try:
    import pymysql
    PYMYSQL_AVAILABLE = True
except ImportError:
    pymysql = None
    PYMYSQL_AVAILABLE = False


class PublicFunc:
    """工具类：报文生成与发送"""

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

    def deal_data(self, data, fix_hour=0, israndomtime=False, isformat=True, time_type=1, return_data_type=1):
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
                             self.fix_str(time_hour) + self.fix_str(time_min) + self.fix_str(time_second)]

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
        with open(file_path, 'rb') as f:
            return chardet.detect(f.read(512))['encoding']

    def get_text_data(self, dir_path, file_name, return_type=1):
        deal_files = []
        result = []
        for f in os.listdir(dir_path):
            if file_name in f:
                deal_files.append(f)
        deal_files.sort()

        for file in deal_files:
            file_path = os.path.join(dir_path, file)
            try:
                with open(file_path, 'r', encoding='GB2312') as f1:
                    for line in f1:
                        line = line.rstrip('\n').rstrip('\r')
                        if line.strip():
                            result.append(line)
            except UnicodeDecodeError:
                try:
                    with open(file_path, 'r', encoding='GBK') as f1:
                        for line in f1:
                            line = line.rstrip('\n').rstrip('\r')
                            if line.strip():
                                result.append(line)
                except Exception as e:
                    print(f"读取文件{file}失败: {e}")
        return result

    def send_to_mss(self, src_ip, dst_ip, dst_port, data, timeout=0.1, hour=0, time_type=1, src_port=10000,
                    show_rec=False, is_hex_data=True):
        """
        发送UDP数据
        :param is_hex_data: 若为True，则data是待处理的十六进制文本（包含注释、占位符），需调用deal_data处理；
                            若为False，则data是普通字符串，直接编码发送。
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)

        if is_hex_data:
            fmt_data = self.deal_data(data, hour, time_type=time_type, isformat=False).upper()
            fmt_data = re.sub(r'[^0-9A-F]', '', fmt_data)
            if len(fmt_data) % 2 != 0:
                fmt_data += '0'
            post_data = bytes.fromhex(fmt_data)
        else:
            post_data = data.encode('utf-8')

        sock.bind((src_ip, src_port))
        sock.sendto(post_data, (dst_ip, dst_port))

        rec_data = ''
        client_addr = ''
        if show_rec:
            try:
                rec_data, client_addr = sock.recvfrom(10240)
                rec_data = self.data_format(rec_data.hex())
            except Exception:
                rec_data = '无返回数据'
        sock.close()
        return client_addr, rec_data


# ------------------------- 公共工具函数 -------------------------
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
    for i, line in enumerate(lines):
        line_clean = re.sub(r'[-*=]+', '', line).strip().upper()
        if keyword.upper() in line_clean:
            return i
    return -1


# ------------------------- 电源屏报文生成 -------------------------
def get_analog_value_int(analog_name):
    min_val = 0
    max_val = 500
    return random.randint(min_val * 100, max_val * 100)


def get_analog_code(analog_data, is_use_analog, func, data_type=1, ex_info=''):
    count = len(analog_data)
    count_hex = func.int_to_hex(count, 4)
    type_name = {1: '输入', 2: '输出'}.get(data_type, '模块输出')

    value_str = ''
    for i in range(count):
        name = analog_data[i]
        if '电压' in name:
            val_int = get_analog_value_int(name)
        else:
            val_int = random.randint(0, 4000)

        value_str += func.int_to_hex(val_int, 4) + ' '
        if i != 0 and (i + 1) % 10 == 0:
            value_str += '\n'

        if is_use_analog and '电流' not in name:
            print(f'{ex_info}{type_name}模拟量:{count}个, 设备 {name}, 值:{val_int / 100:.2f}')

    code = f'{count_hex} #{type_name}模拟量个数 {count}个#\n{value_str}'
    return code.replace(' ', '').strip('\n')


def get_state_code(state_data, is_use_state, func, ex_info=''):
    count = len(state_data)
    count_hex = func.int_to_hex(count, 4)
    status_map = {0: '断开', 1: '闭合'}
    value_str = ''

    for i in range(count):
        name = state_data[i]
        idx = random.randint(0, 1)
        value_str += f'0{idx} '
        if is_use_state:
            print(f'{ex_info}开关状态量:{count}个, 设备 {name}, 值:{status_map[idx]}')

    code = f'{count_hex} #开关状态量个数 {count}个#\n{value_str}'
    return code.replace(' ', '').strip('\n')


def get_alarm_code(alarm_data, is_use_alarm, is_alarm, func, data_type=1, ex_info='', protocol='DH2'):
    count = len(alarm_data)
    count_hex = func.int_to_hex(count, 4)
    type_name = '输入输出' if data_type == 1 else '模块'

    if protocol == 'DH1':
        value_str = pack_alarms_to_hex(count, is_alarm)
    else:
        byte_num = math.ceil(count / 8)
        value_str = ''
        for _ in range(byte_num):
            value_str += 'FF ' if is_alarm else '00 '
        value_str = value_str.strip()

    if is_use_alarm:
        status = '告警' if is_alarm else '正常'
        for name in alarm_data:
            print(f'{ex_info}{type_name}告警:{count}个, 设备 {name}, 值:{status}')

    code = f'{count_hex} #{type_name}告警个数 {count}个#\n{value_str}'
    return code.replace(' ', '').strip('\n')


def get_module_code(module_data, name_code_map, is_use_analog, is_use_state, is_use_alarm, is_alarm, func,
                    protocol='DH2'):
    type_count = 0
    module_data_dict = {}
    module_names = []
    current_name = ''
    current_count = 0
    flags = {'analog': False, 'state': False, 'alarm': False}

    for line in module_data:
        line_strip = line.strip()

        if 'PWR_MODULE_TYPE_NUM' in line_strip:
            try:
                type_count = int(line_strip.split('=')[1])
            except:
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
            except Exception as e:
                print(f"警告：模块行[{line_strip}]解析失败: {e}")
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
        analog_part = info['analog']
        state_part = info['state']
        alarm_part = info['alarm']

        value_code = ''
        for i in range(count):
            ex = f'模块：{name} {count}-{i + 1} '
            idx_hex = func.int_to_hex(i + 1)
            a_code = get_analog_code(analog_part, is_use_analog, func, 3, ex)
            s_code = get_state_code(state_part, is_use_state, func, ex)
            al_code = get_alarm_code(alarm_part, is_use_alarm, is_alarm, func, 2, ex, protocol)
            block = f'{idx_hex} #模块{name}序号{idx}-{i + 1}#\n{a_code}\n{s_code}\n{al_code}'
            value_code += '\n' + block.replace(' ', '').strip('\n')

        part_code = f'{m_code} #类型{idx}的模块{name}类型码#\n{func.int_to_hex(count)} #类型{idx}的模块数量{count}#\n{value_code}'
        all_code += '\n' + part_code.replace(' ', '').strip('\n')

    return all_code


def get_powerdh_code(file_path, file_name, is_use_analog, is_use_state, is_use_alarm, is_alarm, func,
                     station_index=1, sn=1, protocol='DH2'):
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
        print("警告：未读取到点表数据，返回空电源屏报文")
        return '''
            aa #帧开始标志#
            (0000) #帧长度#
            {30 #Message Type#
            [00000000] #时间戳#
            01 #站点编号#
            00000001 #报文序列号#
            0000 #输入模拟量个数#
            0000 #状态量个数#
            0000 #告警量个数#
            0000 #输出模拟量个数#
            00 #模块类型总数#
            55 #结束标识#
            00000000 #CRC校验#}
        '''

    ups_section_idx = find_section_index(files_data, 'UPS&BAT_Info')
    if ups_section_idx == -1:
        ups_section_idx = len(files_data)
    power_data = files_data[:ups_section_idx]

    input_analog_idx = find_section_index(power_data, 'PMS_INPUT_ANALOG')
    state_idx = find_section_index(power_data, 'PMS_SWITCH_STATE')
    alarm_idx = find_section_index(power_data, 'PMS_INPUT_ALARM')
    if alarm_idx == -1:
        alarm_idx = find_section_index(power_data, 'PMS_ALARM')

    out_term_idx = find_section_index(power_data, 'PMS_输出端子表')
    output_analog_idx = find_section_index(power_data, 'PMS_OUTPUT_ANALOG')
    module_info_idx = find_section_index(power_data, 'PMS_Module_Info')

    def extract_points(start_idx, end_idx):
        if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
            return []
        points = []
        for line in power_data[start_idx + 1:end_idx]:
            name = clean_point_name(line)
            if name and name != '未命名点位':
                points.append(name)
        return points

    input_analog = extract_points(input_analog_idx, state_idx)
    state_data = extract_points(state_idx, alarm_idx)
    alarm_data = extract_points(alarm_idx, out_term_idx)
    output_analog = extract_points(output_analog_idx, module_info_idx)
    module_data = power_data[module_info_idx + 1:ups_section_idx] if module_info_idx != -1 else []

    print(
        f"\n电源屏解析结果：输入模拟量{len(input_analog)}个，状态量{len(state_data)}个，告警量{len(alarm_data)}个，输出模拟量{len(output_analog)}个")

    input_code = get_analog_code(input_analog, is_use_analog, func, 1)
    state_code = get_state_code(state_data, is_use_state, func)
    alarm_code = get_alarm_code(alarm_data, is_use_alarm, is_alarm, func, 1, '', protocol)
    output_code = get_analog_code(output_analog, is_use_analog, func, 2)
    module_code = get_module_code(module_data, module_name_code, is_use_analog, is_use_state, is_use_alarm, is_alarm,
                                  func, protocol)

    send_data = f'''
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
    return send_data


# ------------------------- UPS报文生成 -------------------------
def build_ups_block(module_data_list, ups_name, is_alarm, is_use_alarm, is_use_analog, func, protocol='DH2'):
    analog_idx = None
    alarm_idx = None

    for i, line in enumerate(module_data_list):
        line_clean = re.sub(r'[-]+', '', line).strip()
        if line_clean == '模拟量':
            analog_idx = i
        if line_clean == '告警量':
            alarm_idx = i

    if analog_idx is None or alarm_idx is None:
        print(f"警告：UPS[{ups_name}] 未找到模拟量/告警量标题，跳过")
        return ''

    if analog_idx >= alarm_idx:
        print(f"警告：UPS[{ups_name}] 模拟量与告警量顺序颠倒，跳过")
        return ''

    analog_points = [clean_point_name(line) for line in module_data_list[analog_idx + 1:alarm_idx] if line.strip()]
    alarm_points = [clean_point_name(line) for line in module_data_list[alarm_idx + 1:] if line.strip()]

    analog_num = len(analog_points)
    alarm_num = len(alarm_points)

    if analog_num > 100 or analog_num < 0:
        print(f"警告：UPS[{ups_name}] 模拟量数量{analog_num}异常，强制设为0")
        analog_num = 0
        analog_points = []
    if alarm_num > 200 or alarm_num < 0:
        print(f"警告：UPS[{ups_name}] 告警量数量{alarm_num}异常，强制设为0")
        alarm_num = 0
        alarm_points = []

    print(f"解析UPS[{ups_name}]：模拟量{analog_num}个，告警量{alarm_num}个")

    code = ''
    code += func.int_to_hex(analog_num, 4) + '\n'
    for j in range(analog_num):
        name = analog_points[j]
        if '电压' in name:
            val = round(random.uniform(200, 400), 2)
        elif '电流' in name:
            val = round(random.uniform(0, 50), 2)
        elif '频率' in name:
            val = round(random.uniform(49, 51), 2)
        elif '功率' in name:
            val = round(random.uniform(0, 100), 2)
        elif '容量' in name:
            val = round(random.uniform(0, 100), 2)
        else:
            val = round(random.uniform(0, 500), 2)

        hex_val = func.str_reverse(func.float_to_hex(val))
        code += hex_val + ' '
        if is_use_analog:
            print(f'  模拟量: {name} = {val}')

    code += '\n' + func.int_to_hex(alarm_num, 4) + '\n'
    if protocol == 'DH1':
        alarm_hex = pack_alarms_to_hex(alarm_num, is_alarm)
        code += alarm_hex
    else:
        byte_count = math.ceil(alarm_num / 8)
        for _ in range(byte_count):
            code += 'FF ' if is_alarm else '00 '
        code = code.strip()

    if is_use_alarm:
        status = '告警' if is_alarm else '正常'
        for name in alarm_points:
            print(f'  告警: {name} = {status}')

    return code


def get_powerdh_anolog(file_path, file_name, is_alarm, is_use_alarm, is_use_analog, func,
                       station_index=1, sn=1, protocol='DH2'):
    files = func.get_text_data(file_path, file_name)
    if not files:
        print("警告：未读取到点表数据，返回空UPS报文")
        return '''
            AA #帧开始标志#
            (0000) #帧长度#
            <
            33 #消息类型#
            [00000000] #时间戳#
            01 #站点编号#
            00000001 #序列号#
            00 #UPS数量#
            55 #帧结束标志#
            00000000 #CRC校验#
            >
        '''

    ups_section_start = find_section_index(files, 'UPS&BAT_Info')
    if ups_section_start == -1:
        print("警告：未找到UPS分区")
        send_data = f'''
            AA #帧开始标志#
            (0000) #帧长度#
            <
            33 #消息类型#
            [00000000] #时间戳#
            {func.int_to_hex(station_index, 2)} #站点编号#
            {func.int_to_hex(sn, 8)} #序列号#
            {func.int_to_hex(0, 2)} #UPS数量#
            55 #帧结束标志#
            00000000 #CRC校验#
            >
        '''
        return send_data

    ups_section = files[ups_section_start + 1:]
    ups_start_lines = []
    for i, line in enumerate(ups_section):
        if '[' in line and ']' in line and 'UPS' in line.upper():
            ups_start_lines.append((i, line))

    if not ups_start_lines:
        print("警告：未识别到任何UPS设备")
        send_data = f'''
            AA #帧开始标志#
            (0000) #帧长度#
            <
            33 #消息类型#
            [00000000] #时间戳#
            {func.int_to_hex(station_index, 2)} #站点编号#
            {func.int_to_hex(sn, 8)} #序列号#
            {func.int_to_hex(0, 2)} #UPS数量#
            55 #帧结束标志#
            00000000 #CRC校验#
            >
        '''
        return send_data

    ups_len = len(ups_start_lines)
    print(f"\n共识别到 {ups_len} 台UPS设备")
    ups_code = ''

    for i in range(ups_len):
        start_idx, start_line = ups_start_lines[i]
        end_idx = ups_start_lines[i + 1][0] if i < ups_len - 1 else len(ups_section)
        single_data = ups_section[start_idx:end_idx]

        try:
            name = start_line.split('[')[1].split(']')[0]
        except IndexError:
            print(f"警告：UPS行[{start_line}]格式错误，跳过")
            continue

        ups_code += f'{func.int_to_hex(i + 1, 2)} #UPS{i + 1}序号#\n'
        ups_code += build_ups_block(single_data, name, is_alarm, is_use_alarm, is_use_analog, func, protocol)
        ups_code += '\n'

    send_data = f'''
        AA #帧开始标志#
        (0000) #帧长度#
        <
        33 #消息类型#
        [00000000] #时间戳#
        {func.int_to_hex(station_index, 2)} #站点编号#
        {func.int_to_hex(sn, 8)} #序列号#
        {func.int_to_hex(ups_len, 2)} #UPS数量#
        {ups_code}
        55 #帧结束标志#
        00000000 #CRC校验#
        >
    '''
    return send_data


# ------------------------- GUI界面 -------------------------
class PowerDHApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PowerDH 报文模拟工具")
        self.root.geometry("1000x800")

        self.func = PublicFunc()
        self.running = False
        self.stop_event = threading.Event()
        self.send_thread = None
        self.send_threads = []

        self.sn_station = 1
        self.sn_ups = 1

        self.folder_path = tk.StringVar()
        self.selected_station = tk.StringVar()
        self.station_idx = tk.IntVar(value=1)
        self.use_ups = tk.BooleanVar(value=False)
        self.use_analog = tk.BooleanVar(value=True)
        self.use_state = tk.BooleanVar(value=True)
        self.use_alarm_print = tk.BooleanVar(value=True)
        self.is_alarm = tk.BooleanVar(value=True)
        self.protocol = tk.StringVar(value="DH1")
        self.src_ip = tk.StringVar(value="192.168.2.131")
        self.dst_ip = tk.StringVar(value="192.168.1.134")
        self.dst_port = tk.IntVar(value=10030)
        self.interval = tk.DoubleVar(value=3.0)

        # 多站点相关变量
        self.use_multi_site = tk.BooleanVar(value=False)
        self.db_host = tk.StringVar(value="127.0.0.1")
        self.db_port = tk.IntVar(value=3306)
        self.db_user = tk.StringVar(value="root")
        self.db_pass = tk.StringVar(value="mysql")
        self.db_name = tk.StringVar(value="base")
        self.site_info_list = []
        self.site_vars = []
        self.log_lock = threading.Lock()

        self._build_ui()

    def _build_ui(self):
        main_container = ttkb.Frame(self.root)
        main_container.pack(fill=BOTH, expand=True, padx=5, pady=5)

        left_panel = ttkb.Frame(main_container, width=320)
        left_panel.pack(side=LEFT, fill=Y, padx=(0, 5))
        left_panel.pack_propagate(False)

        frame_folder = ttkb.LabelFrame(left_panel, text="站点文件夹")
        frame_folder.pack(fill=X, pady=(0, 5))
        inner_folder = ttkb.Frame(frame_folder, padding=8)
        inner_folder.pack(fill=BOTH, expand=True)
        ttkb.Entry(inner_folder, textvariable=self.folder_path).pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        ttkb.Button(inner_folder, text="浏览", command=self.select_folder, bootstyle=PRIMARY).pack(side=RIGHT)

        chk_multi = ttkb.Checkbutton(left_panel, text="启用多站点发送（数据库）", variable=self.use_multi_site,
                                     bootstyle="round-toggle", command=self._toggle_multi_site)
        chk_multi.pack(fill=X, pady=(0, 5))

        self.frame_single = ttkb.LabelFrame(left_panel, text="单站点选择")
        self.frame_single.pack(fill=BOTH, expand=True)
        inner_single = ttkb.Frame(self.frame_single, padding=8)
        inner_single.pack(fill=BOTH, expand=True)

        single_list_frame = ttkb.Frame(inner_single)
        single_list_frame.pack(fill=BOTH, expand=True)
        single_scrollbar = ttkb.Scrollbar(single_list_frame, orient="vertical")
        self.station_list = tk.Listbox(single_list_frame, height=8, yscrollcommand=single_scrollbar.set)
        single_scrollbar.config(command=self.station_list.yview)
        self.station_list.pack(side=LEFT, fill=BOTH, expand=True)
        single_scrollbar.pack(side=RIGHT, fill=Y)
        self.station_list.bind("<<ListboxSelect>>", self._on_station_select)

        self.frame_multi = ttkb.Frame(left_panel)

        frame_db = ttkb.LabelFrame(self.frame_multi, text="数据库配置")
        frame_db.pack(fill=X, pady=(0, 5))
        inner_db = ttkb.Frame(frame_db, padding=8)
        inner_db.pack(fill=BOTH, expand=True)

        row_db1 = ttkb.Frame(inner_db)
        row_db1.pack(fill=X, pady=2)
        ttkb.Label(row_db1, text="主机:", width=6).pack(side=LEFT)
        ttkb.Entry(row_db1, textvariable=self.db_host, width=12).pack(side=LEFT, padx=2)
        ttkb.Label(row_db1, text="端口:", width=6).pack(side=LEFT, padx=(8, 0))
        ttkb.Entry(row_db1, textvariable=self.db_port, width=6).pack(side=LEFT, padx=2)

        row_db2 = ttkb.Frame(inner_db)
        row_db2.pack(fill=X, pady=2)
        ttkb.Label(row_db2, text="用户名:", width=6).pack(side=LEFT)
        ttkb.Entry(row_db2, textvariable=self.db_user, width=12).pack(side=LEFT, padx=2)
        ttkb.Label(row_db2, text="密码:", width=6).pack(side=LEFT, padx=(8, 0))
        ttkb.Entry(row_db2, textvariable=self.db_pass, width=12, show="*").pack(side=LEFT, padx=2)

        row_db3 = ttkb.Frame(inner_db)
        row_db3.pack(fill=X, pady=2)
        ttkb.Label(row_db3, text="数据库:", width=6).pack(side=LEFT)
        ttkb.Entry(row_db3, textvariable=self.db_name, width=12).pack(side=LEFT, padx=2)
        ttkb.Button(row_db3, text="连接并获取站点", command=self.fetch_sites_from_db, bootstyle=INFO).pack(side=LEFT,
                                                                                                        padx=10)

        frame_sites = ttkb.LabelFrame(self.frame_multi, text="选择站点（可多选）")
        frame_sites.pack(fill=BOTH, expand=True)
        inner_sites = ttkb.Frame(frame_sites, padding=5)
        inner_sites.pack(fill=BOTH, expand=True)

        canvas_sites = tk.Canvas(inner_sites, highlightthickness=0)
        scrollbar_sites = ttkb.Scrollbar(inner_sites, orient="vertical", command=canvas_sites.yview)
        self.scrollable_frame_sites = ttkb.Frame(canvas_sites)
        self.scrollable_frame_sites.bind("<Configure>",
                                         lambda e: canvas_sites.configure(scrollregion=canvas_sites.bbox("all")))
        canvas_sites.create_window((0, 0), window=self.scrollable_frame_sites, anchor="nw")
        canvas_sites.configure(yscrollcommand=scrollbar_sites.set)
        canvas_sites.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar_sites.pack(side=RIGHT, fill=Y)

        self.frame_multi.pack_forget()

        right_panel = ttkb.Frame(main_container)
        right_panel.pack(side=LEFT, fill=BOTH, expand=True)

        frame_opt = ttkb.LabelFrame(right_panel, text="功能配置")
        frame_opt.pack(fill=X, pady=(0, 5))
        inner_opt = ttkb.Frame(frame_opt, padding=8)
        inner_opt.pack(fill=BOTH, expand=True)

        row1 = ttkb.Frame(inner_opt)
        row1.pack(fill=X, pady=3)
        ttkb.Checkbutton(row1, text="启用UPS模式(分开发送)", variable=self.use_ups, bootstyle="round-toggle").pack(
            side=LEFT, padx=5)
        ttkb.Checkbutton(row1, text="模拟量打印", variable=self.use_analog, bootstyle="round-toggle").pack(side=LEFT,
                                                                                                           padx=5)
        ttkb.Checkbutton(row1, text="状态量打印", variable=self.use_state, bootstyle="round-toggle").pack(side=LEFT,
                                                                                                          padx=5)
        ttkb.Checkbutton(row1, text="报警打印", variable=self.use_alarm_print, bootstyle="round-toggle").pack(side=LEFT,
                                                                                                              padx=5)

        row2 = ttkb.Frame(inner_opt)
        row2.pack(fill=X, pady=3)
        ttkb.Label(row2, text="报警状态:").pack(side=LEFT, padx=5)
        ttkb.Radiobutton(row2, text="报警", variable=self.is_alarm, value=True, bootstyle="toolbutton").pack(side=LEFT,
                                                                                                             padx=2)
        ttkb.Radiobutton(row2, text="恢复", variable=self.is_alarm, value=False, bootstyle="toolbutton").pack(side=LEFT,
                                                                                                              padx=2)

        row3 = ttkb.Frame(inner_opt)
        row3.pack(fill=X, pady=3)
        ttkb.Label(row3, text="协议版本:").pack(side=LEFT, padx=5)
        ttkb.Radiobutton(row3, text="DH1", variable=self.protocol, value="DH1", bootstyle="toolbutton").pack(side=LEFT,
                                                                                                             padx=2)
        ttkb.Radiobutton(row3, text="DH2", variable=self.protocol, value="DH2", bootstyle="toolbutton").pack(side=LEFT,
                                                                                                             padx=2)

        frame_net = ttkb.LabelFrame(right_panel, text="网络配置")
        frame_net.pack(fill=X, pady=(0, 5))
        inner_net = ttkb.Frame(frame_net, padding=8)
        inner_net.pack(fill=BOTH, expand=True)

        net_row1 = ttkb.Frame(inner_net)
        net_row1.pack(fill=X, pady=2)
        ttkb.Label(net_row1, text="本机IP:", width=9).pack(side=LEFT)
        ttkb.Entry(net_row1, textvariable=self.src_ip, width=18).pack(side=LEFT, padx=5)
        ttkb.Label(net_row1, text="目标IP:", width=9).pack(side=LEFT, padx=(10, 0))
        ttkb.Entry(net_row1, textvariable=self.dst_ip, width=18).pack(side=LEFT, padx=5)

        net_row2 = ttkb.Frame(inner_net)
        net_row2.pack(fill=X, pady=2)
        ttkb.Label(net_row2, text="目标端口:", width=9).pack(side=LEFT)
        ttkb.Entry(net_row2, textvariable=self.dst_port, width=10).pack(side=LEFT, padx=5)
        ttkb.Label(net_row2, text="站点编号:", width=9).pack(side=LEFT, padx=(10, 0))
        ttkb.Entry(net_row2, textvariable=self.station_idx, width=10).pack(side=LEFT, padx=5)

        net_row3 = ttkb.Frame(inner_net)
        net_row3.pack(fill=X, pady=2)
        ttkb.Label(net_row3, text="发送间隔(秒):", width=11).pack(side=LEFT)
        ttkb.Entry(net_row3, textvariable=self.interval, width=10).pack(side=LEFT, padx=5)
        ttkb.Label(net_row3, text="(文档默认3秒)", foreground="gray").pack(side=LEFT, padx=5)

        frame_ctrl = ttkb.Frame(right_panel)
        frame_ctrl.pack(fill=X, pady=(0, 5))
        self.btn_start = ttkb.Button(frame_ctrl, text="开始发送", command=self.start_send, bootstyle=SUCCESS)
        self.btn_start.pack(side=LEFT, padx=5)
        self.btn_stop = ttkb.Button(frame_ctrl, text="停止发送", command=self.stop_send, bootstyle=DANGER,
                                    state=DISABLED)
        self.btn_stop.pack(side=LEFT, padx=5)
        self.btn_check = ttkb.Button(frame_ctrl, text="校验单帧报文", command=self.check_frame, bootstyle=INFO)
        self.btn_check.pack(side=LEFT, padx=5)

        frame_log = ttkb.LabelFrame(right_panel, text="运行日志")
        frame_log.pack(fill=BOTH, expand=True)
        inner_log = ttkb.Frame(frame_log, padding=8)
        inner_log.pack(fill=BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(inner_log, height=16, font=("Consolas", 9))
        self.log_text.pack(fill=BOTH, expand=True)

    def select_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.folder_path.set(path)
            self._load_stations(path)

    def _load_stations(self, folder):
        self.station_list.delete(0, tk.END)
        try:
            files = [f for f in os.listdir(folder) if f.lower().endswith('.txt')]
            for f in files:
                self.station_list.insert(tk.END, f)
            self._log(f"已加载 {len(files)} 个站点文件")
        except Exception as e:
            self._log(f"加载文件夹失败: {str(e)}")

    def _on_station_select(self, _):
        sel = self.station_list.curselection()
        if sel:
            file = self.station_list.get(sel[0])
            self.selected_station.set(file)
            self._log(f"已选择站点: {file}")

    def _toggle_multi_site(self):
        if self.use_multi_site.get():
            self.frame_single.pack_forget()
            self.frame_multi.pack(fill=BOTH, expand=True)
        else:
            self.frame_multi.pack_forget()
            self.frame_single.pack(fill=BOTH, expand=True)

    def fetch_sites_from_db(self):
        if not PYMYSQL_AVAILABLE:
            self._log("错误：未安装pymysql库，请先安装（pip install pymysql）")
            return

        host = self.db_host.get()
        port = self.db_port.get()
        user = self.db_user.get()
        password = self.db_pass.get()
        db = self.db_name.get()

        try:
            connection = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=db,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            with connection.cursor() as cursor:
                sql = """
                    SELECT a.IP, b.STATION_NAME, b.STATION_NO
                    FROM dic_mss_netaddress_config a
                    RIGHT JOIN dic_station b ON a.STATION_NO = b.STATION_NO
                    WHERE sys_no = 6 AND master = 1
                """
                cursor.execute(sql)
                results = cursor.fetchall()
            connection.close()

            if not results:
                self._log("数据库查询结果为空")
                return

            self.site_info_list = []
            for row in results:
                ip = row.get('IP', '')
                name = row.get('STATION_NAME', '')
                station_no = row.get('STATION_NO', 1)
                if ip and name:
                    self.site_info_list.append({
                        'ip': ip,
                        'name': name,
                        'station_no': station_no,
                        'target_ip': host
                    })
                else:
                    self._log(f"跳过站点 {name}：IP或名称为空")

            self._log(f"数据库获取到 {len(self.site_info_list)} 个站点")
            self._populate_site_checkboxes()

        except Exception as e:
            self._log(f"数据库连接/查询失败: {str(e)}")
            traceback.print_exc()

    def _populate_site_checkboxes(self):
        for widget in self.scrollable_frame_sites.winfo_children():
            widget.destroy()
        self.site_vars = []

        for info in self.site_info_list:
            var = tk.BooleanVar(value=True)
            self.site_vars.append(var)
            text = f"{info['name']} (本机IP:{info['ip']}, 目标IP:{info['target_ip']}, 站点号:{info['station_no']})"
            cb = ttkb.Checkbutton(self.scrollable_frame_sites, text=text, variable=var, bootstyle="round-toggle")
            cb.pack(anchor=W, pady=1, fill=X)

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        with self.log_lock:
            self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
            self.log_text.see(tk.END)

    def check_frame(self):
        folder = self.folder_path.get()
        if not folder:
            self._log("请先选择文件夹！")
            return
        if self.use_multi_site.get():
            self._log("多站点模式下请使用单站点校验功能（选择单站点模式）")
            return
        station = self.selected_station.get()
        if not station:
            self._log("请先选择站点文件！")
            return

        station_name = os.path.splitext(station)[0]
        protocol = self.protocol.get()
        station_idx = self.station_idx.get()

        try:
            ups_data = get_powerdh_anolog(
                folder, station_name, self.is_alarm.get(),
                self.use_alarm_print.get(), self.use_analog.get(),
                self.func, station_index=station_idx, sn=1, protocol=protocol
            )
            fmt_data = self.func.deal_data(ups_data, isformat=False).upper()
            fmt_data = re.sub(r'[^0-9A-F]', '', fmt_data)
            if len(fmt_data) % 2 != 0:
                fmt_data += '0'
            raw = bytes.fromhex(fmt_data)

            self._log("=== UPS报文结构校验 ===")
            self._log(f"总长度: {len(raw)} 字节")
            self._log(f"帧头: 0x{raw[0]:02X} {'正确' if raw[0] == 0xAA else '错误'}")
            self._log(f"MSG_ID: 0x{raw[3]:02X} {'正确' if raw[3] == 0x33 else '错误'}")
            self._log(f"站点号: {raw[8]}")
            self._log(f"UPS数量: {raw[13]} 台")
            self._log(f"帧尾标志: 0x{raw[-5]:02X} {'正确' if raw[-5] == 0x55 else '错误(位置不对)'}")
            self._log(f"CRC长度: {len(raw[-4:])} 字节")
            self._log("========================")
        except Exception as e:
            self._log(f"校验失败: {str(e)}")
            traceback.print_exc()

    def start_send(self):
        folder = self.folder_path.get()
        if not folder:
            self._log("请先选择站点文件夹！")
            return

        self.running = True
        self.stop_event.clear()
        self.btn_start.config(state=DISABLED)
        self.btn_stop.config(state=NORMAL)

        if self.use_multi_site.get():
            selected_sites = [self.site_info_list[i] for i, var in enumerate(self.site_vars) if var.get()]
            if not selected_sites:
                self._log("未选择任何站点！")
                self.btn_start.config(state=NORMAL)
                self.btn_stop.config(state=DISABLED)
                return
            self._log(f"启动多站点发送，共 {len(selected_sites)} 个站点")
            self.send_threads = []
            for site in selected_sites:
                t = threading.Thread(target=self._send_multi_site_loop, args=(site,), daemon=True)
                t.start()
                self.send_threads.append(t)
        else:
            station = self.selected_station.get()
            if not station:
                self._log("请先在左侧选择站点文件！")
                self.btn_start.config(state=NORMAL)
                self.btn_stop.config(state=DISABLED)
                return
            self.send_thread = threading.Thread(target=self._send_loop, daemon=True)
            self.send_thread.start()
            self._log("开始发送报文...")

    def stop_send(self):
        self.running = False
        self.stop_event.set()
        self.btn_start.config(state=NORMAL)
        self.btn_stop.config(state=DISABLED)
        self._log("已停止发送")

    def _send_loop(self):
        folder = self.folder_path.get()
        station_file = self.selected_station.get()
        station_name = os.path.splitext(station_file)[0]

        use_ups = self.use_ups.get()
        use_analog = self.use_analog.get()
        use_state = self.use_state.get()
        use_alarm = self.use_alarm_print.get()
        is_alarm = self.is_alarm.get()
        protocol = self.protocol.get()

        src = self.src_ip.get()
        dst = self.dst_ip.get()
        port = self.dst_port.get()
        interval = self.interval.get()
        station_idx = self.station_idx.get()

        while not self.stop_event.is_set():
            try:
                normal_data = get_powerdh_code(
                    folder, station_name, use_analog, use_state, use_alarm, is_alarm,
                    self.func, station_index=station_idx, sn=self.sn_station, protocol=protocol
                )
                self.func.send_to_mss(src, dst, port, normal_data, timeout=0.5,
                                      src_port=10000, show_rec=False, is_hex_data=True)
                self._log(f"已发送 电源屏报文 | 协议:{protocol} | SN:{self.sn_station}")
                self.sn_station = (self.sn_station + 1) & 0xFFFFFFFF
                if self.sn_station == 0:
                    self.sn_station = 1

                if use_ups and not self.stop_event.is_set():
                    ups_data = get_powerdh_anolog(
                        folder, station_name, is_alarm, use_alarm, use_analog,
                        self.func, station_index=station_idx, sn=self.sn_ups, protocol=protocol
                    )
                    self.func.send_to_mss(src, dst, port, ups_data, timeout=0.5,
                                          src_port=10001, show_rec=False, is_hex_data=True)
                    self._log(f"已发送 UPS 报文 | 协议:{protocol} | SN:{self.sn_ups}")
                    self.sn_ups = (self.sn_ups + 1) & 0xFFFFFFFF
                    if self.sn_ups == 0:
                        self.sn_ups = 1

            except Exception as e:
                err_msg = f"发送异常: {str(e)}"
                self._log(err_msg)
                traceback.print_exc()

            self.stop_event.wait(interval)

    def _send_multi_site_loop(self, site_info):
        folder = self.folder_path.get()
        station_name = site_info['name']
        station_ip = site_info['target_ip']
        station_no = site_info['station_no']
        src = site_info['ip']

        use_ups = self.use_ups.get()
        use_analog = self.use_analog.get()
        use_state = self.use_state.get()
        use_alarm = self.use_alarm_print.get()
        is_alarm = self.is_alarm.get()
        protocol = self.protocol.get()

        port = self.dst_port.get()
        interval = self.interval.get()

        sn_station = 1
        sn_ups = 1

        while not self.stop_event.is_set():
            try:
                normal_data = get_powerdh_code(
                    folder, station_name, use_analog, use_state, use_alarm, is_alarm,
                    self.func, station_index=station_no, sn=sn_station, protocol=protocol
                )
                self.func.send_to_mss(src, station_ip, port, normal_data, timeout=0.5,
                                      src_port=0, show_rec=False, is_hex_data=True)
                self._log(f"[{station_name}] 已发送电源屏报文 SN:{sn_station}")
                sn_station = (sn_station + 1) & 0xFFFFFFFF
                if sn_station == 0:
                    sn_station = 1

                if use_ups and not self.stop_event.is_set():
                    ups_data = get_powerdh_anolog(
                        folder, station_name, is_alarm, use_alarm, use_analog,
                        self.func, station_index=station_no, sn=sn_ups, protocol=protocol
                    )
                    self.func.send_to_mss(src, station_ip, port, ups_data, timeout=0.5,
                                          src_port=0, show_rec=False, is_hex_data=True)
                    self._log(f"[{station_name}] 已发送UPS报文 SN:{sn_ups}")
                    sn_ups = (sn_ups + 1) & 0xFFFFFFFF
                    if sn_ups == 0:
                        sn_ups = 1

            except Exception as e:
                self._log(f"[{station_name}] 发送异常: {str(e)}")
                traceback.print_exc()

            self.stop_event.wait(interval)

    def on_close(self):
        self.stop_send()
        self.root.destroy()


def main():
    app = ttkb.Window(themename="yeti")
    gui = PowerDHApp(app)
    app.protocol("WM_DELETE_WINDOW", gui.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()