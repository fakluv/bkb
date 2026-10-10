import random
import math
import time  # 新增导入，用于生成当前时间戳


class PublicFunc:
    """辅助函数类（仅提取用到的部分）"""

    @staticmethod
    def fix_str(s, length):
        """左侧补零至指定长度"""
        return s.zfill(length)

    @staticmethod
    def int_to_hex(data, num=2):
        """10进制数值转为固定长度Hex字符串（无0x前缀，大写）"""
        data = int(data)
        data_hex = hex(data)[2:]
        data_hex_len = len(data_hex)
        if data_hex_len > num:
            num = math.ceil(data_hex_len / 2) * 2
        data_hex = PublicFunc.fix_str(data_hex, num)
        return data_hex.upper()

    @staticmethod
    def deal_data(s):
        """去除空格和换行，返回纯Hex字符串（用于模板处理）"""
        return s.replace(' ', '').replace('\n', '').replace('\r', '')

    @staticmethod
    def str_to_bytes(hex_str):
        """将Hex字符串转为bytes对象"""
        return bytes.fromhex(hex_str)


func = PublicFunc()


def analog_part(data_num):
    """生成模拟量数据区（所有路的拼接字符串）"""
    return_data = ''
    for i in range(data_num):
        # 路数编号 (从1开始)
        analog_id = func.int_to_hex(i + 1)
        # 相角 (3个)
        xj1_ab = func.int_to_hex(random.randint(10000, 15000), 4)
        xj1_bc = func.int_to_hex(random.randint(10000, 15000), 4)
        xj1_ca = func.int_to_hex(random.randint(10000, 15000), 4)
        # 频率 (1个)
        pl1 = func.int_to_hex(random.randint(4000, 6000), 4)
        # 相电压 (3个)
        xiangdy1_Ua = func.int_to_hex(random.randint(18000, 26000), 4)
        xiangdy1_Ub = func.int_to_hex(random.randint(18000, 26000), 4)
        xiangdy1_Uc = func.int_to_hex(random.randint(18000, 26000), 4)
        # 线电压 (3个)
        xiandy1_Uab = func.int_to_hex(random.randint(30000, 42000), 4)
        xiandy1_Ubc = func.int_to_hex(random.randint(30000, 42000), 4)
        xiandy1_Uca = func.int_to_hex(random.randint(30000, 42000), 4)
        # 相电流 (3个)
        xdl1_Ia = func.int_to_hex(random.randint(0, 2000), 4)
        xdl1_Ib = func.int_to_hex(random.randint(0, 2000), 4)
        xdl1_Ic = func.int_to_hex(random.randint(0, 2000), 4)
        # 有功功率 (4个)
        pgl1_Pa = func.int_to_hex(random.randint(0, 5000), 4)
        pgl1_Pb = func.int_to_hex(random.randint(0, 5000), 4)
        pgl1_Pc = func.int_to_hex(random.randint(0, 5000), 4)
        pgl1_Pz = func.int_to_hex(random.randint(0, 5000), 4)
        # 无功功率 (4个)
        qgl1_Qa = func.int_to_hex(random.randint(0, 5000), 4)
        qgl1_Qb = func.int_to_hex(random.randint(0, 5000), 4)
        qgl1_Qc = func.int_to_hex(random.randint(0, 5000), 4)
        qgl1_Qz = func.int_to_hex(random.randint(0, 5000), 4)

        # 单路数据模板
        part_code = (
                analog_id +  # 路数编号
                '51' + '03' +  # 相角类型码+数量
                xj1_ab + xj1_bc + xj1_ca +
                '52' + '01' +  # 频率类型码+数量
                pl1 +
                '53' + '03' +  # 相电压类型码+数量
                xiangdy1_Ua + xiangdy1_Ub + xiangdy1_Uc +
                '54' + '03' +  # 线电压类型码+数量
                xiandy1_Uab + xiandy1_Ubc + xiandy1_Uca +
                '55' + '03' +  # 相电流类型码+数量
                xdl1_Ia + xdl1_Ib + xdl1_Ic +
                '56' + '04' +  # 有功功率类型码+数量
                pgl1_Pa + pgl1_Pb + pgl1_Pc + pgl1_Pz +
                '57' + '04' +  # 无功功率类型码+数量
                qgl1_Qa + qgl1_Qb + qgl1_Qc + qgl1_Qz
        )
        return_data += part_code
    return return_data


def generate_message():
    """生成一帧完整的报文（返回字节串）"""
    station_no = 20
    station_hex = func.int_to_hex(station_no, 4)

    # 计算模拟量总路数 (原逻辑：data_max_index=126，每路21个数据项)
    data_max_index = 126
    data_num = int(data_max_index / 21)  # 6
    data_num_hex = func.int_to_hex(data_num)

    # 生成模拟量数据区
    data_part = analog_part(data_num)

    # 帧长度 = 17(固定头尾) + 每路57字节 * 路数
    frame_len_int = 17 + data_num * 57
    frame_len_hex = func.int_to_hex(frame_len_int, 4)

    # ----- 动态生成当前时间戳（4字节，小端序？这里按大端存储，即直接取低32位）-----
    current_ts = int(time.time()) & 0xFFFFFFFF
    ts_hex = func.int_to_hex(current_ts, 8)  # 8个Hex字符，即4字节

    # 报文模板（Hex字符串）
    send_data_template = (
            'AA' +  # 帧开始标志
            frame_len_hex +  # 帧长度
            station_hex +  # 站号
            '40' +  # Message Type
            '46' +  # Data Type
            ts_hex +  # 时间戳（动态）
            '00785439' +  # 报文序列号
            data_num_hex +  # 模拟量总路数
            data_part +
            'D0320729' +  # CRC校验 (硬编码)
            '55'  # 帧结束标志
    )

    # 清理模板（去除可能的空格等）
    send_data_hex = func.deal_data(send_data_template)
    # 转为字节串
    return func.str_to_bytes(send_data_hex)


def format_hex_with_timestamp(hex_str):
    """
    将无空格的Hex字符串转为每个字节空格分隔，
    并将时间戳字段（4字节）整体用方括号括起来，
    且时间戳内部每个字节也以空格分隔。
    时间戳起始字节索引（0-based）为7，长度4。
    """
    byte_list = [hex_str[i:i + 2] for i in range(0, len(hex_str), 2)]
    ts_start = 7
    ts_end = ts_start + 4

    # 提取时间戳字节
    ts_bytes = byte_list[ts_start:ts_end]
    # 生成带空格的时间戳内部字符串，例如 "5D 9C 8B 28"
    ts_inner = ' '.join(ts_bytes)
    # 整体用方括号括起来
    ts_formatted = f'[{ts_inner}]'

    # 构建格式化列表
    formatted_parts = []
    # 加入时间戳之前的字节
    formatted_parts.extend(byte_list[:ts_start])
    # 加入格式化后的时间戳
    formatted_parts.append(ts_formatted)
    # 加入时间戳之后的字节
    formatted_parts.extend(byte_list[ts_end:])

    # 用空格连接所有部分（注意：时间戳内部已有空格，所以直接join）
    return ' '.join(formatted_parts)


if __name__ == '__main__':
    msg_bytes = generate_message()
    hex_str = msg_bytes.hex().upper()

    print('报文长度:', len(msg_bytes), '字节')
    print('原始Hex（无空格）:')
    print(hex_str)
    print('\n格式化输出（时间戳用[]框起，字节以空格分隔）:')
    print(format_hex_with_timestamp(hex_str))