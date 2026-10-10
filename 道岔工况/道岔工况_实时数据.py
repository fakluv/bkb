#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import struct
import random
import time
import socket

# ===== 固定协议字段 =====
HEADER = b'qknet'
CODE = 0x02
DATA_VERSION = 0x01
TYPE = 0x8F
RESERVED = 0xFFFFFFFF
END = 0xFFFFFFFF
CMD = 0x81
DATA_LEN = 1 + 2 + 4 + 2 + 2 + 4  # 15 字节

# 所有需要生成的值类型列表
ALL_VALUE_TYPES = [0x01, 0x02, 0x04, 0x05, 0x06, 0x07, 0x09, 0x0A]

# ===== 可配置参数（直接修改此处） =====
SWITCH_COUNT = 4                    # 转辙机数量
START_SWITCH_ID = 0x0001            # 起始转辙机编号（后续自动递增）
OUTPUT_PREFIX = None                # 文件保存前缀，为 None 则不保存

# TCP 服务器设置
ENABLE_TCP_SERVER = True            # 是否启用 TCP 服务器模式
TCP_SERVER_PORT = 9999             # 服务器监听端口

# 持续发送控制
SEND_INTERVAL = 1.0                 # 每组报文发送后的等待时间（秒）
# =====================================

def pack_packet(switch_id, timestamp, value_type, value):
    """打包报文（小端序数据部分，固定头部）"""
    data = struct.pack('<B H I H h I',
                       CMD,
                       switch_id,
                       timestamp,
                       value_type,
                       value,
                       RESERVED)
    length = struct.pack('>I', DATA_LEN)
    packet = (HEADER +
              struct.pack('>B', CODE) +
              struct.pack('>B', DATA_VERSION) +
              struct.pack('>B', TYPE) +
              length +
              data +
              struct.pack('>I', END))
    return packet

def hex_dump(data):
    return ' '.join(f'{b:02X}' for b in data)

def random_value():
    """生成随机实际值（-100.0 ~ 100.0），返回协议整数值（×10）"""
    real = round(random.uniform(-100.0, 100.0), 1)
    return int(real * 10)

def generate_packet_group(switch_ids):
    """
    生成当前时刻的一组报文（所有转辙机 × 所有值类型）
    返回 (packets, timestamp)，packets 是列表，每个元素为 (switch_id, vt, val, packet)
    """
    timestamp = int(time.time())
    group = []
    for sid in switch_ids:
        for vt in ALL_VALUE_TYPES:
            val = random_value()
            packet = pack_packet(sid, timestamp, vt, val)
            group.append((sid, vt, val, packet))
    return group, timestamp

def run_tcp_server():
    """启动 TCP 服务器，持续接受客户端并发送实时数据"""
    if not ENABLE_TCP_SERVER:
        print("TCP 服务器未启用。")
        return

    # 生成转辙机编号列表
    switch_ids = [START_SWITCH_ID + i for i in range(SWITCH_COUNT)]
    print(f"转辙机数量: {SWITCH_COUNT}")
    print(f"编号列表: {[f'0x{sid:04X}' for sid in switch_ids]}")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(('0.0.0.0', TCP_SERVER_PORT))
    server_sock.listen(5)
    print(f"TCP 服务器已启动，持续监听端口 {TCP_SERVER_PORT}，等待客户端连接...")

    try:
        while True:
            conn, addr = server_sock.accept()
            print(f"\n客户端已连接: {addr}")
            try:
                with conn:
                    conn.settimeout(1.0)  # 便于检测客户端断开
                    while True:
                        # 生成一组实时报文
                        group, timestamp = generate_packet_group(switch_ids)
                        print(f"\n--- 时间戳: {timestamp} (0x{timestamp:08X}) ---")
                        for sid, vt, val, packet in group:
                            real_val = val / 10.0
                            print(f"发送 转辙机 0x{sid:04X}  值类型 0x{vt:02X}  实际值 {real_val:.1f} ({len(packet)} 字节)")
                            try:
                                conn.sendall(packet)
                            except (BrokenPipeError, ConnectionResetError):
                                print("客户端断开连接。")
                                raise  # 跳出内层循环
                        print(f"本组发送完毕，等待 {SEND_INTERVAL} 秒...")
                        time.sleep(SEND_INTERVAL)
            except (BrokenPipeError, ConnectionResetError, socket.timeout):
                print(f"客户端 {addr} 已断开。")
            except KeyboardInterrupt:
                print("\n服务器被中断。")
                break
            finally:
                conn.close()
                print("等待下一个客户端连接...")
    except KeyboardInterrupt:
        print("\n服务器正在关闭...")
    finally:
        server_sock.close()
        print("TCP 服务器已关闭。")

if __name__ == '__main__':
    run_tcp_server()