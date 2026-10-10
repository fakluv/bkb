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
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext


# ========== 公共函数类（保持原有） ==========
class PublicFunc:

    def deal_data(self, data, fix_hour=0, israndomtime=False, isformat=True, time_type=1, return_data_type=1):
        return_time = []
        regex = re.compile(r'(#)(.*)(#)')
        if isinstance(data, str):
            data1 = regex.sub(r'', data)
        else:
            data1 = regex.sub(r'', data.decode('utf-8'))

        data2 = data1.upper().replace('\n', '').replace('\t', '')
        data3 = data2.replace(" ", "")

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
                part_time = [self.fix_str(time_mon) + self.fix_str(time_day) + self.fix_str(time_hour) + self.fix_str(time_min) + self.fix_str(time_second)]

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
        if time_type == 1:
            if is_random_time:
                hour = random.randint(0, 30 * 24)
            else:
                hour = fix_hour
            ori_time = int(time.time()) - hour * 3600
        elif time_type == 2:
            ori_time = target_time
        else:
            ori_time = time.time()

        stamp_time = time.localtime(ori_time)
        time_year = stamp_time[0]
        time_mon = hex(stamp_time[1])[2:]
        time_day = hex(stamp_time[2])[2:]
        time_hour = hex(stamp_time[3])[2:]
        time_min = hex(stamp_time[4])[2:]
        time_second = hex(stamp_time[5])[2:]
        part_time = '{:0>2}{:0>2}{:0>2}{:0>2}{:0>2}'.format(time_mon, time_day, time_hour, time_min, time_second)

        is_reverse_time = True if 'R' in old_time_data.upper() else False
        time_hex = old_time_data.replace('R', '').replace('r', '')
        time_byte = int(len(time_hex) / 2)

        if time_byte == 4:
            stamp_time = int(ori_time)
            hex_time = hex(stamp_time)[2:]
            if is_reverse_time:
                hex_time = self.str_reverse(hex_time)
        elif time_byte == 6:
            time_year_hex = hex(time_year - 2000)[2:]
            hex_time = '{:0>2}{}'.format(time_year_hex, part_time)
            if is_reverse_time:
                hex_time = self.str_reverse(hex_time)
        elif time_byte == 7 or time_byte == 9:
            time_year_hex = '{:0>4}'.format(hex(time_year)[2:])
            if is_reverse_time:
                time_year_hex = self.str_reverse(time_year_hex)
            hex_time = time_year_hex + part_time
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
        regex = re.compile(r'(#)(.*)(#)')
        if isinstance(data, str):
            data1 = regex.sub(r'', data)
        else:
            data1 = regex.sub(r'', data.decode('utf-8'))
        data2 = data1.replace('\n', '').replace(' ', '')

        is_change_time = True
        while is_change_time:
            if '[' in data2 and ']' in data2:
                start_index = data2.index('[')
                end_index = data2.index(']')
                head_data = data2[0: start_index]
                time_data = data2[start_index + 1:end_index]
                end_data = data2[end_index + 1:]
                ori_time, new_hex_time = self.modify_code_time(time_data, time_type, fix_hour, israndomtime)
                return_time.append(ori_time)
                data2 = head_data + new_hex_time + end_data
            else:
                is_change_time = False

        frame_len, new_data = self.calc_code_len(data2, len_byte)
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
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_socket.settimeout(time_out)

        if sourse_port in [10000, 10001]:
            data1 = self.deal_data(data, hour, time_type=time_type)
            data1 = data1.upper()
            postdata = bytes.fromhex(data1)
        else:
            data1 = data.encode('utf-8')
            postdata = data1

        host_address = (sourse_ip, sourse_port)
        server_address = (dest_ip, dest_port)
        client_socket.bind(host_address)
        client_socket.sendto(postdata, server_address)

        if is_show_rec:
            try:
                receive_data, client = client_socket.recvfrom(10240)
                client_socket.close()
                return_data = self.data_format(receive_data.hex())
                return client, return_data
            except Exception:
                return '', '没有接收到返回报文!'

    def send_mss_by_tcp_xml(self, ip, port, xmlbw, isshowcode=False):
        if isshowcode:
            print("发送的报文: \n", xmlbw)
        xmlbw = xmlbw.replace(' ', '')
        address = (ip, port)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(0.5)
        try:
            client.connect(address)
        except Exception:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(address)
        finally:
            by = xmlbw.encode('utf8')
            client.send(by)
        try:
            data = client.recv(1024)
            client.close()
            return data
        except Exception:
            client.close()
            return None

    def send_mss_by_tcp_byte(self, tcpclisock, send_message):
        data1 = self.deal_data(send_message)
        data1 = data1.upper()
        postdata = bytes.fromhex(data1)
        tcpclisock.send(postdata)

    def write_ini(self, file, section_data):
        config = configparser.ConfigParser(allow_no_value=True)
        try:
            config.read(file, encoding='utf-8')
        except UnicodeDecodeError:
            config.read(file, encoding='gbk')
        for section_name, section_values in section_data.items():
            for key, value in section_values.items():
                config.set(section_name, key, value)
        try:
            f = open(file, "w", encoding='utf-8')
        except UnicodeDecodeError:
            f = open(file, "w", encoding='gbk')
        config.write(f)

    def update_ini(self, file, section_name, key, value):
        config = configparser.ConfigParser()
        try:
            config.read(file, encoding='utf-8')
        except UnicodeDecodeError:
            config.read(file, encoding='gbk')
        config.set(section_name, key, value)
        try:
            config.write(open(file, "w", encoding='utf-8'))
        except UnicodeDecodeError:
            config.write(open(file, "w", encoding='gbk'))

    def delete_ini(self, file, section_data):
        config = configparser.ConfigParser()
        config.read(file)
        for data in section_data:
            section_name, item = data
            config.remove_option(section_name, item)
        config.write(open(file, "w"))

    def data_format(self, data, num=2):
        num1 = int(num)
        return_data = ['']
        data = data.replace(" ", "")
        for i in range(len(data)):
            return_data[0] = return_data[0] + data[num1 * i:num1 * (i + 1)] + ' '
        return return_data[0].upper().strip()

    def get_nowtime(self, isneeddecimal=False, isstamp=False, return_type=1, format_stamp=0):
        time_stamp = time.time() + format_stamp
        time_stamp_int = int(time_stamp)
        decimal_part = str(time_stamp - time_stamp_int)[1:5]
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
            return time_stamp_int, hex_time_re
        else:
            return time_stamp_int, hex_time

    def fix_str(self, data, num=2, ishead=True, fix_character='0'):
        str_len = len(data)
        if ishead:
            if str_len < num:
                data = fix_character * (num - str_len) + data
        else:
            if str_len < num:
                data = data + fix_character * (num - str_len)
        return data

    def get_random_num(self, num1, num2, num_len=2, isneedint=False):
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
        return_str = ['']
        deal_data = []
        data = data.replace(' ', '')
        for i in range(int(len(data) / num)):
            deal_data.append(data[num * i:num * (i + 1)])
        for data in deal_data[::-1]:
            return_str[0] = return_str[0] + data
        return return_str[0]

    def str_to_bytes(self, str_data):
        str_data = str_data.upper().replace(" ", "")
        bytes_data = bytes.fromhex(str_data)
        return bytes_data

    def letter_to_number(self, num):
        return_data = ['']
        num1 = num.upper()
        data = {
            'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8,
            'I': 9, 'J': 10, 'K': 11, 'L': 12, 'M': 13, 'N': 14, 'O': 15,
            'P': 16, 'Q': 17, 'R': 18, 'S': 19, 'T': 20, 'U': 21, 'V': 22,
            'W': 23, 'X': 24, 'Y': 25, 'Z': 26
        }
        num_len = len(num1)
        if num_len == 1:
            return_data[0] = data[num1]
        elif num_len == 2:
            return_data[0] = 26 * (data[num1[0]]) + data[num1[-1]]
        else:
            print('待开发...')
        return return_data[0]

    def get_excel_data(self, dir_path, file_name, sheet_name, row_col_name='', start_index=1, end_index=None, isrow=False, isint=True):
        deal_files = []
        return_data = []
        dir_files = os.listdir(dir_path)
        for file in dir_files:
            if file_name in file:
                deal_files.append(file)
        for file in deal_files:
            file_path = dir_path + '/' + file
            file_datas = xlrd.open_workbook(file_path, formatting_info=False)
            sheet_table = file_datas.sheet_by_name(sheet_name)
            if isrow:
                rows = sheet_table.nrows
                if end_index:
                    rows = end_index
                for i in range(start_index, rows):
                    rowdata = sheet_table.row_values(i)
            else:
                col_index = self.letter_to_number(row_col_name) - 1
                values = sheet_table.col(col_index)
                number_start_index = start_index - 1
                if end_index:
                    number_end_index = end_index + 1
                else:
                    number_end_index = len(values)
                for i in range(number_start_index, number_end_index):
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
        deal_files = []
        return_data = []
        dir_files = os.listdir(dir_path)
        for file in dir_files:
            if file_name in file:
                deal_files.append(file)
        deal_files.sort()
        for file in deal_files:
            file_path = dir_path + '/' + file
            f_encoded = self.get_file_charset(file_path)
            f1 = open(file_path, 'r', encoding='GB2312')
            for line_data in f1:
                if return_type == 1:
                    line_data = line_data.replace('\n', '')
                    if line_data != '':
                        line_data = line_data.replace('-', '').replace('*', '').replace(' ', '')
                        return_data.append(line_data)
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
                else:
                    line_data = line_data.replace(' ', '')
                    return_data.append(line_data)
        return return_data

    def float_to_hex(self, f):
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
        return num_int, num_hex

    def get_mysql_data(self, server_ip, sql, return_type=1, database='base', port=3306, isall=True):
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
        if return_type == 1:
            return res_all
        elif return_type == 2:
            return_data = []
            for data in res_all:
                return_data.append(data[0])
            return return_data
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
        data = int(data)
        data_hex = hex(data)[2:]
        data_hex_len = len(data_hex)
        if data_hex_len > num:
            num = math.ceil(data_hex_len/2) * 2
        data_hex = self.fix_str(data_hex, num)
        return data_hex.upper()

    def int_to_bin(self, data, num=8):
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
        if return_type == 1:
            return year_month
        else:
            return

    def start_tcp_server(self, sourse_ip, dest_ip, port):
        print('正在启用TCP服务器(IP: %s   PORT: %s)...' % (sourse_ip, port))
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((sourse_ip, port))
        server.listen(5)
        is_connect = False
        tcpclisock = ''
        server_addr = []
        while not is_connect:
            tcpclisock, server_addr = server.accept()
            tcpclisock.settimeout(3)
            if server_addr[0] != dest_ip:
                print('当前连接的TCP客户端IP(%s)不是目标IP(%s)，正断开重连...' % (server_addr[0], dest_ip))
                time.sleep(1)
                tcpclisock.close()
            else:
                is_connect = True
                print('当前连接的TCP客户端 IP= %s ,PORT= %s' % (server_addr[0], server_addr[1]))
                return tcpclisock

    def start_tcp_client(self, ip, port):
        print('正在启用TCP客户端...')
        address = (ip, port)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(10)
        client.connect(address)
        client.settimeout(None)
        sourse_addr = client.getsockname()
        dest_addr = client.getpeername()
        print('本机地址：', sourse_addr, '服务器地址：', dest_addr)
        return client

    def tcp_client_send_data(self, tcp_client, data, data_type=1):
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
        data_bytes = bytes.fromhex(data)
        data_cn = data_bytes.decode('GBK')
        return data_cn

    def chiness_to_hex(self, data):
        data_gbk = data.encode('GBK')
        data_hex = bytes.hex(data_gbk)
        data_hex = self.data_format(data_hex)
        return data_hex

    def ascii_to_hex(self, data):
        return_data = ['']
        value_mapping = {30: 0,31: 1,32: 2,33: 3,34: 4,35: 5,36: 6,37: 7,38: 8,39: 9,41: 'A',42: 'B',43: 'C',44: 'D',45: 'E',46: 'F',61: 'a',62: 'b',63: 'c',64: 'd',65: 'e',66: 'f'}
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
        return_data = ['']
        value_mapping = {'0': '30','1': '31','2': '32','3': '33','4': '34','5': '35','6': '36','7': '37','8': '38','9': '39','A': '41','B': '42','C': '43','D': '44','E': '45','F': '46','a': '61','b': '62','c': '63','d': '64','e': '65','f': '66'}
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
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, port, username, password)
        if isreadfile:
            file_path = args[0]
            file_data = []
            sftp_client = ssh.open_sftp()
            remote_file = sftp_client.open(file_path)
            try:
                for line in remote_file:
                    file_data.append(line)
            finally:
                remote_file.close()
                return file_data
        else:
            if is_root:
                with paramiko_expect.SSHClientInteraction(ssh, display=True) as interact:
                    su_password = 'shenzhen@tct#server{}'.format(ip.split('.')[-1])
                    interact.send('su')
                    interact.send(su_password)
            ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(order)
            return_data = []
            result = ssh_stdout.readlines()
            for data in result:
                data = data.replace('\n', '')
                return_data.append(data)
            return_data.sort()
            notice_data = ssh_stderr.read().decode('utf8')
            ssh.close()
            return return_data if return_data else ['']

    def get_line_detail(self, ip, data_type=1):
        url = 'http://%s:8080/mss/ledger/getLineDetails2?userId=fbd1d0fdb5ae434cab15de9fe376c834' % ip
        api_data = requests.post(url).json()
        train_num = int(api_data['train'])
        old_stations = api_data['station']
        center = api_data['centerStation']
        new_stations = {0: '全部站点'}
        for data in old_stations:
            new_stations[int(data['stationNo'])] = data['stationName']
        if data_type == 1:
            return new_stations
        elif data_type == 2:
            return train_num
        elif data_type == 3:
            center_name = []
            for data in center:
                center_name.append(data['centerName'])
            return center_name

    def restart_tomcat(self, ip):
        kill_tomcat = "ps -ef | grep tomcat | grep -v grep | awk '{print $2}' | xargs kill -9;"
        restart_memcahced = "service memcached-repcached restart;"
        restart_tomcat = "source /etc/profile; sh /var/local/apache-tomcat-8.0.33/bin/startup.sh;"
        order = kill_tomcat + restart_memcahced + restart_tomcat
        self.execute_linux_order(ip, order)

    def restart_mss_app(self, ip):
        order = "ps -ef | grep mss-app | grep -v grep | awk '{print $2}' | xargs kill -9;cd /var/local/mss/mss-app-bdms300;" \
                "chmod 755 mss-app.sh;sh mss-app.sh"
        self.execute_linux_order(ip, order)

    def create_docker(self, ip, line_label, memcached_port, activemq_back_port, activemq_front_port, tomcat_port, iscreatememcahced=True):
        create_memcached = 'docker run -d --name memcached_%s -p %d:11211  docker.io/memcached:latest; docker start memcached_%s;' % (line_label, memcached_port, line_label)
        create_activemq = 'docker run -d --name activemq_%s -p %s:61616 -p %d:8161 docker.io/webcenter/activemq:latest; docker start activemq_%s;' % (line_label, activemq_back_port, activemq_front_port, line_label)
        create_tomcat = 'docker run -d --name tomcat_%s -v  /var/local/project/%s/mss:/usr/local/tomcat/webapps/mss -p %s:8080 docker.io/tomcat;' \
                        'docker start tomcat_%s;' % (line_label, line_label, tomcat_port, line_label)
        if iscreatememcahced:
            order = create_activemq + create_tomcat
        else:
            order = create_memcached + create_activemq + create_tomcat
        self.execute_linux_order(ip, order)

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
        config = configparser.ConfigParser(allow_no_value=True)
        config.read(file, encoding='utf-8')
        if value_type == 1:
            a = dict(config.items(section_name))
            return a
        elif value_type == 2:
            a = config.get(section_name, key)
            a = a.split(', ')
            return a
        elif value_type == 3:
            a = list(config.options(section_name))
            return a
        elif value_type == 4:
            a = dict(config.items(section_name))
            for key in a:
                a[key] = a[key].split(',')
            return a
        elif value_type == 5:
            a = dict(config.items(section_name))
            for key in a:
                try:
                    a[key] = a[key].split()
                except Exception:
                    a[key] = a[key].decode('gbk').encode('utf8').split()
            return a

    def get_file_names(self, dir_path, isflie='', isneedpath=False):
        deal_files = []
        dir_files = os.listdir(dir_path)
        if isflie:
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
        sql1 = '''SELECT a.*,b.station_name FROM dic_sys_station_mapping a LEFT JOIN dic_station b ON a.station_no=b.station_no WHERE a.sys_no = {} and b.station_name like '%{}%' '''.format(sys_no, station_name)
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
            if time_len == 8:
                time_stamp = str_time.replace(' ', '').upper()
                time_int = int(time_stamp, 16)
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
        data_hex = ['']
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
            data_hex[0] = data_hex[0] + value1 + str(value2_deal_str)
            for j in range(value_cycle):
                data_hex[0] = data_hex[0] + value1 + str(value2_deal_str)
        data_code = data_hex[0].replace(' ', '')
        for i in range(int(len(data_code) / 4)):
            data = data_code[4 * i:4 * i + 4]
            data = data[2:] + data[0:2]
            value_float.append(int(data, 16) / 100)
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
        if y_type ==1:
            y_len = len(y_value)
            y_max = max(y_value)
            y_min = min(y_value)
            data_max_len[0] = y_len
            y_max_value[0] = y_max
            y_min_value[0] = y_min
        elif y_type==2:
            for data in y_value:
                y_len = len(data)
                y_max = max(data)
                y_min = min(data)
                if y_len > data_max_len[0]: data_max_len[0] = y_len
                if y_max > y_max_value[0]: y_max_value[0] = y_max
                if y_min < y_min_value[0]: y_min_value[0] = y_min
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
        if x_xticks:
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
            return str(start_date), str(end_date)
        else:
            return all_day

    def get_machine_ip(self):
        net_if_addrs = psutil.net_if_addrs()
        net_if_stats = psutil.net_if_stats()
        used_net_name = {}
        used_ip = []
        for net_name, net_value in net_if_addrs.items():
            if net_name not in net_if_stats.keys(): continue
            net_status = net_if_stats[net_name].isup
            if not net_status: continue
            for row_data in net_value:
                family = row_data.family
                address = row_data.address
                if family == 2 and address != '127.0.0.1':
                    ip = address
                    used_net_name[net_name] = ip
                    used_ip.append(ip)
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
        if server_type == 1:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client_socket.settimeout(2)
            host_address = (sourse_ip, sourse_port)
            client_socket.bind(host_address)
            return client_socket
        elif server_type == 2:
            tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_server.bind((sourse_ip, dest_port))
            tcp_server.listen(5)
            is_connect = False
            tcp_connect = ''
            while not is_connect:
                tcp_connect, server_addr = tcp_server.accept()
                tcp_connect.settimeout(5)
                connect_ip, connect_port = server_addr
                if connect_ip == dest_ip:
                    is_connect = True
                else:
                    time.sleep(1)
            if is_connect:
                return tcp_connect
        else:
            tcp_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_client.settimeout(3)
            is_connect = False
            while not is_connect:
                try:
                    address = (dest_ip, dest_port)
                    tcp_client.connect(address)
                    is_connect = True
                except:
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


# ========== 报文生成函数 ==========
def make_code(path, file, hour, isAlarm=True):
    func = PublicFunc()
    name = '计轴机柜0_ETH板配置'
    start_index = 4

    section_no = func.get_excel_data(path, file, name, 'N', start_index)
    section_name = func.get_excel_data(path, file, name, 'P', start_index, isint=False)
    sensor_no = func.get_excel_data(path, file, name, 'X', start_index)
    sensor_name = func.get_excel_data(path, file, name, 'Z', start_index, isint=False)
    fangdaban = func.get_excel_data(path, file, name, 'D', start_index, 6)
    jizhouban = func.get_excel_data(path, file, name, 'E', start_index, 6)
    jigui_no = func.get_excel_data(path, file, name, 'C', start_index, 6)

    section_no_len = len(section_no)
    section_name_len = len(section_name)
    section_len = min(section_no_len, section_name_len)

    sensor_no_len = len(sensor_no)
    sensor_name_len = len(sensor_name)
    sensor_len = min(sensor_no_len, sensor_name_len)

    fangdaban_len = [0]
    jizhouban_len = [0]
    for i in range(len(fangdaban)):
        fangdaban_len[0] = fangdaban_len[0] + fangdaban[i]
        jizhouban_len[0] = jizhouban_len[0] + jizhouban[i]
    fangdaban_len[0] = int(fangdaban_len[0])

    shuchuban_len = jizhouban_len

    section_part = ['']
    sensor_part = ['']
    fangdaban_part = ['']
    jizhouban_part = ['']
    shuchuban_part = ['']
    zhuji_part = ['']
    xiaweiji_part = ['']

    for i in range(section_len):
        if isAlarm:
            baojin_status = '01'
        else:
            baojin_status = '10'
        fuling_status = '00'
        guidao_status = '00'
        quduan_status = random.choice(['01', '10'])
        section_bit = baojin_status + fuling_status + guidao_status + quduan_status
        section_int = int(section_bit, 2)
        section_hex = func.int_to_hex(section_int)
        section_part[0] = section_part[0] + section_hex + ' '

    for i in range(sensor_len):
        if isAlarm:
            baojin_hex = '05'
        else:
            baojin_hex = '0A'
        sensor_part[0] = sensor_part[0] + baojin_hex + ' '

    for i in range(fangdaban_len[0]):
        if isAlarm:
            baojin_hex = '02'
        else:
            baojin_hex = '01'
        fangdaban_part[0] = fangdaban_part[0] + baojin_hex + ' '

    for i in range(jizhouban_len[0]):
        if isAlarm:
            baojin_hex = '02'
        else:
            baojin_hex = '01'
        jizhouban_part[0] = jizhouban_part[0] + baojin_hex + ' '

    for i in range(shuchuban_len[0]):
        if isAlarm:
            baojin_hex = '02'
        else:
            baojin_hex = '01'
        shuchuban_part[0] = shuchuban_part[0] + baojin_hex + ' '

    for i in range(len(jigui_no)):
        if isAlarm:
            baojin_hex = '02'
        else:
            baojin_hex = '01'
        zhuji_part[0] = zhuji_part[0] + baojin_hex + ' '

    if isAlarm:
        xiaweiji_part[0] = '01'
    else:
        xiaweiji_part[0] = '02'

    baowen = '''
        {AA #帧开始标志#
        (10 B6) #帧长度(从帧头到帧尾)#
        70 #Message Type#
        [5D 88 6D 70] #时间戳#
        00 00 AA AF #报文序列号#
        00 05 #计轴子系统的车站编号#
        #计轴区段 报警:0x40 恢复报警:0x80#
        %s 
        #传感器板 报警:0x05 恢复报警:0x0A#
        %s 
        #放大板 0:初始化 1:板在位 2:板不在位(故障态)#
        %s 
        #计轴板 0:初始化 1:板在位 2:板不在位(故障态)#
        %s 
        #输出板 0:初始化 1:板在位 2:板不在位(故障态)#
        %s
        %s #计轴机柜监测主机箱状态 0:初始化 1:通信正常 2:通信故障(故障态)#
        %s #下位机告警驱动状态 0:初始化 1:有告警(故障态) 2:无告警#
        AA #帧结束标识#}
        ''' % (section_part[0], sensor_part[0], fangdaban_part[0], jizhouban_part[0], shuchuban_part[0],
               zhuji_part[0], xiaweiji_part[0])

    send_data = func.deal_data(baowen, hour)
    return send_data


# ========== GUI 应用程序 ==========
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("计轴报文发送工具")
        self.root.geometry("1100x700")
        self.root.minsize(800, 600)

        self.func = PublicFunc()
        self.send_thread = None
        self.stop_event = threading.Event()

        # 变量
        self.folder_path = tk.StringVar(value=os.getcwd())
        self.src_ip = tk.StringVar(value="192.168.2.143")
        self.dst_ip = tk.StringVar(value="192.168.1.249")
        self.dst_port = tk.IntVar(value=10070)
        self.alarm_mode = tk.StringVar(value="alarm")
        self.selected_station = tk.StringVar()

        # 存储站点与对应文件名的映射
        self.station_map = {}

        self.setup_ui()
        self.load_stations()

    def setup_ui(self):
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True)

        # 左侧：站点列表
        left_frame = ttk.LabelFrame(main_paned, text="站点列表", padding=5)
        main_paned.add(left_frame, weight=1)

        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill=tk.X, pady=(0,5))
        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        search_entry.bind("<KeyRelease>", self.filter_stations)

        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.station_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        self.station_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.station_listbox.yview)
        self.station_listbox.bind("<<ListboxSelect>>", self.on_station_select)

        folder_frame = ttk.Frame(left_frame)
        folder_frame.pack(fill=tk.X, pady=5)
        ttk.Label(folder_frame, text="文件夹:").pack(side=tk.LEFT)
        ttk.Entry(folder_frame, textvariable=self.folder_path, width=20).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(folder_frame, text="浏览", command=self.browse_folder).pack(side=tk.LEFT)

        # 右侧：报文预览与日志
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=3)

        preview_frame = ttk.LabelFrame(right_frame, text="报文预览", padding=5)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0,5))
        self.preview_text = scrolledtext.ScrolledText(preview_frame, wrap=tk.WORD, height=12, font=("Consolas", 10))
        self.preview_text.pack(fill=tk.BOTH, expand=True)

        log_frame = ttk.LabelFrame(right_frame, text="运行日志", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=8, font=("Consolas", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 底部控制区
        control_frame = ttk.Frame(self.root, padding=10)
        control_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ip_frame = ttk.LabelFrame(control_frame, text="网络配置", padding=5)
        ip_frame.pack(fill=tk.X, pady=5)

        ttk.Label(ip_frame, text="本机IP:").grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        ttk.Entry(ip_frame, textvariable=self.src_ip, width=15).grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(ip_frame, text="目标IP:").grid(row=0, column=2, padx=5, pady=2, sticky=tk.W)
        ttk.Entry(ip_frame, textvariable=self.dst_ip, width=15).grid(row=0, column=3, padx=5, pady=2)

        ttk.Label(ip_frame, text="端口:").grid(row=0, column=4, padx=5, pady=2, sticky=tk.W)
        ttk.Entry(ip_frame, textvariable=self.dst_port, width=8).grid(row=0, column=5, padx=5, pady=2)

        mode_frame = ttk.Frame(control_frame)
        mode_frame.pack(fill=tk.X, pady=5)
        ttk.Radiobutton(mode_frame, text="报警", variable=self.alarm_mode, value="alarm", command=self.update_preview).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(mode_frame, text="恢复", variable=self.alarm_mode, value="recover", command=self.update_preview).pack(side=tk.LEFT, padx=10)

        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="发送一次", command=self.send_once).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="开始循环发送", command=self.start_loop_send).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="停止发送", command=self.stop_send).pack(side=tk.LEFT, padx=5)

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.folder_path.set(path)
            self.load_stations()

    def load_stations(self):
        folder = self.folder_path.get()
        if not os.path.isdir(folder):
            messagebox.showerror("错误", "文件夹不存在")
            return
        self.station_map.clear()
        self.station_listbox.delete(0, tk.END)
        files = os.listdir(folder)
        for f in files:
            if f.endswith('.xls') or f.endswith('.xlsx'):
                base = os.path.splitext(f)[0]
                if '_' in base:
                    station = base.rsplit('_', 1)[-1]
                else:
                    station = base
                self.station_map[station] = f
                self.station_listbox.insert(tk.END, station)
        if self.station_map:
            self.log(f"已加载 {len(self.station_map)} 个站点")

    def filter_stations(self, event=None):
        search = self.search_var.get().lower()
        self.station_listbox.delete(0, tk.END)
        for station in self.station_map:
            if search in station.lower():
                self.station_listbox.insert(tk.END, station)

    def on_station_select(self, event):
        selection = self.station_listbox.curselection()
        if selection:
            station = self.station_listbox.get(selection[0])
            self.selected_station.set(station)
            # 打印站点读取信息到日志
            self.log_station_info(station)
            self.update_preview()

    def log_station_info(self, station):
        """读取Excel文件，打印站点概要信息到日志（兼容两种Sheet格式）"""
        try:
            path = self.folder_path.get()
            file = self.station_map.get(station)
            if not file:
                self.log(f"未找到站点文件: {station}")
                return

            func = self.func
            file_path = os.path.join(path, file)

            # 优先尝试读取“计轴机柜配置”sheet
            try:
                wb = xlrd.open_workbook(file_path)
                if '计轴机柜配置' in wb.sheet_names():
                    sheet = wb.sheet_by_name('计轴机柜配置')
                    # 初始化汇总数据
                    mainhost_count = 0
                    segment_count = 0
                    dss_count = 0
                    fangdaban_total = 0
                    jizhouban_total = 0

                    for row_idx in range(sheet.nrows):
                        row_vals = [str(sheet.cell_value(row_idx, col)) for col in range(sheet.ncols)]
                        # 跳过空行或标题行
                        if not row_vals or row_vals[0].strip() == '' or '配置标识符' in row_vals[0]:
                            continue

                        # 识别 amount 行
                        if len(row_vals) >= 4 and row_vals[1].strip().lower() == 'mainhost' and row_vals[
                            2].strip().lower() == 'amount':
                            mainhost_count = int(float(row_vals[3])) if row_vals[3].strip() else 0
                        elif len(row_vals) >= 4 and row_vals[1].strip().lower() == 'segment' and row_vals[
                            2].strip().lower() == 'amount':
                            segment_count = int(float(row_vals[3])) if row_vals[3].strip() else 0
                        elif len(row_vals) >= 4 and row_vals[1].strip().lower() == 'dss' and row_vals[
                            2].strip().lower() == 'amount':
                            dss_count = int(float(row_vals[3])) if row_vals[3].strip() else 0

                        # 识别普通机柜行，累加放大板、计轴板数
                        if len(row_vals) >= 6 and row_vals[1].strip().lower() == 'mainhost' and row_vals[
                            2].strip().isdigit():
                            fangda = int(float(row_vals[3])) if row_vals[3].strip() else 0
                            jizhou = int(float(row_vals[4])) if row_vals[4].strip() else 0
                            fangdaban_total += fangda
                            jizhouban_total += jizhou

                    info = (f"站点 [{station}] 数据(计轴机柜配置): "
                            f"机柜 {mainhost_count}, "
                            f"区段 {segment_count}, "
                            f"传感器 {dss_count}, "
                            f"放大板 {fangdaban_total}, "
                            f"计轴板 {jizhouban_total}, "
                            f"输出板 {jizhouban_total}")
                    self.log(info)
                    return
            except Exception as e:
                # 若新格式读取失败，尝试回退
                self.log(f"新格式读取失败({e})，尝试旧格式...")

            # 回退：读取“计轴机柜0_ETH板配置”sheet
            start_index = 4
            sheet_name = '计轴机柜0_ETH板配置'
            section_no = func.get_excel_data(path, file, sheet_name, 'N', start_index)
            section_name = func.get_excel_data(path, file, sheet_name, 'P', start_index, isint=False)
            sensor_no = func.get_excel_data(path, file, sheet_name, 'X', start_index)
            sensor_name = func.get_excel_data(path, file, sheet_name, 'Z', start_index, isint=False)
            fangdaban = func.get_excel_data(path, file, sheet_name, 'D', start_index, 6)
            jizhouban = func.get_excel_data(path, file, sheet_name, 'E', start_index, 6)
            jigui_no = func.get_excel_data(path, file, sheet_name, 'C', start_index, 6)

            section_len = min(len(section_no), len(section_name))
            sensor_len = min(len(sensor_no), len(sensor_name))
            fangdaban_total = sum(fangdaban)
            jizhouban_total = sum(jizhouban)
            shuchuban_total = jizhouban_total
            jigui_count = len(jigui_no)

            info = (f"站点 [{station}] 数据(ETH板配置): "
                    f"区段 {section_len}, "
                    f"传感器 {sensor_len}, "
                    f"放大板 {fangdaban_total}, "
                    f"计轴板 {jizhouban_total}, "
                    f"输出板 {shuchuban_total}, "
                    f"机柜 {jigui_count}")
            self.log(info)

        except Exception as e:
            self.log(f"读取站点 [{station}] 数据失败: {e}")

    def update_preview(self):
        station = self.selected_station.get()
        if not station:
            self.preview_text.delete(1.0, tk.END)
            self.preview_text.insert(tk.END, "未选择站点")
            return
        is_alarm = self.alarm_mode.get() == "alarm"
        try:
            path = self.folder_path.get()
            file = self.station_map[station]
            func = self.func
            name = '计轴机柜0_ETH板配置'
            start_index = 4
            section_no = func.get_excel_data(path, file, name, 'N', start_index)
            section_name = func.get_excel_data(path, file, name, 'P', start_index, isint=False)
            sensor_no = func.get_excel_data(path, file, name, 'X', start_index)
            sensor_name = func.get_excel_data(path, file, name, 'Z', start_index, isint=False)
            fangdaban = func.get_excel_data(path, file, name, 'D', start_index, 6)
            jizhouban = func.get_excel_data(path, file, name, 'E', start_index, 6)
            jigui_no = func.get_excel_data(path, file, name, 'C', start_index, 6)

            section_len = min(len(section_no), len(section_name))
            sensor_len = min(len(sensor_no), len(sensor_name))

            fangdaban_len = [0]
            jizhouban_len = [0]
            for i in range(len(fangdaban)):
                fangdaban_len[0] = fangdaban_len[0] + fangdaban[i]
                jizhouban_len[0] = jizhouban_len[0] + jizhouban[i]
            fangdaban_len[0] = int(fangdaban_len[0])
            shuchuban_len = jizhouban_len

            section_part = ''
            sensor_part = ''
            fangdaban_part = ''
            jizhouban_part = ''
            shuchuban_part = ''
            zhuji_part = ''
            xiaweiji_part = ''

            for i in range(section_len):
                baojin_status = '01' if is_alarm else '10'
                fuling_status = '00'
                guidao_status = '00'
                quduan_status = random.choice(['01', '10'])
                section_bit = baojin_status + fuling_status + guidao_status + quduan_status
                section_int = int(section_bit, 2)
                section_hex = func.int_to_hex(section_int)
                section_part += section_hex + ' '

            for i in range(sensor_len):
                baojin_hex = '05' if is_alarm else '0A'
                sensor_part += baojin_hex + ' '

            for i in range(fangdaban_len[0]):
                baojin_hex = '02' if is_alarm else '01'
                fangdaban_part += baojin_hex + ' '

            for i in range(jizhouban_len[0]):
                baojin_hex = '02' if is_alarm else '01'
                jizhouban_part += baojin_hex + ' '

            for i in range(shuchuban_len[0]):
                baojin_hex = '02' if is_alarm else '01'
                shuchuban_part += baojin_hex + ' '

            for i in range(len(jigui_no)):
                baojin_hex = '02' if is_alarm else '01'
                zhuji_part += baojin_hex + ' '

            xiaweiji_part = '01' if is_alarm else '02'

            preview_template = (
                "AA #帧开始标志#\n"
                "(10 B6) #帧长度(从帧头到帧尾)#\n"
                "70 #Message Type#\n"
                "[5D 88 6D 70] #时间戳#\n"
                "00 00 AA AF #报文序列号#\n"
                "00 05 #计轴子系统的车站编号#\n"
                "#计轴区段 报警:0x40 恢复报警:0x80#\n"
                "{section} \n"
                "#传感器板 报警:0x05 恢复报警:0x0A#\n"
                "{sensor} \n"
                "#放大板 0:初始化 1:板在位 2:板不在位(故障态)#\n"
                "{fangda} \n"
                "#计轴板 0:初始化 1:板在位 2:板不在位(故障态)#\n"
                "{jizhou} \n"
                "#输出板 0:初始化 1:板在位 2:板不在位(故障态)#\n"
                "{shuchu}\n"
                "{zhuji} #计轴机柜监测主机箱状态 0:初始化 1:通信正常 2:通信故障(故障态)#\n"
                "{xiaweiji} #下位机告警驱动状态 0:初始化 1:有告警(故障态) 2:无告警#\n"
                "AA #帧结束标识#"
            ).format(
                section=section_part.strip(),
                sensor=sensor_part.strip(),
                fangda=fangdaban_part.strip(),
                jizhou=jizhouban_part.strip(),
                shuchu=shuchuban_part.strip(),
                zhuji=zhuji_part.strip(),
                xiaweiji=xiaweiji_part
            )

            self.preview_text.delete(1.0, tk.END)
            self.preview_text.insert(tk.END, preview_template)
        except Exception as e:
            self.preview_text.delete(1.0, tk.END)
            self.preview_text.insert(tk.END, f"生成预览失败: {e}")

    def log(self, msg):
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {msg}\n")
        self.log_text.see(tk.END)

    def send_once(self):
        station = self.selected_station.get()
        if not station:
            messagebox.showwarning("警告", "请先选择一个站点")
            return
        is_alarm = self.alarm_mode.get() == "alarm"
        self.log(f"手动发送一条报文 - 站点:{station} 状态:{'报警' if is_alarm else '恢复'}")
        threading.Thread(target=self._send_task, args=(station, is_alarm), daemon=True).start()

    def start_loop_send(self):
        station = self.selected_station.get()
        if not station:
            messagebox.showwarning("警告", "请先选择一个站点")
            return
        if self.send_thread and self.send_thread.is_alive():
            self.log("已有发送任务在运行")
            return
        self.stop_event.clear()
        is_alarm = self.alarm_mode.get() == "alarm"
        self.log(f"开始循环发送 - 站点:{station} 状态:{'报警' if is_alarm else '恢复'}")
        self.send_thread = threading.Thread(target=self._loop_send_task, args=(station, is_alarm), daemon=True)
        self.send_thread.start()

    def stop_send(self):
        if self.send_thread and self.send_thread.is_alive():
            self.stop_event.set()
            self.log("停止发送请求已发出")
        else:
            self.log("当前无发送任务")

    def _send_task(self, station, is_alarm):
        try:
            path = self.folder_path.get()
            file = self.station_map[station]
            hour = 0
            send_data = make_code(path, file, hour, is_alarm)
            self.func.send_to_mss(
                self.src_ip.get(),
                self.dst_ip.get(),
                self.dst_port.get(),
                send_data,
                time_out=0.1,
                hour=hour,
                time_type=1,
                sourse_port=10000,
                is_show_rec=False
            )
            self.log(f"发送成功: {send_data}")
        except Exception as e:
            self.log(f"发送失败: {e}")

    def _loop_send_task(self, station, is_alarm):
        path = self.folder_path.get()
        file = self.station_map[station]
        hour = 0
        index = 1
        while not self.stop_event.is_set():
            try:
                send_data = make_code(path, file, hour, is_alarm)
                self.func.send_to_mss(
                    self.src_ip.get(),
                    self.dst_ip.get(),
                    self.dst_port.get(),
                    send_data,
                    time_out=0.1,
                    hour=hour,
                    time_type=1,
                    sourse_port=10000,
                    is_show_rec=False
                )
                self.log(f"第{index}条发送成功")
                index += 1
            except Exception as e:
                self.log(f"发送失败: {e}")
            time.sleep(1)


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()