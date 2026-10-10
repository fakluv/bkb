import os
import re
import math
import time
import random
import socket
import struct
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
import chardet


class PublicFunc:
    """精简版工具类，仅保留报文生成与发送相关方法"""

    def deal_data(self, data, fix_hour=0, israndomtime=False, isformat=True, time_type=1, return_data_type=1):
        return_time = []
        regex = re.compile(r'(#)(.*)(#)')
        if isinstance(data, str):
            data1 = regex.sub(r'', data)
        else:
            data1 = regex.sub(r'', data.decode('utf-8'))

        data2 = data1.upper().replace('\n', '').replace('\t', '')
        data3 = data2.replace(" ", "")

        # 实时更新时间戳
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

        # 计算帧长度
        data4 = data3
        frame_len_int = 0
        if '{' in data4 and '}' in data4:
            start_idx = data3.index('{')
            end_idx = data3.index('}')
            frame = data3[start_idx+1:end_idx].replace('(', '').replace(')', '').replace('R', '')
            frame_len_int = int(len(frame) / 2)
            data4 = data4.replace('{', '').replace('}', '')

        if '<' in data4 and '>' in data4:
            start_idx = data3.index('<')
            end_idx = data3.index('>')
            frame = data3[start_idx+1:end_idx].replace('(', '').replace(')', '').replace('R', '')
            frame_len_int = int(len(frame) / 2)
            data4 = data4.replace('<', '').replace('>', '')

        # 替换帧长度占位符
        data5 = data4.replace('（', '(').replace('）', ')')
        if '(' in data5 and ')' in data5:
            if frame_len_int != 0:
                start_idx = data4.index('(')
                end_idx = data4.index(')')
                len_part = data4[start_idx:end_idx+1]
                len_byte = int(len(len_part.replace('R', '')) - 2)
                len_hex = self.int_to_hex(frame_len_int, len_byte)
                if 'R' in len_part:
                    len_hex = self.str_reverse(len_hex)
                data5 = data4[:start_idx] + len_hex + data4[end_idx+1:]
            else:
                data5 = data4.replace('(', '').replace(')', '')

        return_data = self.data_format(data5) if isformat else data5
        return return_data if return_data_type == 1 else (return_data, return_time[0])

    def data_format(self, data, num=2):
        num = int(num)
        result = ''
        data = data.replace(" ", "")
        for i in range(0, len(data), num):
            result += data[i:i+num] + ' '
        return result.upper().strip()

    def fix_str(self, data, num=2, ishead=True, fix_char='0'):
        str_len = len(data)
        if str_len < num:
            pad = fix_char * (num - str_len)
            data = pad + data if ishead else data + pad
        return data

    def str_reverse(self, data, num=2):
        data = data.replace(' ', '')
        parts = [data[i*num : (i+1)*num] for i in range(int(len(data)/num))]
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
            byte_num = int(len(f_hex)/2)
            boundary = int('80' + '00'*(byte_num-1), 16)
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
            with open(file_path, 'r', encoding='GB2312') as f1:
                for line in f1:
                    if return_type == 1:
                        line = line.replace('\n', '')
                        if line:
                            line = line.replace('-', '').replace('*', '').replace(' ', '')
                            result.append(line)
                    else:
                        result.append(line.replace(' ', ''))
        return result

    def send_to_mss(self, src_ip, dst_ip, dst_port, data, timeout=0.1, hour=0, time_type=1, src_port=10000, show_rec=False):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)

        if src_port in [10000, 10001]:
            fmt_data = self.deal_data(data, hour, time_type=time_type).upper()
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


# ------------------------- 普通动力环境报文生成 -------------------------
def get_analog_value_int(analog_name):
    min_val = 0
    max_val = 500

    if '路A相电压' in analog_name:
        pass
    if any(x in analog_name for x in ['继电器电源电压', 'LEU单元电源电压', '熔丝报警电源电压']):
        pass
    if any(x in analog_name for x in ['折返按钮电源电压', '24VDC备用回路1电压', '24VDC备用回路2电压', '折返按钮稳光电源电压']):
        pass

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
            print(f'{ex_info}{type_name}模拟量:{count}个, 设备 {name}, 值:{val_int/100:.2f}')

    code = f'{count_hex} #{type_name}模拟量个数 {count}个#\n{value_str}'
    return code.replace(' ', '').strip('\n')


def get_state_code(state_data, is_use_state, func, ex_info=''):
    count = len(state_data)
    count_hex = func.int_to_hex(count, 4)
    status_map = {0: '断开', 1: '闭合'}
    normal_status = [0]
    value_str = ''

    for i in range(count):
        name = state_data[i]
        idx = random.randint(0, 1)
        if i == 2:
            normal_status[0] = idx
        if i == 3:
            idx = 1 if normal_status[0] == 0 else 0

        value_str += f'0{idx} '
        if is_use_state:
            print(f'{ex_info}开关状态量:{count}个, 设备 {name}, 值:{status_map[idx]}')

    code = f'{count_hex} #开关状态量个数 {count}个#\n{value_str}'
    return code.replace(' ', '').strip('\n')


def get_alarm_code(alarm_data, is_use_alarm, is_alarm, func, data_type=1, ex_info=''):
    count = len(alarm_data)
    count_hex = func.int_to_hex(count, 4)
    byte_num = math.ceil(count / 8)
    type_name = '输入输出' if data_type == 1 else '模块'

    value_str = ''
    for _ in range(byte_num):
        value_str += 'FF ' if is_alarm else '00 '

    if is_use_alarm:
        status = '告警' if is_alarm else '正常'
        for name in alarm_data:
            print(f'{ex_info}{type_name}告警:{count}个, 设备 {name}, 值:{status}')

    code = f'{count_hex} #{type_name}告警个数 {count}个#\n{value_str}'
    return code.replace(' ', '').strip('\n')


def get_module_code(module_data, name_code_map, is_use_analog, is_use_state, is_use_alarm, is_alarm, func):
    type_count = 0
    module_data_dict = {}
    module_names = []
    current_name = ''
    flags = {'analog': False, 'state': False, 'alarm': False}

    for data in module_data:
        if '[' in data and ']' in data:
            type_count += 1
            start = data.index('[')
            end = data.index(']')
            name = data[start+1:end]
            m_count = int(data.split('=')[1])
            code = name_code_map[name.upper()]
            current_name = name
            module_names.append(name)
            module_data_dict[name] = {
                'count': m_count, 'code': code,
                'analog': [], 'state': [], 'alarm': []
            }
            flags = {'analog': False, 'state': False, 'alarm': False}
            continue

        if 'analog' in data.lower() or '输出路数' in data:
            flags = {'analog': True, 'state': False, 'alarm': False}
            continue
        if 'state' in data.lower():
            flags = {'analog': False, 'state': True, 'alarm': False}
            continue
        if 'alarm' in data.lower():
            flags = {'analog': False, 'state': False, 'alarm': True}
            continue

        if flags['analog']:
            module_data_dict[current_name]['analog'].append(data)
        if flags['state']:
            module_data_dict[current_name]['state'].append(data)
        if flags['alarm']:
            module_data_dict[current_name]['alarm'].append(data)

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
            ex = f'模块：{name} {count}-{i+1} '
            idx_hex = func.int_to_hex(i + 1)
            a_code = get_analog_code(analog_part, is_use_analog, func, 3, ex)
            s_code = get_state_code(state_part, is_use_state, func, ex)
            al_code = get_alarm_code(alarm_part, is_use_alarm, is_alarm, func, 2, ex)
            block = f'{idx_hex} #模块{name}序号{idx}-{i+1}#\n{a_code}\n{s_code}\n{al_code}'
            value_code += '\n' + block.replace(' ', '').strip('\n')

        part_code = f'{m_code} #类型{idx}的模块{name}类型码#\n{func.int_to_hex(count)} #类型{idx}的模块数量{count}#\n{value_code}'
        all_code += '\n' + part_code.replace(' ', '').strip('\n')

    return all_code


def get_powerdh_code(file_path, file_name, is_use_analog, is_use_state, is_use_alarm, is_alarm, func):
    module_name_code = {
        'TH1': '00', 'TC1': '01', 'TE1': '04', 'TE2': '05', 'TE3': '07',
        'DHXDD1': '08', 'DHXDD2': '09', 'DHXDE ': '0A', 'DHXDF2': '0C',
        'DHXDF3': '0D', 'DHXDH4': '15', 'TU1': '16', 'SC1': '20', 'SD1': '21',
        'SD2': '22', 'SD3': '23', 'SE1': '24', 'SE2': '25', 'SE3': '26',
        'SE4': '27', 'SE5': '28', 'SH1': '29', 'SF1': '2a', 'SF2': '2b',
        'SF3': '2c', 'SC2': '2d', 'SW1': '2e', 'SD4': '2f', 'SD5': '30',
        'SE6': '31', 'SD7': '32', 'SC3': '33', 'HD11010(20)': '34', 'TH5': '0F'
    }

    files_data = func.get_text_data(file_path, file_name)

    ups_name = ''
    for data in files_data:
        if 'UPS' in data.upper() and '[' in data and ']' in data and not ups_name:
            ups_name = data

    input_analog_idx = files_data.index('PMS_INPUT_ANALOG')
    state_idx = files_data.index('PMS_SWITCH_STATE')
    alarm_idx = files_data.index('PMS_ALARM')

    if 'PMS_输出端子表(特别说明)' in files_data:
        out_term_idx = files_data.index('PMS_输出端子表(特别说明)')
    else:
        out_term_idx = files_data.index('PMS_OUTPUT_ANALOG')

    output_analog_idx = files_data.index('PMS_OUTPUT_ANALOG')
    module_info_idx = files_data.index('PMS_Module_Info')
    ups_idx = files_data.index(ups_name)

    input_analog = files_data[input_analog_idx+1 : state_idx]
    state_data = files_data[state_idx+1 : alarm_idx]
    alarm_data = files_data[alarm_idx+1 : out_term_idx]
    output_analog = files_data[output_analog_idx+1 : module_info_idx]
    module_data = files_data[module_info_idx+1 : ups_idx]

    input_code = get_analog_code(input_analog, is_use_analog, func, 1)
    state_code = get_state_code(state_data, is_use_state, func)
    alarm_code = get_alarm_code(alarm_data, is_use_alarm, is_alarm, func)
    output_code = get_analog_code(output_analog, is_use_analog, func, 2)
    module_code = get_module_code(module_data, module_name_code, is_use_analog, is_use_state, is_use_alarm, is_alarm, func)

    send_data = f'''
        aa #帧开始标志#
        (01 f1) #帧长度#
        {{30 #Message Type#
        [5e426a31] #时间戳#
        12 #站点编号#
        000000b2 #报文序列号#
        {input_code}
        {state_code}
        {alarm_code}
        {output_code}
        {module_code}
        55 #结束标识#
        64a4aca2 #CRC校验#}}
    '''
    return send_data


# ------------------------- UPS+蓄电池报文生成 -------------------------
def is_in_data(in_data, filter_list):
    lower_in = in_data.lower()
    for item in filter_list:
        if item.lower() in lower_in:
            return True
    return False


def build_module_block(module_data_list, module_name, is_alarm, is_use_alarm, is_use_analog, func):
    analog_idx = module_data_list.index('模拟量')
    alarm_idx = module_data_list.index('告警量')
    analog_num = alarm_idx - analog_idx - 1
    alarm_num = len(module_data_list[alarm_idx+1:])

    code = ''
    # 模拟量部分
    code += func.int_to_hex(analog_num, 4) + '\n'
    for j in range(analog_num):
        val = round(random.uniform(0, 50), 2)
        hex_val = func.str_reverse(func.float_to_hex(val))
        code += hex_val + ' '
        if is_use_analog:
            print(f'模块{module_name} 模拟量:{analog_num}个, 设备: {module_data_list[analog_idx+j+1]}, 值: {val}')

    # 告警量部分
    code += '\n' + func.int_to_hex(alarm_num, 4) + '\n'
    byte_count = math.ceil(alarm_num / 8)
    status_map = {0: '正常', 1: '告警'}
    for j in range(byte_count):
        val = 'FF' if is_alarm else '00'
        code += val + ' '
        if is_use_alarm:
            bin_val = func.fix_str(bin(int(val[0], 16))[2:], 8)
            for k in range(8):
                bit = int(bin_val[7 - k])
                pos = 8 * j + k + 1 + alarm_idx
                if pos < len(module_data_list):
                    print(f'模块{module_name} 告警:{alarm_num}个, 设备: {module_data_list[pos]}, 值: {status_map[bit]}')
    return code


def get_powerdh_anolog(file_path, file_name, is_alarm, is_use_alarm, is_use_analog, func):
    files = func.get_text_data(file_path, file_name)

    ups_start = ''
    bat_start = ''
    for data in files:
        if '[' not in data or ']' not in data:
            continue
        if is_in_data(data, ['ups1', 'ups-1', '1[UPS_UL33_Modbus]']):
            ups_start = data
        if is_in_data(data, ['BAT-1', 'BAT1']):
            bat_start = data

    ups_idx = files.index(ups_start)
    bat_start_idx = files.index(bat_start) if bat_start else 5000

    # 提取UPS模块
    ups_all = []
    ups_names = []
    ups_indexes = []
    for i in range(len(files)):
        if ups_idx <= i < bat_start_idx:
            ups_all.append(files[i])
            if '[' in files[i] and ']' in files[i] and 'ups' in files[i].lower():
                ups_names.append(files[i])
                ups_indexes.append(len(ups_all) - 1)

    # 提取蓄电池模块
    bat_all = []
    bat_names = []
    bat_indexes = []
    for i in range(len(files)):
        if i >= bat_start_idx:
            bat_all.append(files[i])
            if '[' in files[i] and ']' in files[i] and 'bat' in files[i].lower():
                bat_names.append(files[i])
                bat_indexes.append(len(bat_all) - 1)

    # 生成UPS模块代码
    ups_len = len(ups_names)
    ups_code = ''
    for i in range(ups_len):
        start = ups_indexes[i]
        end = ups_indexes[i+1] if i < ups_len-1 else len(ups_all)
        single_data = ups_all[start:end]
        name = ups_names[i].split('_')[0]
        ups_code += f'\n{func.int_to_hex(i+1)}\n'
        ups_code += build_module_block(single_data, name, is_alarm, is_use_alarm, is_use_analog, func)

    # 生成蓄电池模块代码
    bat_len = len(bat_names)
    bat_code = ''
    for i in range(bat_len):
        start = bat_indexes[i]
        end = bat_indexes[i+1] if i < bat_len-1 else len(bat_all)
        single_data = bat_all[start:end]
        name = bat_names[i].split('_')[0]
        bat_code += f'\n{func.int_to_hex(i+1)}\n'
        bat_code += build_module_block(single_data, name, is_alarm, is_use_alarm, is_use_analog, func)

    send_data = f'''
        AA #帧开始标志#
        (01 C2) #帧长度#
        <
        33 #Message Type#
        [5CB479D7] #时间戳#
        18 #站点编号#
        002CFB42 #SN号#
        {func.int_to_hex(ups_len)} #UPS数量#
        {func.int_to_hex(bat_len)} #蓄电池组数目#
        {ups_code}
        {bat_code}
        55 #帧结束标志#
        D7FB0000 #CRC校验#
        >
    '''
    return send_data


# ------------------------- GUI 主界面 -------------------------
class PowerDHApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PowerDH 报文模拟工具")
        self.root.geometry("820x680")

        self.func = PublicFunc()
        self.running = False
        self.stop_event = threading.Event()
        self.send_thread = None

        # 界面变量
        self.folder_path = tk.StringVar()
        self.selected_station = tk.StringVar()
        self.use_ups = tk.BooleanVar(value=False)
        self.use_analog = tk.BooleanVar(value=True)
        self.use_state = tk.BooleanVar(value=True)
        self.use_alarm_print = tk.BooleanVar(value=True)
        self.is_alarm = tk.BooleanVar(value=True)
        self.src_ip = tk.StringVar(value="192.168.2.166")
        self.dst_ip = tk.StringVar(value="192.168.1.134")
        self.dst_port = tk.IntVar(value=10030)
        self.interval = tk.DoubleVar(value=1.0)

        self._build_ui()

    def _build_ui(self):
        # 1. 文件夹选择
        frame_folder = ttkb.LabelFrame(self.root, text="站点文件夹")
        frame_folder.pack(fill=X, padx=10, pady=5)
        inner_folder = ttkb.Frame(frame_folder, padding=8)
        inner_folder.pack(fill=BOTH, expand=True)
        ttkb.Entry(inner_folder, textvariable=self.folder_path).pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        ttkb.Button(inner_folder, text="浏览", command=self.select_folder, bootstyle=PRIMARY).pack(side=RIGHT)

        # 2. 站点列表
        frame_station = ttkb.LabelFrame(self.root, text="站点选择")
        frame_station.pack(fill=X, padx=10, pady=5)
        inner_station = ttkb.Frame(frame_station, padding=8)
        inner_station.pack(fill=BOTH, expand=True)
        self.station_list = tk.Listbox(inner_station, height=4)
        self.station_list.pack(fill=X)
        self.station_list.bind("<<ListboxSelect>>", self._on_station_select)

        # 3. 功能选项
        frame_opt = ttkb.LabelFrame(self.root, text="功能配置")
        frame_opt.pack(fill=X, padx=10, pady=5)
        inner_opt = ttkb.Frame(frame_opt, padding=8)
        inner_opt.pack(fill=BOTH, expand=True)

        row1 = ttkb.Frame(inner_opt)
        row1.pack(fill=X, pady=3)
        ttkb.Checkbutton(row1, text="启用UPS模式(分开发送)", variable=self.use_ups, bootstyle="round-toggle").pack(side=LEFT, padx=5)
        ttkb.Checkbutton(row1, text="模拟量打印", variable=self.use_analog, bootstyle="round-toggle").pack(side=LEFT, padx=5)
        ttkb.Checkbutton(row1, text="状态量打印", variable=self.use_state, bootstyle="round-toggle").pack(side=LEFT, padx=5)
        ttkb.Checkbutton(row1, text="报警打印", variable=self.use_alarm_print, bootstyle="round-toggle").pack(side=LEFT, padx=5)

        row2 = ttkb.Frame(inner_opt)
        row2.pack(fill=X, pady=3)
        ttkb.Label(row2, text="报警状态:").pack(side=LEFT, padx=5)
        ttkb.Radiobutton(row2, text="报警", variable=self.is_alarm, value=True, bootstyle="toolbutton").pack(side=LEFT, padx=2)
        ttkb.Radiobutton(row2, text="恢复", variable=self.is_alarm, value=False, bootstyle="toolbutton").pack(side=LEFT, padx=2)

        # 4. 网络配置
        frame_net = ttkb.LabelFrame(self.root, text="网络配置")
        frame_net.pack(fill=X, padx=10, pady=5)
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
        ttkb.Label(net_row2, text="发送间隔(秒):", width=11).pack(side=LEFT, padx=(10, 0))
        ttkb.Entry(net_row2, textvariable=self.interval, width=10).pack(side=LEFT, padx=5)

        # 5. 控制按钮
        frame_ctrl = ttkb.Frame(self.root)
        frame_ctrl.pack(fill=X, padx=10, pady=8)
        self.btn_start = ttkb.Button(frame_ctrl, text="开始发送", command=self.start_send, bootstyle=SUCCESS)
        self.btn_start.pack(side=LEFT, padx=5)
        self.btn_stop = ttkb.Button(frame_ctrl, text="停止发送", command=self.stop_send, bootstyle=DANGER, state=DISABLED)
        self.btn_stop.pack(side=LEFT, padx=5)

        # 6. 日志区
        frame_log = ttkb.LabelFrame(self.root, text="运行日志")
        frame_log.pack(fill=BOTH, expand=True, padx=10, pady=5)
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

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_text.see(tk.END)

    def start_send(self):
        folder = self.folder_path.get()
        station = self.selected_station.get()
        if not folder or not station:
            self._log("请先选择文件夹和站点！")
            return

        self.running = True
        self.stop_event.clear()
        self.btn_start.config(state=DISABLED)
        self.btn_stop.config(state=NORMAL)
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

        src = self.src_ip.get()
        dst = self.dst_ip.get()
        port = self.dst_port.get()
        interval = self.interval.get()

        while not self.stop_event.is_set():
            try:
                # 发送普通动力环境报文
                normal_data = get_powerdh_code(folder, station_name, use_analog, use_state, use_alarm, is_alarm, self.func)
                self.func.send_to_mss(src, dst, port, normal_data, show_rec=False)
                self._log("已发送 普通动力环境报文")

                # UPS模式下单独发送UPS+蓄电池报文
                if use_ups:
                    ups_data = get_powerdh_anolog(folder, station_name, is_alarm, use_alarm, use_analog, self.func)
                    self.func.send_to_mss(src, dst, port, ups_data, show_rec=False)
                    self._log("已发送 UPS+蓄电池 报文")

            except Exception as e:
                self._log(f"发送异常: {str(e)}")

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