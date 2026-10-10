import random
import time
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import socket
import re
import math
import ipaddress
import os
import json
import pymysql  # 需要安装 pymysql


# ===================== 精简版底层函数 =====================
class PublicFunc:
    @staticmethod
    def fix_str(data, num=2, ishead=True, fix_character='0'):
        data = str(data)
        if len(data) < num:
            if ishead:
                data = fix_character * (num - len(data)) + data
            else:
                data = data + fix_character * (num - len(data))
        return data

    @staticmethod
    def str_reverse(data, num=2):
        data = data.replace(' ', '')
        chunks = [data[i:i + num] for i in range(0, len(data), num)]
        return ''.join(chunks[::-1])

    @staticmethod
    def data_format(data, num=2):
        data = data.replace(' ', '')
        return ' '.join(data[i:i + num] for i in range(0, len(data), num)).upper()

    def int_to_hex(self, data, num=2):
        data = int(data)
        h = hex(data)[2:]
        if num < 2:
            num = 2
        if len(h) > num:
            num = math.ceil(len(h) / 2) * 2
        return self.fix_str(h, num).upper()

    def deal_data(self, data, fix_hour=0, israndomtime=False, isformat=True, time_type=1, return_data_type=1):
        return_time = []
        regex = re.compile(r'(#)(.*)(#)')
        if isinstance(data, str):
            data = regex.sub(r'', data)
        else:
            data = regex.sub(r'', data.decode('utf-8'))
        data = data.upper().replace('\n', '').replace('\t', '').replace(' ', '')

        while '[' in data and ']' in data:
            start = data.index('[')
            end = data.index(']')
            old_hex = data[start + 1:end]

            if time_type == 1:
                hour = random.randint(0, 30 * 24) if israndomtime else fix_hour
                ori_time = int(time.time()) - hour * 3600
            else:
                ori_time = time.time()

            stamp = time.localtime(ori_time)
            mon = hex(stamp[1])[2:]
            day = hex(stamp[2])[2:]
            hour_h = hex(stamp[3])[2:]
            min_h = hex(stamp[4])[2:]
            sec = hex(stamp[5])[2:]
            part = self.fix_str(mon) + self.fix_str(day) + self.fix_str(hour_h) + self.fix_str(min_h) + self.fix_str(
                sec)

            is_rev = 'R' in old_hex.upper()
            old_clean = old_hex.replace('R', '').replace('r', '')
            time_len = len(old_clean)

            if time_len == 8:
                stamp_int = int(ori_time)
                new_hex = self.int_to_hex(stamp_int, 8)
                if is_rev: new_hex = self.str_reverse(new_hex)
            elif time_len == 12:
                year = hex(stamp[0] - 2000)[2:]
                new_hex = self.fix_str(year) + part
                if is_rev: new_hex = self.str_reverse(new_hex)
            elif time_len in (14, 18):
                year = hex(stamp[0])[2:]
                year = self.fix_str(year, 4)
                if is_rev: year = self.str_reverse(year)
                new_hex = year + part
                if time_len == 18:
                    ms = int(str(ori_time - int(ori_time))[2:5])
                    ms_hex = self.fix_str(hex(ms)[2:], 4)
                    if is_rev: ms_hex = self.str_reverse(ms_hex)
                    new_hex = new_hex + ms_hex
            else:
                stamp_int = int(ori_time)
                new_hex = self.int_to_hex(stamp_int)
                if is_rev: new_hex = self.str_reverse(new_hex)

            return_time.append(int(ori_time))
            data = data[:start] + new_hex + data[end + 1:]

        frame_len_int = 0
        data_clean = data
        for brace_open, brace_close in [('{', '}'), ('<', '>')]:
            if brace_open in data_clean and brace_close in data_clean:
                s = data_clean.index(brace_open)
                e = data_clean.index(brace_close)
                inner = data_clean[s + 1:e]
                clean = inner.replace('(', '').replace(')', '').replace('R', '').replace('r', '')
                frame_len_int = len(clean) // 2
                data_clean = data_clean.replace(brace_open, '').replace(brace_close, '')
                break

        data = data_clean
        if '(' in data and ')' in data and frame_len_int:
            s = data.index('(')
            e = data.index(')')
            len_part = data[s:e + 1]
            len_clean = len_part.replace('R', '').replace('r', '')
            len_byte = len(len_clean) - 2
            len_hex = self.int_to_hex(frame_len_int, len_byte)
            if 'R' in len_part or 'r' in len_part:
                len_hex = self.str_reverse(len_hex)
            data = data[:s] + len_hex + data[e + 1:]
        else:
            data = data.replace('(', '').replace(')', '')

        if isformat:
            result = self.data_format(data)
        else:
            result = data

        if return_data_type == 1:
            return result
        else:
            return result, return_time[0]

    def send_to_mss(self, sourse_ip, dest_ip, dest_port, data, time_out=0.1, hour=0, time_type=1,
                    sourse_port=10000, is_show_rec=False):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(time_out)
        formatted = self.deal_data(data, hour, time_type=time_type).upper()
        post = bytes.fromhex(formatted)
        sock.bind((sourse_ip, sourse_port))
        sock.sendto(post, (dest_ip, dest_port))
        if is_show_rec:
            try:
                recv, addr = sock.recvfrom(10240)
                sock.close()
                return addr, self.data_format(recv.hex())
            except:
                return '', '无响应'
        sock.close()


class CphmFunc(PublicFunc):
    pass


# ===================== 协议构造函数 =====================
def make_kad1_overcar(func, cabinet_no, curve_index_list, curve_num, volt_min, volt_max, freq):
    curve_count = 1
    cab_hex = func.int_to_hex(cabinet_no, 2)
    freq_hex = func.int_to_hex(freq, 1)
    cnt_hex = func.int_to_hex(curve_count, 2)
    cnt_rev = func.str_reverse(cnt_hex)
    num_hex = func.int_to_hex(curve_num, 4)
    num_rev = func.str_reverse(num_hex)

    total = []
    for ci in curve_index_list:
        ci_hex = func.int_to_hex(ci, 2)
        curve_data = ''
        for i in range(curve_num):
            v = 550 if i == 0 else random.randint(volt_min, volt_max)
            v_hex = func.int_to_hex(v, 4)
            curve_data += func.str_reverse(v_hex)

        content = ''
        for i in range(curve_count):
            idx_hex = func.int_to_hex(i)
            content += f'''
                {ci_hex} #设备序号#
                {idx_hex} #设备内曲线序号#
                01 #曲线方向#
                [E3 07 0A 0A 09 00 00 00 01 R] #动作开始时间#
                {num_rev} #曲线数据数#
                00 #曲线数据压缩方法#
                {curve_data} #曲线数据#
            '''

        code = f'''
            EF EF EF EF
            10
            01 00 00 00
            30
            F6
            [E3 07 0A 08 09 00 00 R]
            (34 00 r)
            {{
            {cab_hex}
            {freq_hex} #采集频率#
            {cnt_rev}
            {content}
            }}
            FF FF
            FE FE FE FE
        '''
        total.append(func.deal_data(code, time_type=2))
    return total


def make_kad2_overcar(func, cabinet_no, curve_index_list, curve_num, volt_min, volt_max, freq):
    curve_count = 1
    cab_hex = func.int_to_hex(cabinet_no, 2)
    freq_hex = func.int_to_hex(freq, 1)
    cnt_hex = func.int_to_hex(curve_count, 2)
    cnt_rev = func.str_reverse(cnt_hex)
    num_hex = func.int_to_hex(curve_num, 4)
    num_rev = func.str_reverse(num_hex)

    total = []
    for ci in curve_index_list:
        ci_hex = func.int_to_hex(ci, 2)
        curve_data = ''
        for i in range(curve_num):
            v = random.randint(volt_min, volt_max)
            v_hex = func.int_to_hex(v, 4)
            curve_data += func.str_reverse(v_hex)

        content = ''
        for i in range(curve_count):
            content += f'''
            {ci_hex} #设备序号#
            0D #设备内曲线序号#
            50 #曲线方向#
            [6E 10 62 63 R] 00 00 #动作开始时间#
            {num_rev} #曲线数据数#
            00 #曲线数据压缩方法#
            {curve_data} #曲线数据#
            '''

        code = f'''
            EF EF EF EF
            10
            01 00 00 00
            3F
            57
            [6E 10 62 63 R]
            (34 00 r)
            {{
            {cab_hex}
            {freq_hex} #采集频率#
            {cnt_rev}
            {content}
            }}
            FF FF
            FA FB FC FD
        '''
        total.append(func.deal_data(code))
    return total


def make_kad1_history(func, cabinet_no, device_num, volt_min, volt_max, freq):
    cab_hex = func.int_to_hex(cabinet_no, 2)
    freq_hex = func.int_to_hex(freq, 1)
    dev_hex = func.int_to_hex(device_num, 4)
    dev_rev = func.str_reverse(dev_hex, 2)

    data_str = ''
    for _ in range(device_num):
        v = random.randint(volt_min, volt_max)
        v_hex = func.int_to_hex(v, 4)
        data_str += func.str_reverse(v_hex)

    code = f'''
        EF EF EF EF
        10
        01 00 00 00
        20
        6A
        [E3 07 09 1D 11 05 2F R]
        (A4 00 r)
        {{
        {cab_hex}
        {freq_hex} #采集频率#
        {dev_rev}
        {func.data_format(data_str)}
        }}
        FF FF
        FE FE FE FE
    '''
    return [func.deal_data(code, time_type=2)]


def make_kad2_history(func, cabinet_no, device_num, volt_min, volt_max, freq):
    cab_hex = func.int_to_hex(cabinet_no, 2)
    freq_hex = func.int_to_hex(freq, 1)
    dev_hex = func.int_to_hex(device_num, 4)
    dev_rev = func.str_reverse(dev_hex, 2)

    data_str = ''
    for _ in range(device_num):
        v = random.randint(volt_min, volt_max)
        v_hex = func.int_to_hex(v, 4)
        data_str += func.str_reverse(v_hex)

    code = f'''
        EF EF EF EF
        10
        01 00 00 00
        3F
        6A
        [6E 10 62 63 R]
        (84 00 r)
        <
        {cab_hex}
        {freq_hex} #采集频率#
        {dev_rev}
        {func.data_format(data_str)}
        >
        FF FF
        FA FB FC FD
    '''
    return [func.deal_data(code)]


def make_kad2_station_door_voltage(func, cabinet_no, analog_count, volt_min, volt_max, freq):
    try:
        analog_count = int(analog_count)
    except Exception:
        raise ValueError(f"站台门电压模拟量数必须为整数：{analog_count}")
    if analog_count < 0 or analog_count > 0xFFFF:
        raise ValueError("站台门电压模拟量数超出2字节范围")

    cab_hex = func.int_to_hex(cabinet_no, 2)
    freq_hex = func.int_to_hex(freq, 1)
    count_hex = func.int_to_hex(analog_count, 4)
    count_rev = func.str_reverse(count_hex, 2)

    data_str = ''
    for _ in range(analog_count):
        v = random.randint(int(volt_min), int(volt_max))
        v_hex = func.int_to_hex(v, 4)
        data_str += func.str_reverse(v_hex, 2)

    expected_data_hex_len = analog_count * 4
    if len(data_str) != expected_data_hex_len:
        raise ValueError(
            f"站台门电压数据长度错误：实际HEX={len(data_str)}，"
            f"期望HEX={expected_data_hex_len}"
        )

    code = f"""
        EF EF EF EF
        10
        01 00 00 00
        3F
        5E
        [6E 10 62 63 R]
        (84 00 r)
        <
        {cab_hex}
        {freq_hex} #采集频率#
        {count_rev} #模拟量数#
        {func.data_format(data_str)}
        >
        FF FF
        FA FB FC FD
    """
    return [func.deal_data(code)]


def make_kad2_curve_analysis(func, cabinet_no, device_num, volt_min, volt_max, command_code, freq):
    cab_hex = func.int_to_hex(cabinet_no, 2)
    freq_hex = func.int_to_hex(freq, 1)
    dev_hex = func.int_to_hex(device_num, 4)
    dev_rev = func.str_reverse(dev_hex, 2)

    data_str = ''
    for _ in range(device_num):
        v = random.randint(volt_min, volt_max)
        v_hex = func.int_to_hex(v, 4)
        data_str += func.str_reverse(v_hex)

    code = f'''
        EF EF EF EF
        10
        01 00 00 00
        3F
        {func.int_to_hex(command_code, 1)}
        [6E 10 62 63 R]
        (84 00 r)
        <
        {cab_hex}
        {freq_hex} #采集频率#
        {dev_rev}
        {func.data_format(data_str)}
        >
        FF FF
        FA FB FC FD
    '''
    return [func.deal_data(code)]


# ===================== 动作记录：文件解析 + 报文生成 =====================
def parse_action_record_file(file_path):
    """
    解析提速道岔曲线配置文件，按设备去重，提取每个设备的6条曲线。
    返回列表：[{'file_name': xxx, 'device_name': xxx, 'device_seq': xxx, 'curves': [...]}, ...]
    """
    content = None
    for encoding in [
        'utf-8', 'gbk', 'gb18030', 'utf-16',
        'utf-16-le', 'utf-16-be', 'big5'
    ]:
        try:
            with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                content = f.read()
            if content:
                break
        except Exception:
            continue

    if content is None:
        return []

    devices = {}
    in_section = False

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith('[') and ']' in line:
            section = line[1:line.index(']')].strip()
            if section == '提速道岔曲线':
                in_section = True
            elif in_section:
                break
            continue

        if not in_section or '=' not in line or ',' not in line:
            continue

        try:
            line_no_str, rest = line.split('=', 1)
            line_no = int(line_no_str.strip())
            parts = [p.strip() for p in rest.split(',')]
            if len(parts) < 9:
                continue

            raw_name = parts[0]
            inner_idx = int(parts[1])
            max_value = float(parts[3])
            resolution = float(parts[4])
            device_seq = int(parts[-1])  # 最后一列

            # 提取设备名称：去掉最后一个 '-' 后面的内容
            if '-' in raw_name:
                device_name = raw_name.rsplit('-', 1)[0]
            else:
                device_name = raw_name

            if device_name not in devices:
                devices[device_name] = {
                    'file_name': os.path.basename(file_path),
                    'device_name': device_name,
                    'device_seq': device_seq,
                    'curves': []
                }

            devices[device_name]['curves'].append({
                'line_no': line_no,
                'inner_idx': inner_idx,
                'max_value': max_value,
                'resolution': resolution,
            })
        except Exception:
            continue

    # 按 device_seq 排序，并保证每条设备包含6条曲线（不足补全，多余截断）
    result = []
    for device_name, dev in devices.items():
        curves = sorted(dev['curves'], key=lambda x: x['inner_idx'])
        # 保证6条曲线
        while len(curves) < 6:
            curves.append({
                'line_no': len(curves) + 1,
                'inner_idx': len(curves),
                'max_value': 10.0,
                'resolution': 0.001,
            })
        dev['curves'] = curves[:6]
        result.append(dev)

    return result


def _action_u8(value, field_name):
    """严格生成固定 1 字节（2 个 HEX 字符）的无符号整数。"""
    try:
        value = int(value)
    except Exception:
        raise ValueError(f'{field_name}必须是整数，当前值={value}')

    if not 0 <= value <= 0xFF:
        raise ValueError(f'{field_name}={value} 超出1字节范围(0~255)')

    return f'{value:02X}'


def _action_u16_le(value, field_name):
    """严格生成固定 2 字节、小端格式的无符号整数。"""
    try:
        value = int(value)
    except Exception:
        raise ValueError(f'{field_name}必须是整数，当前值={value}')

    if not 0 <= value <= 0xFFFF:
        raise ValueError(f'{field_name}={value} 超出2字节范围(0~65535)')

    return value.to_bytes(2, byteorder='little', signed=False).hex().upper()


def _build_action_start_time():
    """
    表8：曲线动作开始时间 = 6字节。

    前4字节：UNIX时间秒
    后2字节：毫秒

    本程序统一按低字节在前生成，避免同一动作的多包时间不一致。
    """
    now = time.time()
    unix_seconds = int(now)
    milliseconds = int((now - unix_seconds) * 1000)
    milliseconds = max(0, min(999, milliseconds))

    sec_hex = unix_seconds.to_bytes(
        4, byteorder='little', signed=False
    ).hex().upper()
    ms_hex = milliseconds.to_bytes(
        2, byteorder='little', signed=False
    ).hex().upper()

    result = sec_hex + ms_hex
    if len(result) != 12:
        raise ValueError(
            f'动作开始时间必须6字节，当前={len(result) // 2}字节'
        )
    return result


def _generate_action_curve_data(max_value, resolution, point_count):
    """
    生成单条动作曲线数据。

    表8：一个采样点占2字节。
    默认50点，因此每条曲线=100字节。
    """
    try:
        max_value = float(max_value)
    except Exception:
        max_value = 10.0

    try:
        resolution = float(resolution)
    except Exception:
        resolution = 0.001

    try:
        point_count = int(point_count)
    except Exception:
        raise ValueError(f'动作记录点数必须是整数，当前值={point_count}')

    if point_count <= 0:
        raise ValueError('动作记录点数必须大于0')
    if resolution <= 0:
        resolution = 0.001
    if max_value < 0:
        max_value = 0.0

    max_int = int(max_value / resolution)
    max_int = max(1, min(max_int, 0xFFFF))

    values = []
    for _ in range(point_count):
        value = random.randint(1, max_int)
        values.append(
            value.to_bytes(2, byteorder='little', signed=False).hex().upper()
        )

    data_hex = ''.join(values)
    expected_hex_len = point_count * 4
    if len(data_hex) != expected_hex_len:
        raise ValueError(
            f'曲线数据长度错误：实际={len(data_hex) // 2}字节，'
            f'期望={point_count * 2}字节'
        )

    return data_hex


def _validate_action_record_structure(
        point_count,
        curve_count,
        curve_data_list,
        total_data_bytes):
    """对表8动作记录数据区进行严格长度校验。"""
    per_curve_bytes = point_count * 2
    expected_total = per_curve_bytes * curve_count

    if total_data_bytes != expected_total:
        raise ValueError(
            f'曲线数据字节数错误：实际={total_data_bytes}，'
            f'期望={expected_total} '
            f'({curve_count}×{point_count}×2)'
        )

    if len(curve_data_list) != curve_count:
        raise ValueError(
            f'曲线条数错误：实际={len(curve_data_list)}，'
            f'期望={curve_count}'
        )

    for i, data_hex in enumerate(curve_data_list, 1):
        expected_hex_len = per_curve_bytes * 2
        if len(data_hex) != expected_hex_len:
            raise ValueError(
                f'曲线{i}数据长度错误：'
                f'实际={len(data_hex) // 2}字节，'
                f'期望={per_curve_bytes}字节'
            )
        try:
            bytes.fromhex(data_hex)
        except ValueError as e:
            raise ValueError(f'曲线{i}存在非法HEX：{e}')


def make_kad2_action_record(
        func,
        cabinet_no,
        freq,
        record,
        point_count,
        direction,
        packet_seq=0xFF,
        action_start_time=None):
    """
    生成 KAD2 动作记录报文（0x3F / 0x57）。

    严格按用户确认的表8规则：

        1  机柜号                  1字节
        2  采集频率                1字节
        3  曲线条数                1字节，固定6
        4  设备序号                1字节
        5  设备N内曲线序号         1字节，固定7
        6  曲线方向                1字节
        7  曲线动作开始时间        6字节
        8  曲线数据字节数          2字节
                                      = 6 × 点数 × 2
        9  实时曲线序号            1字节
                                      0~FE：普通包
                                      FF：最后一包
        10 曲线1数据               N字节
           ...
           曲线6数据               N字节

    用户已确认：
        - 曲线数据字节数是6条曲线总长度
        - 每包固定50点（GUI可调整点数）
        - 发送包数代表增加多少段数据
    """
    if not record or 'curves' not in record:
        return []

    try:
        point_count = int(point_count)
    except Exception:
        raise ValueError(f'动作记录点数必须是整数，当前值={point_count}')

    if point_count <= 0:
        raise ValueError('动作记录点数必须大于0')

    curve_count = 6
    curves = list(record.get('curves', []))
    if len(curves) < curve_count:
        raise ValueError(
            f"设备[{record.get('device_name', '')}]曲线数量不足6条：{len(curves)}"
        )
    curves = curves[:curve_count]

    try:
        packet_seq = int(packet_seq)
    except Exception:
        raise ValueError(f'实时曲线序号必须是整数，当前值={packet_seq}')

    if not 0 <= packet_seq <= 0xFF:
        raise ValueError(f'实时曲线序号超出范围：{packet_seq}')

    cab_hex = _action_u8(cabinet_no, '机柜号')
    freq_hex = _action_u8(freq, '采集频率')
    curve_count_hex = _action_u8(curve_count, '曲线条数')
    dev_seq_hex = _action_u8(record.get('device_seq', 1), '设备序号')

    # 表8明确：设备N内曲线序号固定为7，不再使用1~6。
    inner_curve_seq_hex = _action_u8(7, '设备N内曲线序号')
    direction_hex = _action_u8(direction, '曲线方向')

    if action_start_time is None:
        action_start_time = _build_action_start_time()

    action_start_time = str(action_start_time).replace(' ', '').upper()
    if len(action_start_time) != 12:
        raise ValueError(
            f'动作开始时间必须6字节，当前={len(action_start_time) // 2}字节'
        )
    try:
        bytes.fromhex(action_start_time)
    except ValueError:
        raise ValueError(f'动作开始时间不是合法HEX：{action_start_time}')

    per_curve_bytes = point_count * 2
    total_data_bytes = per_curve_bytes * curve_count
    if total_data_bytes > 0xFFFF:
        raise ValueError(
            f'6条曲线总数据长度超过2字节范围：{total_data_bytes}字节'
        )

    # 用户确认：这里填写6条曲线总数据长度。
    # 50点时：6 × 50 × 2 = 600 = 0x0258，按当前工程的小端约定为58 02。
    data_bytes_hex = _action_u16_le(
        total_data_bytes,
        '曲线数据字节数'
    )
    seq_hex = _action_u8(packet_seq, '实时曲线序号')

    curve_data_list = []
    for curve in curves:
        curve_data_list.append(
            _generate_action_curve_data(
                curve.get('max_value', 10.0),
                curve.get('resolution', 0.001),
                point_count
            )
        )

    _validate_action_record_structure(
        point_count,
        curve_count,
        curve_data_list,
        total_data_bytes
    )

    # --------------------------------------------------------
    # 表8数据区：公共字段只出现一次，随后连续放6条曲线数据。
    # --------------------------------------------------------
    body = (
        cab_hex +
        freq_hex +
        curve_count_hex +
        dev_seq_hex +
        inner_curve_seq_hex +
        direction_hex +
        action_start_time +
        data_bytes_hex +
        seq_hex +
        ''.join(curve_data_list)
    )

    expected_body_bytes = 1 + 1 + 1 + 1 + 1 + 1 + 6 + 2 + 1 + total_data_bytes
    actual_body_bytes = len(body) // 2
    if actual_body_bytes != expected_body_bytes:
        raise ValueError(
            f'动作记录数据区长度错误：实际={actual_body_bytes}字节，'
            f'期望={expected_body_bytes}字节'
        )

    code = f"""
        EF EF EF EF
        10
        01 00 00 00
        3F
        57
        [6E 10 62 63 R]
        (00 00 r)
        {{
        {func.data_format(body)}
        }}
        FF FF
        FA FB FC FD
    """

    packet = func.deal_data(code)
    clean_packet = packet.replace(' ', '').replace('\n', '').replace('\r', '').upper()

    if len(clean_packet) % 2 != 0:
        raise ValueError(
            f'最终动作记录报文HEX长度不是偶数：{len(clean_packet)}'
        )

    try:
        bytes.fromhex(clean_packet)
    except ValueError as e:
        raise ValueError(f'最终动作记录报文存在非法HEX：{e}')

    return [packet]


# ===================== 单个连接发送线程 =====================
class ConnectionSendThread(threading.Thread):
    def __init__(self, gui, mode, conn_info, common_params, curve_num=None, command_codes=None):
        super().__init__(daemon=True)
        self.gui = gui
        self.mode = mode
        self.conn_info = conn_info
        self.common_params = common_params
        self.curve_num = curve_num
        self.command_codes = command_codes
        self._stop = threading.Event()
        self.func = CphmFunc()

    def stop(self):
        self._stop.set()

    def get_cmd_description(self, cmd):
        descs = {
            0x21: "定位表示交流电压", 0x22: "定位表示直流电压",
            0x23: "反位表示交流电压", 0x24: "反位表示直流电压",
            0x6D: "定位表示12线交流电压", 0x6E: "定位表示12线直流电压",
            0x6F: "反位表示13线交流电压", 0x70: "反位表示13线直流电压",
        }
        return descs.get(cmd, f"0x{cmd:02X}")

    def run(self):
        src_ip = self.conn_info['src_ip']
        src_port = self.conn_info['src_port']
        if self.mode in ('KAD1_OVERCAR', 'KAD2_OVERCAR'):
            device_count = self.conn_info['overcar_device_count']
        elif self.mode in ('KAD1_HISTORY', 'KAD2_HISTORY'):
            device_count = self.conn_info['history_device_count']
        elif self.mode == 'KAD2_STATION_DOOR_VOLTAGE':
            device_count = self.conn_info.get('station_door_voltage_count', 0)
        elif self.mode == 'KAD2_CURVE_ANALYSIS':
            device_count = self.conn_info['curve_analysis_count']
        else:
            device_count = 0

        freq = self.common_params['freq']
        self.gui.log(f"连接 {src_ip}:{src_port} 开始发送 (模式={self.mode}, 设备数量={device_count}, 频率={freq})")

        try:
            while not self._stop.is_set():
                send_items = []

                if self.mode == 'KAD1_OVERCAR':
                    curve_list = list(range(device_count + 1))
                    codes = make_kad1_overcar(self.func, self.common_params['cabinet_no'],
                                              curve_list, self.curve_num,
                                              self.common_params['volt_min'], self.common_params['volt_max'], freq)
                    send_items = [(c, "KAD1过车曲线") for c in codes]

                elif self.mode == 'KAD2_OVERCAR':
                    curve_list = list(range(device_count + 1))
                    codes = make_kad2_overcar(self.func, self.common_params['cabinet_no'],
                                              curve_list, self.curve_num,
                                              self.common_params['volt_min'], self.common_params['volt_max'], freq)
                    send_items = [(c, "KAD2过车曲线") for c in codes]

                elif self.mode == 'KAD1_HISTORY':
                    codes = make_kad1_history(self.func, self.common_params['cabinet_no'],
                                              device_count,
                                              self.common_params['volt_min'], self.common_params['volt_max'], freq)
                    send_items = [(c, "KAD1历史电压曲线") for c in codes]

                elif self.mode == 'KAD2_HISTORY':
                    codes = make_kad2_history(self.func, self.common_params['cabinet_no'],
                                              device_count,
                                              self.common_params['volt_min'], self.common_params['volt_max'], freq)
                    send_items = [(c, "KAD2历史电压曲线") for c in codes]

                elif self.mode == 'KAD2_STATION_DOOR_VOLTAGE':
                    codes = make_kad2_station_door_voltage(
                        self.func, self.common_params['cabinet_no'], device_count,
                        self.common_params['volt_min'], self.common_params['volt_max'], freq)
                    send_items = [(c, "KAD2站台门电压") for c in codes]

                elif self.mode == 'KAD2_CURVE_ANALYSIS':
                    for cmd in self.command_codes:
                        cmd_codes = make_kad2_curve_analysis(
                            self.func, self.common_params['cabinet_no'], device_count,
                            self.common_params['volt_min'], self.common_params['volt_max'], cmd, freq)
                        desc = f"曲线分析 {self.get_cmd_description(cmd)}"
                        send_items.extend((c, desc) for c in cmd_codes)

                elif self.mode == 'KAD2_ACTION_RECORD':
                    records = self.common_params.get('action_records', [])
                    point_cnt = self.common_params.get('action_point_count', 50)
                    direction = self.common_params.get('action_direction', 0x50)
                    packet_count = self.common_params.get('action_packet_count', 1)

                    try:
                        point_cnt = int(point_cnt)
                        packet_count = int(packet_count)
                    except Exception:
                        raise ValueError('动作记录点数和发送包数必须是整数')

                    if point_cnt <= 0:
                        raise ValueError('动作记录点数必须大于0')
                    if packet_count <= 0:
                        raise ValueError('动作记录发送包数必须大于0')
                    if packet_count > 255:
                        raise ValueError('动作记录发送包数最大为255')

                    for rec in records:
                        # 同一动作的所有分包共用一个动作开始时间。
                        action_start_time = _build_action_start_time()

                        for pkt_idx in range(packet_count):
                            # 最后一包固定FF，其余从00开始递增。
                            packet_seq = 0xFF if pkt_idx == packet_count - 1 else pkt_idx

                            rec_codes = make_kad2_action_record(
                                self.func,
                                self.common_params['cabinet_no'],
                                freq,
                                rec,
                                point_cnt,
                                direction,
                                packet_seq=packet_seq,
                                action_start_time=action_start_time
                            )

                            desc = (
                                f"动作记录 ({rec['device_name']} "
                                f"第{pkt_idx + 1}/{packet_count}包 "
                                f"实时序号=0x{packet_seq:02X})"
                            )
                            send_items.extend((c, desc) for c in rec_codes)

                else:
                    self.gui.log(f"连接 {src_ip}:{src_port} 未知模式，停止")
                    break

                for code, desc in send_items:
                    self.gui.log(f"--- {desc} ---\n{code}")
                    self.func.send_to_mss(src_ip, self.common_params['dst_ip'],
                                          self.common_params['dst_port'], code,
                                          hour=0, time_type=2, sourse_port=src_port)

                if self._stop.is_set():
                    break
                time.sleep(self.common_params['interval'])
        except Exception as e:
            self.gui.log(f"连接 {src_ip}:{src_port} 发送异常: {e}")
        self.gui.log(f"连接 {src_ip}:{src_port} 停止发送")


# ===================== GUI =====================
class SimulatorGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("防雷柜曲线模拟器 (KAD_1 & KAD_2)")
        self.root.geometry("1400x900")
        self.root.resizable(True, True)

        self.state_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'LightningSimulator')
        os.makedirs(self.state_dir, exist_ok=True)
        self.state_file = os.path.join(self.state_dir, 'state.json')

        self.send_threads = []
        self.connections = []
        self.action_records = []

        self.create_widgets()
        self.update_db_host_label()
        self.load_state()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        # ---- 公共设置 ----
        common_frame = ttk.LabelFrame(self.root, text="公共设置", padding=10)
        common_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(common_frame, text="目标IP/数据库IP:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.dst_ip_var = tk.StringVar(value="192.168.1.249")
        ttk.Entry(common_frame, textvariable=self.dst_ip_var, width=15).grid(row=0, column=1, sticky="w")

        ttk.Label(common_frame, text="目标端口:").grid(row=0, column=2, padx=5, pady=5, sticky="e")
        self.dst_port_var = tk.IntVar(value=7001)
        ttk.Entry(common_frame, textvariable=self.dst_port_var, width=8).grid(row=0, column=3, sticky="w")

        ttk.Label(common_frame, text="机柜号:").grid(row=0, column=4, padx=5, pady=5, sticky="e")
        self.cabinet_no_var = tk.IntVar(value=250)
        ttk.Entry(common_frame, textvariable=self.cabinet_no_var, width=8).grid(row=0, column=5, sticky="w")

        ttk.Label(common_frame, text="采集频率:").grid(row=0, column=6, padx=5, pady=5, sticky="e")
        self.freq_var = tk.IntVar(value=1)
        ttk.Entry(common_frame, textvariable=self.freq_var, width=8).grid(row=0, column=7, sticky="w")

        ttk.Label(common_frame, text="电压最小值(x100):").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.volt_min_var = tk.IntVar(value=600)
        ttk.Entry(common_frame, textvariable=self.volt_min_var, width=8).grid(row=1, column=1, sticky="w")

        ttk.Label(common_frame, text="电压最大值(x100):").grid(row=1, column=2, padx=5, pady=5, sticky="e")
        self.volt_max_var = tk.IntVar(value=800)
        ttk.Entry(common_frame, textvariable=self.volt_max_var, width=8).grid(row=1, column=3, sticky="w")

        ttk.Label(common_frame, text="发送间隔(秒):").grid(row=1, column=4, padx=5, pady=5, sticky="e")
        self.interval_var = tk.DoubleVar(value=2.0)
        ttk.Entry(common_frame, textvariable=self.interval_var, width=8).grid(row=1, column=5, sticky="w")

        # ---- 连接列表 ----
        conn_frame = ttk.LabelFrame(self.root, text="连接列表", padding=10)
        conn_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        db_info_row = ttk.Frame(conn_frame)
        db_info_row.pack(fill=tk.X, pady=2)

        ttk.Label(db_info_row, text="数据库IP(目标IP):").pack(side=tk.LEFT, padx=5)
        self.db_host_label = ttk.Label(db_info_row, text="", foreground="blue")
        self.db_host_label.pack(side=tk.LEFT, padx=5)
        self.dst_ip_var.trace_add("write", self.update_db_host_label)

        ttk.Label(db_info_row, text="端口:").pack(side=tk.LEFT, padx=5)
        self.db_port_var = tk.IntVar(value=3306)
        ttk.Entry(db_info_row, textvariable=self.db_port_var, width=6).pack(side=tk.LEFT, padx=5)

        ttk.Label(db_info_row, text="用户:").pack(side=tk.LEFT, padx=5)
        self.db_user_var = tk.StringVar(value="root")
        ttk.Entry(db_info_row, textvariable=self.db_user_var, width=10).pack(side=tk.LEFT, padx=5)

        ttk.Label(db_info_row, text="密码:").pack(side=tk.LEFT, padx=5)
        self.db_pass_var = tk.StringVar(value="mysql")
        ttk.Entry(db_info_row, textvariable=self.db_pass_var, width=10, show="*").pack(side=tk.LEFT, padx=5)

        ttk.Label(db_info_row, text="数据库名:").pack(side=tk.LEFT, padx=5)
        self.db_name_var = tk.StringVar(value="base")
        ttk.Entry(db_info_row, textvariable=self.db_name_var, width=10).pack(side=tk.LEFT, padx=5)

        db_action_row = ttk.Frame(conn_frame)
        db_action_row.pack(fill=tk.X, pady=2)

        ttk.Label(db_action_row, text="Master过滤:").pack(side=tk.LEFT, padx=5)
        self.import_master_var = tk.StringVar(value="")
        ttk.Entry(db_action_row, textvariable=self.import_master_var, width=5).pack(side=tk.LEFT, padx=5)

        ttk.Label(db_action_row, text="导入起始端口:").pack(side=tk.LEFT, padx=5)
        self.import_start_port_var = tk.IntVar(value=10000)
        ttk.Entry(db_action_row, textvariable=self.import_start_port_var, width=8).pack(side=tk.LEFT, padx=5)

        self.filter_ip_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(db_action_row, text="启用网段过滤(192.168)", variable=self.filter_ip_enabled).pack(side=tk.LEFT,
                                                                                                           padx=10)

        ttk.Button(db_action_row, text="从数据库导入连接", command=self.import_connections_from_db).pack(side=tk.LEFT,
                                                                                                         padx=10)
        ttk.Button(db_action_row, text="清空连接", command=self.clear_connections).pack(side=tk.LEFT, padx=5)
        ttk.Button(db_action_row, text="读取文件填充设备数量", command=self.load_files_fill_device_count).pack(
            side=tk.LEFT, padx=10)

        table_frame = ttk.Frame(conn_frame)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ("src_ip", "src_port", "station", "master", "overcar_dev", "history_dev", "station_door_dev",
                   "curve_analysis_dev", "enabled")
        self.conn_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=8)
        self.conn_tree.heading("src_ip", text="本机IP")
        self.conn_tree.heading("src_port", text="本机端口")
        self.conn_tree.heading("station", text="站点")
        self.conn_tree.heading("master", text="Master")
        self.conn_tree.heading("overcar_dev", text="过车设备数量")
        self.conn_tree.heading("history_dev", text="历史设备数量")
        self.conn_tree.heading("station_door_dev", text="站台门电压数量")
        self.conn_tree.heading("curve_analysis_dev", text="曲线分析数量")
        self.conn_tree.heading("enabled", text="启用")
        self.conn_tree.column("src_ip", width=120, anchor=tk.CENTER)
        self.conn_tree.column("src_port", width=90, anchor=tk.CENTER)
        self.conn_tree.column("station", width=160, anchor=tk.CENTER)
        self.conn_tree.column("master", width=60, anchor=tk.CENTER)
        self.conn_tree.column("overcar_dev", width=100, anchor=tk.CENTER)
        self.conn_tree.column("history_dev", width=100, anchor=tk.CENTER)
        self.conn_tree.column("station_door_dev", width=110, anchor=tk.CENTER)
        self.conn_tree.column("curve_analysis_dev", width=100, anchor=tk.CENTER)
        self.conn_tree.column("enabled", width=60, anchor=tk.CENTER)
        self.conn_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.conn_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.conn_tree.configure(yscrollcommand=scrollbar.set)
        self.conn_tree.bind("<Double-1>", self.on_tree_double_click)

        # ---- 标签页 ----
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.overcar_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.overcar_frame, text="过车曲线")
        self.create_overcar_page()

        self.history_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.history_frame, text="历史电压曲线")
        self.create_history_page()

        self.station_door_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.station_door_frame, text="站台门电压")
        self.create_station_door_voltage_page()

        self.curve_analysis_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.curve_analysis_frame, text="曲线分析")
        self.create_curve_analysis_page()

        self.action_record_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.action_record_frame, text="动作记录")
        self.create_action_record_page()

        # ---- 底部按钮和日志 ----
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(fill=tk.X, padx=10, pady=5)

        self.start_btn = ttk.Button(bottom_frame, text="开始发送", command=self.start_sending)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(bottom_frame, text="停止发送", command=self.stop_sending, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.log_area = scrolledtext.ScrolledText(log_frame, width=110, height=8, state='normal')
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def create_overcar_page(self):
        frame = ttk.Frame(self.overcar_frame, padding=10)
        frame.pack(fill=tk.X, pady=10)
        ttk.Label(frame, text="曲线数据点数:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.curve_num_var = tk.IntVar(value=50)
        ttk.Entry(frame, textvariable=self.curve_num_var, width=10).grid(row=0, column=1, sticky="w")
        ttk.Label(frame, text="协议版本:").grid(row=0, column=2, padx=5, pady=5, sticky="e")
        self.overcar_protocol_var = tk.StringVar(value="KAD_1")
        ttk.Combobox(frame, textvariable=self.overcar_protocol_var,
                     values=["KAD_1", "KAD_2"], state="readonly", width=8).grid(row=0, column=3, sticky="w")

    def create_history_page(self):
        frame = ttk.Frame(self.history_frame, padding=10)
        frame.pack(fill=tk.X, pady=10)
        ttk.Label(frame, text="协议版本:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.history_protocol_var = tk.StringVar(value="KAD_1")
        ttk.Combobox(frame, textvariable=self.history_protocol_var,
                     values=["KAD_1", "KAD_2"], state="readonly", width=8).grid(row=0, column=1, sticky="w")

    def create_station_door_voltage_page(self):
        frame = ttk.Frame(self.station_door_frame, padding=10)
        frame.pack(fill=tk.X, pady=10)
        ttk.Label(frame, text="协议版本:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        ttk.Label(frame, text="KAD_2", foreground="blue").grid(row=0, column=1, padx=5, pady=5, sticky="w")
        ttk.Label(frame, text="主类型:").grid(row=0, column=2, padx=5, pady=5, sticky="e")
        ttk.Label(frame, text="0x3F", foreground="blue").grid(row=0, column=3, padx=5, pady=5, sticky="w")
        ttk.Label(frame, text="子类型:").grid(row=0, column=4, padx=5, pady=5, sticky="e")
        ttk.Label(frame, text="0x5E 站台门电压", foreground="blue").grid(row=0, column=5, padx=5, pady=5, sticky="w")
        ttk.Label(frame, text="模拟量数来源:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        ttk.Label(frame, text="[站台门电压] → 模拟量数", foreground="blue").grid(row=1, column=1, columnspan=5, padx=5,
                                                                                 pady=5, sticky="w")
        ttk.Label(frame, text="帧说明:").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        ttk.Label(frame, text="与历史电压帧结构一致；3F后的时间戳反转", foreground="blue").grid(row=2, column=1,
                                                                                               columnspan=5, padx=5,
                                                                                               pady=5, sticky="w")

    def create_curve_analysis_page(self):
        frame = ttk.Frame(self.curve_analysis_frame, padding=10)
        frame.pack(fill=tk.X, pady=10)
        ttk.Label(frame, text="选择命令码（可多选）:").grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.curve_cmd_vars = {}
        cmd_list = [
            (0x21, "定位表示交流电压"), (0x22, "定位表示直流电压"),
            (0x23, "反位表示交流电压"), (0x24, "反位表示直流电压"),
            (0x6D, "定位表示12线交流电压"), (0x6E, "定位表示12线直流电压"),
            (0x6F, "反位表示13线交流电压"), (0x70, "反位表示13线直流电压"),
        ]
        for idx, (cmd, desc) in enumerate(cmd_list):
            var = tk.BooleanVar(value=False)
            self.curve_cmd_vars[cmd] = var
            ttk.Checkbutton(frame, text=f"0x{cmd:02X} - {desc}", variable=var).grid(
                row=1 + idx // 4, column=idx % 4, padx=10, pady=5, sticky="w")

    def create_action_record_page(self):
        frame = ttk.Frame(self.action_record_frame, padding=10)
        frame.pack(fill=tk.BOTH, expand=True, pady=10)

        ctrl_frame = ttk.Frame(frame)
        ctrl_frame.pack(fill=tk.X, pady=5)

        ttk.Button(ctrl_frame, text="读取配置文件(.txt)", command=self.load_action_record_config).pack(side=tk.LEFT,
                                                                                                       padx=5)
        ttk.Button(ctrl_frame, text="清空配置", command=self.clear_action_record_config).pack(side=tk.LEFT, padx=5)

        ttk.Label(ctrl_frame, text="点数:").pack(side=tk.LEFT, padx=5)
        self.action_point_count_var = tk.IntVar(value=50)
        ttk.Entry(ctrl_frame, textvariable=self.action_point_count_var, width=6).pack(side=tk.LEFT, padx=5)

        ttk.Label(ctrl_frame, text="曲线方向:").pack(side=tk.LEFT, padx=5)
        self.action_direction_var = tk.StringVar(value="0x50 定位到定位")
        ttk.Combobox(ctrl_frame, textvariable=self.action_direction_var,
                     values=[
                         "0x50 定位到定位", "0x60 定位到反位", "0x40 定位到故障位",
                         "0x90 反位到定位", "0xA0 反位到反位", "0x80 反位到故障位",
                         "0x10 故障位到定位", "0x20 故障位到反位", "0x00 故障位到故障位",
                     ], state="readonly", width=18).pack(side=tk.LEFT, padx=5)

        ttk.Label(ctrl_frame, text="发送包数:").pack(side=tk.LEFT, padx=5)
        self.action_packet_count_var = tk.IntVar(value=1)
        ttk.Entry(ctrl_frame, textvariable=self.action_packet_count_var, width=6).pack(side=tk.LEFT, padx=5)

        ttk.Label(ctrl_frame, text="已读取设备数:").pack(side=tk.LEFT, padx=5)
        self.action_curve_count_label = ttk.Label(ctrl_frame, text="0", foreground="blue")
        self.action_curve_count_label.pack(side=tk.LEFT, padx=5)

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ("file", "device_seq", "device_name", "curve_count", "curve_details")
        self.action_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=12)
        self.action_tree.heading("file", text="文件")
        self.action_tree.heading("device_seq", text="设备序号")
        self.action_tree.heading("device_name", text="设备名称")
        self.action_tree.heading("curve_count", text="曲线条数")
        self.action_tree.heading("curve_details", text="包含曲线")
        self.action_tree.column("file", width=280, anchor=tk.CENTER)
        self.action_tree.column("device_seq", width=80, anchor=tk.CENTER)
        self.action_tree.column("device_name", width=200, anchor=tk.CENTER)
        self.action_tree.column("curve_count", width=100, anchor=tk.CENTER)
        self.action_tree.column("curve_details", width=300, anchor=tk.CENTER)
        self.action_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.action_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.action_tree.configure(yscrollcommand=scrollbar.set)

    def update_db_host_label(self, *args):
        self.db_host_label.config(text=self.dst_ip_var.get())

    # ===================== 动作记录读取/清空 =====================
    def load_action_record_config(self):
        file_paths = filedialog.askopenfilenames(
            title="选择提速道岔曲线配置文件",
            filetypes=[("文本文件", "*.txt;*.ini"), ("所有文件", "*.*")]
        )
        if not file_paths:
            return

        self.clear_action_record_config()
        total_devices = 0
        for file_path in file_paths:
            records = parse_action_record_file(file_path)
            if not records:
                self.log(f"文件 {os.path.basename(file_path)} 中未找到 [提速道岔曲线] 有效数据")
                continue
            file_name = os.path.basename(file_path)
            self.action_records.extend(records)
            for rec in records:
                curve_details = ",".join([f"{c['line_no']}" for c in rec['curves']])
                self.action_tree.insert('', tk.END, values=(
                    file_name, rec['device_seq'], rec['device_name'],
                    "6", curve_details))
            total_devices += len(records)
            self.log(f"文件 {file_name} 解析到 {len(records)} 个设备")

        self.action_curve_count_label.config(text=str(total_devices))
        self.log(f"动作记录配置读取完成，共 {len(self.action_records)} 个设备")
        messagebox.showinfo("完成", f"读取完成，共 {total_devices} 个设备")

    def clear_action_record_config(self):
        self.action_records = []
        for item in self.action_tree.get_children():
            self.action_tree.delete(item)
        if hasattr(self, 'action_curve_count_label'):
            self.action_curve_count_label.config(text="0")

    @staticmethod
    def parse_direction(dir_str):
        hex_str = dir_str.split(' ')[0] if ' ' in dir_str else dir_str
        try:
            return int(hex_str, 16)
        except Exception:
            return 0x50

    @staticmethod
    def parse_compress(comp_str):
        hex_str = comp_str.split(' ')[0] if ' ' in comp_str else comp_str
        try:
            return int(hex_str, 16)
        except Exception:
            return 0x00

    # ===================== 连接管理 =====================
    def clear_connections(self):
        self.connections.clear()
        for item in self.conn_tree.get_children():
            self.conn_tree.delete(item)

    def import_connections_from_db(self):
        if not self.dst_ip_var.get().strip():
            messagebox.showerror("错误", "请先设置目标IP/数据库IP")
            return
        db_config = {
            'host': self.dst_ip_var.get().strip(),
            'port': self.db_port_var.get(),
            'user': self.db_user_var.get().strip(),
            'password': self.db_pass_var.get(),
            'database': self.db_name_var.get().strip()
        }
        try:
            conn = pymysql.connect(**db_config)
            cursor = conn.cursor()
            sql = """
                  SELECT a.IP, b.STATION_NAME, a.master
                  FROM dic_mss_netaddress_config a
                           RIGHT JOIN dic_station b ON a.STATION_NO = b.STATION_NO
                  WHERE a.SYS_NO = 4 \
                    AND a.used != 0 \
                  """
            master_filter = self.import_master_var.get().strip()
            params = []
            if master_filter:
                sql += " AND a.master = %s"
                params.append(int(master_filter))
            cursor.execute(sql, tuple(params))
            results = cursor.fetchall()
            cursor.close()
            conn.close()

            filtered = []
            if self.filter_ip_enabled.get():
                for ip, station, master in results:
                    if ip.startswith('192.168'):
                        filtered.append((ip, station, master))
                    else:
                        self.log(f"已过滤非192.168网段IP: {ip}")
            else:
                filtered = results

            if not filtered:
                messagebox.showinfo("提示", "数据库中没有符合要求的记录")
                return

            self.clear_connections()
            start_port = self.import_start_port_var.get()
            for i, (ip, station, master) in enumerate(filtered):
                port = start_port + i
                self.connections.append({
                    'src_ip': ip, 'src_port': port,
                    'station': station if station else '',
                    'master': master if master is not None else 0,
                    'overcar_device_count': 0, 'history_device_count': 0,
                    'station_door_voltage_count': 0, 'curve_analysis_count': 0, 'enabled': True
                })
                self.conn_tree.insert('', tk.END, values=(
                    ip, port, station if station else '',
                    master if master is not None else 0, 0, 0, 0, 0, "是"))
            self.log(f"从数据库导入 {len(filtered)} 个连接，起始端口 {start_port}")
            messagebox.showinfo("完成", f"成功导入 {len(filtered)} 个连接")
        except ImportError:
            messagebox.showerror("缺少模块", "请先安装 pymysql")
        except Exception as e:
            messagebox.showerror("数据库错误", f"导入失败: {e}")

    @staticmethod
    def _read_section_int(content, section_name, key_name):
        lines = content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        in_section = False
        section_norm = section_name.strip().replace(' ', '')
        key_norm = key_name.strip().replace(' ', '')

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith('[') and ']' in line:
                current = line[1:line.index(']')].strip().replace(' ', '')
                in_section = (current == section_norm)
                continue

            if not in_section or '=' not in line:
                continue

            key, value = line.split('=', 1)
            if key.strip().replace(' ', '') != key_norm:
                continue

            m = re.search(r'-?\d+', value.strip())
            if m:
                return int(m.group(0))

        return None

    def load_files_fill_device_count(self):
        if not self.connections:
            messagebox.showwarning("警告", "请先导入连接")
            return
        file_paths = filedialog.askopenfilenames(
            title="选择配置文件",
            filetypes=[("配置文件", "*.ini;*.txt;*.conf"), ("所有文件", "*.*")]
        )
        if not file_paths:
            return

        matched_count = 0
        unmatched_files = []

        for file_path in file_paths:
            filename = os.path.basename(file_path)
            base_name = os.path.splitext(filename)[0].strip()
            if '配置表' in base_name:
                base_name = base_name.split('配置表')[0].strip()
            matches = re.findall(r'[\u4e00-\u9fff]+(?:站|车辆段|停车场|基地)', base_name)
            if matches:
                station_name = matches[-1].strip()
            else:
                station_name = re.sub(r'[Ff]\d*$', '', base_name).strip()
                station_name = re.sub(r'[_\d]+$', '', station_name).strip()

            if not station_name:
                self.log(f"文件 {filename} 无法提取站点名")
                unmatched_files.append(filename)
                continue

            content = None
            for encoding in ['utf-8', 'gbk', 'gb18030', 'utf-16', 'utf-16-le', 'utf-16-be', 'big5']:
                try:
                    with open(file_path, 'rb') as f:
                        raw_data = f.read()
                    text = raw_data.decode(encoding, errors='ignore')
                    if re.search(r'[\u4e00-\u9fff]', text):
                        content = text
                        break
                except Exception:
                    continue
            if content is None:
                try:
                    with open(file_path, 'r', encoding='gbk', errors='ignore') as f:
                        content = f.read()
                except Exception as e:
                    self.log(f"文件 {filename} 读取失败: {e}")
                    unmatched_files.append(filename)
                    continue

            overcar_count = None
            history_count = None
            station_door_voltage_count = None
            curve_analysis_count = None
            freq = None

            m = re.search(r'\[?\s*计轴磁头过车曲线\s*\]?\s*[\s\S]*?曲线数\s*[:=]\s*(\d+)', content, re.IGNORECASE)
            if not m:
                m = re.search(r'计轴磁头过车曲线[\s\S]*?曲线数\s*[:=]\s*(\d+)', content, re.IGNORECASE)
            if m:
                overcar_count = int(m.group(1))

            m = re.search(r'\[?\s*计轴磁头电压\s*\]?\s*[\s\S]*?模拟量数\s*[:=]\s*(\d+)', content, re.IGNORECASE)
            if not m:
                m = re.search(r'计轴磁头电压[\s\S]*?模拟量数\s*[:=]\s*(\d+)', content, re.IGNORECASE)
            if m:
                history_count = int(m.group(1))

            station_door_voltage_count = self._read_section_int(
                content, '站台门电压', '模拟量数'
            )

            curve_analysis_count = self._read_section_int(
                content, '定位表示交流电压', '模拟量数'
            )

            m = re.search(r'采集频率\s*[:=]\s*(\d+)', content, re.IGNORECASE)
            if m:
                freq = int(m.group(1))
                self.freq_var.set(freq)
                self.log(f"从文件 {filename} 读取到采集频率={freq}")

            if overcar_count is None and history_count is None and station_door_voltage_count is None and curve_analysis_count is None and freq is None:
                preview = content[:300].replace('\n', ' ')
                self.log(f"文件 {filename} 中未找到有效数据，预览: {preview}")
                unmatched_files.append(filename)
                continue

            found = False
            for i, conn in enumerate(self.connections):
                if conn['station'] == station_name:
                    item_id = self.conn_tree.get_children()[i]
                    if overcar_count is not None:
                        conn['overcar_device_count'] = overcar_count
                        self.conn_tree.set(item_id, 'overcar_dev', overcar_count)
                    if history_count is not None:
                        conn['history_device_count'] = history_count
                        self.conn_tree.set(item_id, 'history_dev', history_count)
                    if station_door_voltage_count is not None:
                        conn['station_door_voltage_count'] = station_door_voltage_count
                        self.conn_tree.set(item_id, 'station_door_dev', station_door_voltage_count)
                    if curve_analysis_count is not None:
                        conn['curve_analysis_count'] = curve_analysis_count
                        self.conn_tree.set(item_id, 'curve_analysis_dev', curve_analysis_count)
                    found = True
                    matched_count += 1

            if found:
                self.log(
                    f"文件 {filename} 已匹配站点 '{station_name}'："
                    f"过车={overcar_count if overcar_count is not None else '-'}，"
                    f"历史={history_count if history_count is not None else '-'}，"
                    f"站台门={station_door_voltage_count if station_door_voltage_count is not None else '-'}，"
                    f"曲线分析={curve_analysis_count if curve_analysis_count is not None else '-'}"
                )
            else:
                self.log(f"文件 {filename} 对应站点 '{station_name}' 在连接列表中未找到")
                unmatched_files.append(filename)

        if unmatched_files:
            messagebox.showwarning("部分未匹配", "以下文件未匹配：\n" + "\n".join(unmatched_files))
        else:
            messagebox.showinfo("完成", f"所有文件均成功匹配，共更新 {matched_count} 个连接")
        self.log(f"文件读取完成，成功匹配 {matched_count} 个连接")

    def on_tree_double_click(self, event):
        region = self.conn_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        column = self.conn_tree.identify_column(event.x)
        row_id = self.conn_tree.identify_row(event.y)
        if not row_id:
            return
        col_idx = int(column[1:]) - 1
        if col_idx not in (3, 4, 5, 6, 7, 8):
            return

        if col_idx == 8:
            current_val = self.conn_tree.item(row_id, 'values')[col_idx]
            new_enabled = not (current_val == "是")
            self.conn_tree.set(row_id, column, "是" if new_enabled else "否")
            row_index = self.conn_tree.index(row_id)
            self.connections[row_index]['enabled'] = new_enabled
            return

        current_value = self.conn_tree.item(row_id, 'values')[col_idx]
        x, y, width, height = self.conn_tree.bbox(row_id, column)
        entry = ttk.Entry(self.conn_tree, width=10)
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, current_value)
        entry.focus()
        entry.select_range(0, tk.END)

        def save_edit(event=None):
            new_value = entry.get()
            try:
                new_val = int(new_value)
            except ValueError:
                messagebox.showerror("错误", "必须为整数")
                entry.destroy()
                return
            self.conn_tree.set(row_id, column, new_val)
            row_index = self.conn_tree.index(row_id)
            if col_idx == 3:
                self.connections[row_index]['master'] = new_val
            elif col_idx == 4:
                self.connections[row_index]['overcar_device_count'] = new_val
            elif col_idx == 5:
                self.connections[row_index]['history_device_count'] = new_val
            elif col_idx == 6:
                self.connections[row_index]['station_door_voltage_count'] = new_val
            elif col_idx == 7:
                self.connections[row_index]['curve_analysis_count'] = new_val
            entry.destroy()

        entry.bind("<Return>", save_edit)
        entry.bind("<FocusOut>", save_edit)

    def log(self, message):
        self.log_area.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_area.see(tk.END)

    def start_sending(self):
        try:
            cabinet_no = self.cabinet_no_var.get()
            dst_ip = self.dst_ip_var.get().strip()
            dst_port = self.dst_port_var.get()
            interval = self.interval_var.get()
            volt_min = self.volt_min_var.get()
            volt_max = self.volt_max_var.get()
            freq = self.freq_var.get()
        except Exception as e:
            messagebox.showerror("输入错误", f"请检查公共参数: {e}")
            return
        if not dst_ip:
            messagebox.showerror("IP错误", "目标IP不能为空")
            return
        if interval <= 0:
            messagebox.showerror("间隔错误", "间隔必须 >0")
            return

        if self.send_threads:
            for t in self.send_threads:
                t.stop()
            self.send_threads.clear()

        enabled_connections = [conn for conn in self.connections if conn.get('enabled', True)]
        if not enabled_connections:
            messagebox.showerror("无启用连接", "请至少启用一个连接")
            return

        current_tab = self.notebook.index(self.notebook.select())
        if current_tab == 0:
            curve_num = self.curve_num_var.get()
            protocol = self.overcar_protocol_var.get()
            mode = 'KAD1_OVERCAR' if protocol == 'KAD_1' else 'KAD2_OVERCAR'
            command_codes = None
        elif current_tab == 1:
            protocol = self.history_protocol_var.get()
            mode = 'KAD1_HISTORY' if protocol == 'KAD_1' else 'KAD2_HISTORY'
            curve_num = None
            command_codes = None
        elif current_tab == 2:
            mode = 'KAD2_STATION_DOOR_VOLTAGE'
            curve_num = None
            command_codes = None
            if not any(conn.get('station_door_voltage_count', 0) > 0 for conn in enabled_connections):
                messagebox.showerror("未找到模拟量数", "请先读取包含 [站台门电压] / 模拟量数 的配置文件")
                return
        elif current_tab == 3:
            mode = 'KAD2_CURVE_ANALYSIS'
            curve_num = None
            command_codes = [cmd for cmd, var in self.curve_cmd_vars.items() if var.get()]
            if not command_codes:
                messagebox.showerror("未选择命令码", "请至少选择一个命令码")
                return
        else:
            if not self.action_records:
                messagebox.showerror("未读取配置", "请先读取动作记录配置文件")
                return
            mode = 'KAD2_ACTION_RECORD'
            curve_num = None
            command_codes = None

        common_params = {
            'cabinet_no': cabinet_no,
            'volt_min': volt_min,
            'volt_max': volt_max,
            'dst_ip': dst_ip,
            'dst_port': dst_port,
            'interval': interval,
            'freq': freq,
            'action_point_count': self.action_point_count_var.get(),
            'action_direction': self.parse_direction(self.action_direction_var.get()),
            'action_packet_count': self.action_packet_count_var.get(),
            'action_records': self.action_records,
        }

        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.send_threads = []
        for conn in enabled_connections:
            thread = ConnectionSendThread(self, mode, conn, common_params,
                                          curve_num=curve_num, command_codes=command_codes)
            self.send_threads.append(thread)
            thread.start()
        self.log(f"已启动 {len(self.send_threads)} 个发送线程 (模式={mode})")

    def stop_sending(self):
        for thread in self.send_threads:
            thread.stop()
        self.send_threads.clear()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.log("停止信号已发送")

    # ===================== 状态保存与恢复 =====================
    def save_state(self):
        state = {
            'dst_ip': self.dst_ip_var.get(),
            'dst_port': self.dst_port_var.get(),
            'cabinet_no': self.cabinet_no_var.get(),
            'freq': self.freq_var.get(),
            'volt_min': self.volt_min_var.get(),
            'volt_max': self.volt_max_var.get(),
            'interval': self.interval_var.get(),
            'db_port': self.db_port_var.get(),
            'db_user': self.db_user_var.get(),
            'db_pass': self.db_pass_var.get(),
            'db_name': self.db_name_var.get(),
            'import_master': self.import_master_var.get(),
            'import_start_port': self.import_start_port_var.get(),
            'filter_ip_enabled': self.filter_ip_enabled.get(),
            'curve_num': self.curve_num_var.get(),
            'overcar_protocol': self.overcar_protocol_var.get(),
            'history_protocol': self.history_protocol_var.get(),
            'selected_tab': self.notebook.index(self.notebook.select()),
            'curve_cmd_selected': [cmd for cmd, var in self.curve_cmd_vars.items() if var.get()],
            'action_point_count': self.action_point_count_var.get(),
            'action_direction': self.action_direction_var.get(),
            'action_packet_count': self.action_packet_count_var.get(),
            'connections': self.connections,
            'action_records': self.action_records,
        }
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"保存状态失败: {e}")

    def load_state(self):
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            self.dst_ip_var.set(state.get('dst_ip', '192.168.1.249'))
            self.dst_port_var.set(state.get('dst_port', 7001))
            self.cabinet_no_var.set(state.get('cabinet_no', 250))
            self.freq_var.set(state.get('freq', 1))
            self.volt_min_var.set(state.get('volt_min', 600))
            self.volt_max_var.set(state.get('volt_max', 800))
            self.interval_var.set(state.get('interval', 2.0))
            self.db_port_var.set(state.get('db_port', 3306))
            self.db_user_var.set(state.get('db_user', 'root'))
            self.db_pass_var.set(state.get('db_pass', 'mysql'))
            self.db_name_var.set(state.get('db_name', 'base'))
            self.import_master_var.set(state.get('import_master', ''))
            self.import_start_port_var.set(state.get('import_start_port', 10000))
            self.filter_ip_enabled.set(state.get('filter_ip_enabled', True))
            self.curve_num_var.set(state.get('curve_num', 50))
            self.overcar_protocol_var.set(state.get('overcar_protocol', 'KAD_1'))
            self.history_protocol_var.set(state.get('history_protocol', 'KAD_1'))

            self.action_point_count_var.set(state.get('action_point_count', 50))
            self.action_direction_var.set(state.get('action_direction', "0x50 定位到定位"))
            self.action_packet_count_var.set(state.get('action_packet_count', 1))

            tab_index = state.get('selected_tab', 0)
            if 0 <= tab_index < self.notebook.index('end'):
                self.notebook.select(tab_index)

            selected_cmds = state.get('curve_cmd_selected', [])
            for cmd, var in self.curve_cmd_vars.items():
                var.set(cmd in selected_cmds)

            connections = state.get('connections', [])
            self.clear_connections()
            self.connections = connections
            for conn in connections:
                self.conn_tree.insert('', tk.END, values=(
                    conn['src_ip'], conn['src_port'], conn['station'], conn['master'],
                    conn['overcar_device_count'], conn['history_device_count'],
                    conn.get('station_door_voltage_count', 0), conn['curve_analysis_count'],
                    "是" if conn.get('enabled', True) else "否"))

            action_records = state.get('action_records', [])
            self.action_records = action_records
            for item in self.action_tree.get_children():
                self.action_tree.delete(item)
            total = 0
            for rec in action_records:
                curve_details = ",".join([f"{c['line_no']}" for c in rec.get('curves', [])])
                self.action_tree.insert('', tk.END, values=(
                    rec.get('file_name', ''), rec.get('device_seq', ''), rec.get('device_name', ''),
                    "6", curve_details))
                total += 1
            self.action_curve_count_label.config(text=str(total))

            self.update_db_host_label()
        except Exception as e:
            self.log(f"加载状态失败: {e}")

    def on_closing(self):
        self.save_state()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = SimulatorGUI()
    app.run()