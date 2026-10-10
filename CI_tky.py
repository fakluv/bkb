import struct

# ---------- 1. 构造 COMMST_INFO（190字节） ----------
commst = bytearray(190)
# 工作状态默认0，通信状态默认0，仅设置板卡数量
commst[58] = 0x08   # A系采集板数
commst[59] = 0x09   # A系驱动板数
commst[124] = 0x08  # B系采集板数
commst[125] = 0x09  # B系驱动板数
# 其余全部为0（包括状态、通信等）

# ---------- 2. 构造对象数据（708字节） ----------
objects = bytearray()
def add_objs(type_id, start_code, count, status_list=None):
    for i in range(count):
        code = start_code + i
        status = status_list[i] if status_list and i < len(status_list) else 0x00
        objects.extend(struct.pack('>BH', type_id, code))  # 类型1 + 代码2
        objects.append(status)

# 按顺序添加（类型值：股道5，逻辑6，信号8，道岔12，单状态灯13，屏蔽门15）
add_objs(0x05, 1, 6)                                  # 股道区段 6个
add_objs(0x06, 1, 82)                                 # 逻辑区段 82个
add_objs(0x08, 1, 32)                                 # 信号机 32个
add_objs(0x0C, 1, 6, [0x00, 0x03, 0x00, 0x03, 0x00, 0x03])  # 道岔6个，奇偶状态
add_objs(0x0D, 1, 45)                                 # 单状态表示灯 45个
add_objs(0x0F, 1, 6)                                  # 屏蔽门 6个
assert len(objects) == 708

# ---------- 3. 组装待校验数据（F1 ~ MSG_COUNT，共923字节） ----------
payload = bytearray()
payload.append(0xF1); payload.append(0x0A)          # 站码（北安河=10）
payload.append(0xF2); payload.extend(b'\x00' * 16) # 版本全0
payload.append(0xF3); payload.extend(commst)        # 通信状态
payload.append(0xF4); payload.extend(struct.pack('>H', 708)); payload.extend(objects)
payload.append(0xF5); payload.append(0x00)          # 无报警记录
assert len(payload) == 923

# ---------- 4. CRC32（CCITT，初值0，取低16位） ----------
def crc32_ccitt(data):
    crc = 0x00000000
    poly = 0x04C11DB7
    for b in data:
        crc ^= (b << 24)
        for _ in range(8):
            if crc & 0x80000000:
                crc = (crc << 1) ^ poly
            else:
                crc <<= 1
            crc &= 0xFFFFFFFF
    return crc

full_crc = crc32_ccitt(payload)
crc_low16 = full_crc & 0xFFFF
crc_bytes = struct.pack('>H', crc_low16)

# ---------- 5. 组装完整帧 ----------
frame = bytearray()
frame.extend(b'\x7F\x7F')                         # HEADER
frame.extend(struct.pack('>H', 925))              # LEN = 0x039D
# STAMP: 2026-08-26 12:34:56（示例，您可修改）
frame.extend(struct.pack('>HHHHHH', 2026, 8, 26, 12, 34, 56))
frame.extend(struct.pack('>I', 1))                # SN = 1
frame.extend(payload)                             # 923字节
frame.extend(crc_bytes)                           # 2字节CRC
frame.append(0xFF)                                # END

# 输出每个字节用空格分隔的大写十六进制
print(' '.join(f'{b:02X}' for b in frame))