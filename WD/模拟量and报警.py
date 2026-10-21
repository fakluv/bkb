import os
import random
import socket
import struct
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# 原有依赖模块
import cphmfunc
import mms_func

try:
    ALARM_TYPE_DICT = mms_func.get_mms_alarm_type_dict()
except AttributeError:
    ALARM_TYPE_DICT = {}
    print("警告: mms_func.get_mms_alarm_type_dict 不存在，使用空字典")

func = cphmfunc.CphmFunc()


# ========================== 报警发送类 ==========================
class AlarmSender:
    """报警发送核心类（使用标准 socket 实现 TCP 客户端）"""
    def __init__(self, src_ip, dst_ip, dst_port, alarm_type_hex,
                 alarm_info, is_alarm, start_dev, end_dev):
        self.src_ip = src_ip
        self.dst_ip = dst_ip
        self.dst_port = dst_port
        self.alarm_type_hex = alarm_type_hex
        self.alarm_info = alarm_info
        self.is_alarm = is_alarm
        self.start_dev = start_dev
        self.end_dev = end_dev
        self.tcp_client = None
        self.running = False

    def _make_code(self, device_no):
        alarm_type_name = ALARM_TYPE_DICT.get(self.alarm_type_hex, "未知类型")
        recover_stamp = '00 00 00 00' if self.is_alarm else '[C9 96 8F 5D R]'
        device_no_hex = func.int_to_hex(device_no, 4)
        device_no_hex_reverse = func.str_reverse(device_no_hex)

        alarm_info_hex = func.chiness_to_hex(self.alarm_info)
        alarm_info_len = func.get_code_len(alarm_info_hex, len_byte=2)
        alarm_info_len_reverse = func.str_reverse(alarm_info_len)

        send_data = f'''
            EF EF EF EF #帧头#
            10 #初版为0x10,后面做修正分别为0x20...依次递增#
            8F #数据帧标志8fH, 心跳帧标志0FH#
            [E3 93 CC 64 R]#时间戳#
            (13 00 00 00 R) #数据长度#
            <
            4A 4B 31 #目的电报码#
            4C 48 5A #源电报码#
            4C 48 5A #自然站电报码#

            13  #数据类型码 报警类型：0x13#
            01 #数据子类型码 0x01#

            [C9 96 8F 5D R] #报警时间#
            {recover_stamp} #恢复时间#
            {device_no_hex_reverse} 00 00 #设备编号#
            {self.alarm_type_hex} 00 #报警类型号 名称：{alarm_type_name}#
            {alarm_info_len_reverse} #报警内容长度#
            {alarm_info_hex} #报警内容: {self.alarm_info}#
            >
            3E 0A #CRC16校验#
            FE FE FE FE #帧尾部#
        '''
        return func.deal_data(send_data)

    def _connect(self):
        if self.tcp_client is None:
            self.tcp_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_client.settimeout(5)
            # 绑定源IP（如果提供了有效地址）
            if self.src_ip:
                try:
                    self.tcp_client.bind((self.src_ip, 0))
                except Exception as e:
                    raise ConnectionError(f"绑定源IP {self.src_ip} 失败: {e}")
            try:
                self.tcp_client.connect((self.dst_ip, self.dst_port))
            except Exception as e:
                self.tcp_client = None
                raise ConnectionError(f"连接 {self.dst_ip}:{self.dst_port} 失败: {e}")

    def _send_one(self, device_no):
        data_str = self._make_code(device_no)
        send_data = func.deal_data(data_str, fix_hour=0)
        byte_data = func.str_to_bytes(send_data)
        self.tcp_client.sendall(byte_data)

    def send_all(self, progress_callback=None, log_callback=None):
        self.running = True
        try:
            self._connect()
            total = self.end_dev - self.start_dev + 1
            for i, dev in enumerate(range(self.start_dev, self.end_dev + 1), 1):
                if not self.running:
                    break
                try:
                    self._send_one(dev)
                    msg = f"设备 {dev} 发送成功"
                except Exception as e:
                    msg = f"设备 {dev} 发送失败: {e}"
                if log_callback:
                    log_callback(msg)
                if progress_callback:
                    progress_callback(i, total)
                time.sleep(0.1)
        except Exception as e:
            if log_callback:
                log_callback(f"严重错误: {e}")
        finally:
            self.running = False
            if log_callback:
                log_callback("发送任务结束")
            if self.tcp_client:
                try:
                    self.tcp_client.close()
                except:
                    pass
                self.tcp_client = None

    def stop(self):
        self.running = False


# ========================== 模拟量发送类（支持轮数控制 + 源IP） ==========================
class AnalogSender:
    """模拟量数据持续发送类，支持指定最大发送次数（0为无限），并可绑定源IP"""
    ANALOG_TYPE_MAP = {
        'DYP': '10', 'WDW': '11', 'UPS': '12', 'GDDY': '20', 'GDXWJ': '21',
        'GDDL': '22', 'GDZLDL': '26', 'DCBSDY': '30', 'DCQK': '31',
        'DSJDQDL': '40', 'HJMNL': '70', 'DLJY': '80', 'DYLL': '81', 'ZLDY': '43',
    }
    ANALOG_COUNT_DEFAULT = {
        'DYP': 0, 'WDW': 0, 'UPS': 0, 'GDDY': 0, 'GDXWJ': 0,
        'GDDL': 0, 'GDZLDL': 0, 'DCBSDY': 0, 'DCQK': 0,
        'DSJDQDL': 0, 'HJMNL': 70, 'DLJY': 0, 'DYLL': 0, 'ZLDY': 72,
    }

    def __init__(self, src_ip, dst_ip, dst_port, analog_type, analog_count, interval=1.0, max_count=0):
        self.src_ip = src_ip              # 源IP，可为空
        self.dst_ip = dst_ip
        self.dst_port = dst_port
        self.analog_type = analog_type
        self.analog_count = analog_count
        self.interval = interval
        self.max_count = max_count          # 0 表示无限
        self.tcp_client = None
        self.running = False
        self.send_count = 0

    @staticmethod
    def float_to_hex(f):
        return hex(struct.unpack('<I', struct.pack('<f', f))[0])[2:]

    def _generate_analog_values(self, num):
        values = ''
        for i in range(num):
            index_hex = func.int_to_hex(i, 4)
            index_hex = func.str_reverse(index_hex)
            float_data = round(random.uniform(0, 100), 2)
            hex_data = self.float_to_hex(float_data)
            hex_data = func.str_reverse(hex_data)
            values += index_hex + hex_data + '[64 25 A0 5D R]'
        return values

    def _connect(self):
        if self.tcp_client is None:
            self.tcp_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_client.settimeout(5)
            # 绑定源IP（如果提供了有效地址）
            if self.src_ip:
                try:
                    self.tcp_client.bind((self.src_ip, 0))
                except Exception as e:
                    raise ConnectionError(f"绑定源IP {self.src_ip} 失败: {e}")
            try:
                self.tcp_client.connect((self.dst_ip, self.dst_port))
            except Exception as e:
                self.tcp_client = None
                raise ConnectionError(f"连接 {self.dst_ip}:{self.dst_port} 失败: {e}")

    def _build_packet(self):
        data_len = 14 + 2 + self.analog_count * 10
        len_hex = func.int_to_hex(data_len, 8)
        len_hex = func.str_reverse(len_hex)

        type_hex = self.ANALOG_TYPE_MAP.get(self.analog_type, '00')
        num_hex = func.int_to_hex(self.analog_count, 4)
        num_hex = func.str_reverse(num_hex)

        part_value = self._generate_analog_values(self.analog_count)

        send_data = f'''
            EF EF EF EF #帧头#
            10 #初版为0x10,后面做修正分别为0x20...依次递增#
            8F #数据帧标志8fH, 心跳帧标志0FH#
            [64 25 A0 5D R] #时间戳#
            {len_hex} #数据长度#

            4A 4B 31 #目的电报码#
            73 78 70 #源电报码#
            00 00 00 #自然站电报码#
            10 #数据类型码 模拟量数据类型：0x10#
            01 #数据子类型码 0x01#

            {type_hex} #模拟量类型#
            01 00 #采集频率#
            {num_hex} #模拟量个数#
            {part_value}
            F6 EB #CRC16校验#
            FE FE FE FE #帧尾部#
        '''
        return func.deal_data(send_data)

    def send_loop(self, progress_callback=None, log_callback=None):
        """循环发送，达到 max_count 后自动停止"""
        self.running = True
        self.send_count = 0
        try:
            self._connect()
            while self.running:
                # 检查是否达到最大次数
                if self.max_count > 0 and self.send_count >= self.max_count:
                    break
                try:
                    packet_str = self._build_packet()
                    byte_data = bytes.fromhex(packet_str.upper())
                    self.tcp_client.sendall(byte_data)
                    self.send_count += 1
                    msg = f"模拟量发送 #{self.send_count} 成功"
                except Exception as e:
                    msg = f"模拟量发送失败: {e}"
                    self.tcp_client = None
                    time.sleep(1)
                    try:
                        self._connect()
                    except:
                        pass
                if log_callback:
                    log_callback(msg)
                if progress_callback:
                    progress_callback(self.send_count, self.max_count)
                # 等待间隔，可被中断
                for _ in range(int(self.interval * 10)):
                    if not self.running:
                        break
                    time.sleep(0.1)
        except Exception as e:
            if log_callback:
                log_callback(f"严重错误: {e}")
        finally:
            self.running = False
            if log_callback:
                log_callback("模拟量发送已停止")
            if self.tcp_client:
                try:
                    self.tcp_client.close()
                except:
                    pass
                self.tcp_client = None

    def stop(self):
        self.running = False


# ========================== GUI 主程序 ==========================
class AlarmGUI:
    def __init__(self, master):
        self.master = master
        master.title("网达协议报文工具 v1.0")
        master.geometry("750x650")
        self.set_window_icon()

        self.notebook = ttk.Notebook(master)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)

        # 报警选项卡
        self.alarm_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.alarm_frame, text="报警发送")
        self._create_alarm_widgets(self.alarm_frame)

        # 模拟量选项卡
        self.analog_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.analog_frame, text="模拟量发送")
        self._create_analog_widgets(self.analog_frame)

        # 线程/发送器引用
        self.alarm_sender = None
        self.alarm_thread = None
        self.analog_sender = None
        self.analog_thread = None

    def set_window_icon(self):
        """设置窗口左上角图标"""
        try:
            # 获取资源路径（兼容 PyInstaller 打包）
            if hasattr(sys, '_MEIPASS'):
                # 打包后的临时目录
                base_path = sys._MEIPASS
            else:
                base_path = os.path.abspath(".")
            icon_path = os.path.join(base_path, "dragon.ico")
            if os.path.exists(icon_path):
                self.master.iconbitmap(icon_path)
                # self.log(f"窗口图标已加载：{icon_path}")
            else:
                # 如果找不到图标文件，可以使用默认图标（无图标）
                pass
        except Exception as e:
            print(f"设置图标失败：{e}")

    # -------------------- 报警选项卡 --------------------
    def _create_alarm_widgets(self, parent):
        input_frame = tk.LabelFrame(parent, text="报警参数设置", padx=10, pady=10)
        input_frame.pack(pady=10, padx=10, fill="x")

        tk.Label(input_frame, text="源IP:").grid(row=0, column=0, sticky="e")
        self.alarm_src_ip = tk.Entry(input_frame, width=15)
        self.alarm_src_ip.grid(row=0, column=1, padx=5, pady=2)
        self.alarm_src_ip.insert(0, "192.168.0.43")

        tk.Label(input_frame, text="目标IP:").grid(row=0, column=2, sticky="e")
        self.alarm_dst_ip = tk.Entry(input_frame, width=15)
        self.alarm_dst_ip.grid(row=0, column=3, padx=5, pady=2)
        self.alarm_dst_ip.insert(0, "192.168.1.213")

        tk.Label(input_frame, text="目标端口:").grid(row=0, column=4, sticky="e")
        self.alarm_dst_port = tk.Entry(input_frame, width=8)
        self.alarm_dst_port.grid(row=0, column=5, padx=5, pady=2)
        self.alarm_dst_port.insert(0, "7777")

        tk.Label(input_frame, text="设备起始号:").grid(row=1, column=0, sticky="e")
        self.alarm_dev_start = tk.Entry(input_frame, width=8)
        self.alarm_dev_start.grid(row=1, column=1, padx=5, pady=2)
        self.alarm_dev_start.insert(0, "26")

        tk.Label(input_frame, text="设备结束号:").grid(row=1, column=2, sticky="e")
        self.alarm_dev_end = tk.Entry(input_frame, width=8)
        self.alarm_dev_end.grid(row=1, column=3, padx=5, pady=2)
        self.alarm_dev_end.insert(0, "32")

        tk.Label(input_frame, text="报警类型(hex):").grid(row=2, column=0, sticky="e")
        self.alarm_type = tk.Entry(input_frame, width=8)
        self.alarm_type.grid(row=2, column=1, padx=5, pady=2)
        self.alarm_type.insert(0, "25")

        tk.Label(input_frame, text="报警内容:").grid(row=2, column=2, sticky="e")
        self.alarm_info = tk.Entry(input_frame, width=20)
        self.alarm_info.grid(row=2, column=3, padx=5, pady=2)
        self.alarm_info.insert(0, "报警")

        self.alarm_is_alarm_var = tk.BooleanVar(value=True)
        tk.Checkbutton(input_frame, text="报警 (勾选为报警，取消为恢复)",
                       variable=self.alarm_is_alarm_var).grid(row=2, column=4, columnspan=2, sticky="w")

        btn_frame = tk.Frame(parent)
        btn_frame.pack(pady=5)
        self.alarm_send_btn = tk.Button(btn_frame, text="开始发送", command=self.alarm_start_send, width=12)
        self.alarm_send_btn.pack(side="left", padx=5)
        self.alarm_stop_btn = tk.Button(btn_frame, text="停止", command=self.alarm_stop_send, width=12, state="disabled")
        self.alarm_stop_btn.pack(side="left", padx=5)
        tk.Button(btn_frame, text="清空日志", command=self.alarm_clear_log, width=12).pack(side="left", padx=5)

        self.alarm_progress_label = tk.Label(parent, text="就绪")
        self.alarm_progress_label.pack(pady=2)

        log_frame = tk.LabelFrame(parent, text="报警日志", padx=5, pady=5)
        log_frame.pack(pady=5, padx=10, fill="both", expand=True)
        self.alarm_log_text = scrolledtext.ScrolledText(log_frame, height=10, state="normal")
        self.alarm_log_text.pack(fill="both", expand=True)

    def alarm_log(self, msg):
        self.alarm_log_text.insert(tk.END, msg + "\n")
        self.alarm_log_text.see(tk.END)

    def alarm_clear_log(self):
        self.alarm_log_text.delete(1.0, tk.END)

    def alarm_update_progress(self, current, total):
        self.alarm_progress_label.config(text=f"进度: {current}/{total}")

    def alarm_start_send(self):
        try:
            src_ip = self.alarm_src_ip.get().strip()
            dst_ip = self.alarm_dst_ip.get().strip()
            dst_port = int(self.alarm_dst_port.get().strip())
            start_dev = int(self.alarm_dev_start.get().strip())
            end_dev = int(self.alarm_dev_end.get().strip())
            alarm_type = self.alarm_type.get().strip()
            alarm_info = self.alarm_info.get().strip()
            is_alarm = self.alarm_is_alarm_var.get()
        except ValueError as e:
            messagebox.showerror("参数错误", f"请输入有效数字: {e}")
            return

        if not src_ip or not dst_ip or not alarm_type:
            messagebox.showerror("参数错误", "IP、端口和报警类型不能为空")
            return
        if start_dev > end_dev:
            messagebox.showerror("参数错误", "起始设备号不能大于结束设备号")
            return

        self.alarm_send_btn.config(state="disabled")
        self.alarm_stop_btn.config(state="normal")
        self.alarm_log("开始发送报警...")

        self.alarm_sender = AlarmSender(
            src_ip, dst_ip, dst_port, alarm_type,
            alarm_info, is_alarm, start_dev, end_dev
        )

        def target():
            self.alarm_sender.send_all(
                progress_callback=self.alarm_update_progress,
                log_callback=self.alarm_log
            )
            self.master.after(0, self.alarm_finish_send)

        self.alarm_thread = threading.Thread(target=target, daemon=True)
        self.alarm_thread.start()

    def alarm_finish_send(self):
        self.alarm_send_btn.config(state="normal")
        self.alarm_stop_btn.config(state="disabled")
        self.alarm_progress_label.config(text="发送完成")

    def alarm_stop_send(self):
        if self.alarm_sender:
            self.alarm_sender.stop()
            self.alarm_log("用户停止发送")
            self.alarm_stop_btn.config(state="disabled")
            if self.alarm_thread and self.alarm_thread.is_alive():
                self.alarm_thread.join(timeout=1)

    # -------------------- 模拟量选项卡（支持轮数 + 源IP） --------------------
    def _create_analog_widgets(self, parent):
        input_frame = tk.LabelFrame(parent, text="模拟量参数设置", padx=10, pady=10)
        input_frame.pack(pady=10, padx=10, fill="x")

        # 行0：源IP、目标IP、目标端口
        tk.Label(input_frame, text="源IP:").grid(row=0, column=0, sticky="e")
        self.analog_src_ip = tk.Entry(input_frame, width=15)
        self.analog_src_ip.grid(row=0, column=1, padx=5, pady=2)
        self.analog_src_ip.insert(0, "")   # 默认留空，使用系统自动选择

        tk.Label(input_frame, text="目标IP:").grid(row=0, column=2, sticky="e")
        self.analog_dst_ip = tk.Entry(input_frame, width=15)
        self.analog_dst_ip.grid(row=0, column=3, padx=5, pady=2)
        self.analog_dst_ip.insert(0, "192.168.1.134")

        tk.Label(input_frame, text="目标端口:").grid(row=0, column=4, sticky="e")
        self.analog_dst_port = tk.Entry(input_frame, width=8)
        self.analog_dst_port.grid(row=0, column=5, padx=5, pady=2)
        self.analog_dst_port.insert(0, "7777")

        # 行1：类型、个数、间隔、轮数
        tk.Label(input_frame, text="模拟量类型:").grid(row=1, column=0, sticky="e")
        self.analog_type_var = tk.StringVar()
        self.analog_type_combo = ttk.Combobox(input_frame, textvariable=self.analog_type_var,
                                              values=list(AnalogSender.ANALOG_TYPE_MAP.keys()), width=10)
        self.analog_type_combo.grid(row=1, column=1, padx=5, pady=2)
        self.analog_type_combo.set("HJMNL")
        self.analog_type_combo.bind("<<ComboboxSelected>>", self._on_analog_type_changed)

        tk.Label(input_frame, text="模拟量个数:").grid(row=1, column=2, sticky="e")
        self.analog_count_entry = tk.Entry(input_frame, width=8)
        self.analog_count_entry.grid(row=1, column=3, padx=5, pady=2)
        self.analog_count_entry.insert(0, "70")

        tk.Label(input_frame, text="间隔(秒):").grid(row=1, column=4, sticky="e")
        self.analog_interval_entry = tk.Entry(input_frame, width=8)
        self.analog_interval_entry.grid(row=1, column=5, padx=5, pady=2)
        self.analog_interval_entry.insert(0, "1.0")

        # 行2：轮数（独占一行或跟在后面）
        tk.Label(input_frame, text="轮数(0无限):").grid(row=2, column=0, sticky="e")
        self.analog_max_count_entry = tk.Entry(input_frame, width=8)
        self.analog_max_count_entry.grid(row=2, column=1, padx=5, pady=2)
        self.analog_max_count_entry.insert(0, "0")

        # 按钮
        btn_frame = tk.Frame(parent)
        btn_frame.pack(pady=5)
        self.analog_send_btn = tk.Button(btn_frame, text="开始发送", command=self.analog_start_send, width=12)
        self.analog_send_btn.pack(side="left", padx=5)
        self.analog_stop_btn = tk.Button(btn_frame, text="停止", command=self.analog_stop_send, width=12, state="disabled")
        self.analog_stop_btn.pack(side="left", padx=5)
        tk.Button(btn_frame, text="清空日志", command=self.analog_clear_log, width=12).pack(side="left", padx=5)

        self.analog_progress_label = tk.Label(parent, text="就绪")
        self.analog_progress_label.pack(pady=2)

        log_frame = tk.LabelFrame(parent, text="模拟量日志", padx=5, pady=5)
        log_frame.pack(pady=5, padx=10, fill="both", expand=True)
        self.analog_log_text = scrolledtext.ScrolledText(log_frame, height=10, state="normal")
        self.analog_log_text.pack(fill="both", expand=True)

        # 初始根据类型设置个数
        self._on_analog_type_changed(None)

    def _on_analog_type_changed(self, event):
        typ = self.analog_type_var.get()
        count = AnalogSender.ANALOG_COUNT_DEFAULT.get(typ, 0)
        self.analog_count_entry.delete(0, tk.END)
        self.analog_count_entry.insert(0, str(count))

    def analog_log(self, msg):
        self.analog_log_text.insert(tk.END, msg + "\n")
        self.analog_log_text.see(tk.END)

    def analog_clear_log(self):
        self.analog_log_text.delete(1.0, tk.END)

    def analog_update_progress(self, current, total):
        if total > 0:
            self.analog_progress_label.config(text=f"进度: {current}/{total}")
        else:
            self.analog_progress_label.config(text=f"已发送: {current} 次")

    def analog_start_send(self):
        try:
            src_ip = self.analog_src_ip.get().strip()
            dst_ip = self.analog_dst_ip.get().strip()
            dst_port = int(self.analog_dst_port.get().strip())
            analog_type = self.analog_type_var.get().strip()
            analog_count = int(self.analog_count_entry.get().strip())
            interval = float(self.analog_interval_entry.get().strip())
            max_count = int(self.analog_max_count_entry.get().strip())
        except ValueError as e:
            messagebox.showerror("参数错误", f"请输入有效数字: {e}")
            return

        if not dst_ip or not analog_type:
            messagebox.showerror("参数错误", "目标IP和模拟量类型不能为空")
            return
        if analog_count < 0:
            messagebox.showerror("参数错误", "模拟量个数不能为负数")
        if max_count < 0:
            messagebox.showerror("参数错误", "轮数不能为负数")

        self.analog_send_btn.config(state="disabled")
        self.analog_stop_btn.config(state="normal")
        self.analog_log("开始模拟量发送...")

        self.analog_sender = AnalogSender(src_ip, dst_ip, dst_port, analog_type, analog_count, interval, max_count)

        def target():
            self.analog_sender.send_loop(
                progress_callback=self.analog_update_progress,
                log_callback=self.analog_log
            )
            self.master.after(0, self.analog_finish_send)

        self.analog_thread = threading.Thread(target=target, daemon=True)
        self.analog_thread.start()

    def analog_finish_send(self):
        self.analog_send_btn.config(state="normal")
        self.analog_stop_btn.config(state="disabled")
        self.analog_progress_label.config(text="发送停止")

    def analog_stop_send(self):
        if self.analog_sender:
            self.analog_sender.stop()
            self.analog_log("用户停止发送")
            self.analog_stop_btn.config(state="disabled")
            if self.analog_thread and self.analog_thread.is_alive():
                self.analog_thread.join(timeout=1)


def main():
    root = tk.Tk()
    app = AlarmGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()