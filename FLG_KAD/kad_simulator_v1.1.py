import random
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import socket
import re
import math
import ipaddress
import os
import json
import pymysql  # 需要安装 pymysql

# ===================== 精简版底层函数 =====================
class PublicFunc:
    @staticmethod
    def fix_str(data, num=2, ishead=True, fix_character='0'):
        data = str(data)
        if len(data) < num:
            if ishead:
                data = fix_character * (num - len(data)) + data
            else:
                data = data + fix_character * (num - len(data))
        return data

    @staticmethod
    def str_reverse(data, num=2):
        data = data.replace(' ', '')
        chunks = [data[i:i+num] for i in range(0, len(data), num)]
        return ''.join(chunks[::-1])

    @staticmethod
    def data_format(data, num=2):
        data = data.replace(' ', '')
        return ' '.join(data[i:i+num] for i in range(0, len(data), num)).upper()

    def int_to_hex(self, data, num=2):
        data = int(data)
        h = hex(data)[2:]
        # 确保 num 至少为 2，保证返回偶数长度
        if num < 2:
            num = 2
        if len(h) > num:
            num = math.ceil(len(h) / 2) * 2
        return self.fix_str(h, num).upper()

    def deal_data(self, data, fix_hour=0, israndomtime=False, isformat=True, time_type=1, return_data_type=1):
        return_time = []
        regex = re.compile(r'(#)(.*)(#)')
        if isinstance(data, str):
            data = regex.sub(r'', data)
        else:
            data = regex.sub(r'', data.decode('utf-8'))
        data = data.upper().replace('\n', '').replace('\t', '').replace(' ', '')

        while '[' in data and ']' in data:
            start = data.index('[')
            end = data.index(']')
            old_hex = data[start+1:end]

            if time_type == 1:
                hour = random.randint(0, 30*24) if israndomtime else fix_hour
                ori_time = int(time.time()) - hour * 3600
            else:
                ori_time = time.time()

            stamp = time.localtime(ori_time)
            mon = hex(stamp[1])[2:]
            day = hex(stamp[2])[2:]
            hour_h = hex(stamp[3])[2:]
            min_h = hex(stamp[4])[2:]
            sec = hex(stamp[5])[2:]
            part = self.fix_str(mon)+self.fix_str(day)+self.fix_str(hour_h)+self.fix_str(min_h)+self.fix_str(sec)

            is_rev = 'R' in old_hex.upper()
            old_clean = old_hex.replace('R','').replace('r','')
            time_len = len(old_clean)

            if time_len == 8:
                stamp_int = int(ori_time)
                new_hex = hex(stamp_int)[2:]
                if is_rev: new_hex = self.str_reverse(new_hex)
            elif time_len == 12:
                year = hex(stamp[0]-2000)[2:]
                new_hex = self.fix_str(year) + part
                if is_rev: new_hex = self.str_reverse(new_hex)
            elif time_len in (14,18):
                year = hex(stamp[0])[2:]
                year = self.fix_str(year, 4)
                if is_rev: year = self.str_reverse(year)
                new_hex = year + part
                if time_len == 18:
                    ms = int(str(ori_time-int(ori_time))[2:5])
                    ms_hex = self.fix_str(hex(ms)[2:],4)
                    if is_rev: ms_hex = self.str_reverse(ms_hex)
                    new_hex = new_hex + ms_hex
            else:
                stamp_int = int(ori_time)
                new_hex = hex(stamp_int)[2:]
                if is_rev: new_hex = self.str_reverse(new_hex)

            return_time.append(int(ori_time))
            data = data[:start] + new_hex + data[end+1:]

        frame_len_int = 0
        data_clean = data
        for brace_open, brace_close in [('{','}'), ('<','>')]:
            if brace_open in data_clean and brace_close in data_clean:
                s = data_clean.index(brace_open)
                e = data_clean.index(brace_close)
                inner = data_clean[s+1:e]
                clean = inner.replace('(','').replace(')','').replace('R','').replace('r','')
                frame_len_int = len(clean) // 2
                data_clean = data_clean.replace(brace_open,'').replace(brace_close,'')
                break

        data = data_clean
        if '(' in data and ')' in data and frame_len_int:
            s = data.index('(')
            e = data.index(')')
            len_part = data[s:e+1]
            len_clean = len_part.replace('R','').replace('r','')
            len_byte = len(len_clean) - 2
            len_hex = self.int_to_hex(frame_len_int, len_byte)
            if 'R' in len_part or 'r' in len_part:
                len_hex = self.str_reverse(len_hex)
            data = data[:s] + len_hex + data[e+1:]
        else:
            data = data.replace('(','').replace(')','')

        if isformat:
            result = self.data_format(data)
        else:
            result = data

        if return_data_type == 1:
            return result
        else:
            return result, return_time[0]

    def send_to_mss(self, sourse_ip, dest_ip, dest_port, data, time_out=0.1, hour=0, time_type=1,
                    sourse_port=10000, is_show_rec=False):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(time_out)
        formatted = self.deal_data(data, hour, time_type=time_type).upper()
        # print("=== DEBUG: 报文字符串 ===")
        # print(formatted)
        # print("=======================")
        # post = bytes.fromhex(formatted)
        post = bytes.fromhex(formatted)
        sock.bind((sourse_ip, sourse_port))
        sock.sendto(post, (dest_ip, dest_port))
        if is_show_rec:
            try:
                recv, addr = sock.recvfrom(10240)
                sock.close()
                return addr, self.data_format(recv.hex())
            except:
                return '', '无响应',formatted
        sock.close()

class CphmFunc(PublicFunc):
    pass

# ===================== 协议构造函数（新增采集频率参数 freq） =====================
def make_kad1_overcar(func, cabinet_no, curve_index_list, curve_num, volt_min, volt_max, freq):
    curve_count = 1
    cab_hex = func.int_to_hex(cabinet_no, 2)
    freq_hex = func.int_to_hex(freq, 1)  # 1字节采集频率
    cnt_hex = func.int_to_hex(curve_count, 2)
    cnt_rev = func.str_reverse(cnt_hex)
    num_hex = func.int_to_hex(curve_num, 4)
    num_rev = func.str_reverse(num_hex)

    total = []
    for ci in curve_index_list:
        ci_hex = func.int_to_hex(ci, 2)
        curve_data = ''
        for i in range(curve_num):
            if i == 0:
                v = 550
            else:
                v = random.randint(volt_min, volt_max)
            v_hex = func.int_to_hex(v, 4)
            curve_data += func.str_reverse(v_hex)

        content = ''
        for i in range(curve_count):
            idx_hex = func.int_to_hex(i)
            content += f'''
                {ci_hex} #设备序号#
                {idx_hex} #设备内曲线序号#
                01 #曲线方向#
                [E3 07 0A 0A 09 00 00 00 01 R] #动作开始时间#
                {num_rev} #曲线数据数#
                00 #曲线数据压缩方法#
                {curve_data} #曲线数据#
            '''

        code = f'''
            EF EF EF EF
            10
            01 00 00 00
            30
            F6
            [E3 07 0A 08 09 00 00 R]
            (34 00 r)
            {{
            {cab_hex}
            {freq_hex}   # 采集频率#
            {cnt_rev}
            {content}
            }}
            FF FF
            FE FE FE FE
        '''
        total.append(func.deal_data(code, time_type=2))
    return total

def make_kad2_overcar(func, cabinet_no, curve_index_list, curve_num, volt_min, volt_max, freq):
    curve_count = 1
    cab_hex = func.int_to_hex(cabinet_no, 2)
    freq_hex = func.int_to_hex(freq, 1)
    cnt_hex = func.int_to_hex(curve_count, 2)
    cnt_rev = func.str_reverse(cnt_hex)
    num_hex = func.int_to_hex(curve_num, 4)
    num_rev = func.str_reverse(num_hex)

    total = []
    for ci in curve_index_list:
        ci_hex = func.int_to_hex(ci, 2)
        curve_data = ''
        for i in range(curve_num):
            v = random.randint(volt_min, volt_max)
            v_hex = func.int_to_hex(v, 4)
            curve_data += func.str_reverse(v_hex)

        content = ''
        for i in range(curve_count):
            content += f'''
            {ci_hex} #设备序号#
            0D #设备内曲线序号#
            50 #曲线方向#
            [6E 10 62 63 R] 00 00 #动作开始时间#
            {num_rev} #曲线数据数#
            00 #曲线数据压缩方法#
            {curve_data} #曲线数据#
            '''

        code = f'''
            EF EF EF EF
            10
            01 00 00 00
            3F
            57
            [6E 10 62 63 R]
            (34 00 r)
            {{
            {cab_hex}
            {freq_hex}   # 采集频率#
            {cnt_rev}
            {content}
            }}
            00 00
            FA FB FC FD
        '''
        total.append(func.deal_data(code))
    return total

def make_kad1_history(func, cabinet_no, device_num, volt_min, volt_max, freq):
    cab_hex = func.int_to_hex(cabinet_no, 2)
    freq_hex = func.int_to_hex(freq, 1)
    dev_hex = func.int_to_hex(device_num, 4)
    dev_rev = func.str_reverse(dev_hex, 2)

    data_str = ''
    for _ in range(device_num):
        v = random.randint(volt_min, volt_max)
        v_hex = func.int_to_hex(v, 4)
        data_str += func.str_reverse(v_hex)

    code = f'''
        EF EF EF EF
        10
        01 00 00 00
        20
        6A
        [E3 07 09 1D 11 05 2F R]
        (A4 00 r)
        {{
        {cab_hex}
        {freq_hex}   # 采集频率#
        {dev_rev}
        {func.data_format(data_str)}
        }}
        FF FF
        FE FE FE FE
    '''
    return [func.deal_data(code, time_type=2)]

def make_kad2_history(func, cabinet_no, device_num, volt_min, volt_max, freq):
    cab_hex = func.int_to_hex(cabinet_no, 2)
    freq_hex = func.int_to_hex(freq, 1)
    dev_hex = func.int_to_hex(device_num, 4)
    dev_rev = func.str_reverse(dev_hex, 2)

    data_str = ''
    for _ in range(device_num):
        v = random.randint(volt_min, volt_max)
        v_hex = func.int_to_hex(v, 4)
        data_str += func.str_reverse(v_hex)

    code = f'''
        EF EF EF EF
        10
        01 00 00 00
        3F
        6A
        [6E 10 62 63 R]
        (84 00 r)
        <
        {cab_hex}
        {freq_hex}   # 采集频率#
        {dev_rev}
        {func.data_format(data_str)}
        >
        00 00
        FA FB FC FD
    '''
    return [func.deal_data(code)]

def make_kad2_curve_analysis(func, cabinet_no, device_num, volt_min, volt_max, command_code, freq):
    cab_hex = func.int_to_hex(cabinet_no, 2)
    freq_hex = func.int_to_hex(freq, 1)
    dev_hex = func.int_to_hex(device_num, 4)
    dev_rev = func.str_reverse(dev_hex, 2)

    data_str = ''
    for _ in range(device_num):
        v = random.randint(volt_min, volt_max)
        v_hex = func.int_to_hex(v, 4)
        data_str += func.str_reverse(v_hex)

    code = f'''
        EF EF EF EF
        10
        01 00 00 00
        3F
        {func.int_to_hex(command_code, 1)}
        [6E 10 62 63 R]
        (84 00 r)
        <
        {cab_hex}
        {freq_hex}   # 采集频率#
        {dev_rev}
        {func.data_format(data_str)}
        >
        00 00
        FA FB FC FD
    '''
    return [func.deal_data(code)]

# ===================== 单个连接发送线程 =====================
class ConnectionSendThread(threading.Thread):
    def __init__(self, gui, mode, conn_info, common_params, curve_num=None, command_codes=None):
        super().__init__(daemon=True)
        self.gui = gui
        self.mode = mode
        self.conn_info = conn_info
        self.common_params = common_params   # 包含 freq
        self.curve_num = curve_num
        self.command_codes = command_codes
        self._stop = threading.Event()
        self.func = CphmFunc()

    def stop(self):
        self._stop.set()

    def get_cmd_description(self, cmd):
        """将命令码转换为可读描述"""
        cmd_descs = {
            0x21: "定位表示交流电压",
            0x22: "定位表示直流电压",
            0x23: "反位表示交流电压",
            0x24: "反位表示直流电压",
            0x6D: "定位表示12线交流电压",
            0x6E: "定位表示12线直流电压",
            0x6F: "反位表示13线交流电压",
            0x70: "反位表示13线直流电压"
        }
        return cmd_descs.get(cmd, f"0x{cmd:02X}")

    def run(self):
        src_ip = self.conn_info['src_ip']
        src_port = self.conn_info['src_port']
        if self.mode in ('KAD1_OVERCAR', 'KAD2_OVERCAR'):
            device_count = self.conn_info['overcar_device_count']
        elif self.mode in ('KAD1_HISTORY', 'KAD2_HISTORY'):
            device_count = self.conn_info['history_device_count']
        elif self.mode == 'KAD2_CURVE_ANALYSIS':
            device_count = self.conn_info['curve_analysis_count']
        else:
            device_count = 0

        freq = self.common_params['freq']

        self.gui.log(f"连接 {src_ip}:{src_port} 开始发送 (设备数量={device_count}, 频率={freq})")
        try:
            while not self._stop.is_set():
                send_items = []  # 存储 (报文, 描述) 元组

                # 根据模式生成报文和描述
                if self.mode == 'KAD1_OVERCAR':
                    curve_list = list(range(device_count + 1))
                    codes = make_kad1_overcar(
                        self.func, self.common_params['cabinet_no'],
                        curve_list, self.curve_num,
                        self.common_params['volt_min'], self.common_params['volt_max'],
                        freq
                    )
                    send_items = [(code, "KAD1过车曲线") for code in codes]

                elif self.mode == 'KAD2_OVERCAR':
                    curve_list = list(range(device_count + 1))
                    codes = make_kad2_overcar(
                        self.func, self.common_params['cabinet_no'],
                        curve_list, self.curve_num,
                        self.common_params['volt_min'], self.common_params['volt_max'],
                        freq
                    )
                    send_items = [(code, "KAD2过车曲线") for code in codes]

                elif self.mode == 'KAD1_HISTORY':
                    codes = make_kad1_history(
                        self.func, self.common_params['cabinet_no'],
                        device_count,
                        self.common_params['volt_min'], self.common_params['volt_max'],
                        freq
                    )
                    send_items = [(code, "KAD1历史电压曲线") for code in codes]

                elif self.mode == 'KAD2_HISTORY':
                    codes = make_kad2_history(
                        self.func, self.common_params['cabinet_no'],
                        device_count,
                        self.common_params['volt_min'], self.common_params['volt_max'],
                        freq
                    )
                    send_items = [(code, "KAD2历史电压曲线") for code in codes]

                elif self.mode == 'KAD2_CURVE_ANALYSIS':
                    for cmd in self.command_codes:
                        cmd_codes = make_kad2_curve_analysis(
                            self.func, self.common_params['cabinet_no'],
                            device_count,
                            self.common_params['volt_min'], self.common_params['volt_max'],
                            cmd, freq
                        )
                        desc = f"曲线分析 {self.get_cmd_description(cmd)}"
                        send_items.extend([(code, desc) for code in cmd_codes])

                else:
                    self.gui.log(f"连接 {src_ip}:{src_port} 未知模式，停止")
                    break

                # 打印日志并发送
                for code, desc in send_items:
                    # 日志：先打印类型注释，再打印报文
                    self.gui.log(f"#--- {desc} ---#\n{code}\n<br>")
                    # self.gui.log(f"<br>")
                    self.func.send_to_mss(
                        src_ip, self.common_params['dst_ip'],
                        self.common_params['dst_port'], code,
                        hour=0, time_type=2, sourse_port=src_port
                    )

                # 检查停止标志，然后休眠
                if self._stop.is_set():
                    break
                time.sleep(self.common_params['interval'])

        except Exception as e:
            self.gui.log(f"连接 {src_ip}:{src_port} 发送异常: {e}")
        self.gui.log(f"连接 {src_ip}:{src_port} 停止发送")

# ===================== GUI =====================
class SimulatorGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("FLG_KAD协议报文工具v1.1.exe")
        self.root.geometry("1000x900")
        self.root.resizable(True, True)

        self.state_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'LightningSimulator')
        os.makedirs(self.state_dir, exist_ok=True)
        self.state_file = os.path.join(self.state_dir, 'state.json')

        self.send_threads = []
        self.connections = []
        self.set_window_icon()
        self.create_widgets()
        self.update_db_host_label()
        self.load_state()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def set_window_icon(self):
        """设置窗口左上角图标"""
        try:
            # 获取资源路径（兼容 PyInstaller 打包）
            if hasattr(sys, '_MEIPASS'):
                # 打包后的临时目录
                base_path = sys._MEIPASS
            else:
                base_path = os.path.abspath(".")
            icon_path = os.path.join(base_path, "thunder.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
                self.log(f"窗口图标已加载：{icon_path}")
            else:
                # 如果找不到图标文件，可以使用默认图标（无图标）
                pass
        except Exception as e:
            print(f"设置图标失败：{e}")

    def create_widgets(self):
        # 公共设置
        common_frame = ttk.LabelFrame(self.root, text="公共设置", padding=10)
        common_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(common_frame, text="目标IP/数据库IP:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.dst_ip_var = tk.StringVar(value="192.168.1.249")
        ttk.Entry(common_frame, textvariable=self.dst_ip_var, width=15).grid(row=0, column=1, sticky="w")

        ttk.Label(common_frame, text="目标端口:").grid(row=0, column=2, padx=5, pady=5, sticky="e")
        self.dst_port_var = tk.IntVar(value=7001)
        ttk.Entry(common_frame, textvariable=self.dst_port_var, width=8).grid(row=0, column=3, sticky="w")

        ttk.Label(common_frame, text="机柜号:").grid(row=0, column=4, padx=5, pady=5, sticky="e")
        self.cabinet_no_var = tk.IntVar(value=250)
        ttk.Entry(common_frame, textvariable=self.cabinet_no_var, width=8).grid(row=0, column=5, sticky="w")

        ttk.Label(common_frame, text="电压最小值(x100):").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.volt_min_var = tk.IntVar(value=600)
        ttk.Entry(common_frame, textvariable=self.volt_min_var, width=8).grid(row=1, column=1, sticky="w")

        ttk.Label(common_frame, text="电压最大值(x100):").grid(row=1, column=2, padx=5, pady=5, sticky="e")
        self.volt_max_var = tk.IntVar(value=800)
        ttk.Entry(common_frame, textvariable=self.volt_max_var, width=8).grid(row=1, column=3, sticky="w")

        ttk.Label(common_frame, text="发送间隔(秒):").grid(row=1, column=4, padx=5, pady=5, sticky="e")
        self.interval_var = tk.DoubleVar(value=2.0)
        ttk.Entry(common_frame, textvariable=self.interval_var, width=8).grid(row=1, column=5, sticky="w")

        # 采集频率输入框（新增）
        ttk.Label(common_frame, text="采集频率:").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.freq_var = tk.IntVar(value=1)  # 默认1，可根据需要修改
        ttk.Entry(common_frame, textvariable=self.freq_var, width=8).grid(row=2, column=1, sticky="w")

        # 连接列表区域
        conn_frame = ttk.LabelFrame(self.root, text="连接列表", padding=10)
        conn_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 数据库设置行
        db_frame = ttk.Frame(conn_frame)
        db_frame.pack(fill=tk.X, pady=5)

        db_info_row = ttk.Frame(db_frame)
        db_info_row.pack(fill=tk.X, pady=2)

        ttk.Label(db_info_row, text="数据库IP(目标IP):").pack(side=tk.LEFT, padx=5)
        self.db_host_label = ttk.Label(db_info_row, text="", foreground="blue")
        self.db_host_label.pack(side=tk.LEFT, padx=5)
        self.dst_ip_var.trace_add("write", self.update_db_host_label)

        ttk.Label(db_info_row, text="端口:").pack(side=tk.LEFT, padx=5)
        self.db_port_var = tk.IntVar(value=3306)
        ttk.Entry(db_info_row, textvariable=self.db_port_var, width=6).pack(side=tk.LEFT, padx=5)

        ttk.Label(db_info_row, text="用户:").pack(side=tk.LEFT, padx=5)
        self.db_user_var = tk.StringVar(value="root")
        ttk.Entry(db_info_row, textvariable=self.db_user_var, width=10).pack(side=tk.LEFT, padx=5)

        ttk.Label(db_info_row, text="密码:").pack(side=tk.LEFT, padx=5)
        self.db_pass_var = tk.StringVar(value="mysql")
        ttk.Entry(db_info_row, textvariable=self.db_pass_var, width=10, show="*").pack(side=tk.LEFT, padx=5)

        ttk.Label(db_info_row, text="数据库名:").pack(side=tk.LEFT, padx=5)
        self.db_name_var = tk.StringVar(value="base")
        ttk.Entry(db_info_row, textvariable=self.db_name_var, width=10).pack(side=tk.LEFT, padx=5)

        db_action_row = ttk.Frame(db_frame)
        db_action_row.pack(fill=tk.X, pady=2)

        ttk.Label(db_action_row, text="Master过滤:").pack(side=tk.LEFT, padx=5)
        self.import_master_var = tk.StringVar(value="")
        ttk.Entry(db_action_row, textvariable=self.import_master_var, width=5).pack(side=tk.LEFT, padx=5)

        ttk.Label(db_action_row, text="导入起始端口:").pack(side=tk.LEFT, padx=5)
        self.import_start_port_var = tk.IntVar(value=10000)
        ttk.Entry(db_action_row, textvariable=self.import_start_port_var, width=8).pack(side=tk.LEFT, padx=5)

        # 网段过滤复选框
        self.filter_ip_enabled = tk.BooleanVar(value=True)
        self.filter_checkbox = ttk.Checkbutton(db_action_row, text="启用网段过滤(192.168)", variable=self.filter_ip_enabled)
        self.filter_checkbox.pack(side=tk.LEFT, padx=10)

        ttk.Button(db_action_row, text="从数据库导入连接", command=self.import_connections_from_db).pack(side=tk.LEFT, padx=10)
        ttk.Button(db_action_row, text="清空连接", command=self.clear_connections).pack(side=tk.LEFT, padx=5)
        ttk.Button(db_action_row, text="读取文件填充设备数量", command=self.load_files_fill_device_count).pack(side=tk.LEFT, padx=10)

        # 连接表格
        table_frame = ttk.Frame(conn_frame)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ("src_ip", "src_port", "station", "master", "overcar_dev", "history_dev", "curve_analysis_dev", "enabled")
        self.conn_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=10)
        self.conn_tree.heading("src_ip", text="本机IP")
        self.conn_tree.heading("src_port", text="本机端口")
        self.conn_tree.heading("station", text="站点")
        self.conn_tree.heading("master", text="Master")
        self.conn_tree.heading("overcar_dev", text="过车设备数量")
        self.conn_tree.heading("history_dev", text="历史设备数量")
        self.conn_tree.heading("curve_analysis_dev", text="曲线分析数量")
        self.conn_tree.heading("enabled", text="启用")
        self.conn_tree.column("src_ip", width=120, anchor=tk.CENTER)
        self.conn_tree.column("src_port", width=90, anchor=tk.CENTER)
        self.conn_tree.column("station", width=180, anchor=tk.CENTER)
        self.conn_tree.column("master", width=60, anchor=tk.CENTER)
        self.conn_tree.column("overcar_dev", width=100, anchor=tk.CENTER)
        self.conn_tree.column("history_dev", width=100, anchor=tk.CENTER)
        self.conn_tree.column("curve_analysis_dev", width=100, anchor=tk.CENTER)
        self.conn_tree.column("enabled", width=60, anchor=tk.CENTER)
        self.conn_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.conn_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.conn_tree.configure(yscrollcommand=scrollbar.set)
        self.conn_tree.bind("<Double-1>", self.on_tree_double_click)

        # 标签页
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.overcar_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.overcar_frame, text="过车曲线")
        self.create_overcar_page()

        self.history_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.history_frame, text="历史电压曲线")
        self.create_history_page()

        self.curve_analysis_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.curve_analysis_frame, text="曲线分析")
        self.create_curve_analysis_page()

        # 底部按钮和日志
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(fill=tk.X, padx=10, pady=5)

        self.start_btn = ttk.Button(bottom_frame, text="开始发送", command=self.start_sending)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(bottom_frame, text="停止发送", command=self.stop_sending, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.log_area = scrolledtext.ScrolledText(log_frame, width=110, height=10, state='normal')
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def create_overcar_page(self):
        frame = ttk.Frame(self.overcar_frame, padding=10)
        frame.pack(fill=tk.X, pady=10)
        ttk.Label(frame, text="曲线数据点数:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.curve_num_var = tk.IntVar(value=50)
        ttk.Entry(frame, textvariable=self.curve_num_var, width=10).grid(row=0, column=1, sticky="w")
        ttk.Label(frame, text="协议版本:").grid(row=0, column=2, padx=5, pady=5, sticky="e")
        self.overcar_protocol_var = tk.StringVar(value="KAD_1")
        ttk.Combobox(frame, textvariable=self.overcar_protocol_var,
                     values=["KAD_1", "KAD_2"], state="readonly", width=8).grid(row=0, column=3, sticky="w")

    def create_history_page(self):
        frame = ttk.Frame(self.history_frame, padding=10)
        frame.pack(fill=tk.X, pady=10)
        ttk.Label(frame, text="协议版本:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.history_protocol_var = tk.StringVar(value="KAD_1")
        ttk.Combobox(frame, textvariable=self.history_protocol_var,
                     values=["KAD_1", "KAD_2"], state="readonly", width=8).grid(row=0, column=1, sticky="w")

    def create_curve_analysis_page(self):
        frame = ttk.Frame(self.curve_analysis_frame, padding=10)
        frame.pack(fill=tk.X, pady=10)
        ttk.Label(frame, text="选择命令码（可多选）:").grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.curve_cmd_vars = {}
        cmd_list = [
            (0x21, "定位表示交流电压"),
            (0x22, "定位表示直流电压"),
            (0x23, "反位表示交流电压"),
            (0x24, "反位表示直流电压"),
            (0x6D, "定位表示 12 线交流电压"),
            (0x6E, "定位表示 12 线直流电压"),
            (0x6F, "反位表示 13 线交流电压"),
            (0x70, "反位表示 13 线直流电压")
        ]
        for idx, (cmd, desc) in enumerate(cmd_list):
            var = tk.BooleanVar(value=False)
            self.curve_cmd_vars[cmd] = var
            cb = ttk.Checkbutton(frame, text=f"0x{cmd:02X} - {desc}", variable=var)
            cb.grid(row=1 + idx // 4, column=idx % 4, padx=10, pady=5, sticky="w")

        ttk.Label(frame, text="说明：曲线分析数量来自配置文件“定位表示交流电压”中的模拟量数").grid(row=3, column=0, columnspan=4, padx=5, pady=10, sticky="w")

    def update_db_host_label(self, *args):
        self.db_host_label.config(text=self.dst_ip_var.get())

    # ===================== 连接管理函数 =====================
    def clear_connections(self):
        self.connections.clear()
        for item in self.conn_tree.get_children():
            self.conn_tree.delete(item)

    def import_connections_from_db(self):
        if not self.dst_ip_var.get().strip():
            messagebox.showerror("错误", "请先设置目标IP/数据库IP")
            return
        db_config = {
            'host': self.dst_ip_var.get().strip(),
            'port': self.db_port_var.get(),
            'user': self.db_user_var.get().strip(),
            'password': self.db_pass_var.get(),
            'database': self.db_name_var.get().strip()
        }
        try:
            conn = pymysql.connect(**db_config)
            cursor = conn.cursor()
            sql = """
                SELECT a.IP, b.STATION_NAME, a.master
                FROM dic_mss_netaddress_config a
                RIGHT JOIN dic_station b ON a.STATION_NO = b.STATION_NO
                WHERE a.SYS_NO = 4 AND a.used != 0
            """
            master_filter = self.import_master_var.get().strip()
            params = []
            if master_filter:
                sql += " AND a.master = %s"
                params.append(int(master_filter))
            cursor.execute(sql, tuple(params))
            results = cursor.fetchall()
            cursor.close()
            conn.close()

            filtered_results = []
            if self.filter_ip_enabled.get():
                for ip, station, master in results:
                    if ip.startswith('192.168'):
                        filtered_results.append((ip, station, master))
                    else:
                        self.log(f"已过滤非192.168网段IP: {ip}")
            else:
                filtered_results = results

            if not filtered_results:
                messagebox.showinfo("提示", "数据库中没有符合要求的记录")
                return

            self.clear_connections()

            start_port = self.import_start_port_var.get()
            for i, (ip, station, master) in enumerate(filtered_results):
                port = start_port + i
                self.connections.append({
                    'src_ip': ip,
                    'src_port': port,
                    'station': station if station else '',
                    'master': master if master is not None else 0,
                    'overcar_device_count': 0,
                    'history_device_count': 0,
                    'curve_analysis_count': 0,
                    'enabled': True
                })
                self.conn_tree.insert('', tk.END, values=(ip, port, station if station else '', master if master is not None else 0, 0, 0, 0, "是"))
            self.log(f"从数据库导入 {len(filtered_results)} 个连接，起始端口 {start_port}")
            messagebox.showinfo("完成", f"成功导入 {len(filtered_results)} 个连接")
        except ImportError:
            messagebox.showerror("缺少模块", "请先安装 pymysql")
        except Exception as e:
            messagebox.showerror("数据库错误", f"导入失败: {e}")

    def load_files_fill_device_count(self):
        if not self.connections:
            messagebox.showwarning("警告", "请先生成或导入连接")
            return

        file_paths = filedialog.askopenfilenames(
            title="选择配置文件",
            filetypes=[("配置文件", "*.ini;*.txt;*.conf"), ("所有文件", "*.*")]
        )
        if not file_paths:
            return

        matched_count = 0
        unmatched_files = []

        for file_path in file_paths:
            filename = os.path.basename(file_path)
            base_name = os.path.splitext(filename)[0].strip()

            if '配置表' in base_name:
                base_name = base_name.split('配置表')[0].strip()

            matches = re.findall(r'[\u4e00-\u9fff]+(?:站|车辆段|停车场|基地)', base_name)
            if matches:
                station_name = matches[-1].strip()
            else:
                station_name = re.sub(r'[Ff]\d*$', '', base_name).strip()
                station_name = re.sub(r'[_\d]+$', '', station_name).strip()

            if not station_name:
                self.log(f"文件 {filename} 无法提取站点名")
                unmatched_files.append(filename)
                continue

            content = None
            encodings_to_try = ['utf-8', 'gbk', 'gb18030', 'utf-16', 'utf-16-le', 'utf-16-be', 'big5']
            for encoding in encodings_to_try:
                try:
                    with open(file_path, 'rb') as f:
                        raw_data = f.read()
                    text = raw_data.decode(encoding, errors='ignore')
                    if re.search(r'[\u4e00-\u9fff]', text):
                        content = text
                        break
                except Exception:
                    continue
            if content is None:
                try:
                    with open(file_path, 'r', encoding='gbk', errors='ignore') as f:
                        content = f.read()
                except Exception as e:
                    self.log(f"文件 {filename} 读取失败: {e}")
                    unmatched_files.append(filename)
                    continue

            overcar_count = None
            history_count = None
            curve_analysis_count = None
            freq = None  # 采集频率

            m = re.search(r'\[?\s*计轴磁头过车曲线\s*\]?\s*[\s\S]*?曲线数\s*[:=]\s*(\d+)', content, re.IGNORECASE)
            if not m:
                m = re.search(r'计轴磁头过车曲线[\s\S]*?曲线数\s*[:=]\s*(\d+)', content, re.IGNORECASE)
            if m:
                overcar_count = int(m.group(1))

            m = re.search(r'\[?\s*计轴磁头电压\s*\]?\s*[\s\S]*?模拟量数\s*[:=]\s*(\d+)', content, re.IGNORECASE)
            if not m:
                m = re.search(r'计轴磁头电压[\s\S]*?模拟量数\s*[:=]\s*(\d+)', content, re.IGNORECASE)
            if m:
                history_count = int(m.group(1))

            m = re.search(r'\[?\s*定位表示交流电压\s*\]?\s*[\s\S]*?模拟量数\s*[:=]\s*(\d+)', content, re.IGNORECASE)
            if not m:
                m = re.search(r'定位表示交流电压[\s\S]*?模拟量数\s*[:=]\s*(\d+)', content, re.IGNORECASE)
            if m:
                curve_analysis_count = int(m.group(1))

            # 新增：提取采集频率
            m = re.search(r'采集频率\s*[:=]\s*(\d+)', content, re.IGNORECASE)
            if m:
                freq = int(m.group(1))

            # 如果文件中有采集频率，则更新全局采集频率输入框
            if freq is not None:
                self.freq_var.set(freq)
                self.log(f"从文件 {filename} 读取到采集频率={freq}")

            if overcar_count is None and history_count is None and curve_analysis_count is None and freq is None:
                preview = content[:500].replace('\n', ' ')
                self.log(f"文件 {filename} 中未找到有效数据，内容预览: {preview}")
                unmatched_files.append(filename)
                continue

            found = False
            for i, conn in enumerate(self.connections):
                if conn['station'] == station_name:
                    item_id = self.conn_tree.get_children()[i]
                    if overcar_count is not None:
                        conn['overcar_device_count'] = overcar_count
                        self.conn_tree.set(item_id, 'overcar_dev', overcar_count)
                    if history_count is not None:
                        conn['history_device_count'] = history_count
                        self.conn_tree.set(item_id, 'history_dev', history_count)
                    if curve_analysis_count is not None:
                        conn['curve_analysis_count'] = curve_analysis_count
                        self.conn_tree.set(item_id, 'curve_analysis_dev', curve_analysis_count)
                    found = True
                    matched_count += 1

            if found:
                self.log(f"文件 {filename} 已匹配站点 '{station_name}' 并更新设备数量")
            else:
                self.log(f"文件 {filename} 对应站点 '{station_name}' 在连接列表中未找到")
                unmatched_files.append(filename)

        if unmatched_files:
            messagebox.showwarning("部分文件未匹配", f"以下文件未匹配到站点：\n" + "\n".join(unmatched_files))
        else:
            messagebox.showinfo("完成", f"所有文件均成功匹配，共更新 {matched_count} 个连接")
        self.log(f"文件读取完成，成功匹配 {matched_count} 个连接")

    def on_tree_double_click(self, event):
        region = self.conn_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        column = self.conn_tree.identify_column(event.x)
        row_id = self.conn_tree.identify_row(event.y)
        if not row_id:
            return
        col_idx = int(column[1:]) - 1
        if col_idx not in (3, 4, 5, 6, 7):
            return

        if col_idx == 7:
            current_val = self.conn_tree.item(row_id, 'values')[col_idx]
            new_enabled = not (current_val == "是")
            self.conn_tree.set(row_id, column, "是" if new_enabled else "否")
            row_index = self.conn_tree.index(row_id)
            self.connections[row_index]['enabled'] = new_enabled
            return

        current_value = self.conn_tree.item(row_id, 'values')[col_idx]
        x, y, width, height = self.conn_tree.bbox(row_id, column)
        entry = ttk.Entry(self.conn_tree, width=10)
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, current_value)
        entry.focus()
        entry.select_range(0, tk.END)

        def save_edit(event=None):
            new_value = entry.get()
            try:
                new_val = int(new_value)
            except ValueError:
                messagebox.showerror("错误", "必须为整数")
                entry.destroy()
                return
            self.conn_tree.set(row_id, column, new_val)
            row_index = self.conn_tree.index(row_id)
            if col_idx == 3:
                self.connections[row_index]['master'] = new_val
            elif col_idx == 4:
                self.connections[row_index]['overcar_device_count'] = new_val
            elif col_idx == 5:
                self.connections[row_index]['history_device_count'] = new_val
            elif col_idx == 6:
                self.connections[row_index]['curve_analysis_count'] = new_val
            entry.destroy()

        entry.bind("<Return>", save_edit)
        entry.bind("<FocusOut>", save_edit)

    def log(self, message):
        self.log_area.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_area.see(tk.END)

    def start_sending(self):
        try:
            cabinet_no = self.cabinet_no_var.get()
            dst_ip = self.dst_ip_var.get().strip()
            dst_port = self.dst_port_var.get()
            interval = self.interval_var.get()
            volt_min = self.volt_min_var.get()
            volt_max = self.volt_max_var.get()
            freq = self.freq_var.get()  # 获取采集频率
        except Exception as e:
            messagebox.showerror("输入错误", f"请检查公共参数: {e}")
            return
        if not dst_ip:
            messagebox.showerror("IP错误", "目标IP不能为空")
            return
        if interval <= 0:
            messagebox.showerror("间隔错误", "间隔必须 >0")
            return

        if self.send_threads:
            for t in self.send_threads:
                t.stop()
            self.send_threads.clear()

        enabled_connections = [conn for conn in self.connections if conn.get('enabled', True)]
        if not enabled_connections:
            messagebox.showerror("无启用连接", "请至少启用一个连接")
            return

        current_tab = self.notebook.index(self.notebook.select())
        if current_tab == 0:
            curve_num = self.curve_num_var.get()
            protocol = self.overcar_protocol_var.get()
            mode = 'KAD1_OVERCAR' if protocol == 'KAD_1' else 'KAD2_OVERCAR'
            command_codes = None
        elif current_tab == 1:
            protocol = self.history_protocol_var.get()
            mode = 'KAD1_HISTORY' if protocol == 'KAD_1' else 'KAD2_HISTORY'
            curve_num = None
            command_codes = None
        else:
            mode = 'KAD2_CURVE_ANALYSIS'
            curve_num = None
            command_codes = [cmd for cmd, var in self.curve_cmd_vars.items() if var.get()]
            if not command_codes:
                messagebox.showerror("未选择命令码", "请至少选择一个命令码")
                return

        common_params = {
            'cabinet_no': cabinet_no,
            'volt_min': volt_min,
            'volt_max': volt_max,
            'dst_ip': dst_ip,
            'dst_port': dst_port,
            'interval': interval,
            'freq': freq  # 采集频率加入公共参数
        }

        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.send_threads = []
        for conn in enabled_connections:
            thread = ConnectionSendThread(self, mode, conn, common_params, curve_num=curve_num, command_codes=command_codes)
            self.send_threads.append(thread)
            thread.start()
        self.log(f"已启动 {len(self.send_threads)} 个发送线程")

    def stop_sending(self):
        for thread in self.send_threads:
            thread.stop()
        self.send_threads.clear()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.log("停止信号已发送")

    # ===================== 状态保存与恢复 =====================
    def save_state(self):
        state = {
            'dst_ip': self.dst_ip_var.get(),
            'dst_port': self.dst_port_var.get(),
            'cabinet_no': self.cabinet_no_var.get(),
            'volt_min': self.volt_min_var.get(),
            'volt_max': self.volt_max_var.get(),
            'interval': self.interval_var.get(),
            'freq': self.freq_var.get(),
            'db_port': self.db_port_var.get(),
            'db_user': self.db_user_var.get(),
            'db_pass': self.db_pass_var.get(),
            'db_name': self.db_name_var.get(),
            'import_master': self.import_master_var.get(),
            'import_start_port': self.import_start_port_var.get(),
            'filter_ip_enabled': self.filter_ip_enabled.get(),
            'curve_num': self.curve_num_var.get(),
            'overcar_protocol': self.overcar_protocol_var.get(),
            'history_protocol': self.history_protocol_var.get(),
            'selected_tab': self.notebook.index(self.notebook.select()),
            'curve_cmd_selected': [cmd for cmd, var in self.curve_cmd_vars.items() if var.get()],
            'connections': self.connections
        }
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"保存状态失败: {e}")

    def load_state(self):
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            self.dst_ip_var.set(state.get('dst_ip', '192.168.1.249'))
            self.dst_port_var.set(state.get('dst_port', 7001))
            self.cabinet_no_var.set(state.get('cabinet_no', 250))
            self.volt_min_var.set(state.get('volt_min', 600))
            self.volt_max_var.set(state.get('volt_max', 800))
            self.interval_var.set(state.get('interval', 2.0))
            self.freq_var.set(state.get('freq', 1))
            self.db_port_var.set(state.get('db_port', 3306))
            self.db_user_var.set(state.get('db_user', 'root'))
            self.db_pass_var.set(state.get('db_pass', 'mysql'))
            self.db_name_var.set(state.get('db_name', 'base'))
            self.import_master_var.set(state.get('import_master', ''))
            self.import_start_port_var.set(state.get('import_start_port', 10000))
            self.filter_ip_enabled.set(state.get('filter_ip_enabled', True))
            self.curve_num_var.set(state.get('curve_num', 50))
            self.overcar_protocol_var.set(state.get('overcar_protocol', 'KAD_1'))
            self.history_protocol_var.set(state.get('history_protocol', 'KAD_1'))

            tab_index = state.get('selected_tab', 0)
            if 0 <= tab_index < self.notebook.index('end'):
                self.notebook.select(tab_index)

            selected_cmds = state.get('curve_cmd_selected', [])
            for cmd, var in self.curve_cmd_vars.items():
                var.set(cmd in selected_cmds)

            connections = state.get('connections', [])
            self.clear_connections()
            self.connections = connections
            for conn in connections:
                self.conn_tree.insert('', tk.END, values=(
                    conn['src_ip'],
                    conn['src_port'],
                    conn['station'],
                    conn['master'],
                    conn['overcar_device_count'],
                    conn['history_device_count'],
                    conn['curve_analysis_count'],
                    "是" if conn.get('enabled', True) else "否"
                ))
            self.update_db_host_label()
        except Exception as e:
            self.log(f"加载状态失败: {e}")

    def on_closing(self):
        self.save_state()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = SimulatorGUI()
    app.run()