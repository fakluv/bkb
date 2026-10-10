import re
import time
import math
import random


class PublicFunc:

    def fix_str(self, data, num=2, ishead=True, fix_character='0'):
        """返回指定长度的字符串，不足前面补0"""
        str_len = len(data)
        if ishead:
            if str_len < num:
                data = fix_character * (num - str_len) + data
        else:
            if str_len < num:
                data = data + fix_character * (num - str_len)
        return data

    def str_reverse(self, data, num=2):
        """按指定字节数反转字符串，如 123456 -> 563412"""
        return_str = ['']
        deal_data = []
        data = data.replace(' ', '')
        for i in range(int(len(data) / num)):
            deal_data.append(data[num * i:num * (i + 1)])
        for d in deal_data[::-1]:
            return_str[0] = return_str[0] + d
        return return_str[0]

    def data_format(self, data, num=2):
        """给字符串按 num 个字符加空格"""
        num1 = int(num)
        return_data = ['']
        data = data.replace(" ", "")
        for i in range(len(data)):
            return_data[0] = return_data[0] + data[num1 * i:num1 * (i + 1)] + ' '
        return return_data[0].upper().strip()

    def int_to_hex(self, data, num=2):
        """十进制转十六进制，自动补齐指定位数"""
        data = int(data)
        data_hex = hex(data)[2:]
        data_hex_len = len(data_hex)
        if data_hex_len > num:
            num = math.ceil(data_hex_len / 2) * 2
        data_hex = self.fix_str(data_hex, num)
        return data_hex.upper()

    def deal_data(self, data, fix_hour=0, israndomtime=False, isformat=True,
                  time_type=1, return_data_type=1):
        """
        格式化报文，去掉注释、空格、换行，替换时间戳。
        返回16进制字符串（默认）或带时间的元组。
        """
        return_time = []

        # 去掉 ## 之间的注释
        regex = re.compile(r'(#)(.*)(#)')
        if isinstance(data, str):
            data1 = regex.sub(r'', data)
        else:
            data1 = regex.sub(r'', data.decode('utf-8'))

        data2 = data1.upper().replace('\n', '').replace('\t', '')
        data3 = data2.replace(" ", "")

        # 替换 [ ] 里的时间戳
        ismiddlebracket = True
        while ismiddlebracket:
            if '[' in data3 and ']' in data3:
                start_index = data3.index('[')
                end_index = data3.index(']')
                old_time_hex = data3[start_index + 1:end_index]

                if time_type == 1:
                    if israndomtime:
                        hour = random.randint(0, 30 * 24)
                    else:
                        hour = fix_hour
                    ori_time = int(time.time()) - hour * 3600
                else:
                    ori_time = time.time()

                stamp_time = time.localtime(ori_time)
                time_mon = hex(stamp_time[1])[2:]
                time_day = hex(stamp_time[2])[2:]
                time_hour = hex(stamp_time[3])[2:]
                time_min = hex(stamp_time[4])[2:]
                time_second = hex(stamp_time[5])[2:]
                part_time = [
                    self.fix_str(time_mon) +
                    self.fix_str(time_day) +
                    self.fix_str(time_hour) +
                    self.fix_str(time_min) +
                    self.fix_str(time_second)
                ]

                if 'R' in old_time_hex.upper():
                    isreversetime = True
                else:
                    isreversetime = False

                time_hex = old_time_hex.replace('R', '')
                time_len = len(time_hex)

                if time_len == 8:
                    stamp_time = int(ori_time)
                    hex_time = hex(stamp_time)[2:]
                    if isreversetime:
                        hex_time = self.str_reverse(hex_time)

                elif time_len == 12:
                    time_year = hex(stamp_time[0] - 2000)[2:]
                    time_year = self.fix_str(time_year)
                    hex_time = time_year + part_time[0]
                    if isreversetime:
                        hex_time = self.str_reverse(hex_time)

                elif time_len == 14 or time_len == 18:
                    time_year = hex(stamp_time[0])[2:]
                    time_year = self.fix_str(time_year, 4)
                    if isreversetime:
                        time_year = self.str_reverse(time_year)
                    hex_time = time_year + part_time[0]

                    if time_len == 18:
                        millionsecond_int = int(str(ori_time - int(ori_time))[2:5])
                        millionsecond_hex1 = hex(millionsecond_int)[2:]
                        millionsecond_hex2 = self.fix_str(millionsecond_hex1, 4)
                        if isreversetime:
                            millionsecond_hex2 = self.str_reverse(millionsecond_hex2)
                        hex_time = hex_time + millionsecond_hex2

                else:
                    print('时间戳字节特殊情况！')
                    stamp_time = int(ori_time)
                    hex_time = hex(stamp_time)[2:]
                    if isreversetime:
                        hex_time = self.str_reverse(hex_time)

                return_time.append(int(ori_time))
                data3 = data3[0:start_index] + hex_time + data3[end_index + 1:]
            else:
                ismiddlebracket = False

        # 处理帧长度占位符
        data4 = data3
        frame_len_int = 0

        if '{' in data4 and '}' in data4:
            start_index = data3.index('{')
            end_index = data3.index('}')
            frame1 = data3[start_index + 1:end_index]
            frame2 = frame1.replace('(', '').replace(')', '')
            frame3 = frame2.replace('R', '')
            frame_len_int = int(len(frame3) / 2)
            data4 = data4.replace('{', '').replace('}', '')

        if '<' in data4 and '>' in data4:
            start_index = data3.index('<')
            end_index = data3.index('>')
            frame1 = data3[start_index + 1:end_index]
            frame2 = frame1.replace('(', '').replace(')', '')
            frame3 = frame2.replace('R', '')
            frame_len_int = int(len(frame3) / 2)
            data4 = data4.replace('<', '').replace('>', '')

        data5 = data4.replace('（', '(').replace('）', ')')
        if '(' in data5 and ')' in data5:
            if frame_len_int != 0:
                start_index = data4.index('(')
                end_index = data4.index(')')
                len_part_code = data4[start_index:end_index + 1]

                new_len_part_code = len_part_code.replace('R', '')
                len_byte = int(len(new_len_part_code) - 2)

                len_byte_hex = self.int_to_hex(frame_len_int, len_byte)
                if 'R' in len_part_code:
                    len_byte_hex = self.str_reverse(len_byte_hex)

                data5 = data4[0:start_index] + len_byte_hex + data4[end_index + 1:]
            else:
                data5 = data4.replace('(', '').replace(')', '')

        if isformat:
            return_data = self.data_format(data5)
        else:
            return_data = data5

        if return_data_type == 1:
            return return_data
        else:
            return return_data, return_time[0]