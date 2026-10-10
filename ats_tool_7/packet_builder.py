import struct
import time
import random
from common import (fix_str, str_reverse, float_to_hex, calculate_crc, int_to_hex, deal_data,
                    ALARM_TYPE_MAP, alarm_status_description,
                    SIGNAL_LAMP_MAP, SECTION_OCCUPY_MAP, SECTION_LOCK_MAP,
                    SWITCH_POS_MAP, PSD_STATUS_MAP, EB_STATUS_MAP, REGULATION_MAP,
                    calculate_crc_with_version, version_ge)

# ------------------------------------------------------------
# 全局序列号
# ------------------------------------------------------------
_sequence_number = 0

def get_next_sequence():
    global _sequence_number
    _sequence_number = (_sequence_number + 1) & 0xFFFFFFFF
    return _sequence_number

# ------------------------------------------------------------
# 报警模式
# ------------------------------------------------------------
def build_alarm_packet(selected_devices, common_status=None, version="11.0", dev_type_map=None, device_statuses=None):
    """
    selected_devices: list of (dev_id, dev_name, site, dev_type)
    common_status: 默认状态，如果 device_statuses 为空则使用此状态
    device_statuses: dict mapping device index (0-based) to status byte, 覆盖 common_status
    """
    if dev_type_map is None:
        dev_type_map = ALARM_TYPE_MAP
    line_id = 0x00000068
    msg_type = 0x51
    timestamp = int(time.time())
    seq = get_next_sequence()
    device_count = len(selected_devices)

    body = bytearray()
    body.append(msg_type)
    body.extend(struct.pack('>I', line_id))
    body.extend(struct.pack('>I', timestamp))
    body.extend(struct.pack('>I', seq))
    body.extend(struct.pack('>H', device_count))

    for idx, (dev_id, dev_name, site, orig_type) in enumerate(selected_devices):
        actual_type = dev_type_map.get(orig_type, int(orig_type) if orig_type.isdigit() else 0)
        body.extend(b'\x00\x00')
        body.append(actual_type)
        body.extend(struct.pack('>H', dev_id))
        if device_statuses and idx in device_statuses:
            status = device_statuses[idx]
        else:
            status = common_status if common_status is not None else 0x55
        body.append(status)
        if version_ge(version, "11.0"):
            body.append(0x00)

    crc_bytes = calculate_crc_with_version(body, version)
    frame_len = len(body) + 4
    header = bytearray([0xAA, 0x20, 0x02]) + struct.pack('>H', frame_len)
    packet = header + body + crc_bytes + b'\x55'

    lines = []
    lines.append("AA #帧开始标志#")
    lines.append("20 02 #应用层通信协议版本号#")
    lines.append(f"({frame_len:04X}) #帧长度(从MSG_ID开始到CRC校验结束)#")
    lines.append("<")
    lines.append("51 #Message Type#")
    lines.append("00 00 00 68 #线路ID#")
    ts_hex = f"{timestamp:08X}"
    lines.append(f"[{' '.join(ts_hex[i:i + 2] for i in range(0, 8, 2))}] #时间戳#")
    seq_hex = f"{seq:08X}"
    lines.append(f"{' '.join(seq_hex[i:i + 2] for i in range(0, 8, 2))} #报文序列号#")
    lines.append(f"{device_count:04X} #设备运行总数#")

    for idx, (dev_id, dev_name, site, orig_type) in enumerate(selected_devices):
        if device_statuses and idx in device_statuses:
            status = device_statuses[idx]
        else:
            status = common_status if common_status is not None else 0x55
        dev_bytes = bytearray()
        dev_bytes.extend(b'\x00\x00')
        actual_type = dev_type_map.get(orig_type, int(orig_type) if orig_type.isdigit() else 0)
        dev_bytes.append(actual_type)
        dev_bytes.extend(struct.pack('>H', dev_id))
        dev_bytes.append(status)
        if version_ge(version, "11.0"):
            dev_bytes.append(0x00)
        hex_str = ' '.join(f'{b:02X}' for b in dev_bytes)
        desc = alarm_status_description(status, orig_type)
        lines.append(f"{hex_str}   # {site} - {dev_name} (ID:{dev_id}, 类型:{orig_type}) {desc} #")

    crc_hex = ' '.join(f'{b:02X}' for b in crc_bytes)
    lines.append(f"{crc_hex} #CRC校验#")
    lines.append(">")
    lines.append("55 #帧的结束标识#")
    return packet, '\n'.join(lines)

def build_alarm_base_packet(selected_devices, common_status=None, version="11.0", dev_type_map=None, device_statuses=None):
    if dev_type_map is None:
        dev_type_map = ALARM_TYPE_MAP
    line_id = 0x00000068
    msg_type = 0x51
    timestamp = 0
    seq = get_next_sequence()
    device_count = len(selected_devices)

    body = bytearray()
    body.append(msg_type)
    body.extend(struct.pack('>I', line_id))
    timestamp_pos = len(body)
    body.extend(struct.pack('>I', timestamp))
    body.extend(struct.pack('>I', seq))
    body.extend(struct.pack('>H', device_count))

    for idx, (dev_id, dev_name, site, orig_type) in enumerate(selected_devices):
        actual_type = dev_type_map.get(orig_type, int(orig_type) if orig_type.isdigit() else 0)
        body.extend(b'\x00\x00')
        body.append(actual_type)
        body.extend(struct.pack('>H', dev_id))
        if device_statuses and idx in device_statuses:
            status = device_statuses[idx]
        else:
            status = common_status if common_status is not None else 0x55
        body.append(status)
        if version_ge(version, "11.0"):
            body.append(0x00)

    crc_bytes = calculate_crc_with_version(body, version)
    frame_len = len(body) + 4
    header = bytearray([0xAA, 0x20, 0x02]) + struct.pack('>H', frame_len)
    packet = header + body + crc_bytes + b'\x55'
    return packet, timestamp_pos   # 返回相对于 body 的偏移

# ------------------------------------------------------------
# 性能模式
# ------------------------------------------------------------
def get_default_thresholds(version):
    thread_threshold = 500 if version in ['9.0', '10.0', '11.0', '12.0'] else 300
    return {
        'disk_free': 5.0,
        'cpu': 75,
        'memory': 1024,
        'handles': 5000,
        'threads': thread_threshold,
        'dmp': 0,
        'disk_total_min': 10.1,
        'disk_total_max': 20.0,
        'run_time_min': 0,
        'run_time_max': 100,
        'cpu_temp_min': 0,
        'cpu_temp_max': 84
    }

PERF_DIRECTIONS = {
    'disk_free': False,
    'cpu': True,
    'memory': True,
    'handles': True,
    'threads': True,
    'dmp': True
}

PERF_RANGES = {
    'disk_free': (1.0, 10.0),
    'cpu': (0, 100),
    'memory': (500, 5096),
    'handles': (0, 10000),
    'threads': (0, 1000),
    'dmp': (0, 10)
}

def generate_value(mode, threshold, value_range, is_greater_alarm=True):
    min_val, max_val = value_range
    if mode == 'recovery':
        if is_greater_alarm:
            low = min_val
            high = min(threshold, max_val)
            if low > high:
                high = low
            return random.randint(int(low), int(high))
        else:
            low = max(threshold, min_val)
            high = max_val
            if low > high:
                low = high
            return random.uniform(low, high)
    else:
        if is_greater_alarm:
            low = max(threshold + 1, min_val)
            high = max_val
            if low > high:
                low = high
            return random.randint(int(low), int(high))
        else:
            low = min_val
            high = min(threshold - 0.1, max_val)
            if low > high:
                high = low
            return random.uniform(low, high)

def generate_perf_packet_by_version(version, mode, device_id_dec, device_name="", thresholds=None, extra_ranges=None):
    device_id_hex = ' '.join(f'{b:02X}' for b in struct.pack('>H', device_id_dec))

    if thresholds is None:
        thresholds = get_default_thresholds(version)
    disk_free_gb = generate_value(mode, thresholds['disk_free'], PERF_RANGES['disk_free'],
                                  PERF_DIRECTIONS['disk_free'])
    cpu_percent = generate_value(mode, thresholds['cpu'], PERF_RANGES['cpu'], PERF_DIRECTIONS['cpu'])
    memory_mb = generate_value(mode, thresholds['memory'], PERF_RANGES['memory'], PERF_DIRECTIONS['memory'])
    handles = generate_value(mode, thresholds['handles'], PERF_RANGES['handles'], PERF_DIRECTIONS['handles'])
    threads = generate_value(mode, thresholds['threads'], PERF_RANGES['threads'], PERF_DIRECTIONS['threads'])
    dmp_count = generate_value(mode, thresholds['dmp'], PERF_RANGES['dmp'], PERF_DIRECTIONS['dmp'])

    disk_free_hex = float_to_hex(disk_free_gb)
    cpu_hex = f"{cpu_percent:02X}"
    memory_hex = f"{(memory_mb >> 8) & 0xFF:02X} {memory_mb & 0xFF:02X}"
    handles_hex = f"{(handles >> 8) & 0xFF:02X} {handles & 0xFF:02X}"
    threads_hex = f"{(threads >> 8) & 0xFF:02X} {threads & 0xFF:02X}"
    dmp_hex = f"{dmp_count:02X}"

    packet = f"[00 00 D6 45]\n{device_id_hex}  # ATS内部设备ID={device_id_dec}#\n"
    packet += f"{disk_free_hex}  # 机械硬盘空闲空间={disk_free_gb:.1f}G#\n"
    packet += f"{cpu_hex}  # CPU使用率={cpu_percent}%#\n"
    packet += f"{memory_hex}  # 物理内存量={memory_mb}M#\n"
    packet += f"{handles_hex}  # 打开的句柄数={handles}#\n"
    packet += f"{threads_hex}  # 活动线程数={threads}#\n"
    packet += f"{dmp_hex}  # 本周期产生dmp={dmp_count}#\n"



    if version in ['10.0', '11.0', '12.0']:
        if extra_ranges and 'disk_total' in extra_ranges:
            dmin, dmax = extra_ranges['disk_total']
        else:
            dmin, dmax = thresholds.get('disk_total_min', 10.1), thresholds.get('disk_total_max', 20.0)
        disk_total_gb = random.uniform(dmin, dmax)
        disk_total_hex = f"00 {int(disk_total_gb):02X}"
        packet += f"{disk_total_hex}  # 硬盘总空间={disk_total_gb:.1f}G#\n"

    if version == '10.0':
        packet += f"00 00 00 00 00 #预留#\n"

    if version in ['11.0', '12.0']:
        if mode == 'recovery':
            if extra_ranges and 'run_time_recovery' in extra_ranges:
                rt_min, rt_max = extra_ranges['run_time_recovery']
            else:
                rt_min, rt_max = thresholds.get('run_time_min', 0), thresholds.get('run_time_max', 100)
            run_time_seconds = random.randint(int(rt_min), int(rt_max))
            if extra_ranges and 'cpu_temp_recovery' in extra_ranges:
                ct_min, ct_max = extra_ranges['cpu_temp_recovery']
            else:
                ct_min, ct_max = thresholds.get('cpu_temp_min', 0), thresholds.get('cpu_temp_max', 84)
            cpu_temp = random.randint(int(ct_min), int(ct_max))
        else:
            if extra_ranges and 'run_time_alarm' in extra_ranges:
                rt_min, rt_max = extra_ranges['run_time_alarm']
            else:
                rt_min, rt_max = 7776001, 155520000
            run_time_seconds = random.randint(int(rt_min), int(rt_max))
            if extra_ranges and 'cpu_temp_alarm' in extra_ranges:
                ct_min, ct_max = extra_ranges['cpu_temp_alarm']
            else:
                ct_min, ct_max = 86, 100
            cpu_temp = random.randint(int(ct_min), int(ct_max))
        run_time_hex = ' '.join(f'{b:02X}' for b in struct.pack('>I', run_time_seconds))
        cpu_temp_hex = f"{cpu_temp:02X}"
        packet += f"{run_time_hex}  # 系统运行时间={run_time_seconds}秒#\n"
        packet += f"{cpu_temp_hex}  # CPU温度={cpu_temp}℃#"

    return packet

def build_full_perf_packet_raw(selected_devices, mode, version, thresholds=None, extra_ranges=None):
    if not selected_devices:
        return None
    selected_devices_sorted = sorted(selected_devices, key=lambda x: x['id'])
    device_packets_raw = []
    for dev in selected_devices_sorted:
        device_packets_raw.append(
            generate_perf_packet_by_version(version, mode, dev['id'], dev['name'], thresholds, extra_ranges))
    device_count = len(selected_devices_sorted)
    device_count_hex = format(device_count, '02X')
    device_data_str = "\n\n".join(device_packets_raw)
    seq = get_next_sequence()
    seq_hex = f"{seq:08X}"
    seq_hex_str = ' '.join(seq_hex[i:i + 2] for i in range(0, 8, 2))
    template = f"""AA 
20 02 
(00 25) 
{{
58 
00 00 00 89 
[66 0B BB 21]
{seq_hex_str}
00 {device_count_hex} #设备个数#

{device_data_str}

B5 52 7E 43
}} 
55"""
    return template

def build_full_perf_packet_clean(selected_devices, mode, version, thresholds=None, extra_ranges=None):
    raw_template = build_full_perf_packet_raw(selected_devices, mode, version, thresholds, extra_ranges)
    if not raw_template:
        return None
    return deal_data(raw_template)

def build_full_perf_packet_raw_bytes(selected_devices, mode, version, thresholds=None, extra_ranges=None):
    raw = build_full_perf_packet_raw(selected_devices, mode, version, thresholds, extra_ranges)
    if raw:
        return bytes.fromhex(deal_data(raw).replace(" ", ""))
    return None

def _build_perf_device_bytes(dev, mode, version, thresholds=None, extra_ranges=None):
    device_id = dev['id']
    if thresholds is None:
        thresholds = get_default_thresholds(version)
    disk_free_gb = generate_value(mode, thresholds['disk_free'], PERF_RANGES['disk_free'],
                                  PERF_DIRECTIONS['disk_free'])
    cpu_percent = generate_value(mode, thresholds['cpu'], PERF_RANGES['cpu'], PERF_DIRECTIONS['cpu'])
    memory_mb = generate_value(mode, thresholds['memory'], PERF_RANGES['memory'], PERF_DIRECTIONS['memory'])
    handles = generate_value(mode, thresholds['handles'], PERF_RANGES['handles'], PERF_DIRECTIONS['handles'])
    threads = generate_value(mode, thresholds['threads'], PERF_RANGES['threads'], PERF_DIRECTIONS['threads'])
    dmp_count = generate_value(mode, thresholds['dmp'], PERF_RANGES['dmp'], PERF_DIRECTIONS['dmp'])

    data = bytearray()
    data.extend(struct.pack('>H', device_id))
    data.extend(struct.pack('>f', disk_free_gb))
    data.append(cpu_percent & 0xFF)
    data.extend(struct.pack('>H', memory_mb))
    data.extend(struct.pack('>H', handles))
    data.extend(struct.pack('>H', threads))
    data.append(dmp_count & 0xFF)

    if version in ['10.0', '11.0', '12.0']:
        if extra_ranges and 'disk_total' in extra_ranges:
            dmin, dmax = extra_ranges['disk_total']
        else:
            dmin, dmax = thresholds.get('disk_total_min', 10.1), thresholds.get('disk_total_max', 20.0)
        disk_total_gb = random.uniform(dmin, dmax)
        data.extend(struct.pack('>H', int(disk_total_gb)))

    if version == "10.0":
        data.extend(b'\x00\x00\x00\x00\x00')

    if version in ['11.0', '12.0']:
        if mode == 'recovery':
            if extra_ranges and 'run_time_recovery' in extra_ranges:
                rt_min, rt_max = extra_ranges['run_time_recovery']
            else:
                rt_min, rt_max = thresholds.get('run_time_min', 0), thresholds.get('run_time_max', 100)
            run_time = random.randint(int(rt_min), int(rt_max))
            if extra_ranges and 'cpu_temp_recovery' in extra_ranges:
                ct_min, ct_max = extra_ranges['cpu_temp_recovery']
            else:
                ct_min, ct_max = thresholds.get('cpu_temp_min', 0), thresholds.get('cpu_temp_max', 84)
            cpu_temp = random.randint(int(ct_min), int(ct_max))
        else:
            if extra_ranges and 'run_time_alarm' in extra_ranges:
                rt_min, rt_max = extra_ranges['run_time_alarm']
            else:
                rt_min, rt_max = 7776001, 155520000
            run_time = random.randint(int(rt_min), int(rt_max))
            if extra_ranges and 'cpu_temp_alarm' in extra_ranges:
                ct_min, ct_max = extra_ranges['cpu_temp_alarm']
            else:
                ct_min, ct_max = 86, 100
            cpu_temp = random.randint(int(ct_min), int(ct_max))
        data.extend(struct.pack('>I', run_time))
        data.append(cpu_temp & 0xFF)

    comment = f"设备ID={device_id} {dev.get('name','')}"
    return data, comment

def build_perf_base_packet(selected_devices, mode, version, thresholds=None, extra_ranges=None):
    if not selected_devices:
        return None, None
    sorted_devices = sorted(selected_devices, key=lambda x: x['id'])

    body = bytearray()
    body.append(0x58)                     # MSG_ID
    body.extend(struct.pack('>I', 0x00000089))  # LINE_NUM
    timestamp_pos_head = len(body)        # 头部时间戳位置
    body.extend(struct.pack('>I', 0))     # STAMP placeholder
    body.extend(struct.pack('>I', get_next_sequence()))  # SN
    body.extend(struct.pack('>H', len(sorted_devices)))  # 设备个数

    timestamp_indices = [timestamp_pos_head]   # 先记录头部时间戳偏移

    for dev in sorted_devices:
        ts_pos = len(body)
        body.extend(struct.pack('>I', 0))
        timestamp_indices.append(ts_pos)

        dev_bytes, _ = _build_perf_device_bytes(dev, mode, version, thresholds, extra_ranges)
        body.extend(dev_bytes)

    crc_bytes = calculate_crc_with_version(body, version)
    frame_len = len(body) + 4
    header = bytearray([0xAA, 0x20, 0x02]) + struct.pack('>H', frame_len)
    packet = header + body + crc_bytes + b'\x55'
    return packet, timestamp_indices

# ------------------------------------------------------------
# 站场模式
# ------------------------------------------------------------
def compute_signal_status_byte(status):
    byte1 = 0x00
    if status['封锁状态'] == '未封锁':
        byte1 |= 0x80
    if status['亮灭状态'] == '灭':
        byte1 |= 0x40
    if status['灯丝断丝状态'] == '未断丝':
        byte1 |= 0x20
    if status['限速状态'] == '限速':
        byte1 |= 0x10
    lamp_val = SIGNAL_LAMP_MAP.get(status['灯位状态'], 0)
    byte1 |= (lamp_val & 0x0F)
    return byte1

def compute_section_status_bytes(status):
    byte1 = 0x00
    if status['联锁限速'] == '有限速':
        byte1 |= 0x01
    if status['封锁状态'] == '未封锁':
        byte1 |= 0x02
    if status['ARB状态'] == '无ARB':
        byte1 |= 0x04
    occupy_val = SECTION_OCCUPY_MAP.get(status['占用状态'], 0)
    byte1 |= (occupy_val & 0x03) << 3
    lock_val = SECTION_LOCK_MAP.get(status['锁闭状态'], 0)
    byte1 |= (lock_val & 0x07) << 5

    byte4 = 0x00
    if status['逻辑区段是否有效'] == '有效':
        byte4 |= 0x40
    if status['区段切除'] == '未切除':
        byte4 |= 0x80
    return byte1, byte4

def compute_switch_status_byte(status):
    byte_val = 0x00
    pos_val = SWITCH_POS_MAP.get(status.get('道岔位置', '四开'), 0)
    byte_val |= (pos_val & 0x03) << 6
    if status.get('单锁状态', '未单锁') == '未单锁':
        byte_val |= 0x20
    if status.get('封锁状态', '未封锁') == '未封锁':
        byte_val |= 0x10
    if status.get('引导总锁', '未引导总锁') == '未引导总锁':
        byte_val |= 0x08
    return byte_val

def parse_train_tracking(data: bytes) -> list:
    lines = []
    offset = 0
    val = struct.unpack_from('>H', data, offset)[0]; offset += 2
    lines.append(f"{val:04X} #车站编号#")
    val = struct.unpack_from('>H', data, offset)[0]; offset += 2
    lines.append(f"{val:04X} #列车总数#")
    val = struct.unpack_from('>H', data, offset)[0]; offset += 2
    lines.append(f"{val:04X} #列车车组号#")
    val = struct.unpack_from('>H', data, offset)[0]; offset += 2
    lines.append(f"{val:04X} #表号#")
    val = struct.unpack_from('>H', data, offset)[0]; offset += 2
    lines.append(f"{val:04X} #车次号#")
    length = data[offset]; offset += 1
    dest = data[offset:offset + length]; offset += length
    dest_hex = ' '.join(f'{b:02X}' for b in dest)
    lines.append(f"{length:02X} #目的地编码长度#")
    lines.append(f"{dest_hex} #目的地编码#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #列车类别#")
    val = struct.unpack_from('>H', data, offset)[0]; offset += 2
    lines.append(f"{val:04X} #司机编号#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #是否有ATP防护#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #列车时刻信息#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #是否跳停#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #扣车状态#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #驾驶模式#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #车轮方向#")
    val = struct.unpack_from('>H', data, offset)[0]; offset += 2
    lines.append(f"{val:04X} #逻辑区段#")
    val = struct.unpack_from('>H', data, offset)[0]; offset += 2
    lines.append(f"{val:04X} #逻辑区段位置编码#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #是否冲突#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #列车停稳信息#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #车门状态#")
    val = struct.unpack_from('>i', data, offset)[0]; offset += 4
    lines.append(f"{' '.join(f'{b:02X}' for b in struct.pack('>i', val))} #早晚点，计划偏差秒数#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #控制级别#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #是否ATP切除#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #休眠唤醒状态#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #是否通信车#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #激活端#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #工况#")
    length = data[offset]; offset += 1
    lines.append(f"{length:02X} #回段字符串长度#")
    if length > 0:
        str_bytes = data[offset:offset + length]; offset += length
        str_hex = ' '.join(f'{b:02X}' for b in str_bytes)
        lines.append(f"{str_hex} #字符串对应ASCLL码#")
    else:
        lines.append("00 #字符串对应ASCLL码（无）#")
    length = data[offset]; offset += 1
    lines.append(f"{length:02X} #工程车标记字符串长度#")
    if length > 0:
        str_bytes = data[offset:offset + length]; offset += length
        str_hex = ' '.join(f'{b:02X}' for b in str_bytes)
        lines.append(f"{str_hex} #工程车标记名称#")
    else:
        lines.append("00 #工程车标记名称（无）#")
    val = struct.unpack_from('>I', data, offset)[0]; offset += 4
    lines.append(f"{' '.join(f'{b:02X}' for b in struct.pack('>I', val))} #车头所在link#")
    val = struct.unpack_from('>I', data, offset)[0]; offset += 4
    lines.append(f"{' '.join(f'{b:02X}' for b in struct.pack('>I', val))} #车头所在LINK偏移量#")
    val = struct.unpack_from('>I', data, offset)[0]; offset += 4
    lines.append(f"{' '.join(f'{b:02X}' for b in struct.pack('>I', val))} #车尾所在link#")
    val = struct.unpack_from('>I', data, offset)[0]; offset += 4
    lines.append(f"{' '.join(f'{b:02X}' for b in struct.pack('>I', val))} #车尾所在link偏移量#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #是否VOBC报警#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #是否车辆报警#")
    val = data[offset]; offset += 1
    lines.append(f"{val:02X} #是否火灾报警#")
    val = struct.unpack_from('>H', data, offset)[0]; offset += 2
    lines.append(f"{val:04X} #源线路号#")
    val = struct.unpack_from('>H', data, offset)[0]; offset += 2
    lines.append(f"{val:04X} #目的线路号#")
    val = struct.unpack_from('>H', data, offset)[0]; offset += 2
    lines.append(f"{val:04X} #目的停车区域编号#")
    reserved = data[offset:offset + 2]; offset += 2
    lines.append(f"{' '.join(f'{b:02X}' for b in reserved)} #预留两个字节#")
    return lines

def build_station_status_packet_full(selected_signals, signal_status, selected_sections, section_status,
                                     selected_switches, switch_status, regulation_status=1,
                                     selected_psds=None, psd_status=0x55,
                                     selected_em_brakes=None, em_brake_status=0xAA,
                                     version="11.0"):
    if selected_psds is None:
        selected_psds = []
    if selected_em_brakes is None:
        selected_em_brakes = []
    line_id = 0x00000063
    msg_type = 0x52
    timestamp = int(time.time())
    seq = get_next_sequence()
    signal_count = len(selected_signals)
    section_count = len(selected_sections)
    switch_count = len(selected_switches)
    sorted_switches = sorted(selected_switches, key=lambda x: x['switch_id'])
    sorted_psds = sorted(selected_psds, key=lambda x: x['psd_id'])
    sorted_em_brakes = sorted(selected_em_brakes, key=lambda x: x['eb_id'])

    signal_data = bytearray()
    for sig in selected_signals:
        signal_data.extend(struct.pack('>H', sig['signal_id']))
        status_byte1 = compute_signal_status_byte(signal_status)
        signal_data.append(status_byte1)
        signal_data.extend(b'\x00\x00')
        signal_data.append(0x00)

    section_data = bytearray()
    for sec in selected_sections:
        section_data.extend(struct.pack('>H', sec['section_id']))
        byte1, byte4 = compute_section_status_bytes(section_status)
        section_data.append(byte1)
        section_data.extend(b'\x00\x00')
        section_data.append(byte4)

    switch_data = bytearray()
    for sw in sorted_switches:
        switch_data.extend(struct.pack('>I', sw['switch_id']))
        byte_val = compute_switch_status_byte(switch_status)
        switch_data.append(byte_val)

    station_status_body = bytearray()
    station_status_body.append(0x01)
    station_status_body.extend(b'\x00\x01')
    station_status_body.extend(struct.pack('>H', signal_count))
    station_status_body.extend(signal_data)
    station_status_body.extend(struct.pack('>H', section_count))
    station_status_body.extend(section_data)
    station_status_body.extend(struct.pack('>H', switch_count))
    station_status_body.extend(switch_data)
    station_status_body.append(regulation_status)
    psd_count = len(sorted_psds)
    station_status_body.extend(struct.pack('>H', psd_count))
    for psd in sorted_psds:
        station_status_body.extend(struct.pack('>I', psd['psd_id']))
        station_status_body.append(psd_status)
    eb_count = len(sorted_em_brakes)
    station_status_body.extend(struct.pack('>H', eb_count))
    for eb in sorted_em_brakes:
        station_status_body.extend(struct.pack('>I', eb['eb_id']))
        station_status_body.append(em_brake_status)
    station_status_body.extend(b'\x00\x00')
    station_status_body.extend(b'\x00\x00')
    station_status_body.extend(b'\x00\x00')
    station_status_len = len(station_status_body)

    train_tracking_data = b'\x00\x01\x00\x01\x00\x0c\x00\x0c\x00\x0d\x02\x00\x05\x01\x00\x02\x01\x02\x00\x00\x03\x01\x00\x3f\x00\x01\x00\x00\x01\x02\x00\x00\x00\xfb\x02\x00\x01\x01\x55\x03\x02\x00\x00\x02\x00\x00\x00\x00\x00\x0e\x00\x00\x00\x00\x00\x00\x00\x0e\x00\x00\x35\x84\x00\x00\x00\x00\x6b\x00\x6b\x00\x30\x00\x00'

    body = bytearray()
    body.append(msg_type)
    body.extend(struct.pack('>I', line_id))
    body.extend(struct.pack('>I', timestamp))
    body.extend(struct.pack('>I', seq))
    body.extend(struct.pack('>H', station_status_len))
    body.extend(station_status_body)
    body.extend(b'\x00\x00')
    body.extend(b'\x00\x48')
    body.extend(train_tracking_data)
    body.extend(b'\x00\x00')
    body.extend(b'\x00\x00')
    body.extend(b'\x00\x00')

    crc_bytes = calculate_crc_with_version(body, version)
    frame_len = len(body) + 4
    header = bytearray([0xAA, 0x20, 0x02]) + struct.pack('>H', frame_len)
    packet = header + body + crc_bytes + b'\x55'

    lines = []
    lines.append("AA #帧开始标志#")
    lines.append("20 02 #应用层通信协议版本号#")
    lines.append(f"({frame_len:04X}) #帧长度(从MSG_ID开始到CRC校验结束)#")
    lines.append("<")
    lines.append("52 #Message Type#")
    lines.append("00 00 00 63 #线路ID#")
    ts_hex = f"{timestamp:08X}"
    lines.append(f"[{' '.join(ts_hex[i:i + 2] for i in range(0, 8, 2))}] #时间戳#")
    seq_hex = f"{seq:08X}"
    lines.append(f"[{' '.join(seq_hex[i:i + 2] for i in range(0, 8, 2))}] #报文序列号#")
    lines.append("")
    lines.append(f"{station_status_len:04X} #站场状态数据长度 {station_status_len} #")
    lines.append("01 #联锁数量#")
    lines.append("00 01 #联锁ID#")
    lines.append("")
    lines.append(f"{signal_count:04X} #信号机数量#")
    for sig in selected_signals:
        id_hex = ' '.join(f'{b:02X}' for b in struct.pack('>H', sig['signal_id']))
        status_byte1 = compute_signal_status_byte(signal_status)
        status_hex = ' '.join(f'{b:02X}' for b in [status_byte1, 0x00, 0x00, 0x00])
        lines.append(f"{id_hex} {status_hex} #信号机ID={sig['signal_id']} {sig['name']} ({sig['station']}) "
                     f"状态: 封锁:{signal_status['封锁状态']}, 亮灭:{signal_status['亮灭状态']}, "
                     f"灯丝断丝:{signal_status['灯丝断丝状态']}, 限速:{signal_status['限速状态']}, 灯位:{signal_status['灯位状态']}#")
    lines.append(f"{section_count:04X} #逻辑区段数量#")
    for sec in selected_sections:
        id_hex = ' '.join(f'{b:02X}' for b in struct.pack('>H', sec['section_id']))
        byte1, byte4 = compute_section_status_bytes(section_status)
        status_hex = ' '.join(f'{b:02X}' for b in [byte1, 0x00, 0x00, byte4])
        lines.append(f"{id_hex} {status_hex} #逻辑区段ID={sec['section_id']} {sec['name']} ({sec['station']}) "
                     f"状态: 联锁限速:{section_status['联锁限速']}, 封锁:{section_status['封锁状态']}, "
                     f"ARB:{section_status['ARB状态']}, 占用:{section_status['占用状态']}, "
                     f"锁闭:{section_status['锁闭状态']}, 有效:{section_status['逻辑区段是否有效']}, 切除:{section_status['区段切除']}#")
    lines.append(f"{switch_count:04X} #道岔数量#")
    for sw in sorted_switches:
        id_hex = ' '.join(f'{b:02X}' for b in struct.pack('>I', sw['switch_id']))
        byte_val = compute_switch_status_byte(switch_status)
        status_hex = f"{byte_val:02X}"
        lines.append(f"{id_hex} {status_hex} #道岔ID={sw['switch_id']} {sw['name']} ({sw['station']}) "
                     f"状态: 位置:{switch_status['道岔位置']}, 单锁:{switch_status['单锁状态']}, "
                     f"封锁:{switch_status['封锁状态']}, 引导总锁:{switch_status['引导总锁']}#")

    reg_desc = REGULATION_MAP.get(regulation_status, "未知")
    lines.append(f"{regulation_status:02X} #调控权状态 ({reg_desc})#")

    lines.append(f"{psd_count:04X} #屏蔽门数量#")
    psd_desc = PSD_STATUS_MAP.get(psd_status, "未知")
    for psd in sorted_psds:
        id_hex = ' '.join(f'{b:02X}' for b in struct.pack('>I', psd['psd_id']))
        lines.append(f"{id_hex} {psd_status:02X} #屏蔽门ID={psd['psd_id']} ({psd['station']}) 状态={psd_desc}#")

    lines.append(f"{eb_count:04X} #紧急停车按钮数量#")
    eb_desc = EB_STATUS_MAP.get(em_brake_status, "未知")
    for eb in sorted_em_brakes:
        id_hex = ' '.join(f'{b:02X}' for b in struct.pack('>I', eb['eb_id']))
        lines.append(f"{id_hex} {em_brake_status:02X} #紧急停车按钮ID={eb['eb_id']} ({eb['station']}) 状态={eb_desc}#")

    lines.append("00 00 #折返模式总数#")
    lines.append("00 00 #自动通过进路总数#")
    lines.append("00 00 #预留2字节#")
    lines.append("00 00 #站场同步数据长度 0个byte#")
    lines.append("00 48 #车次追踪数据长度 72个byte#")
    train_lines = parse_train_tracking(train_tracking_data)
    lines.extend(train_lines)
    lines.append("00 00 #临时限速状态数据长度#")
    lines.append("00 00 #牵引供电信息长度#")
    lines.append("00 00 #主所供电信息长度#")
    lines.append(">")
    lines.append("55 #帧结束标识#")
    return packet, '\n'.join(lines)

def build_station_base_packet(selected_signals, signal_status, selected_sections, section_status,
                              selected_switches, switch_status, regulation_status=1,
                              selected_psds=None, psd_status=0x55,
                              selected_em_brakes=None, em_brake_status=0xAA,
                              version="11.0"):
    if selected_psds is None:
        selected_psds = []
    if selected_em_brakes is None:
        selected_em_brakes = []
    line_id = 0x00000063
    msg_type = 0x52
    timestamp = 0
    seq = get_next_sequence()
    signal_count = len(selected_signals)
    section_count = len(selected_sections)
    switch_count = len(selected_switches)
    sorted_switches = sorted(selected_switches, key=lambda x: x['switch_id'])
    sorted_psds = sorted(selected_psds, key=lambda x: x['psd_id'])
    sorted_em_brakes = sorted(selected_em_brakes, key=lambda x: x['eb_id'])

    signal_data = bytearray()
    for sig in selected_signals:
        signal_data.extend(struct.pack('>H', sig['signal_id']))
        status_byte1 = compute_signal_status_byte(signal_status)
        signal_data.append(status_byte1)
        signal_data.extend(b'\x00\x00')
        signal_data.append(0x00)

    section_data = bytearray()
    for sec in selected_sections:
        section_data.extend(struct.pack('>H', sec['section_id']))
        byte1, byte4 = compute_section_status_bytes(section_status)
        section_data.append(byte1)
        section_data.extend(b'\x00\x00')
        section_data.append(byte4)

    switch_data = bytearray()
    for sw in sorted_switches:
        switch_data.extend(struct.pack('>I', sw['switch_id']))
        byte_val = compute_switch_status_byte(switch_status)
        switch_data.append(byte_val)

    station_status_body = bytearray()
    station_status_body.append(0x01)
    station_status_body.extend(b'\x00\x01')
    station_status_body.extend(struct.pack('>H', signal_count))
    station_status_body.extend(signal_data)
    station_status_body.extend(struct.pack('>H', section_count))
    station_status_body.extend(section_data)
    station_status_body.extend(struct.pack('>H', switch_count))
    station_status_body.extend(switch_data)
    station_status_body.append(regulation_status)
    psd_count = len(sorted_psds)
    station_status_body.extend(struct.pack('>H', psd_count))
    for psd in sorted_psds:
        station_status_body.extend(struct.pack('>I', psd['psd_id']))
        station_status_body.append(psd_status)
    eb_count = len(sorted_em_brakes)
    station_status_body.extend(struct.pack('>H', eb_count))
    for eb in sorted_em_brakes:
        station_status_body.extend(struct.pack('>I', eb['eb_id']))
        station_status_body.append(em_brake_status)
    station_status_body.extend(b'\x00\x00')
    station_status_body.extend(b'\x00\x00')
    station_status_body.extend(b'\x00\x00')
    station_status_len = len(station_status_body)

    train_tracking_data = b'\x00\x01\x00\x01\x00\x0c\x00\x0c\x00\x0d\x02\x00\x05\x01\x00\x02\x01\x02\x00\x00\x03\x01\x00\x3f\x00\x01\x00\x00\x01\x02\x00\x00\x00\xfb\x02\x00\x01\x01\x55\x03\x02\x00\x00\x02\x00\x00\x00\x00\x00\x0e\x00\x00\x00\x00\x00\x00\x00\x0e\x00\x00\x35\x84\x00\x00\x00\x00\x6b\x00\x6b\x00\x30\x00\x00'

    body = bytearray()
    body.append(msg_type)
    body.extend(struct.pack('>I', line_id))
    timestamp_pos = len(body)
    body.extend(struct.pack('>I', timestamp))
    body.extend(struct.pack('>I', seq))
    body.extend(struct.pack('>H', station_status_len))
    body.extend(station_status_body)
    body.extend(b'\x00\x00')
    body.extend(b'\x00\x48')
    body.extend(train_tracking_data)
    body.extend(b'\x00\x00')
    body.extend(b'\x00\x00')
    body.extend(b'\x00\x00')

    crc_bytes = calculate_crc_with_version(body, version)
    frame_len = len(body) + 4
    header = bytearray([0xAA, 0x20, 0x02]) + struct.pack('>H', frame_len)
    packet = header + body + crc_bytes + b'\x55'
    return packet, timestamp_pos   # 返回相对于 body 的偏移

def build_station_preview_from_cached(selected_signals, signal_byte,
                                      selected_sections, section_byte1, section_byte4,
                                      selected_switches, switch_byte,
                                      regulation_status,
                                      selected_psds, psd_status,
                                      selected_em_brakes, em_brake_status,
                                      version="11.0"):
    lines = []
    lines.append("AA #帧开始标志#")
    lines.append("20 02 #应用层通信协议版本号#")
    line_id = 0x00000063
    msg_type = 0x52
    timestamp = int(time.time())
    seq = get_next_sequence()
    signal_count = len(selected_signals)
    section_count = len(selected_sections)
    switch_count = len(selected_switches)
    sorted_switches = sorted(selected_switches, key=lambda x: x['switch_id'])
    sorted_psds = sorted(selected_psds, key=lambda x: x['psd_id'])
    sorted_em_brakes = sorted(selected_em_brakes, key=lambda x: x['eb_id'])

    station_status_body = bytearray()
    station_status_body.append(0x01)
    station_status_body.extend(b'\x00\x01')
    station_status_body.extend(struct.pack('>H', signal_count))
    for sig in selected_signals:
        station_status_body.extend(struct.pack('>H', sig['signal_id']))
        station_status_body.append(signal_byte)
        station_status_body.extend(b'\x00\x00')
        station_status_body.append(0x00)
    station_status_body.extend(struct.pack('>H', section_count))
    for sec in selected_sections:
        station_status_body.extend(struct.pack('>H', sec['section_id']))
        station_status_body.append(section_byte1)
        station_status_body.extend(b'\x00\x00')
        station_status_body.append(section_byte4)
    station_status_body.extend(struct.pack('>H', switch_count))
    for sw in sorted_switches:
        station_status_body.extend(struct.pack('>I', sw['switch_id']))
        station_status_body.append(switch_byte)
    station_status_body.append(regulation_status)
    psd_count = len(sorted_psds)
    station_status_body.extend(struct.pack('>H', psd_count))
    for psd in sorted_psds:
        station_status_body.extend(struct.pack('>I', psd['psd_id']))
        station_status_body.append(psd_status)
    eb_count = len(sorted_em_brakes)
    station_status_body.extend(struct.pack('>H', eb_count))
    for eb in sorted_em_brakes:
        station_status_body.extend(struct.pack('>I', eb['eb_id']))
        station_status_body.append(em_brake_status)
    station_status_body.extend(b'\x00\x00')
    station_status_body.extend(b'\x00\x00')
    station_status_body.extend(b'\x00\x00')
    station_status_len = len(station_status_body)

    train_tracking_data = b'\x00\x01\x00\x01\x00\x0c\x00\x0c\x00\x0d\x02\x00\x05\x01\x00\x02\x01\x02\x00\x00\x03\x01\x00\x3f\x00\x01\x00\x00\x01\x02\x00\x00\x00\xfb\x02\x00\x01\x01\x55\x03\x02\x00\x00\x02\x00\x00\x00\x00\x00\x0e\x00\x00\x00\x00\x00\x00\x00\x0e\x00\x00\x35\x84\x00\x00\x00\x00\x6b\x00\x6b\x00\x30\x00\x00'

    body = bytearray()
    body.append(msg_type)
    body.extend(struct.pack('>I', line_id))
    body.extend(struct.pack('>I', timestamp))
    body.extend(struct.pack('>I', seq))
    body.extend(struct.pack('>H', station_status_len))
    body.extend(station_status_body)
    body.extend(b'\x00\x00')
    body.extend(b'\x00\x48')
    body.extend(train_tracking_data)
    body.extend(b'\x00\x00')
    body.extend(b'\x00\x00')
    body.extend(b'\x00\x00')

    crc_bytes = calculate_crc_with_version(body, version)
    frame_len = len(body) + 4
    lines.append(f"({frame_len:04X}) #帧长度(从MSG_ID开始到CRC校验结束)#")
    lines.append("<")
    lines.append("52 #Message Type#")
    lines.append("00 00 00 63 #线路ID#")
    ts_hex = f"{timestamp:08X}"
    lines.append(f"[{' '.join(ts_hex[i:i + 2] for i in range(0, 8, 2))}] #时间戳#")
    seq_hex = f"{seq:08X}"
    lines.append(f"[{' '.join(seq_hex[i:i + 2] for i in range(0, 8, 2))}] #报文序列号#")
    lines.append("")
    lines.append(f"{station_status_len:04X} #站场状态数据长度 {station_status_len} #")
    lines.append("01 #联锁数量#")
    lines.append("00 01 #联锁ID#")
    lines.append("")
    lines.append(f"{signal_count:04X} #信号机数量#")
    for sig in selected_signals:
        id_hex = ' '.join(f'{b:02X}' for b in struct.pack('>H', sig['signal_id']))
        status_hex = ' '.join(f'{b:02X}' for b in [signal_byte, 0x00, 0x00, 0x00])
        lines.append(f"{id_hex} {status_hex} #信号机 {sig['signal_id']} #")
    lines.append(f"{section_count:04X} #逻辑区段数量#")
    for sec in selected_sections:
        id_hex = ' '.join(f'{b:02X}' for b in struct.pack('>H', sec['section_id']))
        status_hex = ' '.join(f'{b:02X}' for b in [section_byte1, 0x00, 0x00, section_byte4])
        lines.append(f"{id_hex} {status_hex} #区段 {sec['section_id']} #")
    lines.append(f"{switch_count:04X} #道岔数量#")
    for sw in sorted_switches:
        id_hex = ' '.join(f'{b:02X}' for b in struct.pack('>I', sw['switch_id']))
        status_hex = f"{switch_byte:02X}"
        lines.append(f"{id_hex} {status_hex} #道岔 {sw['switch_id']} #")
    reg_desc = REGULATION_MAP.get(regulation_status, "未知")
    lines.append(f"{regulation_status:02X} #调控权状态 ({reg_desc})#")
    lines.append(f"{psd_count:04X} #屏蔽门数量#")
    psd_desc = PSD_STATUS_MAP.get(psd_status, "未知")
    for psd in sorted_psds:
        id_hex = ' '.join(f'{b:02X}' for b in struct.pack('>I', psd['psd_id']))
        lines.append(f"{id_hex} {psd_status:02X} #屏蔽门 {psd['psd_id']} #")
    lines.append(f"{eb_count:04X} #紧急停车按钮数量#")
    eb_desc = EB_STATUS_MAP.get(em_brake_status, "未知")
    for eb in sorted_em_brakes:
        id_hex = ' '.join(f'{b:02X}' for b in struct.pack('>I', eb['eb_id']))
        lines.append(f"{id_hex} {em_brake_status:02X} #紧急停车按钮 {eb['eb_id']} #")
    lines.append("00 00 #折返模式总数#")
    lines.append("00 00 #自动通过进路总数#")
    lines.append("00 00 #预留2字节#")
    lines.append("00 00 #站场同步数据长度 0个byte#")
    lines.append("00 48 #车次追踪数据长度 72个byte#")
    train_lines = parse_train_tracking(train_tracking_data)
    lines.extend(train_lines)
    lines.append("00 00 #临时限速状态数据长度#")
    lines.append("00 00 #牵引供电信息长度#")
    lines.append("00 00 #主所供电信息长度#")
    lines.append(">")
    lines.append("55 #帧结束标识#")
    return None, '\n'.join(lines)

# ------------------------------------------------------------
# 早晚点模式
# ------------------------------------------------------------
def _generate_single_train_bytes(section_data, min_index, max_index):
    train_serial = random.randint(1, 99)
    train_no = random.randint(1001, 2999)
    early_or_late = random.choice([1,2,3,4,5,6,7,8,9])
    drive_mode = random.choice([0,1,2,2,3,1,4,5,6,7,8,9])
    direction = random.choice([0,1,1,2,2])
    idx = random.randint(0, len(section_data)-1)
    logic_section = section_data[idx][0]
    early_time = random.randint(1, 254)
    destination = random.randint(min_index, max_index)

    data = bytearray()
    data.extend(struct.pack('>H', train_serial))
    data.extend(b'\x00\x15')
    data.extend(struct.pack('>H', train_no))
    data.append(0x02)
    data.extend(b'\x56\x43')
    data.append(0x01)
    data.extend(b'\xFF\xFF')
    data.append(0x01)
    data.append(early_or_late)
    data.append(0x00)
    data.append(0x00)
    data.append(drive_mode)
    data.append(direction)
    data.extend(struct.pack('>H', logic_section))
    data.extend(b'\x00\x01')
    data.append(0x00)
    data.append(0x01)
    data.append(0x02)
    data.extend(struct.pack('>I', early_time))
    data.append(0x03)
    data.append(0x00)
    data.append(0x00)
    data.append(0x01)
    data.append(0xAA)
    data.append(0x00)
    data.append(0x02)
    data.extend(b'\x00\x00')
    data.append(0x02)
    data.extend(b'\x00\x00')
    data.extend(b'\x00' * 16)
    data.extend(b'\x00\x00\x00')
    data.extend(b'\x00\x00\x00\x00')
    data.extend(struct.pack('>H', destination))
    data.extend(b'\x00\x00')
    return bytes(data)

def _generate_track_data_bytes(section_data, min_index, max_index):
    station_count = random.randint(1, 10)
    total = bytearray()
    for station_idx in range(1, station_count + 1):
        total.extend(struct.pack('>H', station_idx))
        train_num = random.randint(1, 10)
        total.extend(struct.pack('>H', train_num))
        for _ in range(train_num):
            total.extend(_generate_single_train_bytes(section_data, min_index, max_index))
    return bytes(total)

def build_track_base_packet(section_data, min_index, max_index, version, random_time=False, timestamp=None):
    if timestamp is None:
        timestamp = int(time.time())
    line_id = 0x00000000
    msg_type = 0x52
    seq = get_next_sequence()

    track_data = _generate_track_data_bytes(section_data, min_index, max_index)
    track_len = len(track_data)

    body = bytearray()
    body.append(msg_type)
    body.extend(struct.pack('>I', line_id))
    timestamp_pos = len(body)
    body.extend(struct.pack('>I', timestamp))
    body.extend(struct.pack('>I', seq))
    body.extend(struct.pack('>H', 0))
    body.extend(struct.pack('>H', 0))
    body.extend(struct.pack('>H', track_len))
    body.extend(track_data)
    body.extend(struct.pack('>H', 0))
    body.extend(struct.pack('>H', 0))
    body.extend(struct.pack('>H', 0))

    crc_bytes = calculate_crc_with_version(body, version)
    frame_len = len(body) + 4
    header = bytearray([0xAA, 0x20, 0x02]) + struct.pack('>H', frame_len)
    packet = header + body + crc_bytes + b'\x55'
    return packet, timestamp_pos