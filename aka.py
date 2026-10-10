value = -95 # int16 范围内的负数
hex_str = format(value & 0xFFFF, '04X') # 保证按无符号16位显示
print(hex_str) # 输出 FF85