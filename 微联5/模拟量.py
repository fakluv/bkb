# coding:utf8
import time
import random
import zlib

# ========== 辅助函数 ==========
def int_to_hex(value, byte_len=2):
    """将整数转为指定字节数的大端十六进制字符串（无空格）"""
    return format(value, '0{}X'.format(byte_len * 2))

def calc_crc(data_hex):
    """计算 CRC32，返回大端4字节十六进制"""
    data_bytes = bytes.fromhex(data_hex)
    crc = zlib.crc32(data_bytes) & 0xFFFFFFFF
    return format(crc, '08X')

# ========== 模拟量生成函数 ==========
def make_cable_insulation(device_no, sn):
    value_int = random.randint(0, 30000)
    item_hex = int_to_hex(device_no, 2)
    analog_hex = int_to_hex(value_int, 2)
    payload = item_hex + analog_hex
    full, stamp = build_packet(payload, 0x40, 0x41, sn)
    show = f'设备号:{device_no}  绝缘值:{value_int/100:.2f} MΩ'
    return full, show, stamp

def make_switch_current(device_no, sn):
    item_hex = int_to_hex(device_no, 2)
    start_time = int(time.time()) - random.randint(10, 100)
    start_hex = int_to_hex(start_time, 4)
    direction = random.randint(0, 8)
    dir_hex = int_to_hex(direction, 1)
    curve_type = random.randint(0, 1)
    curve_type_hex = int_to_hex(curve_type, 1)
    curve_num = 3
    curve_num_hex = int_to_hex(curve_num, 1)
    curves_hex = ''
    for _ in range(curve_num):
        point_num = random.randint(10, 50)
        point_num_hex = int_to_hex(point_num, 2)
        points_hex = ''
        for _ in range(point_num):
            pt = random.randint(0, 5000)
            points_hex += int_to_hex(pt, 2)
        curves_hex += point_num_hex + points_hex
    switch_cnt = random.randint(1, 999999)
    switch_cnt_hex = int_to_hex(switch_cnt, 4)
    payload = item_hex + start_hex + dir_hex + curve_type_hex + curve_num_hex + curves_hex + switch_cnt_hex
    full, stamp = build_packet(payload, 0x40, 0x42, sn)
    show = f'设备号:{device_no}  道岔电流曲线(模拟)'
    return full, show, stamp

def make_switch_power(device_no, sn):
    item_hex = int_to_hex(device_no, 2)
    start_time = int(time.time()) - random.randint(10, 100)
    start_hex = int_to_hex(start_time, 4)
    direction = random.randint(0, 8)
    dir_hex = int_to_hex(direction, 1)
    curve_type = 0
    curve_type_hex = int_to_hex(curve_type, 1)
    curve_num = 1
    curve_num_hex = int_to_hex(curve_num, 1)
    point_num = random.randint(10, 30)
    point_num_hex = int_to_hex(point_num, 2)
    points_hex = ''
    for _ in range(point_num):
        pt = random.randint(0, 5000)
        points_hex += int_to_hex(pt, 2)
    curves_hex = point_num_hex + points_hex
    switch_cnt = random.randint(1, 999999)
    switch_cnt_hex = int_to_hex(switch_cnt, 4)
    payload = item_hex + start_hex + dir_hex + curve_type_hex + curve_num_hex + curves_hex + switch_cnt_hex
    full, stamp = build_packet(payload, 0x40, 0x53, sn)
    show = f'设备号:{device_no}  道岔功率曲线(模拟)'
    return full, show, stamp

def make_track_voltage(device_no, sn):
    analog_num = random.randint(1, 10)
    analog_num_hex = int_to_hex(analog_num, 2)
    analogs_hex = ''
    for _ in range(analog_num):
        val = random.randint(150, 280)
        analogs_hex += int_to_hex(val, 2)
    payload = analog_num_hex + analogs_hex
    full, stamp = build_packet(payload, 0x40, 0x43, sn)
    show = f'设备号:{device_no}  轨道电压({analog_num}路)'
    return full, show, stamp

def make_temperature(device_no, sn):
    analog_num = random.randint(1, 5)
    analog_num_hex = int_to_hex(analog_num, 2)
    analogs_hex = ''
    for _ in range(analog_num):
        val = random.randint(0, 300)
        analogs_hex += int_to_hex(val, 2)
    payload = analog_num_hex + analogs_hex
    full, stamp = build_packet(payload, 0x40, 0x45, sn)
    show = f'设备号:{device_no}  温湿度({analog_num}路)'
    return full, show, stamp

def make_switch_indication_voltage(device_no, sn):
    analog_num = 4
    analog_num_hex = int_to_hex(analog_num, 2)
    analogs_hex = ''
    for _ in range(analog_num):
        val = random.randint(0, 500)
        analogs_hex += int_to_hex(val, 2)
    payload = analog_num_hex + analogs_hex
    full, stamp = build_packet(payload, 0x40, 0x44, sn)
    show = f'设备号:{device_no}  道岔表示电压(4路)'
    return full, show, stamp

def make_signal_lamp_current(device_no, sn):
    analog_num = random.randint(1, 5)
    analog_num_hex = int_to_hex(analog_num, 2)
    items_hex = ''
    for i in range(analog_num):
        item_no = device_no * 100 + i
        items_hex += int_to_hex(item_no, 2)
        val = random.randint(0, 5000)
        items_hex += int_to_hex(val, 2)
    payload = analog_num_hex + items_hex
    full, stamp = build_packet(payload, 0x40, 0x47, sn)
    show = f'设备号:{device_no}  信号机点灯电流({analog_num}路)'
    return full, show, stamp

def make_platform_door_voltage_all(total_devices, sn):
    """站台门电压：一帧包含所有设备，模拟量总数=设备总数，每个模拟量2字节，值/10=电压(V)"""
    analog_num = total_devices
    analog_num_hex = int_to_hex(analog_num, 2)

    analogs_hex = ''
    voltages = []
    for _ in range(analog_num):
        val = random.randint(0, 5000)   # 0 ~ 500.0V
        analogs_hex += int_to_hex(val, 2)
        voltages.append(val / 10.0)

    payload = analog_num_hex + analogs_hex
    full, stamp = build_packet(payload, 0x40, 0x51, sn)

    show = f'站台门电压 共{analog_num}路: ' + ', '.join(f'{v:.1f}V' for v in voltages)
    return full, show, stamp

def make_power_leakage(device_no, sn):
    value_int = random.randint(0, 30000)
    item_hex = int_to_hex(device_no, 2)
    analog_hex = int_to_hex(value_int, 2)
    payload = item_hex + analog_hex
    full, stamp = build_packet(payload, 0x40, 0x52, sn)
    show = f'设备号:{device_no}  漏流值:{value_int/100:.2f} mA'
    return full, show, stamp

def make_axle_counter_voltage(device_no, sn):
    analog_num = 4
    analog_num_hex = int_to_hex(analog_num, 2)
    analogs_hex = ''
    for _ in range(analog_num):
        val = random.randint(0, 500)
        analogs_hex += int_to_hex(val, 2)
    payload = analog_num_hex + analogs_hex
    full, stamp = build_packet(payload, 0x40, 0x54, sn)
    show = f'设备号:{device_no}  计轴电压(4路)'
    return full, show, stamp

def make_track_phase_angle(device_no, sn):
    analog_num = 4
    analog_num_hex = int_to_hex(analog_num, 2)
    analogs_hex = ''
    for _ in range(analog_num):
        val = random.randint(0, 30000)
        analogs_hex += int_to_hex(val, 2)
    payload = analog_num_hex + analogs_hex
    full, stamp = build_packet(payload, 0x40, 0x55, sn)
    show = f'设备号:{device_no}  轨道相位角(4路)'
    return full, show, stamp

def make_switch_machine_current(device_no, sn):
    analog_num = 4
    analog_num_hex = int_to_hex(analog_num, 2)
    analogs_hex = ''
    for _ in range(analog_num):
        val = random.randint(0, 1000)
        analogs_hex += int_to_hex(val, 2)
    payload = analog_num_hex + analogs_hex
    full, stamp = build_packet(payload, 0x40, 0x56, sn)
    show = f'设备号:{device_no}  转辙机总电流(4路)'
    return full, show, stamp

# ========== 通用报文构建函数 ==========
def build_packet(payload_hex, msg_id, type_id, sn, stamp=None):
    if stamp is None:
        stamp = int(time.time())
    stamp_hex = int_to_hex(stamp, 4)
    sn_hex = int_to_hex(sn, 4)
    station_hex = int_to_hex(1, 2)
    mid_hex = int_to_hex(msg_id, 1)
    tid_hex = int_to_hex(type_id, 1)
    check_data_no_len = station_hex + mid_hex + tid_hex + stamp_hex + sn_hex + payload_hex
    len_bytes = 2 + 1 + 1 + 4 + 4 + len(payload_hex)//2 + 4
    len_hex = int_to_hex(len_bytes, 2)
    check_data = len_hex + check_data_no_len
    crc_hex = calc_crc(check_data)
    full = 'AA' + len_hex + check_data_no_len + crc_hex + '55'
    return full, stamp_hex

# ========== 格式化输出 ==========
def format_packet(full_packet, stamp_hex):
    part1 = full_packet[:14]
    stamp_part = '[' + ' '.join(stamp_hex[i:i+2] for i in range(0, 8, 2)).upper() + ']'
    part2 = full_packet[22:]
    part1_spaced = ' '.join(part1[i:i+2] for i in range(0, len(part1), 2)).upper()
    part2_spaced = ' '.join(part2[i:i+2] for i in range(0, len(part2), 2)).upper()
    return f"{part1_spaced} {stamp_part} {part2_spaced}"

# ========== 主菜单 ==========
BATCH_TYPES = {'9'}   # 站台门电压为批量生成类型

TYPE_MAP = {
    '1': ('电缆绝缘', 0x41, make_cable_insulation),
    '2': ('道岔电流', 0x42, make_switch_current),
    '3': ('道岔功率', 0x53, make_switch_power),
    '4': ('轨道电压', 0x43, make_track_voltage),
    '5': ('温湿度', 0x45, make_temperature),
    '6': ('道岔表示电压', 0x44, make_switch_indication_voltage),
    '8': ('信号机点灯电流', 0x47, make_signal_lamp_current),
    '9': ('站台门电压', 0x51, None),          # 批量生成，函数在代码中单独调用
    '10': ('电源漏流', 0x52, make_power_leakage),
    '11': ('计轴电压', 0x54, make_axle_counter_voltage),
    '12': ('轨道相位角', 0x55, make_track_phase_angle),
    '13': ('转辙机总电流', 0x56, make_switch_machine_current),
}

def print_menu():
    print("请选择要生成的模拟量类型：")
    for key, (name, _, _) in TYPE_MAP.items():
        print(f"  {key}. {name}")
    print("  0. 生成所有类型")

if __name__ == '__main__':
    print_menu()
    choice = input("请输入类型编号: ").strip()
    if choice not in TYPE_MAP and choice != '0':
        print("无效选择")
        exit(1)
    try:
        count = int(input("请输入设备数量: "))
        if count <= 0:
            raise ValueError
    except ValueError:
        print("请输入正整数")
        exit(1)

    if choice == '0':
        for key, (name, _, _) in TYPE_MAP.items():
            print(f"\n#=== {name} ===#")

            if key in BATCH_TYPES:
                # 站台门电压：一帧包含所有设备
                full_hex, show, stamp_hex = make_platform_door_voltage_all(count, 1)
                formatted = format_packet(full_hex, stamp_hex)
                ts_display = ' '.join(stamp_hex[i:i+2] for i in range(0, 8, 2)).upper()
                print(f"# {show} 时间戳:[{ts_display}] #")
                print(formatted)
                print("<br>")
            else:
                func = TYPE_MAP[key][2]
                for dev_no in range(0, count):
                    sn = dev_no
                    full_hex, show, stamp_hex = func(dev_no, sn)
                    formatted = format_packet(full_hex, stamp_hex)
                    ts_display = ' '.join(stamp_hex[i:i+2] for i in range(0, 8, 2)).upper()
                    print(f"#设备 {dev_no}: {show} 时间戳:[{ts_display}] #")
                    print(formatted)
                    print("<br>")
    else:
        name, _, _ = TYPE_MAP[choice]
        print(f"\n#=== {name} ===#")

        if choice in BATCH_TYPES:
            # 站台门电压：一帧包含所有设备
            full_hex, show, stamp_hex = make_platform_door_voltage_all(count, 1)
            formatted = format_packet(full_hex, stamp_hex)
            ts_display = ' '.join(stamp_hex[i:i+2] for i in range(0, 8, 2)).upper()
            print(f"# {show} 时间戳:[{ts_display}] #")
            print(formatted)
            print("<br>")
        else:
            func = TYPE_MAP[choice][2]
            for dev_no in range(0, count):
                sn = dev_no
                full_hex, show, stamp_hex = func(dev_no, sn)
                formatted = format_packet(full_hex, stamp_hex)
                ts_display = ' '.join(stamp_hex[i:i+2] for i in range(0, 8, 2)).upper()
                print(f"#设备 {dev_no}: {show} 时间戳:[{ts_display}] #")
                print(formatted)
                print("<br>")