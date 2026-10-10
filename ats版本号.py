import struct, time, binascii, random

devices = [
    (1,  "应用服务器"), (2,  "操作工作站"), (5,  "计划工作站"),
    (9,  "网关计算机"), (10, "现地工作站"), (12, "大屏显示终端"),
    (26, "中间件"),     (30, "TDT软件"),   (31, "车站分机"),
    (35, "互联接口机"), (37, "数据库同步软件"), (38, "看门狗软件"),
    (51, "通信前置机"), (91, "TIAS插件bin"), (92, "TIAS插件ops"),
    (98, "检修网关"),   (99, "车辆网关"),   (102, "PSD接口机"),
    (104,"车辆调度"),   (105,"数据库DG"),   (106,"运行图大屏工作站")
]

# 固定随机种子（可注释掉以每次不同）
random.seed(42)

# ---- 构造帧头 ----
header      = b'\xAA'
ver_proto   = b'\x20\x02'
msg_id      = b'\x56'
line_num    = struct.pack('>I', 1)
timestamp   = struct.pack('>I', int(time.time()))  # 当前Unix秒数
sn          = struct.pack('>I', 1)
dev_count   = struct.pack('>H', len(devices))

# ---- 构造设备数据 ----
data = b''
dev_hex_list = []
for dev_id, name in devices:
    data += struct.pack('>H', dev_id)
    v1 = random.randint(1, 999)
    v2 = random.randint(1, 999)
    v3 = random.randint(1, 999)
    v4 = random.randint(1, 999)
    data += struct.pack('>HHHH', v1, v2, v3, v4)
    dv = random.randint(1, 999999)
    data += struct.pack('>I', dv)
    dev_bytes = struct.pack('>H', dev_id) + struct.pack('>HHHH', v1,v2,v3,v4) + struct.pack('>I', dv)
    dev_hex_list.append((dev_bytes, name))

# ---- 计算LEN ----
len_without_crc = len(msg_id) + len(line_num) + len(timestamp) + len(sn) + len(dev_count) + len(data)
len_total = len_without_crc + 4
len_field = struct.pack('>H', len_total)

# ---- 组装不含CRC的帧 ----
frame_no_crc = header + ver_proto + len_field + msg_id + line_num + timestamp + sn + dev_count + data
crc = binascii.crc32(frame_no_crc[3:]) & 0xFFFFFFFF
crc_bytes = struct.pack('>I', crc)
full = frame_no_crc + crc_bytes + b'\x55'

# ---- 格式化输出（注释用 ## 名称 ## ） ----
all_bytes = full
# 头部各字段
header_parts = []
header_parts.append(f'{all_bytes[0]:02X}')                         # HEADER
header_parts.append(f'{all_bytes[1]:02X} {all_bytes[2]:02X}')      # Version_No
header_parts.append(f'{all_bytes[3]:02X} {all_bytes[4]:02X}')      # LEN
header_parts.append(f'{all_bytes[5]:02X}')                         # MSG_ID
header_parts.append(f'{all_bytes[6]:02X} {all_bytes[7]:02X} {all_bytes[8]:02X} {all_bytes[9]:02X}')  # LINE_NUM
# 时间戳用 [] 框起
stamp_hex = ' '.join(f'{b:02X}' for b in all_bytes[10:14])
header_parts.append(f'[{stamp_hex}]')                              # [STAMP]
header_parts.append(f'{all_bytes[14]:02X} {all_bytes[15]:02X} {all_bytes[16]:02X} {all_bytes[17]:02X}')  # SN
header_parts.append(f'{all_bytes[18]:02X} {all_bytes[19]:02X}')    # DEV_COUNT

head_line = ' '.join(header_parts) + '    ## HEADER + Ver + LEN + MSG_ID + LINE + [STAMP] + SN + DEV_COUNT ##'

output_lines = [head_line]

# 设备行
dev_start = 20
for i, (dev_bytes, name) in enumerate(dev_hex_list):
    dev_hex = ' '.join(f'{b:02X}' for b in dev_bytes)
    output_lines.append(f'    {dev_hex}    ## {name} ##')

# CRC和END
crc_start = dev_start + len(data)
crc_hex = ' '.join(f'{b:02X}' for b in full[crc_start:crc_start+4])
end_hex = f'{full[-1]:02X}'
output_lines.append(f'    {crc_hex}    ## CRC32 ##')
output_lines.append(f'    {end_hex}    ## END (0x55) ##')

print('\n'.join(output_lines))