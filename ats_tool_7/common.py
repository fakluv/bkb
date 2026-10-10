import struct
import time
import zlib
import re

def float_to_hex(f):
    return ' '.join(f'{b:02X}' for b in struct.pack('>f', f))

def data_format(data, num=2):
    data = data.replace(" ", "")
    parts = [data[i:i + num] for i in range(0, len(data), num)]
    return ' '.join(parts).upper()

def fix_str(data, num=2, ishead=True, fix_character='0'):
    str_len = len(data)
    if ishead:
        if str_len < num:
            data = fix_character * (num - str_len) + data
    else:
        if str_len < num:
            data = data + fix_character * (num - str_len)
    return data

def str_reverse(data, num=2):
    deal = []
    data = data.replace(' ', '')
    for i in range(int(len(data) / num)):
        deal.append(data[num * i:num * (i + 1)])
    return ''.join(deal[::-1])

def int_to_hex(data, num=2):
    data = int(data)
    data_hex = hex(data)[2:]
    if len(data_hex) > num:
        num = ((len(data_hex) + 1) // 2) * 2
    return fix_str(data_hex, num).upper()

def deal_data(data):
    regex = re.compile(r'(#)(.*)(#)')
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
            ori_time = int(time.time())
            stamp_time = time.localtime(ori_time)
            time_mon = hex(stamp_time[1])[2:]
            time_day = hex(stamp_time[2])[2:]
            time_hour = hex(stamp_time[3])[2:]
            time_min = hex(stamp_time[4])[2:]
            time_second = hex(stamp_time[5])[2:]
            part_time = ''.join([fix_str(x) for x in [time_mon, time_day, time_hour, time_min, time_second]])
            if 'R' in old_time_hex.upper():
                isreversetime = True
            else:
                isreversetime = False
            time_hex = old_time_hex.replace('R', '')
            time_len = len(time_hex)
            if time_len == 8:
                hex_time = hex(ori_time)[2:]
                if isreversetime:
                    hex_time = str_reverse(hex_time)
            elif time_len == 12:
                time_year = hex(stamp_time[0] - 2000)[2:]
                time_year = fix_str(time_year)
                hex_time = time_year + part_time
                if isreversetime:
                    hex_time = str_reverse(hex_time)
            elif time_len == 14 or time_len == 18:
                time_year = hex(stamp_time[0])[2:]
                time_year = fix_str(time_year, 4)
                if isreversetime:
                    time_year = str_reverse(time_year)
                hex_time = time_year + part_time
                if time_len == 18:
                    millionsecond_int = int(str(ori_time - int(ori_time))[2:5])
                    millionsecond_hex = fix_str(hex(millionsecond_int)[2:], 4)
                    if isreversetime:
                        millionsecond_hex = str_reverse(millionsecond_hex)
                    hex_time = hex_time + millionsecond_hex
            else:
                hex_time = hex(ori_time)[2:]
                if isreversetime:
                    hex_time = str_reverse(hex_time)
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
    data5 = data4.replace('（', '(').replace('）', ')')
    if '(' in data5 and ')' in data5:
        if frame_len_int != 0:
            start_index = data4.index('(')
            end_index = data4.index(')')
            len_part_code = data4[start_index:end_index + 1]
            new_len_part_code = len_part_code.replace('R', '')
            len_byte = int(len(new_len_part_code) - 2)
            len_byte_hex = int_to_hex(frame_len_int, len_byte)
            if 'R' in len_part_code:
                len_byte_hex = str_reverse(len_byte_hex)
            data5 = data4[0:start_index] + len_byte_hex + data4[end_index + 1:]
        else:
            data5 = data4.replace('(', '').replace(')', '')
    return data_format(data5)

def calculate_crc(data: bytes) -> bytes:
    crc = zlib.crc32(data) & 0xFFFFFFFF
    return struct.pack('>I', crc)

def calculate_crc_with_version(body: bytes, version: str, version_no: int = 0x2002) -> bytes:
    if version_ge(version, "12.0"):
        frame_len = len(body) + 4
        crc_data = struct.pack('>H', version_no) + struct.pack('>H', frame_len) + body
    else:
        crc_data = body
    return calculate_crc(crc_data)

# -------------------- 状态映射 --------------------
ALARM_TYPE_MAP = {
    "01": 1, "02": 2, "03": 3, "04": 4, "05": 5,
    "14": 0x14, "15": 0x15, "16": 0x16, "17": 0x17, "18": 0x18, "19": 0x19,
    "20": 0x20,
}

def alarm_status_description(status_byte: int, dev_type: str) -> str:
    if dev_type == "05":
        parts = []
        if not (status_byte & 0x01):
            parts.append("黄网未连接")
        if not (status_byte & 0x02):
            parts.append("紫网未连接")
        if not (status_byte & 0x04):
            parts.append("直连黄网未连接")
        if not (status_byte & 0x08):
            parts.append("直连紫网未连接")
        return "报警恢复" if not parts else ",".join(parts)
    elif dev_type == "04":
        return {0x55: "主状态", 0x33: "备状态", 0xaa: "维护态", 0x00: "与维护工作站通信中断"}.get(status_byte, "未知")
    elif dev_type in ("01", "02", "03", "20"):
        return {0x55: "正常", 0xaa: "中断", 0x33: "未知"}.get(status_byte, "未知")
    elif dev_type in ("14", "15", "16", "17", "18", "19"):
        return {0x55: "正常", 0xaa: "中断", 0x33: "未知"}.get(status_byte, "未知")
    return "未知"

def version_tuple(v):
    return tuple(map(int, v.split('.')))

def version_ge(v, target):
    return version_tuple(v) >= version_tuple(target)

# 站场状态映射
SIGNAL_LAMP_MAP = {"未知": 0, "单红": 1, "单绿": 2, "单黄": 3, "单白": 4, "红黄": 5, "单蓝": 6}
SECTION_OCCUPY_MAP = {"未占用": 0, "通信车占用": 1, "非通信车占用": 2, "通信车占用和非通信车占用": 3}
SECTION_LOCK_MAP = {"空闲": 0, "上电锁闭": 1, "进路锁闭": 3, "故障锁闭": 4, "保护锁闭": 5, "跳跃锁闭": 6}
SWITCH_POS_MAP = {"四开": 0, "定位": 1, "反位": 2, "挤岔": 3}
PSD_STATUS_MAP = {0x55: "关", 0xAA: "开", 0xFF: "互锁解除"}
EB_STATUS_MAP = {0x55: "按钮被按下", 0xAA: "按钮处于释放状态"}
REGULATION_MAP = {0: "未知", 1: "遥控", 2: "站控", 4: "紧急站控"}