import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import random
import struct
from socket import *

from publicfunc import PublicFunc

func = PublicFunc()

# ------------------ 模拟量字典 ------------------
analog_type = {
    'DYP': '10',  # 电源屏
    'WDW': '11',  # 外电网
    'UPS': '12',  # UPS
    'GDDY': '20',  # 轨道电压
    'GDXWJ': '21',  # 轨道相位角
    'GDDL': '22',  # 轨道电流
    'GDZLDL': '26',  # 轨道直流电压
    'DCBSDY': '30',  # 道岔表示电压
    'DCQK': '31',  # 道岔缺口
    'DSJDQDL': '40',  # 灯丝继电器电流
    'HJMNL': '70',  # 环境模拟量
    'DLJY': '80',  # 电缆绝缘
    'DYLL': '81',  # 电源漏流
    'ZLDY': '43',  # 站联电压
}

# 默认数量（可根据需要修改）
analog_num_default = {
    'DYP': 0,
    'WDW': 0,
    'UPS': 0,
    'GDDY': 0,
    'GDXWJ': 0,
    'GDDL': 0,
    'GDZLDL': 0,
    'DCBSDY': 0,
    'DCQK': 0,
    'DSJDQDL': 0,
    'HJMNL': 70,
    'DLJY': 0,
    'DYLL': 0,
    'ZLDY': 72,
}


# ------------------ 辅助函数 ------------------
def float_to_hex(f):
    return hex(struct.unpack('<I', struct.pack('<f', f))[0])


def generate_single_value(index):
    """生成单个模拟量条目的十六进制字符串（不含时间戳占位符）"""
    index_hex = func.int_to_hex(index, 4)
    index_hex = func.str_reverse(index_hex)

    float_data = random.uniform(0, 100)
    float_data = round(float_data, 2)
    hex_data = float_to_hex(float_data)[2:]
    hex_data = func.str_reverse(hex_data)

    return index_hex + hex_data


def build_single_frame(type_name, index):
    """构建只包含一个模拟量点的完整报文字符串（处理前）"""
    num_int = 1  # 单条报文模拟量个数为1
    len_int = 14 + 2 + num_int * 10
    len_hex = func.int_to_hex(len_int, 8)
    len_hex = func.str_reverse(len_hex)

    type_hex = analog_type[type_name]
    num_hex = func.int_to_hex(num_int, 4)
    num_hex = func.str_reverse(num_hex)

    part_value = generate_single_value(index) + '[64 25 A0 5D R]'

    send_data = '''
        EF EF EF EF #帧头#
        10 #初版为0x10,后面做修正分别为0x20...依次递增#
        8F #数据帧标志8fH, 心跳帧标志0FH#
        [64 25 A0 5D R] #时间戳#
        %s #数据长度#

        4A 4B 31 #目的电报码#
        73 78 70 #源电报码#
        00 00 00 #自然站电报码#
        10 #数据类型码 模拟量数据类型：0x10#
        01 #数据子类型码 0x01#

        %s #模拟量类型#
        01 00 #采集频率#
        %s #模拟量个数#
        %s
        F6 EB #CRC16校验#
        FE FE FE FE #帧尾部#
    ''' % (len_hex, type_hex, num_hex, part_value)

    return send_data


def build_batch_frame(type_name, num):
    """构建包含多个模拟量点的完整报文字符串（处理前）"""
    len_int = 14 + 2 + num * 10
    len_hex = func.int_to_hex(len_int, 8)
    len_hex = func.str_reverse(len_hex)

    type_hex = analog_type[type_name]
    num_hex = func.int_to_hex(num, 4)
    num_hex = func.str_reverse(num_hex)

    part_value = ''
    for i in range(num):
        part_value += generate_single_value(i) + '[64 25 A0 5D R]'

    send_data = '''
        EF EF EF EF #帧头#
        10 #初版为0x10,后面做修正分别为0x20...依次递增#
        8F #数据帧标志8fH, 心跳帧标志0FH#
        [64 25 A0 5D R] #时间戳#
        %s #数据长度#

        4A 4B 31 #目的电报码#
        73 78 70 #源电报码#
        00 00 00 #自然站电报码#
        10 #数据类型码 模拟量数据类型：0x10#
        01 #数据子类型码 0x01#

        %s #模拟量类型#
        01 00 #采集频率#
        %s #模拟量个数#
        %s
        F6 EB #CRC16校验#
        FE FE FE FE #帧尾部#
    ''' % (len_hex, type_hex, num_hex, part_value)

    return send_data


# ------------------ GUI 类 ------------------
class AnalogSenderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("模拟量发送工具")
        self.root.geometry("800x600")
        self.root.resizable(True, True)

        # 控制变量
        self.is_sending = False
        self.send_thread = None
        self.tcp_socket = None
        self.connected = False

        # 创建界面
        self.create_widgets()

        # 关闭窗口时停止线程
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_widgets(self):
        # 连接设置区
        conn_frame = ttk.LabelFrame(self.root, text="TCP 连接设置", padding=10)
        conn_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(conn_frame, text="服务器IP:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.ip_var = tk.StringVar(value="192.168.1.134")
        ip_entry = ttk.Entry(conn_frame, textvariable=self.ip_var, width=20)
        ip_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(conn_frame, text="端口:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        self.port_var = tk.IntVar(value=7777)
        port_entry = ttk.Entry(conn_frame, textvariable=self.port_var, width=10)
        port_entry.grid(row=0, column=3, padx=5, pady=5)

        self.connect_btn = ttk.Button(conn_frame, text="连接", command=self.connect_server)
        self.connect_btn.grid(row=0, column=4, padx=10, pady=5)

        self.disconnect_btn = ttk.Button(conn_frame, text="断开", command=self.disconnect_server, state=tk.DISABLED)
        self.disconnect_btn.grid(row=0, column=5, padx=5, pady=5)

        self.conn_status = ttk.Label(conn_frame, text="未连接", foreground="red")
        self.conn_status.grid(row=0, column=6, padx=10, pady=5)

        # 模拟量设置区
        sim_frame = ttk.LabelFrame(self.root, text="模拟量设置", padding=10)
        sim_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(sim_frame, text="模拟量类型:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.type_combo = ttk.Combobox(sim_frame, values=list(analog_type.keys()), state="readonly", width=15)
        self.type_combo.current(7)  # 默认选择 DCBSDY
        self.type_combo.grid(row=0, column=1, padx=5, pady=5)
        self.type_combo.bind("<<ComboboxSelected>>", self.on_type_selected)

        ttk.Label(sim_frame, text="数量:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        self.num_var = tk.IntVar(value=0)
        num_spin = ttk.Spinbox(sim_frame, from_=0, to=1000, textvariable=self.num_var, width=10)
        num_spin.grid(row=0, column=3, padx=5, pady=5)

        # 更新默认数量
        self.on_type_selected(None)

        # 发送设置区
        send_frame = ttk.LabelFrame(self.root, text="发送控制", padding=10)
        send_frame.pack(fill=tk.X, padx=10, pady=5)

        self.send_check = tk.BooleanVar(value=False)
        send_cb = ttk.Checkbutton(send_frame, text="实际通过TCP发送", variable=self.send_check)
        send_cb.grid(row=0, column=0, padx=5, pady=5)

        # 新增：逐条发送选项
        self.single_send_check = tk.BooleanVar(value=True)
        single_cb = ttk.Checkbutton(send_frame, text="逐条发送（每个模拟量单独一帧）",
                                    variable=self.single_send_check)
        single_cb.grid(row=0, column=1, padx=5, pady=5)

        self.start_btn = ttk.Button(send_frame, text="开始发送", command=self.start_sending)
        self.start_btn.grid(row=0, column=2, padx=10, pady=5)

        self.stop_btn = ttk.Button(send_frame, text="停止发送", command=self.stop_sending, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=3, padx=10, pady=5)

        # 显示区
        display_frame = ttk.LabelFrame(self.root, text="报文输出", padding=10)
        display_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.text_area = scrolledtext.ScrolledText(display_frame, wrap=tk.WORD, height=20)
        self.text_area.pack(fill=tk.BOTH, expand=True)

    def on_type_selected(self, event):
        """类型改变时自动填充默认数量"""
        type_name = self.type_combo.get()
        if type_name in analog_num_default:
            self.num_var.set(analog_num_default[type_name])

    def connect_server(self):
        ip = self.ip_var.get().strip()
        port = self.port_var.get()
        if not ip or not port:
            messagebox.showwarning("提示", "请输入服务器IP和端口")
            return

        try:
            self.tcp_socket = socket(AF_INET, SOCK_STREAM)
            self.tcp_socket.settimeout(5)
            self.tcp_socket.connect((ip, port))
            self.connected = True
            self.conn_status.config(text=f"已连接 {ip}:{port}", foreground="green")
            self.connect_btn.config(state=tk.DISABLED)
            self.disconnect_btn.config(state=tk.NORMAL)
            self.log("TCP 连接成功")
        except Exception as e:
            messagebox.showerror("连接失败", f"无法连接到 {ip}:{port}\n错误: {e}")
            self.tcp_socket = None
            self.connected = False

    def disconnect_server(self):
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except:
                pass
        self.tcp_socket = None
        self.connected = False
        self.conn_status.config(text="未连接", foreground="red")
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        self.log("TCP 已断开")

    def log(self, msg):
        """在文本区域添加一行"""
        self.text_area.insert(tk.END, msg + "\n")
        self.text_area.see(tk.END)

    def start_sending(self):
        if self.is_sending:
            return

        # 检查连接
        if self.send_check.get() and not self.connected:
            messagebox.showwarning("提示", "勾选了实际发送，但尚未连接服务器")
            return

        # 获取配置
        type_name = self.type_combo.get()
        num = self.num_var.get()
        if num < 1:
            messagebox.showwarning("提示", "模拟量数量必须大于0")
            return

        self.is_sending = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.type_combo.config(state=tk.DISABLED)
        self.num_var.set(num)

        # 启动发送线程
        self.send_thread = threading.Thread(target=self.send_loop, args=(type_name, num), daemon=True)
        self.send_thread.start()

    def stop_sending(self):
        self.is_sending = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.type_combo.config(state="readonly")
        self.log("已停止发送")

    def send_loop(self, type_name, num):
        while self.is_sending:
            try:
                if self.single_send_check.get():
                    # 逐条发送：每个模拟量单独一条报文
                    for i in range(num):
                        if not self.is_sending:
                            break
                        raw_frame = build_single_frame(type_name, i)
                        formatted = func.deal_data(raw_frame)
                        self.root.after(0, self.log, formatted)

                        if self.send_check.get() and self.tcp_socket:
                            try:
                                data_bytes = bytes.fromhex(formatted.replace(" ", ""))
                                self.tcp_socket.send(data_bytes)
                            except Exception as e:
                                self.root.after(0, self.log, f"发送失败: {e}")

                        time.sleep(0.5)  # 每条间隔0.5秒
                else:
                    # 批量发送：所有模拟量合并在一个报文中
                    raw_frame = build_batch_frame(type_name, num)
                    formatted = func.deal_data(raw_frame)
                    self.root.after(0, self.log, formatted)

                    if self.send_check.get() and self.tcp_socket:
                        try:
                            data_bytes = bytes.fromhex(formatted.replace(" ", ""))
                            self.tcp_socket.send(data_bytes)
                        except Exception as e:
                            self.root.after(0, self.log, f"发送失败: {e}")

                    time.sleep(1)  # 批量发送间隔1秒

            except Exception as e:
                self.root.after(0, self.log, f"生成报文出错: {e}")
                time.sleep(2)

    def on_close(self):
        self.stop_sending()
        self.disconnect_server()
        self.root.destroy()


# ------------------ 启动 ------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = AnalogSenderApp(root)
    root.mainloop()