import random
import time
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import socket
import re
import math

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
        """生成指定范围内的随机整数，返回指定位数的 hex 字符串"""
        val = random.randint(int(num1), int(num2))
        hex_val = self.int_to_hex(val, num_len)
        if isneedint:
            return val, hex_val
        return hex_val

    def deal_data(self, data, fix_hour=0, israndomtime=False, isformat=True, time_type=1, return_data_type=1):
        """处理报文中的 [时间戳]、{长度}/<>长度、(长度)"""
        return_time = []
        # 去注释
        regex = re.compile(r'(#)(.*)(#)')
        if isinstance(data, str):
            data = regex.sub(r'', data)
        else:
            data = regex.sub(r'', data.decode('utf-8'))
        data = data.upper().replace('\n', '').replace('\t', '').replace(' ', '')

        # 处理 [时间戳]
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

            if time_len == 8:           # 4字节时间戳
                stamp_int = int(ori_time)
                new_hex = hex(stamp_int)[2:]
                if is_rev: new_hex = self.str_reverse(new_hex)
            elif time_len == 12:        # 6字节
                year = hex(stamp[0]-2000)[2:]
                new_hex = self.fix_str(year) + part
                if is_rev: new_hex = self.str_reverse(new_hex)
            elif time_len in (14,18):   # 7或9字节
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

        # 处理 { } 或 < > 帧内容长度（计算出后填入 ( ) 中）
        frame_len_int = 0
        data_clean = data
        for brace_open, brace_close in [('{','}'), ('<','>')]:
            if brace_open in data_clean and brace_close in data_clean:
                s = data_clean.index(brace_open)
                e = data_clean.index(brace_close)
                inner = data_clean[s+1:e]
                # 去掉内部可能有的 ( ) 和 R
                clean = inner.replace('(','').replace(')','').replace('R','').replace('r','')
                frame_len_int = len(clean) // 2
                data_clean = data_clean.replace(brace_open,'').replace(brace_close,'')
                break

        data = data_clean
        # 替换 ( ) 内的长度值
        if '(' in data and ')' in data and frame_len_int:
            s = data.index('(')
            e = data.index(')')
            len_part = data[s:e+1]  # 包含括号
            len_clean = len_part.replace('R','').replace('r','')
            len_byte = len(len_clean) - 2   # 去掉括号本身
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
        if sourse_port in [10000, 10001]:
            formatted = self.deal_data(data, hour, time_type=time_type).upper()
            post = bytes.fromhex(formatted)
        else:
            post = data.encode('utf-8')
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

# ===================== 发送线程 =====================
class SendThread(threading.Thread):
    def __init__(self, gui, mode, params):
        super().__init__(daemon=True)
        self.gui = gui
        self.mode = mode          # 'KAD1_OVERCAR', 'KAD2_OVERCAR', 'KAD1_HISTORY', 'KAD2_HISTORY'
        self.params = params
        self._stop = threading.Event()
        self.func = CphmFunc()

    def stop(self):
        self._stop.set()

    def run(self):
        p = self.params
        self.gui.log("开始发送数据...")
        while not self._stop.is_set():
            try:
                if self.mode == 'KAD1_OVERCAR':
                    codes = make_kad1_overcar(self.func, p['cabinet_no'], p['curve_list'],
                                              p['curve_num'], p['volt_min'], p['volt_max'])
                    for c in codes:
                        self.func.send_to_mss(p['src_ip'], p['dst_ip'], p['dst_port'],
                                              c, hour=0, time_type=2)
                elif self.mode == 'KAD2_OVERCAR':
                    codes = make_kad2_overcar(self.func, p['cabinet_no'], p['curve_list'],
                                              p['curve_num'], p['volt_min'], p['volt_max'])
                    for c in codes:
                        self.func.send_to_mss(p['src_ip'], p['dst_ip'], p['dst_port'],
                                              c, hour=0, time_type=2, time_out=0)
                elif self.mode == 'KAD1_HISTORY':
                    codes = make_kad1_history(self.func, p['cabinet_no'], p['device_num'],
                                              p['volt_min'], p['volt_max'])
                    for c in codes:
                        self.func.send_to_mss(p['src_ip'], p['dst_ip'], p['dst_port'],
                                              c, hour=0, time_type=2)
                elif self.mode == 'KAD2_HISTORY':
                    codes = make_kad2_history(self.func, p['cabinet_no'], p['device_num'],
                                              p['volt_min'], p['volt_max'])
                    for c in codes:
                        self.func.send_to_mss(p['src_ip'], p['dst_ip'], p['dst_port'],
                                              c, hour=0, time_type=2)
                self.gui.log(f"已发送 {len(codes)} 条数据，间隔 {p['interval']} 秒")
                time.sleep(p['interval'])
            except Exception as e:
                self.gui.log(f"发送异常: {e}")
                break
        self.gui.log("发送已停止")


# ===================== GUI =====================
class SimulatorGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("防雷柜曲线模拟器 (KAD_1 & KAD_2 过车/历史)")
        self.root.geometry("680x650")
        self.root.resizable(False, False)
        self.send_thread = None
        self.create_widgets()
        self.update_ui()  # 初始状态调整

    def create_widgets(self):
        # 数据类型
        ttk.Label(self.root, text="数据类型:").grid(row=0, column=0, padx=10, pady=5, sticky="e")
        self.data_type_var = tk.StringVar(value="过车曲线")
        data_type_combo = ttk.Combobox(self.root, textvariable=self.data_type_var,
                                       values=["过车曲线", "历史电压曲线"], state="readonly", width=12)
        data_type_combo.grid(row=0, column=1, sticky="w")
        data_type_combo.bind("<<ComboboxSelected>>", lambda e: self.update_ui())

        # 协议版本
        ttk.Label(self.root, text="协议版本:").grid(row=0, column=2, padx=10, pady=5, sticky="e")
        self.protocol_var = tk.StringVar(value="KAD_1")
        ttk.Combobox(self.root, textvariable=self.protocol_var,
                     values=["KAD_1", "KAD_2"], state="readonly", width=10).grid(row=0, column=3, sticky="w")

        # 源IP
        ttk.Label(self.root, text="源IP:").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        self.src_ip_var = tk.StringVar(value="192.168.0.43")
        ttk.Entry(self.root, textvariable=self.src_ip_var, width=18).grid(row=1, column=1, sticky="w")

        # 目标IP
        ttk.Label(self.root, text="目标IP:").grid(row=2, column=0, padx=10, pady=5, sticky="e")
        self.dst_ip_var = tk.StringVar(value="192.168.1.249")
        ttk.Entry(self.root, textvariable=self.dst_ip_var, width=18).grid(row=2, column=1, sticky="w")

        # 目标端口
        ttk.Label(self.root, text="目标端口:").grid(row=3, column=0, padx=10, pady=5, sticky="e")
        self.dst_port_var = tk.IntVar(value=7001)
        ttk.Entry(self.root, textvariable=self.dst_port_var, width=10).grid(row=3, column=1, sticky="w")

        # 机柜号
        ttk.Label(self.root, text="机柜号:").grid(row=4, column=0, padx=10, pady=5, sticky="e")
        self.cabinet_no_var = tk.IntVar(value=250)
        ttk.Entry(self.root, textvariable=self.cabinet_no_var, width=10).grid(row=4, column=1, sticky="w")

        # 设备数量 / 传感器数量（过车曲线为传感器数量，历史电压为设备数量）
        ttk.Label(self.root, text="设备数量 (0~N):").grid(row=5, column=0, padx=10, pady=5, sticky="e")
        self.dev_count_var = tk.IntVar(value=121)
        self.dev_count_entry = ttk.Entry(self.root, textvariable=self.dev_count_var, width=10)
        self.dev_count_entry.grid(row=5, column=1, sticky="w")

        # 曲线点数（仅过车曲线需要）
        ttk.Label(self.root, text="曲线数据点数:").grid(row=6, column=0, padx=10, pady=5, sticky="e")
        self.curve_num_var = tk.IntVar(value=50)
        self.curve_num_entry = ttk.Entry(self.root, textvariable=self.curve_num_var, width=10)
        self.curve_num_entry.grid(row=6, column=1, sticky="w")
        self.curve_num_label = ttk.Label(self.root, text="曲线数据点数:")  # 用于隐藏时重新引用

        # 电压范围
        ttk.Label(self.root, text="电压最小值 (x100):").grid(row=7, column=0, padx=10, pady=5, sticky="e")
        self.volt_min_var = tk.IntVar(value=600)
        ttk.Entry(self.root, textvariable=self.volt_min_var, width=10).grid(row=7, column=1, sticky="w")

        ttk.Label(self.root, text="电压最大值 (x100):").grid(row=7, column=2, padx=5, pady=5, sticky="e")
        self.volt_max_var = tk.IntVar(value=800)
        ttk.Entry(self.root, textvariable=self.volt_max_var, width=10).grid(row=7, column=3, sticky="w")

        # 发送间隔
        ttk.Label(self.root, text="发送间隔(秒):").grid(row=8, column=0, padx=10, pady=5, sticky="e")
        self.interval_var = tk.DoubleVar(value=2.0)
        ttk.Entry(self.root, textvariable=self.interval_var, width=10).grid(row=8, column=1, sticky="w")

        # 按钮
        self.start_btn = ttk.Button(self.root, text="开始发送", command=self.start_sending)
        self.start_btn.grid(row=9, column=0, padx=10, pady=15)
        self.stop_btn = ttk.Button(self.root, text="停止发送", command=self.stop_sending, state=tk.DISABLED)
        self.stop_btn.grid(row=9, column=1, padx=10, pady=15)

        # 日志区域
        ttk.Label(self.root, text="运行日志:").grid(row=10, column=0, columnspan=4, sticky="w", padx=10)
        self.log_area = scrolledtext.ScrolledText(self.root, width=80, height=15, state='normal')
        self.log_area.grid(row=11, column=0, columnspan=4, padx=10, pady=5)

    def update_ui(self):
        """根据数据类型切换控件状态"""
        if self.data_type_var.get() == "历史电压曲线":
            # 隐藏曲线点数相关控件
            self.curve_num_entry.grid_remove()
            # 修改设备数量标签提示
            # 注意：label 在创建时已固定，这里直接改文本
            for child in self.root.grid_slaves(row=5):
                if isinstance(child, ttk.Label):
                    child.config(text="设备数量 (模拟量个数):")
        else:
            self.curve_num_entry.grid()
            for child in self.root.grid_slaves(row=5):
                if isinstance(child, ttk.Label):
                    child.config(text="设备数量 (0~N):")

    def log(self, message):
        self.log_area.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_area.see(tk.END)

    def start_sending(self):
        try:
            cabinet_no = self.cabinet_no_var.get()
            dev_count = self.dev_count_var.get()
            curve_num = self.curve_num_var.get() if self.data_type_var.get() == "过车曲线" else 0
            src_ip = self.src_ip_var.get().strip()
            dst_ip = self.dst_ip_var.get().strip()
            dst_port = self.dst_port_var.get()
            interval = self.interval_var.get()
            volt_min = self.volt_min_var.get()
            volt_max = self.volt_max_var.get()
        except Exception as e:
            messagebox.showerror("输入错误", f"请检查参数: {e}")
            return

        if not src_ip or not dst_ip:
            messagebox.showerror("IP错误", "IP不能为空")
            return
        if interval <= 0:
            messagebox.showerror("间隔错误", "间隔必须 >0")
            return

        data_type = self.data_type_var.get()
        protocol = self.protocol_var.get()

        if data_type == "过车曲线":
            if dev_count < 0:
                messagebox.showerror("设备数量错误", "不能为负")
                return
            curve_list = list(range(dev_count + 1))
            mode = 'KAD1_OVERCAR' if protocol == 'KAD_1' else 'KAD2_OVERCAR'
            params = {
                'cabinet_no': cabinet_no,
                'curve_list': curve_list,
                'curve_num': curve_num,
                'volt_min': volt_min,
                'volt_max': volt_max,
                'src_ip': src_ip,
                'dst_ip': dst_ip,
                'dst_port': dst_port,
                'interval': interval
            }
        else:  # 历史电压曲线
            if dev_count <= 0:
                messagebox.showerror("设备数量错误", "必须 >0")
                return
            mode = 'KAD1_HISTORY' if protocol == 'KAD_1' else 'KAD2_HISTORY'
            params = {
                'cabinet_no': cabinet_no,
                'device_num': dev_count,
                'volt_min': volt_min,
                'volt_max': volt_max,
                'src_ip': src_ip,
                'dst_ip': dst_ip,
                'dst_port': dst_port,
                'interval': interval
            }

        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.send_thread = SendThread(self, mode, params)
        self.send_thread.start()

    def stop_sending(self):
        if self.send_thread and self.send_thread.is_alive():
            self.send_thread.stop()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = SimulatorGUI()
    app.run()