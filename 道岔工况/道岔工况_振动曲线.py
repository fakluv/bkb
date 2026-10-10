import struct
import time
import random
import socket

def generate_vibration_frame(switch_id, timestamp, freq, vib_type, direction, curves):
    """
    生成单个道岔扳动/过车振动曲线信息帧（协议 3.3.2.2.13）
    curves: list of (curve_type, point_count) 或 (curve_type, [占位列表])
    """
    data = bytearray()
    data.append(0x71)                                      # 指令码
    data.extend(struct.pack('<H', switch_id))              # 转辙机编号（小端）
    data.extend(struct.pack('<I', timestamp))              # 时间戳（小端）
    data.append(freq & 0xFF)                               # 采集频率
    data.append(vib_type & 0xFF)                           # 振动类型
    data.append(direction & 0xFF)                          # 方向
    data.extend(b'\xFF\xFF\xFF\xFF')                       # 预留4字节
    data.append(len(curves) & 0xFF)                        # 曲线条数

    for ctype, points in curves:
        data.append(ctype & 0xFF)                          # 曲线类型
        data.extend(b'\xFF\xFF\xFF\xFF')                   # 预留4字节
        raw = bytearray()
        for _ in range(len(points)):                       # 每个点重新生成随机值（绝对值<20）
            int_val = random.randint(-19, 19)
            raw.extend(struct.pack('<h', int_val))
        data.extend(struct.pack('<H', len(raw)))           # 曲线数据长度 2字节（小端）
        data.extend(raw)                                   # 曲线数据

    data_len = len(data)
    frame = bytearray()
    frame.extend(b'qknet')                                 # 帧头
    frame.append(0x02)                                     # 协议标识
    frame.append(0x01)                                     # 数据版本
    frame.append(0x8F)                                     # 帧类型（数据帧）
    frame.extend(struct.pack('<I', data_len))              # 数据长度（小端）
    frame.extend(data)
    frame.extend(b'\xFF\xFF\xFF\xFF')                      # 帧尾
    return bytes(frame)


def print_frame_details(frame, frame_index=None):
    """逐字段解析并打印单个帧（带注释，每条曲线间空行）"""
    if frame_index is not None:
        print(f"\n{'='*80}\n第 {frame_index} 个转辙机的帧解析\n{'='*80}")
    idx = 0
    print("=" * 80)
    print("逐字段解析（字节间空格分隔，注释用 # 包围，曲线间空行）")
    print("=" * 80)

    header = frame[idx:idx+5]
    print(f"{' '.join(f'{b:02X}' for b in header)}  # 'qknet' ASCII 码 #")
    idx += 5

    print(f"{frame[idx]:02X}  # 协议标识，固定 0x02 #")
    idx += 1
    print(f"{frame[idx]:02X}  # 数据版本，固定 0x01 #")
    idx += 1
    print(f"{frame[idx]:02X}  # 帧类型，0x8F 数据帧 #")
    idx += 1

    len_bytes = frame[idx:idx+4]
    len_le = struct.unpack('<I', len_bytes)[0]
    len_be = struct.unpack('>I', len_bytes)[0]
    print(f"{' '.join(f'{b:02X}' for b in len_bytes)}  # 数据长度，小端={len_le}，反转(大端)={len_be} #")
    idx += 4

    print(f"{frame[idx]:02X}  # 指令码，固定 0x71 #")
    idx += 1

    sw_bytes = frame[idx:idx+2]
    sw_le = struct.unpack('<H', sw_bytes)[0]
    sw_be = struct.unpack('>H', sw_bytes)[0]
    print(f"{' '.join(f'{b:02X}' for b in sw_bytes)}  # 转辙机编号，小端={sw_le}，反转(大端)={sw_be} #")
    idx += 2

    ts_bytes = frame[idx:idx+4]
    ts_le = struct.unpack('<I', ts_bytes)[0]
    ts_be = struct.unpack('>I', ts_bytes)[0]
    print(f"{' '.join(f'{b:02X}' for b in ts_bytes)}  # 时间戳(Unix)，小端={ts_le}，反转(大端)={ts_be} #")
    idx += 4

    print(f"{frame[idx]:02X}  # 采集频率 #")
    idx += 1

    vtype = frame[idx]
    vtype_str = "扳动" if vtype == 0x01 else "过车" if vtype == 0x02 else "未知"
    print(f"{vtype:02X}  # 振动类型，{vtype_str} #")
    idx += 1

    dir_val = frame[idx]
    if vtype == 0x01:
        dir_map = {0:"定到反",1:"反到定",2:"定到定",3:"反到反",4:"定位->故障",5:"反位->故障",6:"故障->定位",7:"故障->反位",8:"故障->故障",0xFF:"无效"}
        dir_str = dir_map.get(dir_val, "未知")
    else:
        dir_str = "定位" if dir_val == 0 else "反位" if dir_val == 1 else "无效"
    print(f"{dir_val:02X}  # 方向，{dir_str} #")
    idx += 1

    res4 = frame[idx:idx+4]
    print(f"{' '.join(f'{b:02X}' for b in res4)}  # 预留，固定 0xFFFFFFFF #")
    idx += 4

    cnt = frame[idx]
    print(f"{cnt:02X}  # 曲线条数，值={cnt} #")
    idx += 1

    for i in range(cnt):
        if i > 0:
            print()

        ctype = frame[idx]
        ctype_str = "X轴" if ctype == 0x00 else "Y轴" if ctype == 0x01 else "Z轴" if ctype == 0x02 else "未知"
        print(f"    {ctype:02X}  # 曲线类型，{ctype_str} #")
        idx += 1

        res4_curve = frame[idx:idx+4]
        print(f"    {' '.join(f'{b:02X}' for b in res4_curve)}  # 预留，固定 0xFFFFFFFF #")
        idx += 4

        clen_bytes = frame[idx:idx+2]
        clen_le = struct.unpack('<H', clen_bytes)[0]
        clen_be = struct.unpack('>H', clen_bytes)[0]
        print(f"    {' '.join(f'{b:02X}' for b in clen_bytes)}  # 曲线数据长度，小端={clen_le}，反转(大端)={clen_be} #")
        idx += 2

        raw_data = frame[idx:idx+clen_le]
        hex_data = ' '.join(f'{b:02X}' for b in raw_data)
        points = []
        for j in range(0, clen_le, 2):
            if j+2 <= clen_le:
                val = struct.unpack('<h', raw_data[j:j+2])[0]
                points.append(val)
        show = min(6, len(points))
        first_vals = ", ".join(f"{p}" for p in points[:show])
        if len(points) > show:
            first_vals += ", ..."
        print(f"    {hex_data}  # 曲线数据（{len(points)}个点，int16小端），前{show}个: {first_vals} #")
        idx += clen_le

    tail = frame[idx:idx+4]
    print(f"{' '.join(f'{b:02X}' for b in tail)}  # 帧尾，固定 0xFFFFFFFF #")
    idx += 4

    print("=" * 80)
    full_hex = ' '.join(f'{b:02X}' for b in frame)
    print("完整报文（字节间空格分隔）：")
    print(full_hex)
    print("=" * 80)
    print(f"总字节数: {len(frame)}")


def handle_client(conn, addr, params):
    """
    处理已连接的客户端：持续发送最新帧，直到客户端断开
    params 包含所有配置参数（带注释）
    """
    print(f"客户端 {addr} 已连接，开始循环发送（间隔 1 秒）")
    try:
        while True:
            # 1. 获取当前时间戳
            timestamp = int(time.time())

            # 2. 构建曲线列表（点数固定）
            curves = []
            if params['ENABLE_X']:
                curves.append((0x00, [0] * params['POINTS_PER_CURVE']))
            if params['ENABLE_Y']:
                curves.append((0x01, [0] * params['POINTS_PER_CURVE']))
            if params['ENABLE_Z']:
                curves.append((0x02, [0] * params['POINTS_PER_CURVE']))
            if not curves:
                curves.append((0x00, [0] * params['POINTS_PER_CURVE']))

            # 3. 生成所有转辙机的帧
            all_frames = bytearray()
            for idx in range(params['NUM_SWITCHES']):
                switch_id = params['BASE_SWITCH_ID'] + idx
                frame = generate_vibration_frame(
                    switch_id, timestamp,
                    params['FREQ'], params['VIB_TYPE'], params['DIRECTION'],
                    curves
                )
                all_frames.extend(frame)

                # 4. 根据 is_print 决定是否打印解析
                if params['is_print']:
                    print_frame_details(frame, frame_index=idx+1)

            # 5. 发送数据
            conn.sendall(all_frames)
            print(f"已发送 {len(all_frames)} 字节，时间戳: {timestamp}")

            # 6. 等待 1 秒再发下一组
            time.sleep(1)

    except (BrokenPipeError, ConnectionResetError):
        print(f"客户端 {addr} 已断开")
    except Exception as e:
        print(f"连接异常: {e}")
    finally:
        conn.close()


def start_tcp_server(host='192.168.2.132', port=9999):
    """主服务：等待连接，每个连接进入 handle_client 循环发送"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    print(f"TCP Server 已启动，监听 {host}:{port}，等待客户端连接...")

    # ========== 配置参数（带注释） ==========
    params = {
        'NUM_SWITCHES': 28,          # 转辙机数量（生成几个转辙机的帧）
        'BASE_SWITCH_ID': 0x0001,   # 起始转辙机编号（递增）
        'FREQ': 0x0A,               # 采集频率（自定义值，如 10Hz 对应 0x0A）
        'VIB_TYPE': 0x01,           # 振动类型：0x01 扳动，0x02 过车
        'DIRECTION': 0x00,          # 方向：扳动时 0定到反/1反到定/...；过车时 0定位/1反位
        'POINTS_PER_CURVE': 20,     # 每条曲线的固定点数（不随机变化）
        'ENABLE_X': True,           # 是否生成 X 轴曲线
        'ENABLE_Y': True,           # 是否生成 Y 轴曲线
        'ENABLE_Z': True,           # 是否生成 Z 轴曲线
        'is_print': True,           # 是否打印带注释的报文解析（True=打印，False=不打印）
    }
    # ========================================

    while True:
        conn, addr = server.accept()
        handle_client(conn, addr, params)


if __name__ == '__main__':
    start_tcp_server()