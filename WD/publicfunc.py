import configparser
import copy
import datetime
import math
import os
import random
import re
import socket
import struct
import time
import traceback

import chardet
import matplotlib.pyplot as plt
import paramiko
import paramiko_expect
import psutil
import pymysql
import requests
import xlrd


class PublicFunc:

    def deal_data(self, data, fix_hour=0, israndomtime=False, isformat=True, time_type=1, return_data_type=1):
        """
        格式化报文，去掉注释等杂乱数据，返回16进制的报文
        :param israndomtime:
        :param isformat:
        :param len_byte:
        :param data: 处理的数据
        :param fix_hour: 减去的小时数，主要是控制发送报文中的报文时间
        :param time_type: 时间类型,1时为一般模式；非1时为存在秒的格式(主要用在计轴电压分析)
        :param return_data_type: 返回数据的格式，1时只返回数据，非1时返回数据和报文时间戳
        :return:
        """

        return_time = []

        # 去掉##之间的数据,去掉空格,去掉换行符; 注意: 字符串为bytes时，要先转换为str
        regex = re.compile(r'(#)(.*)(#)')
        if isinstance(data, str):
            data1 = regex.sub(r'', data)
        else:
            data1 = regex.sub(r'', data.decode('utf-8'))

        data2 = data1.upper().replace('\n', '').replace('\t', '')
        data3 = data2.replace(" ", "")

        # 修改[ ]里面的时间,加'R'或'r'表示反转时间
        ismiddlebracket = True
        while ismiddlebracket:

            if '[' in data3 and ']' in data3:

                # 获取[]里面的时间报文
                start_index = data3.index('[')
                end_index = data3.index(']')
                old_time_hex = data3[start_index + 1:end_index]

                # if len(old_time_hex) == 8:
                #     print('修改前报文时间:', time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(old_time_hex,16))))

                # 随机时间设置 hour = random.randint(0, 30*24)
                if time_type == 1:

                    if israndomtime:
                        hour = random.randint(0, 30 * 24)
                    else:
                        hour = fix_hour

                    ori_time = int(time.time()) - hour * 3600

                # 如果时间长度为9个字节时，要启用下面这个ori_time(现主要用在计轴电压分析)
                else:
                    ori_time = time.time()

                # 设置时间:月、日、时、分、秒
                stamp_time = time.localtime(ori_time)
                time_mon = hex(stamp_time[1])[2:]
                time_day = hex(stamp_time[2])[2:]
                time_hour = hex(stamp_time[3])[2:]
                time_min = hex(stamp_time[4])[2:]
                time_second = hex(stamp_time[5])[2:]
                part_time = [self.fix_str(time_mon) + self.fix_str(time_day) + self.fix_str(time_hour) + self.fix_str(time_min) + self.fix_str(time_second)]

                # 判断[]时间里面是否存在R、r
                if 'R' in old_time_hex.upper():
                    isreversetime = True
                else:
                    isreversetime = False

                # 替换[]时间的R或R为空
                time_hex = old_time_hex.replace('R', '')
                time_len = len(time_hex)

                # 替换时间,4个字节的时间戳，北京时间，如 5C ED 9E A0
                if time_len == 8:
                    stamp_time = int(ori_time)
                    hex_time = hex(stamp_time)[2:]

                    if isreversetime:
                        hex_time = self.str_reverse(hex_time)

                # 6个字节的时间戳，格林威治时间,如：13 02 13 03 00 16 (2019-02-19 03:00:22)
                elif time_len == 12:
                    time_year = hex(stamp_time[0] - 2000)[2:]
                    time_year = self.fix_str(time_year)

                    hex_time = time_year + part_time[0]

                    if isreversetime:
                        hex_time = self.str_reverse(hex_time)

                # 7个或9个字节的时间戳,9个字节时，最后两个字节时毫秒
                elif time_len == 14 or time_len == 18:

                    time_year = hex(stamp_time[0])[2:]
                    time_year = self.fix_str(time_year, 4)

                    if isreversetime:
                        time_year = self.str_reverse(time_year)

                    hex_time = time_year + part_time[0]

                    # 判断时间是否为9个字节，若是需加上毫秒
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
                # print('修改后时间:', hex_time)
                # print('报文的时间为:', time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ori_time)))
                # print('前端显示的时间:', time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ori_time + hour*60*60)))

            else:
                ismiddlebracket = False

        # 计算{}里面的帧长度
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

        # 替换( )里面的帧长度
        data5 = data4.replace('（','(').replace('）',')')
        if '(' in data5 and ')' in data5:

            if frame_len_int != 0:
                start_index = data4.index('(')
                end_index = data4.index(')')

                len_part_code = data4[start_index:end_index + 1]

                new_len_part_code = len_part_code.replace('R', '')
                len_byte = int(len(new_len_part_code)-2)

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

    def modify_code_time(self, old_time_data, time_type=1, fix_hour=0, target_time=0,is_random_time=False):
        # if len(old_time_hex) == 8:
        #     print('修改前报文时间:', time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(old_time_hex,16))))

        # 随机时间设置 hour = random.randint(0, 30*24)
        if time_type == 1:
            if is_random_time:
                hour = random.randint(0, 30 * 24)
            else:
                hour = fix_hour

            ori_time = int(time.time()) - hour * 3600

        # 适配指定时间
        elif time_type == 2:
            ori_time = target_time

        # 如果时间长度为9个字节时，要启用下面这个ori_time(现主要用在计轴电压分析)
        else:
            ori_time = time.time()

        # 设置时间:月、日、时、分、秒
        stamp_time = time.localtime(ori_time)
        time_year = stamp_time[0]
        time_mon = hex(stamp_time[1])[2:]
        time_day = hex(stamp_time[2])[2:]
        time_hour = hex(stamp_time[3])[2:]
        time_min = hex(stamp_time[4])[2:]
        time_second = hex(stamp_time[5])[2:]
        part_time = '{:0>2}{:0>2}{:0>2}{:0>2}{:0>2}'.format(time_mon, time_day, time_hour, time_min, time_second)

        # 判断[]时间里面是否存在R、r, 并去掉
        is_reverse_time = True if 'R' in old_time_data.upper() else False
        time_hex = old_time_data.replace('R', '').replace('r', '')
        time_byte = int(len(time_hex) / 2)

        # 替换时间,4个字节的时间戳，北京时间，如 5C ED 9E A0
        if time_byte == 4:
            stamp_time = int(ori_time)
            hex_time = hex(stamp_time)[2:]

            if is_reverse_time:
                hex_time = self.str_reverse(hex_time)

        # 6个字节的时间戳，格林威治时间,如：13 02 13 03 00 16 (2019-02-19 03:00:22)
        elif time_byte == 6:

            time_year_hex = hex(time_year - 2000)[2:]
            hex_time = '{:0>2}{}'.format(time_year_hex, part_time)

            if is_reverse_time:
                hex_time = self.str_reverse(hex_time)

        # 7个或9个字节的时间戳,9个字节时，最后两个字节时毫秒
        elif time_byte == 7 or time_byte == 9:

            time_year_hex = '{:0>4}'.format(hex(time_year)[2:])

            if is_reverse_time:
                time_year_hex = self.str_reverse(time_year_hex)

            hex_time = time_year_hex + part_time

            # 判断时间是否为9个字节，若是需加上毫秒
            if time_byte == 18:
                millionsecond_int = int(str(ori_time - int(ori_time))[2:5])
                millionsecond_hex = '{:0>4}'.format(hex(millionsecond_int)[2:])
                hex_time = hex_time + millionsecond_hex
        else:

            print('时间戳字节特殊情况！')
            stamp_time = int(ori_time)
            hex_time = hex(stamp_time)[2:]
            if is_reverse_time:
                hex_time = self.str_reverse(hex_time)

        return int(ori_time), hex_time

    def modify_code_len(self, data, frame_len):

        if frame_len:
            if '(' in data and ')' in data:

                start_index = data.index('(')
                end_index = data.index(')')
                len_part = data[start_index:end_index + 1]

                if 'R' in len_part.upper():
                    frame_len = self.str_reverse(frame_len)

                new_data = data[0:start_index] + frame_len + data[end_index + 1:]
            else:
                new_data = data.replace('(', '').replace(')', '')
        else:
            new_data = data

        return new_data

    def calc_code_len(self, data, len_byte=2):
        if '{' in data and '}' in data:
            start_index = data.index('{')
            end_index = data.index('}')
            old_frame = data[start_index + 1:end_index]
            frame = old_frame.replace('(', '').replace(')', '')
            frame = frame.replace('R', '').replace('r', '')

            frame_int = int(len(frame) / 2)
            frame_len = self.fix_str(hex(frame_int)[2:], len_byte * 2)
            new_data = data.replace('{', '').replace('}', '')
        else:
            frame_len = False
            new_data = data

        return frame_len, new_data

    def deal_data_new(self, data, fix_hour=0, israndomtime=False, isformat=True, time_type=1, len_byte=4, return_data_type=1):

        return_time = []

        # 去掉##之间的数据,去掉空格,去掉换行符; 注意: 字符串为bytes时，要先转换为str
        regex = re.compile(r'(#)(.*)(#)')
        if isinstance(data, str):
            data1 = regex.sub(r'', data)
        else:
            data1 = regex.sub(r'', data.decode('utf-8'))

        data2 = data1.replace('\n', '').replace(' ', '')

        # 修改[ ]里面的时间,加'R'或'r'表示反转时间
        is_change_time = True
        while is_change_time:
            if '[' in data2 and ']' in data2:

                # 获取[]里面的时间报文
                start_index = data2.index('[')
                end_index = data2.index(']')

                head_data = data2[0: start_index]
                time_data = data2[start_index + 1:end_index]
                end_data = data2[end_index + 1:]

                ori_time, new_hex_time = self.modify_code_time(time_data, time_type, fix_hour, israndomtime)

                return_time.append(ori_time)
                data2 = head_data + new_hex_time + end_data

                # print('发送报文的时间:', time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ori_time)))
                # print('前端显示的时间:', time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ori_time + hour*60*60)))
            else:
                is_change_time = False

        # 计算{}里面的帧长度
        frame_len, new_data = self.calc_code_len(data2, len_byte)

        # 替换()里面的帧长度
        new_data = self.modify_code_len(new_data, frame_len)

        if isformat:
            return_data = self.data_format(new_data)
        else:
            return_data = new_data

        if return_data_type == 1:
            return return_data
        else:
            return return_data, return_time[0]

    def send_to_mss(self, sourse_ip, dest_ip, dest_port, data, time_out=0.1, hour=0, time_type=1, sourse_port=10000, is_show_rec=True):
        """
        通过UDP往MSS采集服务器发送bytes报文
        :param sourse_ip: 源IP
        :param dest_ip: 目的IP
        :param dest_port: 端口
        :param data: 发送报文
        :param time_out: 超时时间,即发送报文后，等待返回报文的最大等待时间
        :param hour:加减小时设置
        :param time_type:时间类型设置
        :param sourse_port：源端口
        :return:
        """
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_socket.settimeout(time_out)

        # print('发送的数据：', data)

        # 对于发送方端口为10000的，数据进行格式化处理
        if sourse_port in [10000, 10001]:
            data1 = self.deal_data(data, hour, time_type=time_type)
            data1 = data1.upper()

            print('data1', data1)
            postdata = bytes.fromhex(data1)

        # 对于发送端口不是10000的不处理，暂时用到的是计轴的LOG日志上传，端口为50001
        else:
            data1 = data.encode('utf-8')
            postdata = data1

        host_address = (sourse_ip, sourse_port)
        server_address = (dest_ip, dest_port)  # 接收方 服务器的ip地址和端口号
        client_socket.bind(host_address)

        client_socket.sendto(postdata, server_address)

        if is_show_rec:
        # noinspection PyBroadException
            try:
                receive_data, client = client_socket.recvfrom(10240)
                client_socket.close()
                return_data = self.data_format(receive_data.hex())
                print('接收的数据：', client, return_data, '\n')
                return client, return_data

            except Exception:
                print("无返回数据\n")
                return '', '没有接收到返回报文!'

    def send_mss_by_tcp_xml(self, ip, port, xmlbw, isshowcode=False):
        """
        TCP客户端发送XML格式的报文，北京7计轴
        :param ip: tcp客户端所在IP
        :param port: 启用的端口
        :param xmlbw: xml格式的报文数据
        :param isshowcode: True时显示发送报文,Fasle时不显示
        :return: 应答报文
        """
        if isshowcode:
            print("发送的报文: \n", xmlbw)
        xmlbw = xmlbw.replace(' ', '')
        address = (ip, port)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(0.5)

        # noinspection PyBroadException
        try:
            client.connect(address)
        except Exception:
            print('报错:', Exception)
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(address)
        finally:
            by = xmlbw.encode('utf8')  # 转为字节数组
            client.send(by)

        # noinspection PyBroadException
        try:
            data = client.recv(1024)  # 接受响应信息
            print('接收响应成功,返回的数据:', data)
            client.close()
            return data
        except Exception:
            print("没有接收到返回报文")
            client.close()
            return None

    def send_mss_by_tcp_byte(self, tcpclisock, send_message):
        """
        TCP协议发送16进制报文数据
        :param tcpclisock: tcp连接对象,可为服务器或未客户端
        :param send_message: 16进制报文数据
        :return:
        """
        data1 = self.deal_data(send_message)
        data1 = data1.upper()
        postdata = bytes.fromhex(data1)
        tcpclisock.send(postdata)

    def write_ini(self, file, section_data):
        """
        往ini文件中写数据
        :param file: ini文件名称
        :param section_data: {
            section_name:{key:value,...}
        :return:
        """
        config = configparser.ConfigParser(allow_no_value=True)

        try:
            config.read(file, encoding='utf-8')
        except UnicodeDecodeError:
            config.read(file, encoding='gbk')

        for section_name, section_values in section_data.items():
            for key, value in section_values.items():
                config.set(section_name, key, value)

        # f = open(file, "w", encoding='utf-8')
        try:
            f = open(file, "w", encoding='utf-8')
        except UnicodeDecodeError:
            f = open(file, "w", encoding='gbk')
        config.write(f)

    def update_ini(self, file, section_name, key, value):
        """
        往ini文件中写数据
        :param file: ini文件名称
        :param section_name: section值
        :param key: key值
        :param value: value值
        :return:
        """
        config = configparser.ConfigParser()
        # config.read(file, encoding='gbk')
        try:
            config.read(file, encoding='utf-8')
        except UnicodeDecodeError:
            config.read(file, encoding='gbk')
        config.set(section_name, key, value)

        try:
            config.write(open(file, "w", encoding='utf-8'))
        except UnicodeDecodeError:
            config.write(open(file, "w", encoding='gbk'))
        # config.write(open(file, "w", encoding='utf-8'))

    def delete_ini(self, file, section_data):
        # section_data： [[section, item1], [section, item2]...]
        config = configparser.ConfigParser()
        config.read(file)

        for data in section_data:
            section_name, item = data
            config.remove_option(section_name, item)
        config.write(open(file, "w"))

    def data_format(self, data, num=2):
        """
        字符串加空格显示
        :param data:要转格式的数据
        :param num: 空格位置,如123456,为2时返回12 34 56,为3时返回123 456
        :return: return_data
        """
        num1 = int(num)
        return_data = ['']
        data = data.replace(" ", "")
        for i in range(len(data)):
            return_data[0] = return_data[0] + data[num1 * i:num1 * (i + 1)] + ' '

        return return_data[0].upper().strip()

    def get_nowtime(self, isneeddecimal=False, isstamp=False, return_type=1, format_stamp=0):
        """
        获取当前时间
        :param isneeddecimal: true返回毫秒值，false返回一般值
        :param isstamp: 是否字符串
        :return: return_time
        """
        time_stamp = time.time() + format_stamp
        time_stamp_int = int(time_stamp)
        decimal_part = str(time_stamp - time_stamp_int)[1:5]  # 小数点部分
        timearray = time.localtime(time_stamp)

        if not isstamp:
            if isneeddecimal:
                return_time = time.strftime("%Y-%m-%d %H:%M:%S", timearray) + decimal_part
            else:
                return_time = time.strftime("%Y-%m-%d %H:%M:%S", timearray)
        else:
            return_time = time_stamp_int

        if return_type == 1:
            return str(return_time)
        elif return_type == 2:
            return time_stamp_int, return_time
        else:
            stamp = '{}{}'.format(time_stamp_int, decimal_part[1:])
            return stamp, return_time

    def get_now_hex_time(self, is_reverse=False):
        time_stamp = time.time()
        time_stamp_int = int(time_stamp)
        hex_time = hex(time_stamp_int)

        hex_time_re = self.str_reverse(hex_time[2:])

        if is_reverse:
            return  time_stamp_int, hex_time_re
        else:
            return time_stamp_int, hex_time

    def fix_str(self, data, num=2, ishead=True, fix_character='0'):
        """
        返回指定长度的字符串,不足长度的前面补0
        :param data: 原字符串
        :param num:  指定长度,默认值为2,
        :param ishead: 补头或补尾
        :param fix_character: 补位符
        :return: 补偿的字符
        """
        str_len = len(data)

        if ishead:
            if str_len < num:
                data = fix_character * (num - str_len) + data
        else:
            if str_len < num:
                data = data + fix_character * (num - str_len)

        return data

    def get_random_num(self, num1, num2, num_len=2, isneedint=False):
        """
        获取指定范围内的随机数，并返回16进制值
        :param num1: 指定最小值
        :param num2: 指定最大值
        :param num_len: 返回16进制数值的长度,默认值为2,为2时返回01，为4时返回0001
        :param isneedint: True时发int型数值也返回，Fase不返回
        :return: hex_num
        """

        num1_int = int(num1)
        num2_int = int(num2)

        int_num = random.randint(num1_int, num2_int)
        hex_num = hex(int_num)[2:]

        hex_num = self.fix_str(hex_num, num_len)

        if isneedint:
            return int_num, hex_num
        else:
            return hex_num

    def str_reverse(self, data, num=2):
        """
        反转字符串
        :param data: 需要反转的字符串数据
        :param num:  反转间隔,默认值为2,如字符串ABCDEF,间隔为2时反转为CCBBAA;为3时反转为DEFABC
        :return: return_str
        """
        return_str = ['']
        deal_data = []

        data = data.replace(' ', '')

        for i in range(int(len(data) / num)):
            deal_data.append(data[num * i:num * (i + 1)])

        for data in deal_data[::-1]:
            return_str[0] = return_str[0] + data

        return return_str[0]

    def str_to_bytes(self, str_data):
        """
        把字符串数据转换成可bytes类型,可进行网络数据传输
        :param str_data: 要转换的字符串数据
        :return: bytes_data
        """

        # print('发送的报文: {}\n'.format(str_data))
        str_data = str_data.upper().replace(" ", "")
        bytes_data = bytes.fromhex(str_data)
        return bytes_data

    def letter_to_number(self, num):
        """
        英文字母转为数字:如A转为1, b转为2, aB转为27
        :param num: 要转换的英文值,如"A","B","a"
        :return: return_data[0]
        """

        return_data = ['']  # 返回的值

        num1 = num.upper()
        data = {
            'A': 1,
            'B': 2,
            'C': 3,
            'D': 4,
            'E': 5,
            'F': 6,
            'G': 7,
            'H': 8,
            'I': 9,
            'J': 10,
            'K': 11,
            'L': 12,
            'M': 13,
            'N': 14,
            'O': 15,
            'P': 16,
            'Q': 17,
            'R': 18,
            'S': 19,
            'T': 20,
            'U': 21,
            'V': 22,
            'W': 23,
            'X': 24,
            'Y': 25,
            'Z': 26
        }

        # 转换数值的长度
        num_len = len(num1)

        # 数值长度为1时
        if num_len == 1:
            return_data[0] = data[num1]

        # 数值长度为2时
        elif num_len == 2:
            return_data[0] = 26 * (data[num1[0]]) + data[num1[-1]]

        # 数值长度大于3时,未开发,一般用不到那么大的数据
        else:
            print('待开发...')

        return return_data[0]

    def get_excel_data(self, dir_path, file_name, sheet_name, row_col_name='', start_index=1, end_index=None, isrow=False, isint=True):
        """
        读取excel文件中指定sheet页的数据
        :param dir_path: 文件存放路径
        :param file_name: 文件名称
        :param sheet_name: sheet页名称
        :param row_col_name: 指定列的名称,如 A列、B列、C列...AB列。直接输入如:"A",表示读取A列的值
        :param start_index: 索引编号开始的行数，即excel中左边序号栏的1,2,3,4,...
        :param end_index：为空时,获取所有行的数据;为N时，获取N行的数据
        :param isrow: true时,获取行数据；Fasle时，获取列数据
        :param isint：true时，返回的数据为INT型；False时,不对读取到的excel单元格中的值做处理
        :return: return_data
        """

        deal_files = []  # 目标文件名称
        return_data = []  # 返回的值

        # 获取目录下所有的文件
        dir_files = os.listdir(dir_path)

        # 过滤出想要的文件
        for file in dir_files:
            if file_name in file:
                deal_files.append(file)

        # 处理想要的文件
        for file in deal_files:

            # 构建文件路径
            file_path = dir_path + '/' + file

            # 打开EXCEL文件,打开指定的sheet页
            file_datas = xlrd.open_workbook(file_path, formatting_info=False)
            sheet_table = file_datas.sheet_by_name(sheet_name)

            if isrow:

                rows = sheet_table.nrows
                print('rows', rows)

                if end_index:
                    rows = end_index

                for i in range(start_index, rows):
                    rowdata = sheet_table.row_values(i)
                    print('rowdata', rowdata)

            else:
                # 获取指定列的值
                col_index = self.letter_to_number(row_col_name) - 1
                values = sheet_table.col(col_index)

                # 数据开始的行索引号
                number_start_index = start_index - 1

                # 数据结束的行索引号
                if end_index:
                    # number_end_index = number_start_index + rows
                    number_end_index = end_index + 1
                else:
                    number_end_index = len(values)

                # 获取数据
                for i in range(number_start_index, number_end_index):

                    # 过滤空值
                    if values[i].value != '':

                        data = values[i].value
                        if isinstance(data, str):
                            data = data.replace('\n', '').replace('\r', '')

                        if isint:
                            return_data.append(int(data))
                        else:
                            return_data.append(data)

        return return_data

    def get_file_charset(self, file_path):

        f = open(file_path,'rb')
        data = f.read()
        encoded = chardet.detect(data[:512])['encoding']

        return encoded

    def get_text_data(self, dir_path, file_name, return_type=1):
        """
        获取指定目录下，指定txt文件的数据
        :param dir_path: 文件存放路径
        :param file_name: 文件名含有的名称(即模糊查询)
        :param return_type：返回数据的类型
        :return: return_data
        """

        deal_files = []  # 目标文件名称
        return_data = []  # 返回的值

        # 获取目录下所有的文件
        dir_files = os.listdir(dir_path)

        # 过滤出想要的文件
        for file in dir_files:
            if file_name in file:
                deal_files.append(file)

        # 处理想要的文件
        deal_files.sort()

        for file in deal_files:

            print('正在处理的文件为：{}/{}'.format(dir_path, file))

            # 构建文件路径
            file_path = dir_path + '/' + file

            # 打开文件
            print('正在打开文件...')
            f_encoded = self.get_file_charset(file_path)

            f1 = open(file_path, 'r', encoding='GB2312')
            # f1 = open(file_path, 'r', encoding=f_encoded)

            print('文件打开成功，读取处理数据...')
            for line_data in f1:

                # 为1时，去掉\n、*、-、和空格，现主要用在读取powerDH的配置文件
                if return_type == 1:
                    line_data = line_data.replace('\n', '')
                    if line_data != '':
                        line_data = line_data.replace('-', '').replace('*', '').replace(' ', '')
                        return_data.append(line_data)

                # 为2时，处理存在[]、{}的子系统报文
                elif return_type == 2:
                    start_index = line_data.index('[')
                    end_index = line_data.index(']')
                    head_part = line_data[start_index + 1:end_index]
                    if 'Send_Heart' in head_part:
                        continue

                    start_index = line_data.index('{')
                    end_index = line_data.index('}')
                    single_data = line_data[start_index + 1:end_index]
                    single_data = single_data.replace(' ', '')
                    return_data.append(single_data)

                # 不做处理，直接返回每行的数据
                else:
                    line_data = line_data.replace(' ', '')
                    return_data.append(line_data)

        return return_data

    def float_to_hex(self, f):
        """
        浮点数转十六进制数
        :param f: 浮点数
        :return:
        """
        f_int = str(f)

        if '.' in f_int:
            f_int = float(f_int)
            data = hex(struct.unpack('<I', struct.pack('<f', f_int))[0])
            return data[2:]

        else:
            f_int = int(f_int)
            f_hex = self.int_to_hex(abs(f_int))

            if f_int >= 0:
                real_f_hex = f_hex
            else:
                f_hex_byte_num = int(len(f_hex)/2)

                boundary_value_hex = '80' + '00' * (f_hex_byte_num - 1)
                boundary_value_int = int(boundary_value_hex, 16)

                real_f_int = float(f) + boundary_value_int
                real_f_bin = self.int_to_bin(int(real_f_int))
                real_f_bin = '1' + real_f_bin[1:]

                real_f_int = int(real_f_bin, 2)
                real_f_hex = self.int_to_hex(real_f_int)

            return real_f_hex

    def hex_to_float(self, h, isreverse=False):
        """
        十六进制数转浮点数
        :param isreverse:
        :param h: 16进制数据
        :return:
        """
        h = h.replace(" ", "")
        h_len = len(h)

        if isreverse:
            h = self.str_reverse(h)

        if h_len == 8:
            i = int(h, 16)
            data = struct.unpack('<f', struct.pack('<I', i))[0]
        else:

            h_int = int(h, 16)
            h_byte_num = math.ceil(len(h)/2)
            h_bin = self.int_to_bin(h_int, num=8*h_byte_num)

            boundary_value_hex = '80' + '00' * (h_byte_num - 1)
            boundary_value_int = int(boundary_value_hex, 16)

            if h_bin[0] == '0':
                data = h_int
            else:
                modify_h_bin = '0' + h_bin[1:]
                modify_h_int = int(modify_h_bin, 2)
                data = modify_h_int - boundary_value_int

        return round(data, 2)

    def hex_to_float2(self, h, isreverse=False):
        """
        十六进制数转浮点数
        :param isreverse:
        :param h: 16进制数据
        :return:
        """
        h = h.replace(" ", "")
        h_len = len(h)

        if isreverse:
            h = self.str_reverse(h)

        h_int = int(h, 16)

        if h_len == 4:
            part_data = 32676

            if h_int > part_data:
                data = h_int - 65536
            else:
                data = h_int

        else:

            h_byte_num = math.ceil(len(h)/2)
            h_bin = self.int_to_bin(h_int, num=8*h_byte_num)

            boundary_value_hex = '80' + '00' * (h_byte_num - 1)
            boundary_value_int = int(boundary_value_hex, 16)

            if h_bin[0] == '0':
                data = h_int
            else:
                modify_h_bin = '0' + h_bin[1:]
                modify_h_int = int(modify_h_bin, 2)
                data = modify_h_int - boundary_value_int

        return round(data, 2)

    def random_float(self, min_value, max_value, isreverse=False):

        num_int = round(random.uniform(min_value, max_value), 2)
        num_hex = self.float_to_hex(num_int)

        if isreverse:
            num_hex = self.str_reverse(num_hex)

        num_hex = self.data_format(num_hex)

        # print('{:.2f} : {}'.format(num_int, num_hex))
        return num_int, num_hex

    def get_mysql_data(self, server_ip, sql, return_type=1, database='base', port=3306, isall=True):
        """
        从MYSQL数据中获取数据
        :param port:
        :param isall:
        :param server_ip: mysql数据库的IP
        :param sql: 要执行的sql语句
        :param return_type: 返回数据的格式，为1时返回全部数据，不做处理；为2时返回特定的数据
        :param database: 读取的数据库，默认为base库
        :return:
        """
        ip = server_ip
        user = 'root'
        passwd = 'mysql'
        db = pymysql.connect(host=ip, user=user, passwd=passwd, db=database, port=port, charset='utf8')

        cursor = db.cursor()
        cursor.execute("%s" % sql)

        if isall:
            res_all = cursor.fetchall()
        else:
            res_all = cursor.fetchone()

        # 直接返回全部，不做任何处理
        if return_type == 1:
            return res_all

        # 返回全部数据中每个元素的第一个索引值的列表
        elif return_type == 2:
            return_data = []
            for data in res_all:
                return_data.append(data[0])
            return return_data

        # 全部数据中每个元素的值用,连接起来后返回
        elif return_type == 3:
            return_data = []
            for data in res_all:
                sigle_data = ['']
                for i in range(len(data)):
                    sigle_data[0] = sigle_data[0] + str(data[i])

                    if i != len(data) - 1:
                        sigle_data[0] = sigle_data[0] + ','

                return_data.append(sigle_data[0])
            return return_data

        db.close()

    def operate_mysql_database(self, server_ip, database_name, port=3306, operate_type=1):
        ip = server_ip
        user = 'root'
        passwd = 'mysql'
        db = pymysql.connect(host=ip, user=user, passwd=passwd, port=port, charset='utf8')
        cursor = db.cursor()

        create_database = 'CREATE DATABASE IF NOT EXISTS %s CHARACTER SET utf8 COLLATE utf8_general_ci' % database_name
        drop_database = 'drop DATABASE IF EXISTS %s' % database_name

        if operate_type == 1:
            cursor.execute(create_database)
            show_data = '成功创建数据库：%s' % database_name
        else:
            cursor.execute(drop_database)
            show_data = '成功删除数据库：%s' % database_name

        print(show_data)

    def execute_mysql(self, server_ip, sql, port=3306, database='base', isreturn_data=True):

        ip = server_ip
        user = 'root'
        passwd = 'mysql'
        db = pymysql.connect(host=ip, user=user, passwd=passwd, port=port, db=database, charset='utf8')
        cursor = db.cursor()
        cursor.execute("%s" % sql)

        if isreturn_data:
            res_all = cursor.fetchall()
            print(res_all)
        db.commit()
        db.close()

    def bin_to_hex(self, data, fix_num=2):

        data = data.replace(' ', '')
        data = self.fix_str(data, 8)

        data_bin = '0b' + data
        data_int = int(data_bin, 2)
        data_hex = self.fix_str(hex(data_int)[2:], fix_num).upper()

        return data_hex

    def int_to_hex(self, data, num=2):
        """
        10进制数值转为16进制数值
        :param data: 10进制数值
        :param num: 16进制数值长度,为2时如01，为4时如0001
        :return: data_hex
        """
        data = int(data)
        data_hex =hex(data)[2:]

        data_hex_len = len(data_hex)
        if data_hex_len > num:
            num = math.ceil(data_hex_len/2) * 2

        data_hex = self.fix_str(data_hex, num)

        return data_hex.upper()

    def int_to_bin(self, data, num=8):
        """
        10进制数值转为2进制数值
        :param data: 10进制数值
        :param num: 2进制数值长度,为8时如0000 0001
        :return: data_bin
        """
        data_bin = bin(data)[2:]

        data_bin_len = len(data_bin)
        if data_bin_len > num:
            num = math.ceil(data_bin_len/8) * 8

        data_bin = self.fix_str(data_bin, num)
        return data_bin

    def int_to_signint(self, data):

        data_bin = self.int_to_bin(data)

        if data_bin[0] == '0':
            data_signint = data

        else:
            data_signbin = '0' + data_bin[1:]
            data_signint = int(data_signbin, 2) - 128

        return data_signint

    def delete_file(self, file_path, file_name, ispath=True):
        if ispath:
            file_path_name = file_path + file_name
        else:
            file_path_name = file_name

        if os.path.exists(file_path_name):
            os.remove(file_path_name)

    def getdate(self, count_date, iscontinue=True, data_type='day', isonlydate=False):

        now_time = datetime.datetime.now().replace(microsecond=0)

        if iscontinue:
            re_date = []
            for i in range(count_date):
                offset = datetime.timedelta(days=-i)
                date = (now_time + offset).strftime('%Y-%m-%d')
                re_date.append(date)
            re_date.sort()

            return re_date
        else:
            if data_type == 'day':
                offset = datetime.timedelta(days=-count_date)

            elif data_type == 'hour':
                offset = datetime.timedelta(hours=-count_date)

            elif data_type == 'minute':
                offset = datetime.timedelta(minutes=-count_date)

            elif data_type == 'week':
                offset = datetime.timedelta(weeks=-count_date)

            else:
                offset = datetime.timedelta(days=-count_date)

            if isonlydate:
                date = (now_time + offset).strftime('%Y-%m-%d')
            else:
                date = (now_time + offset).strftime('%Y-%m-%d %H:%M:%S')
            return str(date), str(now_time)

    def get_date_info(self, target_date=None, return_type=1, is_target_date=True):


        now_stamp = time.time()
        now_stamp_int = int(now_stamp)
        now_stamp_microsecond_int = int(now_stamp*1000)

        time_array = time.localtime(now_stamp_int)


        year_month = time.strftime("%Y-%m", time_array)
        year_month_day = time.strftime("%Y-%m-%d", time_array)
        date_time = time.strftime("%Y-%m-%d %H:%M:%S", time_array)


        print(now_stamp, now_stamp_microsecond_int, year_month, year_month_day, date_time)


        if return_type == 1:
            return year_month

        else:
            return


    def start_tcp_server(self, sourse_ip, dest_ip, port):
        """
        启用TCP服务器
        :param sourse_ip: TCP服务器的IP
        :param dest_ip: 需要连接的TCP客户端IP
        :param port: TCP服务器启用的端口
        :return: tcp服务器对象
        """

        print('正在启用TCP服务器(IP: %s   PORT: %s)...' % (sourse_ip, port))
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((sourse_ip, port))
        server.listen(5)
        print(f'服务器打开成功, 等待客户端{dest_ip}连接...')

        # tcpclisock, server_addr = server.accept()
        # while server_addr[0] != dest_ip:
        #     print('当前连接的TCP客户端IP(%s)不是目标IP(%s)，正断开重连...' % (server_addr[0], dest_ip))
        #     tcpclisock.close()
        #     tcpclisock, server_addr = server.accept()

        is_connect = False

        tcpclisock = ''
        server_addr = []
        while not is_connect:


            tcpclisock, server_addr = server.accept()
            tcpclisock.settimeout(3)

            print('server_addr', server_addr)

            if server_addr[0] != dest_ip:
                print('当前连接的TCP客户端IP(%s)不是目标IP(%s)，正断开重连...' % (server_addr[0], dest_ip))
                time.sleep(1)
                tcpclisock.close()
            else:
                is_connect = True

            # time.sleep(1)

            # rec_data = tcpCliSock.recv(2048).hex()
            # print('rec_data: ', rec_data)

                print('当前连接的TCP客户端 IP= %s ,PORT= %s' % (server_addr[0], server_addr[1]))

                return tcpclisock

    def start_tcp_client(self, ip, port):
        """
        启用TCP客户端
        :param ip: 想要连接的TCP服务器地址
        :param port: 想要连接的TCP服务器端口
        :return: tcp客户端对象
        """

        print('正在启用TCP客户端...')
        address = (ip, port)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(10)
        # client.bind(('192.168.1.25', 0))
        client.connect(address)
        client.settimeout(None)

        sourse_addr = client.getsockname()
        dest_addr = client.getpeername()
        print('本机地址：', sourse_addr, '服务器地址：', dest_addr)

        return client

    def tcp_client_send_data(self, tcp_client, data, data_type=1):
        """
        TCP客户端发送数据
        :param tcp_client: tcp客户端对象
        :param data: 发送的数据
        :param data_type: 数据类型,1时为一般值转成bytes类型数据;其他值时以utf-8编码对u进行编码，获得bytes类型对象
        :return: 无
        """

        data = data.replace(' ', '')

        if data_type == 1:
            send_data = bytes.fromhex(data.upper())
        else:
            send_data = data.encode('utf8')

        tcp_client.send(send_data)

    def write_txt_data(self, file_path, file_name, data, isprint=False):

        if isprint:
            print(data)

        file_path_name = file_path + file_name

        if not os.path.exists(file_path):
            os.makedirs(file_path)

        with open(file_path_name, 'a+') as f:
            f.write(data + '\n')

    def hex_to_chiness(self, data):
        """
        hex字符串转中文
        :param data: 要转换的hex字符串
        :return: 返回转换后的中文data_cn
        """
        # hex字符串转换成bytes
        data_bytes = bytes.fromhex(data)
        print('data_bytes: ', data_bytes)

        # bytes解码gbk格式成中文
        data_cn = data_bytes.decode('GBK')
        print('转换后的中文值: ', data_cn)

        return data_cn

    def chiness_to_hex(self, data):
        """
        中文转hex字符串
        :param data: 要转换的中文值
        :return: 转换后的hex字符串data_hex
        """

        # 中文值GBK编码成bytes
        data_gbk = data.encode('GBK')
        print('data_gbk: ', data_gbk)

        # bytes转换为hex字符串
        data_hex = bytes.hex(data_gbk)
        data_hex = self.data_format(data_hex)
        print('转换后的hex字符串: ', data_hex)

        return data_hex

    def ascii_to_hex(self, data):
        """
        ASCLL字符串转hex字符串
        :param data: ASCII字符串
        :return: hex字符串return_data
        """
        return_data = ['']
        value_mapping = {
            30: 0,
            31: 1,
            32: 2,
            33: 3,
            34: 4,
            35: 5,
            36: 6,
            37: 7,
            38: 8,
            39: 9,
            41: 'A',
            42: 'B',
            43: 'C',
            44: 'D',
            45: 'E',
            46: 'F',
            61: 'a',
            62: 'b',
            63: 'c',
            64: 'd',
            65: 'e',
            66: 'f',
        }

        data = data.replace(' ', '')
        data_len = int(len(data) / 2)

        for i in range(data_len):
            sigle_data_hex = data[2 * i:2 * (i + 1)]
            sigle_data_int = int(sigle_data_hex)
            sigle_data_value = str(value_mapping[sigle_data_int])

            return_data[0] = return_data[0] + sigle_data_value

        return_data[0] = self.data_format(return_data[0])

        return return_data[0]

    def hex_to_ascii(self, data):
        """
            hex字符串转ASCLL字符串
            :param data: hex字符串
            :return: hex字符串return_data
        """
        return_data = ['']
        value_mapping = {
            '0': '30',
            '1': '31',
            '2': '32',
            '3': '33',
            '4': '34',
            '5': '35',
            '6': '36',
            '7': '37',
            '8': '38',
            '9': '39',
            'A': '41',
            'B': '42',
            'C': '43',
            'D': '44',
            'E': '45',
            'F': '46',
            'a': '61',
            'b': '62',
            'c': '63',
            'd': '64',
            'e': '65',
            'f': '66',
        }

        data_len = len(data)
        for i in range(data_len):
            key = data[i]

            if key != ' ':
                value = value_mapping[key]
            else:
                value = ' '

            return_data[0] = return_data[0] + value

        return return_data[0]

    def date_to_stamp(self, date, data_type=1, istime=False):
        """
        日期和时间戳转换
        :param date: 日期
        :param data_type: 转换类型:1时为日期零点；2时为日期的23点
        :param istime: 是否包含时间
        :return:
        """
        if not istime:
            if data_type == 1:
                date = date + ' 00:00:00'
            else:
                date = date + ' 23:59:59'
        else:
            date = date

        date = date.split('-')
        year = date[0]
        month = date[1]
        other_date = date[2]

        other_date = other_date.split(':')
        day = other_date[0][0:2]
        hour = other_date[0][2:]
        minute = other_date[1]
        second = other_date[2]

        new_date = '{}-{}-{} {}:{}:{}'.format(year, month, day, hour, minute, second)
        timearray = time.strptime(new_date, "%Y-%m-%d %H:%M:%S")
        timestamp = int(time.mktime(timearray))

        return date, timestamp

    def stamp_to_date(self, send_stamp, data_type=1):

        if data_type == 1:
            date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(send_stamp)))
        else:
            date_str = time.strftime("%Y-%m-%d", time.localtime(int(send_stamp)))

        return date_str

    def execute_linux_order(self, ip, order, username="root", port=22, password='mysql', is_root=False, isreadfile=False, *args):
        """
        执行Linux命令
        :param username:
        :param port:
        :param password:
        :param is_root:
        :param isreadfile:
        :param ip: Linux服务器IP
        :param order: 执行名称
        :return: None
        密码都由root修改为 shenzhen@tct
        """

        ssh = paramiko.SSHClient()

        # 设定自动 远程主机的 SSH Key
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # 设定连接 ssh 的主机IP, 端口，用户名，用户密码
        # port = 6622
        # password = "shenzhen@tct#server{}".format(ip.split('.')[-1])

        ssh.connect(ip, port, username, password)
        if isreadfile:
            file_path = args[0]
            file_data = []

            sftp_client = ssh.open_sftp()
            remote_file = sftp_client.open(file_path)  # 文件路径
            try:
                for line in remote_file:
                    file_data.append(line)
            finally:
                remote_file.close()
                return file_data
        else:
            # paramiko_expect模块：进行终端交互
            if is_root:
                with paramiko_expect.SSHClientInteraction(ssh, display=True) as interact:
                    su_password = 'shenzhen@tct#server{}'.format(ip.split('.')[-1])
                    interact.send('su')
                    interact.send(su_password)

                    # interact.send(order)

            # ssh_stdin：标准输入  ssh_stdout: 标准输出  ssh_stderr：标准错误
            print('当前执行的Linux命令为:', order)
            ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(order)

            return_data = []
            result = ssh_stdout.readlines()
            print('终端显示的信息:')
            for data in result:
                data = data.replace('\n', '')
                return_data.append(data)
                print(data)

            return_data.sort()

            notice_data = ssh_stderr.read().decode('utf8')
            if notice_data:
                print('提示信息:\n', notice_data)

            print('命令执行成功\n')

            ssh.close()
            return return_data if return_data else ['']

    def get_line_detail(self, ip, data_type=1):
        """
        获取工程线的详细数据
        :param ip: 服务器IP
        :param data_type: 获取数据的类型
        :return: 1时返回站点编号名称信息；2时返回列车总数
        """

        url = 'http://%s:8080/mss/ledger/getLineDetails2?userId=fbd1d0fdb5ae434cab15de9fe376c834' % ip
        api_data = requests.post(url).json()

        train_num = int(api_data['train'])
        old_stations = api_data['station']
        center = api_data['centerStation']

        # 处理API返回的站点信息，并添加0作为全部站点
        new_stations = {0: '全部站点'}

        for data in old_stations:
            new_stations[int(data['stationNo'])] = data['stationName']

        # 获取站点编号名称信息，类型为字段
        if data_type == 1:
            return new_stations

        # 获取列车总数量
        elif data_type == 2:
            return train_num

        # 获取列车总数量
        elif data_type == 3:
            center_name = []
            for data in center:
                center_name.append(data['centerName'])

            return center_name

    # 重启tomcat
    def restart_tomcat(self, ip):

        kill_tomcat = "ps -ef | grep tomcat | grep -v grep | awk '{print $2}' | xargs kill -9;"
        restart_memcahced = "service memcached-repcached restart;"
        restart_tomcat = "source /etc/profile; sh /var/local/apache-tomcat-8.0.33/bin/startup.sh;"
        order = kill_tomcat + restart_memcahced + restart_tomcat

        self.execute_linux_order(ip, order)

    # 重启采集mss-qpp
    def restart_mss_app(self, ip):

        order = "ps -ef | grep mss-app | grep -v grep | awk '{print $2}' | xargs kill -9;cd /var/local/mss/mss-app-bdms300;" \
                "chmod 755 mss-app.sh;sh mss-app.sh"
        self.execute_linux_order(ip, order)

    # 创建工程线Docker
    def create_docker(self, ip, line_label, memcached_port, activemq_back_port, activemq_front_port, tomcat_port, iscreatememcahced=True):
        """
        创建工程线Docker
        :param ip: docker所在服务器
        :param line_label: 线路标签，如 bj16
        :param memcached_port: memcached端口
        :param activemq_back_port: mq后台端口
        :param activemq_front_port: mq前端端口
        :param tomcat_port: tomcat端口
        :param iscreatememcahced: True时创建memcached；False时不创建
        :return:
        """

        create_memcached = 'docker run -d --name memcached_%s -p %d:11211  docker.io/memcached:latest; docker start memcached_%s;' % \
                           (line_label, memcached_port, line_label)
        create_activemq = 'docker run -d --name activemq_%s -p %s:61616 -p %d:8161 docker.io/webcenter/activemq:latest; docker start activemq_%s;' % \
                          (line_label, activemq_back_port, activemq_front_port, line_label)
        create_tomcat = 'docker run -d --name tomcat_%s -v  /var/local/project/%s/mss:/usr/local/tomcat/webapps/mss -p %s:8080 docker.io/tomcat;' \
                        'docker start tomcat_%s;' % (line_label, line_label, tomcat_port, line_label)

        print(create_memcached)
        print(create_activemq)
        print(create_tomcat)

        if iscreatememcahced:
            order = create_activemq + create_tomcat
        else:
            order = create_memcached + create_activemq + create_tomcat

        self.execute_linux_order(ip, order)

    # 停止，启动、重启docker
    def execute_docker(self, ip, line_label, order_type=2):

        stop_docker = 'docker stop tomcat_%s; docker stop activemq_%s; docker stop activemq_%s;' % (line_label, line_label, line_label,)
        start_docker = 'docker start activemq_%s;docker start activemq_%s; docker start tomcat_%s;' % (line_label, line_label, line_label,)
        restart_docker = 'docker restart activemq_%s;docker restart activemq_%s; docker restart tomcat_%s;' % (line_label, line_label, line_label,)

        if order_type == 1:
            order = start_docker
        elif order_type == 2:
            order = stop_docker
        else:
            order = restart_docker

        self.execute_linux_order(ip, order)

    def get_ini(self, file, section_name, value_type=1, key=''):
        """
        获取ini文件数据
        :param file: inn文件名称
        :param section_name: section名称
        :param value_type: 获取值类型：
            1：键值对字典返回
            2：返回单个值,并,分割值
            3：返回keys
            4:键值值字典返回，值为list
        :param key:
        :return:
        """

        config = configparser.ConfigParser(allow_no_value=True)
        config.read(file, encoding='utf-8')
        # config.read(file)

        # 字典返回键值对，如{key1:value1, key2:value2}
        if value_type == 1:
            a = dict(config.items(section_name))
            return a

        # 列表返回key对应的value值,并以","分割
        elif value_type == 2:
            a = config.get(section_name, key)
            a = a.split(', ')
            return a

        # 列表返回section下面的所有keys值
        elif value_type == 3:
            a = list(config.options(section_name))
            return a

        # 字典返回键值对,值为列表，如{key:[value]},值以,分割
        elif value_type == 4:
            a = dict(config.items(section_name))
            for key in a:
                a[key] = a[key].split(',')
            return a

        # 字典返回键值对,值为列表，如{key:[value]}，值以空格分割
        elif value_type == 5:
            a = dict(config.items(section_name))
            print(a)
            for key in a:
                # noinspection PyBroadException
                try:
                    a[key] = a[key].split()
                except Exception:
                    a[key] = a[key].decode('gbk').encode('utf8').split()
            return a

    def get_file_names(self, dir_path, isflie='', isneedpath=False):

        deal_files = []

        # 获取目录下所有的文件
        dir_files = os.listdir(dir_path)

        if isflie:
            # 过滤出想要的文件
            for file in dir_files:

                if file.startswith('~$'): continue

                if isflie in file:
                    deal_files.append(file)

            if isneedpath:
                if dir_path[-1] != '/':
                    dir_path += '/'

                return dir_path + deal_files[0]
            else:
                return deal_files[0]
        else:
            return dir_files

    def get_station_index_no(self, server_ip, sys_no, station_name):

        sql1 = '''
        SELECT a.*,b.station_name 
            FROM dic_sys_station_mapping a 
        LEFT JOIN dic_station b ON a.station_no=b.station_no 
        WHERE a.sys_no = {}
            and b.station_name like '%{}%'
        '''.format(sys_no, station_name)

        sql2 = "select STATION_NO,STATION_NAME from dic_station where station_name like '%{}%'".format(station_name)

        sql1_data = self.get_mysql_data(server_ip, sql1, isall=False)

        if sql1_data:
            station_index_no = sql1_data[1]
            true_station_name = sql1_data[4]
        else:
            sql2_data = self.get_mysql_data(server_ip, sql2, isall=False)
            if sql2_data:
                station_index_no = sql2_data[0]
                true_station_name = sql2_data[1]
            else:
                station_index_no = 1
                true_station_name = station_name

        station_index_no_hex = self.int_to_hex(station_index_no)

        return station_index_no_hex, true_station_name

    def time_to_int(self, str_time):
        if str_time:
            time_len = len(str_time.replace(' ', ''))

            # 时间类型: 60 9C 2D 41
            if time_len == 8:
                time_stamp = str_time.replace(' ', '').upper()
                time_int = int(time_stamp, 16)

            # 时间类型: 1620847937
            elif time_len == 10:
                time_int = int(str_time)

            elif '-' in str_time:
                date, timestamp = self.date_to_stamp(str_time, istime=True)
                time_int = timestamp
            else:
                time_int = int(str_time, 16)

            time_date = self.stamp_to_date(time_int)
        else:
            time_int = None
            time_date = None

        return time_int, time_date

    def kad_axle_uncompress(self, data):
        data_hex = ['',]
        value_list = []
        value_float = []

        for i in range(int(len(data) / 2)):
            value_str = data[2 * i: 2 * i + 2]
            value_list.append(value_str)

        value_num = int(len(value_list) / 2)
        for i in range(value_num):

            value1 = value_list[2 * i]
            value2 = value_list[2 * i + 1]

            value2_deal_int = int(value2, 16) & 3
            value_cycle = int(value2, 16) >> 2

            value2_deal_str = self.fix_str(str(value2_deal_int))

            data_hex[0] = data_hex[0] + value1
            data_hex[0] = data_hex[0] + str(value2_deal_str)

            for j in range(value_cycle):
                data_hex[0] = data_hex[0] + value1
                data_hex[0] = data_hex[0] + str(value2_deal_str)

        # print('解压后数据报文:', self.data_format(data_hex[0]))

        data_code = data_hex[0].replace(' ', '')
        for i in range(int(len(data_code) / 4)):
            data = data_code[4 * i:4 * i + 4]
            data = data[2:] + data[0:2]
            value_float.append(int(data, 16) / 100)

        # print('解压后的数据：', value_float)

        return value_float

    def hex_to_float_list(self, hex_str, value_len=2, is_reverse=False, is_float=False, xs=1):

        value_list = []

        start_index = [0]
        while start_index[0] < len(hex_str):

            end_index = start_index[0] + 2 * value_len
            data = hex_str[start_index[0]: end_index]
            if is_reverse and value_len > 1:
                data = self.str_reverse(data)

            if is_float:
                value = self.hex_to_float(data)
            else:
                value = int(data, 16)

            value = round(value * xs, 2)
            value_list.append(value)
            start_index[0] = end_index

        return value_list

    def hex_to_float_list2(self, hex_str, value_len=2, is_reverse=False, is_float=False, xs=1):

        value_list = []

        start_index = [0]
        while start_index[0] < len(hex_str):

            end_index = start_index[0] + 2 * value_len
            data = hex_str[start_index[0]: end_index]
            if is_reverse and value_len > 1:
                data = self.str_reverse(data)

            if is_float:
                value = self.hex_to_float2(data)
            else:
                value = int(data, 16)

            value = round(value * xs, 2)
            value_list.append(value)
            start_index[0] = end_index

        return value_list

    def get_list_max_len(self, list_data):
        max_len = [0]

        for i in range(len(list_data)):
            data = str(list_data[i])
            data_len = len(data)
            max_len[0] = data_len if data_len > max_len[0] else max_len[0]

        return max_len[0]

    def set_output_color(self, data, sign_field='<>', is_show=False):

        # color_type: 30-黑色 31-红色 32-绿色 33-黄色 34-蓝色 35-紫红色 36-青蓝色 37-白色
        # aa{bb1}cc

        start_sign = sign_field[0]
        end_sign = sign_field[1]

        is_change = True
        while is_change:

            if start_sign in data and end_sign in data:
                start_index = data.index(start_sign)
                end_index = data.index(end_sign)
                start_data = data[0: start_index]
                end_data = data[end_index + 1:]
                color_data = data[start_index + 1:end_index - 1]
                color_type = '3{}'.format(data[end_index - 1])

                new_color_data = '\033[{}m{}\033[0m'.format(color_type, color_data)

                data = start_data + new_color_data + end_data

            else:
                is_change = False
        if is_show: print(data)
        return data

    def get_curve_data(self, y_value, x_value=None, x_xticks=None, y_yticks=None, y_type=1, title=''):

        y_max_value = [0]
        y_min_value = [0]
        data_max_len = [0]

        # y_value: [data1, data2,...]
        if y_type ==1:
            y_len = len(y_value)
            y_max = max(y_value)
            y_min = min(y_value)

            data_max_len[0] = y_len
            y_max_value[0] = y_max
            y_min_value[0] = y_min

        # y_value: [[data1, data2,...], [data1, data2,...] ]
        elif y_type==2:
            for data in y_value:
                y_len = len(data)
                y_max = max(data)
                y_min = min(data)
                if y_len > data_max_len[0]: data_max_len[0] = y_len
                if y_max > y_max_value[0]: y_max_value[0] = y_max
                if y_min < y_min_value[0]: y_min_value[0] = y_min

        # y_value: {a:[data1, data2,...], b:[data1, data2,...],}
        else:

            for key, value in y_value.items():
                y_len = len(value)
                y_max = max(value)
                y_min = min(value)
                if y_len > data_max_len[0]: data_max_len[0] = y_len
                if y_max > y_max_value[0]: y_max_value[0] = y_max
                if y_min < y_min_value[0]: y_min_value[0] = y_min


        if x_value:
            if isinstance(x_value, list):
                x_data = x_value
            else:
                x_data = [round(x_value * i, 2) for i in range(data_max_len[0])]
        else:
            x_data = [i+1 for i in range(data_max_len[0])]

        plt.rcParams['font.sans-serif'] = ['KaiTi']
        plt.rcParams['axes.unicode_minus'] = False

        plt.figure(1, figsize=(10, 4.6))
        plt.subplot(1,1,1)
        plt.gca().spines['right'].set_color('None')
        plt.gca().spines['top'].set_color('None')
        plt.gca().spines['bottom'].set_position(('data', 0.05))

        x_max = math.ceil(max(x_data))
        y_max = math.ceil(y_max_value[0])
        y_min = 0 if math.floor(y_min_value[0]) > 0 else math.floor(y_min_value[0])
        plt.xlim(0, x_max)
        plt.ylim(y_min, y_max)
        # plt.ylim(0, 150)

        if x_xticks:
            # plt.xticks(x_data, x_xticks, rotation='vertical')

            x_xticks_len = len(x_xticks)
            dif_len = math.ceil(x_xticks_len/10)
            for i in range(x_xticks_len):
                if i % dif_len != 0:
                    x_xticks[i] = ''

            plt.xticks(x_data, x_xticks, rotation='45')
            plt.margins(0.2)
            plt.subplots_adjust(bottom=0.25)

        if y_yticks:
            plt.yticks(x_data, y_yticks)
            plt.margins(0.2)
            plt.subplots_adjust(bottom=0.15)


        if y_type ==1:
            plt.title(title) if title else plt.title('test')
            plt.xlabel(xlabel='时间/s', loc='right')
            plt.ylabel(ylabel='电流/mA', rotation='horizontal', loc='top')

            plt.plot(x_data, y_value, marker='o')

            plt.show()

        elif y_type ==2:

            for y_data in y_value:
                plt.title(title) if title else plt.title('test')
                plt.xlabel(xlabel='时间/s', loc='right')
                plt.ylabel(ylabel='电流/mA', rotation='horizontal', loc='top')

                plt.plot(x_data, y_data, marker='o')

                plt.show()

        else:

            for key, y_data in y_value.items():
                plt.title(title) if title else plt.title('test')
                plt.xlabel(xlabel='时间/s', loc='right')
                plt.ylabel(ylabel='电流/mA', rotation='horizontal', loc='top')

                plt.plot(x_data, y_data, marker='o', label=key)
                plt.legend()

            plt.show()

    def get_curve_data_for_switch(self, y_value, x_value=None, x_xticks=None, y_yticks=None, title=''):

        y_max_value = [0]
        y_min_value = [0]
        data_max_len = [0]

        for key, value in y_value.items():
            y_len = len(value)
            y_max = max(value)
            y_min = min(value)
            if y_len > data_max_len[0]: data_max_len[0] = y_len
            if y_max > y_max_value[0]: y_max_value[0] = y_max
            if y_min < y_min_value[0]: y_min_value[0] = y_min


        if x_value:
            if isinstance(x_value, list):
                x_data = x_value
            else:
                x_data = [round(x_value * i, 2) for i in range(data_max_len[0])]
        else:
            x_data = [i+1 for i in range(data_max_len[0])]

        plt.rcParams['font.sans-serif'] = ['KaiTi']
        plt.rcParams['axes.unicode_minus'] = False

        plt.figure(1, figsize=(10, 4.6))
        plt.subplot(1,1,1)
        plt.gca().spines['left'].set_color('None')
        plt.gca().spines['right'].set_color('None')
        plt.gca().spines['top'].set_color('None')
        plt.gca().spines['bottom'].set_position(('data', 0.05))

        x_max = math.ceil(max(x_data)) + 0.1
        y_max = math.ceil(y_max_value[0]) + 1
        y_min = 0 if math.floor(y_min_value[0]) > 0 else math.floor(y_min_value[0])
        plt.xlim(0, x_max)
        plt.ylim(y_min, y_max)

        if x_xticks:

            x_xticks_len = len(x_xticks)
            dif_len = math.ceil(x_xticks_len/10)
            for i in range(x_xticks_len):
                if i % dif_len != 0:
                    x_xticks[i] = ''

            plt.xticks(x_data, x_xticks, rotation='45')
            plt.margins(0.2)
            plt.subplots_adjust(bottom=0.25)

        # if y_yticks:
        #     plt.yticks(x_data, y_yticks)
        #     plt.margins(0.2)
        #     plt.subplots_adjust(bottom=0.15)
        plt.yticks([])

        now_value = []
        for key, y_data in y_value.items():
            plt.title(title) if title else plt.title('test')
            plt.xlabel(xlabel='时间/s', loc='right')

            key_x_data = copy.deepcopy(x_data)
            for i in range(len(x_data)):
                x_value = key_x_data[i]
                y_value = y_data[i]

                if not now_value: now_value.append(y_value)

                if y_value != now_value[0]:
                    key_x_data.insert(i, x_value)
                    y_data.insert(i, now_value[0])
                    now_value[0] = y_value

            plt.plot(key_x_data, y_data, marker='o', label=key)


            plt.legend()
            now_value = []

        plt.show()


    def get_start_end_data(self, dif_day = 29, day_type=1):
        end_date = datetime.date.today().isoformat()
        start_date = datetime.datetime.now() - datetime.timedelta(days=dif_day)
        start_date = start_date.strftime('%Y-%m-%d')

        all_day = []
        for i in range(dif_day+1):
            start_date = datetime.datetime.now() - datetime.timedelta(days=i)
            start_date = start_date.strftime('%Y-%m-%d')
            all_day.insert(0, start_date)

        if day_type == 1:
            print('start_date, end_date', start_date, end_date)
            return str(start_date), str(end_date)
        else:
            print('all_day', len(all_day), all_day)
            return all_day

    def get_machine_ip(self):
        '''
        获取使用中的网卡信息
        :return:
        '''

        net_if_addrs = psutil.net_if_addrs()  # 网络接口信息
        net_if_stats = psutil.net_if_stats()  # 网络接口状态信息
        used_net_name = {}
        used_ip = []
        for net_name, net_value in net_if_addrs.items():
            if net_name not in net_if_stats.keys(): continue

            net_status = net_if_stats[net_name].isup

            if not net_status: continue

            # print(net_name, net_status, net_value)

            for row_data in net_value:

                family = row_data.family
                address = row_data.address

                if family == 2 and address != '127.0.0.1':
                    ip = address
                    # print('ip', ip)
                    used_net_name[net_name] = ip
                    used_ip.append(ip)

        print('used_ip', used_ip)

        return used_ip[0]

    def get_real_file_name(self, path, file_part):

        real_file = path
        dir_files = os.listdir(path)

        file_part_lower = file_part.lower()

        for file in dir_files:

            if file.startswith('~$'): continue

            if file_part_lower in file.lower():

                if path[-1] == '/':
                    real_file += f'{file}'
                else:
                    real_file += f'/{file}'


        return real_file


    def start_udp_server(self, sourse_ip, dest_ip, dest_port, sourse_port=10000, server_type=1):

        # udp服务
        if server_type == 1:
            print(f'已启用UDP服务 {sourse_ip}:{sourse_port}...')
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client_socket.settimeout(2)

            host_address = (sourse_ip, sourse_port)
            client_socket.bind(host_address)

            return client_socket

        # tcperver服务
        elif server_type == 2:
            print(f'开始启用TCP服务端 {sourse_ip}:{dest_port} ,并等待目标设备{dest_ip}连接...')
            tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_server.bind((sourse_ip, dest_port))
            tcp_server.listen(5)

            is_connect = False
            tcp_connect = ''
            while not is_connect:

                print(f'等待TCP客户端{dest_ip}连接...')
                tcp_connect, server_addr = tcp_server.accept()
                tcp_connect.settimeout(5)
                connect_ip, connect_port = server_addr

                if connect_ip == dest_ip:
                    is_connect = True

                    print(f'当前连接的TCP客户端为 {connect_ip}:{connect_port}')
                else:
                    print(f'当前连接的TCP客户端IP({connect_ip})不是目标IP({dest_ip})，已断开并等待重连...')
                    time.sleep(1)
            if is_connect:
                return tcp_connect

        # tcpclient服务
        else:
            print(f'已启用tcp客户端 {sourse_ip},尝试连接tcp服务器{dest_ip}:{dest_port}...')
            tcp_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_client.settimeout(3)

            is_connect = False
            while not is_connect:
                try:
                    address = (dest_ip, dest_port)
                    tcp_client.connect(address)
                    sourse_addr = tcp_client.getsockname()
                    dest_addr = tcp_client.getpeername()

                    is_connect = True
                    info = f'成功连接服务器,连接信息 - 本机地址:{sourse_addr} 服务器地址:{dest_addr}'
                    print(info)

                except:
                    traceback.print_exc()
                    info = f'TCP服务器({dest_ip}:{dest_port})连接失败，请检查TCP服务是否已开启，3S后尝试重连...'
                    print(info)
                    time.sleep(3)

            if is_connect:
                return tcp_client


    def get_code_len(self, code_data, len_byte=2):
        regex = re.compile(r'(#)(.*)(#)')
        if isinstance(code_data, str):
            data = regex.sub(r'', code_data)
        else:
            data = regex.sub(r'', code_data.decode('utf-8'))

        data = data.replace(' ','').replace('\n', '')

        byte_num = int(len(data)/2)

        date_len_hex = self.int_to_hex(byte_num, num=2*len_byte)

        return date_len_hex


if __name__ == "__main__":
    func = PublicFunc()

    print("func.hex_to_float('00 40 CA 43')", func.hex_to_float('00 40 CA 43', isreverse=True))
    print("func.hex_to_float2('00 40 CA 43')", func.hex_to_float2('00 40 CA 43', isreverse=True))