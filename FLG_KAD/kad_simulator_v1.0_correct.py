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
        if len(h) > num:
            num = math.ceil(len(h) / 2) * 2
        return self.fix_str(h, num).upper()

    def get_random_num(self, num1, num2, num_len=2, isneedint=False):
        val = random.randint(int(num1), int(num2))
        hex_val = self.int_to_hex(val, num_len)
        if isneedint:
            return val, hex_val
        return hex_val

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
        post = bytes.fromhex(formatted)
        sock.bind((sourse_ip, sourse_port))
        sock.sendto(post, (dest_ip, dest_port))
        if is_show_rec:
            try:
                recv, addr = sock.recvfrom(10240)
                sock.close()
                return addr, self.data_format(recv.hex())
            except:
                return '', '无响应'
        sock.close()

class CphmFunc(PublicFunc):
    pass

# ===================== 四种协议构造函数 =====================
def make_kad1_overcar(func, cabinet_no, curve_index_list, curve_num, volt_min, volt_max):
    curve_count = 1
    cab_hex = func.int_to_hex(cabinet_no, 2)
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
            01
            {cnt_rev}
            {content}
            }}
            FF FF
            FE FE FE FE
        '''
        total.append(func.deal_data(code, time_type=2))
    return total

def make_kad2_overcar(func, cabinet_no, curve_index_list, curve_num, volt_min, volt_max):
    curve_count = 1
    cab_hex = func.int_to_hex(cabinet_no, 2)
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
            FA
            {cnt_rev}
            {content}
            }}
            FF FF
            FA FB FC FD
        '''
        total.append(func.deal_data(code))
    return total

def make_kad1_history(func, cabinet_no, device_num, volt_min, volt_max):
    cab_hex = func.int_to_hex(cabinet_no, 2)
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
        01
        {dev_rev}
        {func.data_format(data_str)}
        }}
        FF FF
        FE FE FE FE
    '''
    return [func.deal_data(code, time_type=2)]

def make_kad2_history(func, cabinet_no, device_num, volt_min, volt_max):
    cab_hex = func.int_to_hex(cabinet_no, 2)
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
        01
        {dev_rev}
        {func.data_format(data_str)}
        >
        FF FF
        FA FB FC FD
    '''
    return [func.deal_data(code)]

# ===================== 单个连接发送线程（优化停止响应） =====================
class ConnectionSendThread(threading.Thread):
    def __init__(self, gui, mode, conn_info, common_params, curve_num=None):
        super().__init__(daemon=True)
        self.gui = gui
        self.mode = mode
        self.conn_info = conn_info
        self.common_params = common_params
        self.curve_num = curve_num
        self._stop = threading.Event()
        self.func = CphmFunc()

    def stop(self):
        self._stop.set()

    def run(self):
        src_ip = self.conn_info['src_ip']
        src_port = self.conn_info['src_port']
        if self.mode in ('KAD1_OVERCAR', 'KAD2_OVERCAR'):
            device_count = self.conn_info['overcar_device_count']
        else:
            device_count = self.conn_info['history_device_count']

        self.gui.log(f"连接 {src_ip}:{src_port} 开始发送 (设备数量={device_count})")
        try:
            while not self._stop.is_set():
                if self.mode == 'KAD1_OVERCAR':
                    curve_list = list(range(device_count + 1))
                    codes = make_kad1_overcar(self.func, self.common_params['cabinet_no'],
                                              curve_list, self.curve_num,
                                              self.common_params['volt_min'], self.common_params['volt_max'])
                elif self.mode == 'KAD2_OVERCAR':
                    curve_list = list(range(device_count + 1))
                    codes = make_kad2_overcar(self.func, self.common_params['cabinet_no'],
                                              curve_list, self.curve_num,
                                              self.common_params['volt_min'], self.common_params['volt_max'])
                elif self.mode == 'KAD1_HISTORY':
                    codes = make_kad1_history(self.func, self.common_params['cabinet_no'],
                                              device_count,
                                              self.common_params['volt_min'], self.common_params['volt_max'])
                elif self.mode == 'KAD2_HISTORY':
                    codes = make_kad2_history(self.func, self.common_params['cabinet_no'],
                                              device_count,
                                              self.common_params['volt_min'], self.common_params['volt_max'])
                else:
                    self.gui.log(f"连接 {src_ip}:{src_port} 未知模式，停止")
                    break

                for c in codes:
                    self.func.send_to_mss(src_ip, self.common_params['dst_ip'],
                                          self.common_params['dst_port'], c,
                                          hour=0, time_type=2, sourse_port=src_port)
                # 在 sleep 前再次检查停止标志，快速退出
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
        # self.root.iconbitmap("thunder.ico")
        self.root.title("防雷柜曲线模拟器 (KAD_1 & KAD_2)")
        self.root.geometry("1000x850")          # 增大默认尺寸
        self.root.resizable(True, True) # 允许调整大小
        self.set_window_icon()
        self.send_threads = []
        self.connections = []
        self.create_widgets()
        self.update_db_host_label()

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
        # ==================== 公共设置 ====================
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

        # ==================== 连接列表区域 ====================
        conn_frame = ttk.LabelFrame(self.root, text="连接列表（每连接独立设备数量，可启用/停用）", padding=10)
        conn_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 批量生成设置行
        gen_frame = ttk.Frame(conn_frame)
        gen_frame.pack(fill=tk.X, pady=5)

        ttk.Label(gen_frame, text="生成数量:").pack(side=tk.LEFT, padx=5)
        self.gen_count_var = tk.IntVar(value=1)
        ttk.Entry(gen_frame, textvariable=self.gen_count_var, width=5).pack(side=tk.LEFT, padx=5)

        ttk.Label(gen_frame, text="起始本机IP:").pack(side=tk.LEFT, padx=5)
        self.start_ip_var = tk.StringVar(value="192.168.0.43")
        ttk.Entry(gen_frame, textvariable=self.start_ip_var, width=15).pack(side=tk.LEFT, padx=5)

        ttk.Label(gen_frame, text="起始本机端口:").pack(side=tk.LEFT, padx=5)
        self.start_port_var = tk.IntVar(value=10000)
        ttk.Entry(gen_frame, textvariable=self.start_port_var, width=8).pack(side=tk.LEFT, padx=5)

        ttk.Label(gen_frame, text="Master:").pack(side=tk.LEFT, padx=5)
        self.master_var = tk.IntVar(value=1)
        ttk.Entry(gen_frame, textvariable=self.master_var, width=5).pack(side=tk.LEFT, padx=5)

        ttk.Label(gen_frame, text="默认设备数量:").pack(side=tk.LEFT, padx=5)
        self.device_count_var = tk.IntVar(value=121)
        ttk.Entry(gen_frame, textvariable=self.device_count_var, width=8).pack(side=tk.LEFT, padx=5)

        ttk.Button(gen_frame, text="生成连接", command=self.generate_connections).pack(side=tk.LEFT, padx=10)
        ttk.Button(gen_frame, text="清空连接", command=self.clear_connections).pack(side=tk.LEFT, padx=5)

        # 数据库设置行（换行显示）
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

        ttk.Button(db_action_row, text="从数据库导入连接", command=self.import_connections_from_db).pack(side=tk.LEFT, padx=10)
        ttk.Button(db_action_row, text="根据IP获取站点", command=self.query_stations).pack(side=tk.LEFT, padx=5)
        ttk.Button(db_action_row, text="读取文件填充设备数量", command=self.load_files_fill_device_count).pack(side=tk.LEFT, padx=10)

        # 连接表格
        table_frame = ttk.Frame(conn_frame)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ("src_ip", "src_port", "station", "master", "overcar_dev", "history_dev", "enabled")
        self.conn_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=10)
        self.conn_tree.heading("src_ip", text="本机IP")
        self.conn_tree.heading("src_port", text="本机端口")
        self.conn_tree.heading("station", text="站点")
        self.conn_tree.heading("master", text="Master")
        self.conn_tree.heading("overcar_dev", text="过车曲线设备数量")
        self.conn_tree.heading("history_dev", text="常规曲线设备数量")
        self.conn_tree.heading("enabled", text="启用")
        self.conn_tree.column("src_ip", width=120, anchor=tk.CENTER)
        self.conn_tree.column("src_port", width=90, anchor=tk.CENTER)
        self.conn_tree.column("station", width=180, anchor=tk.CENTER)
        self.conn_tree.column("master", width=60, anchor=tk.CENTER)
        self.conn_tree.column("overcar_dev", width=100, anchor=tk.CENTER)
        self.conn_tree.column("history_dev", width=100, anchor=tk.CENTER)
        self.conn_tree.column("enabled", width=60, anchor=tk.CENTER)
        self.conn_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.conn_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.conn_tree.configure(yscrollcommand=scrollbar.set)

        self.conn_tree.bind("<Double-1>", self.on_tree_double_click)

        # ==================== 标签页（Notebook） ====================
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.overcar_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.overcar_frame, text="过车曲线")
        self.create_overcar_page()

        self.history_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.history_frame, text="常规曲线")
        self.create_history_page()

        # ==================== 底部按钮和日志 ====================
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

    def update_db_host_label(self, *args):
        self.db_host_label.config(text=self.dst_ip_var.get())

    # ===================== 连接管理函数 =====================
    def generate_connections(self):
        try:
            count = self.gen_count_var.get()
            start_ip = self.start_ip_var.get().strip()
            start_port = self.start_port_var.get()
            master = self.master_var.get()
            default_device_count = self.device_count_var.get()
            if count <= 0:
                messagebox.showerror("错误", "生成数量必须大于0")
                return
            self.clear_connections()
            try:
                ip_int = int(ipaddress.ip_address(start_ip))
            except ValueError:
                messagebox.showerror("IP错误", "起始本机IP格式不正确")
                return

            for i in range(count):
                ip = str(ipaddress.ip_address(ip_int + i))
                port = start_port + i
                self.connections.append({
                    'src_ip': ip,
                    'src_port': port,
                    'station': '',
                    'master': master,
                    'overcar_device_count': default_device_count,
                    'history_device_count': default_device_count,
                    'enabled': True
                })
                self.conn_tree.insert('', tk.END, values=(ip, port, '', master, default_device_count, default_device_count, "是"))
            self.log(f"已生成 {count} 个连接，默认设备数量={default_device_count}")
        except Exception as e:
            messagebox.showerror("生成错误", f"生成连接失败: {e}")

    def clear_connections(self):
        self.connections.clear()
        for item in self.conn_tree.get_children():
            self.conn_tree.delete(item)

    def import_connections_from_db(self):
        """从数据库导入连接，过滤IP不是192.168开头的记录"""
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

            # 过滤IP不是192.168开头的记录
            filtered_results = []
            for ip, station, master in results:
                if ip.startswith('192.168'):
                    filtered_results.append((ip, station, master))
                else:
                    self.log(f"已过滤非192.168网段IP: {ip}")

            if not filtered_results:
                messagebox.showinfo("提示", "数据库中没有符合192.168网段的记录")
                return

            # 清空现有列表
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
                    'enabled': True
                })
                self.conn_tree.insert('', tk.END, values=(ip, port, station if station else '', master if master is not None else 0, 0, 0, "是"))
            self.log(f"从数据库导入 {len(filtered_results)} 个连接（已过滤非192.168网段），起始端口 {start_port}")
            messagebox.showinfo("完成", f"成功导入 {len(filtered_results)} 个连接")
        except ImportError:
            messagebox.showerror("缺少模块", "请先安装 pymysql: pip install pymysql")
        except Exception as e:
            messagebox.showerror("数据库错误", f"导入失败: {e}")

    def query_stations(self):
        """手动查询站点信息（用于手动生成的连接）"""
        if not self.connections:
            messagebox.showwarning("警告", "请先生成连接")
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
            success_count = 0
            for i, conn_item in enumerate(self.connections):
                ip = conn_item['src_ip']
                master = conn_item['master']
                sql = """
                    SELECT a.IP, b.STATION_NAME
                    FROM dic_mss_netaddress_config a
                    RIGHT JOIN dic_station b ON a.STATION_NO = b.STATION_NO
                    WHERE a.SYS_NO = 4 AND a.used != 0 AND a.master = %s AND a.IP = %s
                """
                cursor.execute(sql, (master, ip))
                result = cursor.fetchone()
                if result:
                    station = result[1] if result[1] else ''
                    self.connections[i]['station'] = station
                    item_id = self.conn_tree.get_children()[i]
                    self.conn_tree.set(item_id, 'station', station)
                    success_count += 1
                else:
                    self.connections[i]['station'] = ''
                    item_id = self.conn_tree.get_children()[i]
                    self.conn_tree.set(item_id, 'station', '')
            cursor.close()
            conn.close()
            self.log(f"站点信息已更新，成功匹配 {success_count} 条记录")
            messagebox.showinfo("完成", f"站点查询完成，成功匹配 {success_count} 个IP")
        except ImportError:
            messagebox.showerror("缺少模块", "请先安装 pymysql: pip install pymysql")
        except Exception as e:
            messagebox.showerror("数据库错误", f"查询失败: {e}")

    def load_files_fill_device_count(self):
        """读取配置文件（.ini/.txt），解析站点和设备数量，填充到连接列表"""
        if not self.connections:
            messagebox.showwarning("警告", "请先生成连接")
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
                station_name = base_name.split('配置表')[0].strip()
            else:
                station_name = base_name
            station_name = re.sub(r'[Ff]\d*$', '', station_name).strip()
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

            if overcar_count is None and history_count is None:
                preview = content[:500].replace('\n', ' ')
                self.log(f"文件 {filename} 中未找到有效数据，内容预览: {preview}")
                unmatched_files.append(filename)
                continue

            found = False
            for i, conn in enumerate(self.connections):
                if conn['station'] == station_name:
                    if overcar_count is not None:
                        conn['overcar_device_count'] = overcar_count
                        self.conn_tree.set(self.conn_tree.get_children()[i], 'overcar_dev', overcar_count)
                    if history_count is not None:
                        conn['history_device_count'] = history_count
                        self.conn_tree.set(self.conn_tree.get_children()[i], 'history_dev', history_count)
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
        # 允许编辑 Master(3), 过车设备数量(4), 历史设备数量(5), 启用(6)
        if col_idx not in (3, 4, 5, 6):
            return

        if col_idx == 6:  # 启用列，双击切换
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
        except Exception as e:
            messagebox.showerror("输入错误", f"请检查公共参数: {e}")
            return
        if not dst_ip:
            messagebox.showerror("IP错误", "目标IP不能为空")
            return
        if interval <= 0:
            messagebox.showerror("间隔错误", "间隔必须 >0")
            return

        # 如果仍有旧线程在运行，先发送停止信号（不等待）
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
        else:
            protocol = self.history_protocol_var.get()
            mode = 'KAD1_HISTORY' if protocol == 'KAD_1' else 'KAD2_HISTORY'
            curve_num = None

        common_params = {
            'cabinet_no': cabinet_no,
            'volt_min': volt_min,
            'volt_max': volt_max,
            'dst_ip': dst_ip,
            'dst_port': dst_port,
            'interval': interval
        }

        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.send_threads = []
        for conn in enabled_connections:
            thread = ConnectionSendThread(self, mode, conn, common_params, curve_num=curve_num)
            self.send_threads.append(thread)
            thread.start()
        self.log(f"已启动 {len(self.send_threads)} 个发送线程（共 {len(enabled_connections)} 个启用连接）")

    def stop_sending(self):
        # 仅设置停止信号，不等待线程结束，避免 GUI 卡顿
        for thread in self.send_threads:
            thread.stop()
        # 清空线程列表（线程对象仍会自行结束）
        self.send_threads.clear()
        # 立即更新按钮状态
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.log("停止信号已发送，所有发送线程将退出")

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = SimulatorGUI()
    app.run()