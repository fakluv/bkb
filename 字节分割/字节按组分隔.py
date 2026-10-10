def split_hex_message(file_path, stop_group):
    """
    读取TXT文件中的16进制报文，按每5个字节为1组拆分，分隔到指定组数后停下，剩余数据整体保留
    :param file_path: TXT文件路径（如：hex_data.txt）
    :param stop_group: 停止的组数（如8，即拆分前8组，每组5字节，剩余数据不分隔）
    """
    try:
        # 1. 读取并清理TXT文件内容（去除多余空格/换行）
        with open(file_path, 'r', encoding='utf-8') as f:
            hex_content = f.read().strip().replace('\n', ' ').replace('\r', ' ')

        # 2. 拆分出所有16进制单元（过滤空字符串）
        hex_list = [item for item in hex_content.split(' ') if item]
        if not hex_list:
            print("错误：文件中未读取到有效16进制数据")
            return

        # 3. 核心逻辑：每5字节1组，拆分到指定组数后，剩余数据整体保留
        result = []
        group_size = 25  # 固定每5个字节为1组
        total_items = len(hex_list)

        # 计算前stop_group组的总字节数
        stop_index = stop_group * group_size

        # 第一步：拆分前stop_group组（每组5字节）
        for i in range(0, min(stop_index, total_items), group_size):
            group = hex_list[i:i + group_size]
            result.append(' '.join(group))

        # 第二步：如果有剩余数据，整体保留（不分隔）
        if total_items > stop_index:
            remaining = hex_list[stop_index:]
            if remaining:
                result.append(' '.join(remaining))

        # 4. 打印格式化结果
        # print(f"按每{group_size}字节1组，分隔到第{stop_group}组后的结果：")
        for idx, line in enumerate(result, 1):
            if idx <= stop_group:
                print(f"{line}  #第{idx}组#")
            else:
                print(f"{line}")

        return result

    except FileNotFoundError:
        print(f"错误：未找到文件 {file_path}")
    except ValueError:
        print("错误：停止组数必须是正整数")
    except Exception as e:
        print(f"处理出错：{str(e)}")


# ===================== 执行脚本 =====================
if __name__ == "__main__":
    # 配置参数（按需修改）
    file_path = "hex_data.txt"  # 你的TXT文件路径
    stop_group = 174  # 自定义分隔到第N组（比如8、4，改这里就行）

    # 调用函数执行分隔
    split_hex_message(file_path, stop_group)