#!/usr/bin/env python3
import sys

def process_number(num):
    if num < 1:
        print(f"跳过无效数字 {num}（必须 ≥ 1）", file=sys.stderr)
        return False
    if num > 65535:
        print(f"警告：数字 {num} 超过 65535，将只使用低 16 位。", file=sys.stderr)
    high_byte = (num >> 8) & 0xFF
    low_byte = num & 0xFF
    # print(f"{high_byte:02X} {low_byte:02X}")
    print(f"{low_byte:02X}")
    return True

def main():
    numbers = []

    if len(sys.argv) > 1:
        # 命令行参数模式（空格分隔）
        for arg in sys.argv[1:]:
            try:
                numbers.append(int(arg))
            except ValueError:
                print(f"错误：'{arg}' 不是有效数字，已忽略。", file=sys.stderr)
    else:
        # 交互模式：每行一个数字，空行结束
        print("请输入数字（每行一个，空行结束）：")
        for line in sys.stdin:
            line = line.strip()
            if line == "":
                break
            try:
                numbers.append(int(line))
            except ValueError:
                print(f"错误：'{line}' 不是有效数字，已忽略。", file=sys.stderr)

    if not numbers:
        print("没有提供任何有效数字，程序退出。", file=sys.stderr)
        return

    for num in numbers:
        process_number(num)

if __name__ == "__main__":
    main()