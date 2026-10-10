import socket
import threading
import time
import struct
import re
import random
from tkinter import scrolledtext, END
import ttkbootstrap as ttk
from ttkbootstrap.constants import *


# ---------- 公共工具函数 ----------
class PublicFunc:
    @staticmethod
    def int_to_hex(i, length=2):
        return format(i, '0{}X'.format(length))

    @staticmethod
    def str_reverse(s):
        if len(s) % 2 != 0:
            s = '0' + s
        return ''.join(reversed([s[i:i + 2] for i in range(0, len(s), 2)]))

    @staticmethod
    def deal_data(raw):
        raw = re.sub(r'#.*', '', raw)
        raw = re.sub(r'\[([0-9A-Fa-f\s]+)\s*R\]', r'\1', raw)
        raw = raw.replace('[', '').replace(']', '')
        raw = ' '.join(raw.split()).upper()
        return raw

    @staticmethod
    def str_to_bytes(hex_str):
        return bytes.fromhex(hex_str.replace(' ', ''))


func = PublicFunc()

# ---------- 缺口报警类型定义 ----------
ALARM_TYPES = {
    1: "1 缺口预警及预警图像",
    2: "2 缺口报警及报警图像",
    3: "3 缺口采集设备故障",
    4: "4 缺口图像无法识别报警",
    5: "5 过车时框量过大报警及过车视频",
    6: "6 转辙机采集设备故障报警",
    7: "7 温度报警",
    8: "8 湿度报警",
    9: "9 油位预警（预留）",
    10: "10 油位报警（预留）",
}
RECOVER_TYPES = {
    101: "101 缺口预警恢复及图像",
    102: "102 缺口报警恢复及图像",
    103: "103 缺口采集设备故障恢复及图像",
    104: "104 缺口图像无法识别报警恢复及图像",
    105: "105 转辙机采集设备故障报警恢复",
    106: "106 过车时框量过大报警恢复及过车视频",
    107: "107 温度报警恢复",
    108: "108 湿度报警恢复",
    109: "109 油位预警恢复（预留）",
    110: "110 油位报警恢复（预留）",
}


# ---------- 动态时间戳（小端，反转） ----------
def get_timestamp_str():
    unix_time = int(time.time())
    big_bytes = struct.pack('>I', unix_time)
    little_bytes = big_bytes[::-1]
    hex_str = ' '.join(f'{b:02X}' for b in little_bytes)
    return f'[{hex_str} R]'


# ---------- 缺口报警报文生成 ----------
def generate_alarm_packet_hex(station_no, typeid):
    no_hex = func.int_to_hex(station_no)
    type_hex = func.int_to_hex(typeid)
    timestamp = get_timestamp_str()
    template = f'''
        71 6B 6E 65 74
        02
        01
        8F
        1c 00 00 00
        27
        {no_hex} 00
        {timestamp}
        05 00 FF FF
        00
        02
        {type_hex}
        00 FF
        00 FF
        00 FF
        FF FF FF FF
        00 00 00 00
        FF FF FF FF
    '''
    return func.deal_data(template)


# ---------- 转辙机油压报文生成（单条） ----------
def generate_pressure_packet_hex(station_no, direction_int, curve_type, data_num, data_min, data_max):
    zzj_no = func.int_to_hex(station_no, 4)
    zzj_no = func.str_reverse(zzj_no)
    direction_hex = func.int_to_hex(direction_int)

    curve_data = ''
    for _ in range(data_num):
        val = random.randint(data_min, data_max)
        val_hex = func.int_to_hex(val, 4)
        val_hex = func.str_reverse(val_hex)
        curve_data += val_hex

    curve_len = func.int_to_hex(data_num * 2, 4)
    curve_len_hex = func.str_reverse(curve_len)
    frame_len_int = 21 + data_num * 2
    frame_len_hex = func.int_to_hex(frame_len_int, 8)
    frame_len_hex = func.str_reverse(frame_len_hex)
    timestamp = get_timestamp_str()

    template = f'''
        71 6B 6E 65 74
        02
        01
        8F
        {frame_len_hex}
        25
        {zzj_no}
        {timestamp}
        01
        {direction_hex}
        FF FF FF FF
        01
        {curve_type}
        FF FF FF FF
        {curve_len_hex}
        {curve_data}
        FF FF FF FF
    '''
    return func.deal_data(template)


# ---------- 统一服务器 ----------
class UnifiedServer:
    def __init__(self, gui):
        self.gui = gui
        self.server_sock = None
        self.clients = []  # (conn, addr)
        self.running = False
        self.send_running = False
        self.send_thread = None

    def start(self, ip, port):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_sock.bind((ip, port))
            self.server_sock.listen(5)
            self.running = True
            self.gui.log(f'✅ 服务器已启动：{ip}:{port}')
            threading.Thread(target=self._accept_loop, daemon=True).start()
        except OSError as e:
            self.gui.log(f'❌ 启动失败：{e}')
            self.server_sock.close()
            self.server_sock = None

    def _accept_loop(self):
        while self.running:
            try:
                conn, addr = self.server_sock.accept()
                self.clients.append((conn, addr))
                self.gui.add_client_with_conn(conn, addr)
                self.gui.log(f'📶 客户端连接：{addr}')
            except OSError:
                break

    def send_data(self, repeat):
        """根据当前模式发送数据"""
        if self.send_running:
            self.gui.log('⚠️ 发送已在进行中……')
            return

        target_conn = self.gui.get_selected_client_conn()
        if not target_conn:
            self.gui.log('❌ 请先选择发送目标客户端')
            return

        mode = self.gui.mode_var.get()
        if mode == 'alarm':
            # 获取报警或恢复类型
            is_alarm = bool(self.gui.get_selected_types(is_alarm=True))
            if not is_alarm and not self.gui.get_selected_types(is_alarm=False):
                self.gui.log('❌ 未选择任何报警/恢复类型')
                return
            type_ids = self.gui.get_selected_types(is_alarm=True) if is_alarm else self.gui.get_selected_types(
                is_alarm=False)
            try:
                count = int(self.gui.count_var.get())
                if count <= 0:
                    raise ValueError
            except ValueError:
                self.gui.log('❌ 数据数量必须为正整数')
                return
            self.send_running = True
            self.send_thread = threading.Thread(target=self._alarm_send_loop,
                                                args=(count, type_ids, repeat, target_conn), daemon=True)
            self.send_thread.start()

        else:  # pressure mode
            # 读取参数
            try:
                count = int(self.gui.pressure_count_var.get())
                data_min = int(self.gui.pressure_data_min.get())
                data_max = int(self.gui.pressure_data_max.get())
                pt_min = int(self.gui.pressure_point_min.get())
                pt_max = int(self.gui.pressure_point_max.get())
                if count <= 0 or data_min > data_max or pt_min > pt_max:
                    raise ValueError
            except ValueError:
                self.gui.log('❌ 参数配置错误')
                return
            direction_mode = self.gui.pressure_dir_mode.get()
            curve_types = self.gui.get_selected_curve_types()
            if not curve_types:
                self.gui.log('❌ 未选择任何曲线类型')
                return

            self.send_running = True
            self.send_thread = threading.Thread(target=self._pressure_send_loop,
                                                args=(count, data_min, data_max, pt_min, pt_max, direction_mode,
                                                      curve_types, repeat, target_conn),
                                                daemon=True)
            self.send_thread.start()

    def _alarm_send_loop(self, count, type_ids, repeat, target_conn):
        while self.send_running:
            for station_no in range(1, count + 1):
                for typeid in type_ids:
                    hex_data = generate_alarm_packet_hex(station_no, typeid)
                    byte_data = bytes.fromhex(hex_data)
                    try:
                        target_conn.sendall(byte_data)
                        target_conn.sendall(byte_data)
                    except Exception:
                        self.gui.log('❌ 发送失败，目标客户端可能已断开')
                        self.gui.remove_client_by_conn(target_conn)
                        self.send_running = False
                        return
            if not repeat:
                break
            time.sleep(0.1)
        self.send_running = False
        self.gui.log('✅ 本轮发送完成')

    def _pressure_send_loop(self, count, data_min, data_max, pt_min, pt_max, direction_mode, curve_types, repeat,
                            target_conn):
        index = [0]
        while self.send_running:
            for i in range(count):
                station_no = i + 1
                if direction_mode == 'order':
                    direction_int = index[0] % 9
                    index[0] += 1
                else:
                    direction_int = random.randint(0, 8)

                curve_type = random.choice(curve_types)
                data_num = random.randint(pt_min, pt_max)

                hex_data = generate_pressure_packet_hex(station_no, direction_int, curve_type, data_num, data_min,
                                                        data_max)
                byte_data = bytes.fromhex(hex_data)
                try:
                    target_conn.sendall(byte_data)
                    target_conn.sendall(byte_data)  # 两条一样
                except Exception:
                    self.gui.log('❌ 发送失败，目标客户端可能已断开')
                    self.gui.remove_client_by_conn(target_conn)
                    self.send_running = False
                    return
            if not repeat:
                break
            time.sleep(0.01)
        self.send_running = False
        self.gui.log('✅ 本轮发送完成')

    def stop_send(self):
        self.send_running = False
        if self.send_thread and self.send_thread.is_alive():
            self.send_thread.join(timeout=1)

    def close(self):
        self.running = False
        self.stop_send()
        for conn, _ in self.clients:
            try:
                conn.close()
            except:
                pass
        self.clients.clear()
        if self.server_sock:
            try:
                self.server_sock.close()
            except:
                pass
            self.server_sock = None


# ---------- 主界面 ----------
class App(ttk.Window):
    def __init__(self):
        super().__init__(themename='litera')
        self.title('转辙机综合模拟器')
        self.geometry('1050x750')
        self.server = None

        # 工作模式变量
        self.mode_var = ttk.StringVar(value='alarm')
        self.local_ip = ttk.StringVar(value='192.168.0.30')
        self.local_port = ttk.IntVar(value=9999)

        # 缺口报警参数
        self.count_var = ttk.StringVar(value='20')
        self.repeat_var = ttk.BooleanVar(value=False)
        self.alarm_vars = {}
        self.recover_vars = {}
        self._mutex_lock = False

        # 转辙机油压参数
        self.pressure_count_var = ttk.StringVar(value='22')
        self.pressure_dir_mode = ttk.StringVar(value='order')
        self.pressure_curve_vars = {}
        self.pressure_data_min = ttk.StringVar(value='400')
        self.pressure_data_max = ttk.StringVar(value='1300')
        self.pressure_point_min = ttk.StringVar(value='2')
        self.pressure_point_max = ttk.StringVar(value='15')

        # 客户端管理
        self.client_dict = {}
        self.selected_client = None

        self.create_widgets()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.update_preview()

    def create_widgets(self):
        left = ttk.Frame(self, padding=5)
        left.pack(side='left', fill='both', expand=True)
        right = ttk.Frame(self, padding=5)
        right.pack(side='right', fill='both', expand=True)

        # ---------- 右侧预览和日志 ----------
        preview_frame = ttk.LabelFrame(right, text='报文预览')
        preview_frame.pack(fill='both', expand=True, pady=3)
        self.preview_text = scrolledtext.ScrolledText(preview_frame, state='normal', wrap='word')
        self.preview_text.pack(fill='both', expand=True, padx=2, pady=2)

        log_frame = ttk.LabelFrame(right, text='日志')
        log_frame.pack(fill='x', pady=3)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, state='normal', wrap='word')
        self.log_text.pack(fill='x', padx=2, pady=2)

        # ---------- 工作模式选择 ----------
        mode_frame = ttk.LabelFrame(left, text='工作模式')
        mode_frame.pack(fill='x', pady=3)
        ttk.Radiobutton(mode_frame, text='缺口报警', variable=self.mode_var,
                        value='alarm', command=self.on_mode_change).pack(side='left', padx=10, pady=5)
        ttk.Radiobutton(mode_frame, text='转辙机油压', variable=self.mode_var,
                        value='pressure', command=self.on_mode_change).pack(side='left', padx=10, pady=5)

        # ---------- 网络配置 ----------
        net_frame = ttk.LabelFrame(left, text='服务器监听设置')
        net_frame.pack(fill='x', pady=3)
        row = ttk.Frame(net_frame)
        row.pack(fill='x', pady=5, padx=5)
        ttk.Label(row, text='IP：').pack(side='left')
        ttk.Entry(row, textvariable=self.local_ip, width=15).pack(side='left', padx=5)
        ttk.Label(row, text='端口：').pack(side='left')
        ttk.Entry(row, textvariable=self.local_port, width=8).pack(side='left', padx=5)
        self.start_btn = ttk.Button(row, text='启动服务器', command=self.start_server)
        self.start_btn.pack(side='left', padx=10)
        self.stop_btn = ttk.Button(row, text='停止服务器', command=self.stop_server)
        self.stop_btn.pack(side='left')

        # ---------- 客户端选择 ----------
        client_frame = ttk.LabelFrame(left, text='目标客户端选择')
        client_frame.pack(fill='x', pady=3)
        c_row = ttk.Frame(client_frame)
        c_row.pack(fill='x', pady=5, padx=5)
        ttk.Label(c_row, text='目标：').pack(side='left')
        self.client_combo = ttk.Combobox(c_row, state='readonly', width=25)
        self.client_combo.pack(side='left', padx=5)
        self.client_combo.bind('<<ComboboxSelected>>', self.on_client_selected)

        # ---------- 发送控制框架 ----------
        self.send_frame = ttk.LabelFrame(left, text='发送控制')
        self.send_frame.pack(fill='x', pady=3)
        self.send_btn = ttk.Button(self.send_frame, text='发送报文', state='disabled', command=self.on_send)
        self.send_btn.pack(side='left', padx=5, pady=5)
        ttk.Checkbutton(self.send_frame, text='循环发送', variable=self.repeat_var).pack(side='left', padx=5)
        self.stop_send_btn = ttk.Button(self.send_frame, text='停止发送', command=self.stop_send)
        self.stop_send_btn.pack(side='left', padx=5)

        # ---------- 参数面板 ----------
        self.alarm_panel = ttk.Frame(left)
        self.pressure_panel = ttk.Frame(left)
        self.create_alarm_panel()
        self.create_pressure_panel()
        self.on_mode_change()

    def create_alarm_panel(self):
        count_frame = ttk.Frame(self.alarm_panel)
        count_frame.pack(fill='x', pady=3)
        ttk.Label(count_frame, text='转辙机数量：').pack(side='left')
        ttk.Entry(count_frame, textvariable=self.count_var, width=6).pack(side='left', padx=5)
        ttk.Label(count_frame, text='（1~N）').pack(side='left')
        self.count_var.trace_add('write', lambda *a: self.update_preview())

        alarm_grp = ttk.LabelFrame(self.alarm_panel, text='报警类型（可多选）')
        alarm_grp.pack(fill='x', pady=3)
        check_frame = ttk.Frame(alarm_grp)
        check_frame.pack(fill='both', expand=True, padx=5, pady=5)
        for i in range(10):
            tid = i + 1
            var = ttk.BooleanVar(value=False)
            self.alarm_vars[tid] = var
            cb = ttk.Checkbutton(check_frame, text=ALARM_TYPES[tid], variable=var,
                                 command=lambda t='alarm': self.on_alarm_check(t))
            cb.grid(row=i // 2, column=i % 2, sticky='w', padx=5, pady=2)
        ctrl = ttk.Frame(alarm_grp)
        ctrl.pack(fill='x', padx=5, pady=2)
        ttk.Button(ctrl, text='全选', command=lambda: self.set_all_alarm_types(True)).pack(side='left', padx=5)
        ttk.Button(ctrl, text='取消全选', command=lambda: self.set_all_alarm_types(False)).pack(side='left', padx=5)

        recover_grp = ttk.LabelFrame(self.alarm_panel, text='恢复类型（可多选）')
        recover_grp.pack(fill='x', pady=3)
        check_frame2 = ttk.Frame(recover_grp)
        check_frame2.pack(fill='both', expand=True, padx=5, pady=5)
        for i in range(10):
            tid = 101 + i
            var = ttk.BooleanVar(value=False)
            self.recover_vars[tid] = var
            cb = ttk.Checkbutton(check_frame2, text=RECOVER_TYPES[tid], variable=var,
                                 command=lambda t='recover': self.on_alarm_check(t))
            cb.grid(row=i // 2, column=i % 2, sticky='w', padx=5, pady=2)
        ctrl2 = ttk.Frame(recover_grp)
        ctrl2.pack(fill='x', padx=5, pady=2)
        ttk.Button(ctrl2, text='全选', command=lambda: self.set_all_recover_types(True)).pack(side='left', padx=5)
        ttk.Button(ctrl2, text='取消全选', command=lambda: self.set_all_recover_types(False)).pack(side='left', padx=5)

    def create_pressure_panel(self):
        count_frame = ttk.Frame(self.pressure_panel)
        count_frame.pack(fill='x', pady=3, padx=5)
        ttk.Label(count_frame, text='转辙机数量：').pack(side='left')
        ttk.Entry(count_frame, textvariable=self.pressure_count_var, width=6).pack(side='left', padx=5)
        ttk.Label(count_frame, text='（1~N）').pack(side='left')
        self.pressure_count_var.trace_add('write', lambda *a: self.update_preview())

        dir_frame = ttk.Frame(self.pressure_panel)
        dir_frame.pack(fill='x', pady=3, padx=5)
        ttk.Label(dir_frame, text='方向生成：').pack(side='left')
        ttk.Radiobutton(dir_frame, text='顺序循环', variable=self.pressure_dir_mode, value='order').pack(side='left',
                                                                                                         padx=5)
        ttk.Radiobutton(dir_frame, text='随机', variable=self.pressure_dir_mode, value='random').pack(side='left',
                                                                                                      padx=5)

        curve_frame = ttk.LabelFrame(self.pressure_panel, text='曲线类型（可多选）')
        curve_frame.pack(fill='x', pady=3)
        curve_check = ttk.Frame(curve_frame)
        curve_check.pack(fill='x', padx=5, pady=5)
        types = {'00': '左油压', '01': '右油压', '02': '启动电流'}
        for k, v in types.items():
            var = ttk.BooleanVar(value=(k == '00'))
            self.pressure_curve_vars[k] = var
            ttk.Checkbutton(curve_check, text=v, variable=var, command=self.update_preview).pack(side='left', padx=5)

        pt_frame = ttk.Frame(self.pressure_panel)
        pt_frame.pack(fill='x', pady=3, padx=5)
        ttk.Label(pt_frame, text='数据点数范围：').pack(side='left')
        ttk.Entry(pt_frame, textvariable=self.pressure_point_min, width=4).pack(side='left')
        ttk.Label(pt_frame, text=' ~ ').pack(side='left')
        ttk.Entry(pt_frame, textvariable=self.pressure_point_max, width=4).pack(side='left')

        val_frame = ttk.Frame(self.pressure_panel)
        val_frame.pack(fill='x', pady=3, padx=5)
        ttk.Label(val_frame, text='数值范围：').pack(side='left')
        ttk.Entry(val_frame, textvariable=self.pressure_data_min, width=5).pack(side='left')
        ttk.Label(val_frame, text=' ~ ').pack(side='left')
        ttk.Entry(val_frame, textvariable=self.pressure_data_max, width=5).pack(side='left')

    # ---------- 按钮状态统一管理 ----------
    def update_send_button_state(self):
        """根据当前模式、服务器状态和客户端选择更新按钮状态"""
        if not self.server or not self.server.running or not self.selected_client:
            self.send_btn.configure(state='disabled', text='发送报文')
        else:
            self.send_btn.configure(state='normal', text='发送报文')

    # ---------- 客户端管理方法 ----------
    def add_client_with_conn(self, conn, addr):
        key = f"{addr[0]}:{addr[1]}"
        self.client_dict[key] = (conn, addr)
        current_values = list(self.client_combo['values'])
        if key not in current_values:
            current_values.append(key)
            self.client_combo['values'] = current_values
            if not self.selected_client:
                self.client_combo.current(0)
                self.on_client_selected()
        self.update_send_button_state()

    def remove_client_by_addr(self, addr):
        key = f"{addr[0]}:{addr[1]}"
        if key in self.client_dict:
            del self.client_dict[key]
            current_values = list(self.client_combo['values'])
            if key in current_values:
                current_values.remove(key)
                self.client_combo['values'] = current_values
                if self.selected_client and self.selected_client[1] == addr:
                    self.selected_client = None
                    self.client_combo.set('')
                    self.log('⚠️ 选中的客户端已断开，请重新选择')
        self.update_send_button_state()

    def remove_client_by_conn(self, conn):
        for key, (c, addr) in list(self.client_dict.items()):
            if c == conn:
                self.remove_client_by_addr(addr)
                break

    def on_client_selected(self, event=None):
        key = self.client_combo.get()
        if key in self.client_dict:
            self.selected_client = self.client_dict[key]
            self.log(f'已选择目标客户端：{key}')
        else:
            self.selected_client = None
            self.client_combo.set('')
            self.log('❌ 无效的客户端选择')
        self.update_send_button_state()

    def get_selected_client_conn(self):
        if self.selected_client:
            return self.selected_client[0]
        return None

    # ---------- 模式切换 ----------
    def on_mode_change(self):
        self.alarm_panel.pack_forget()
        self.pressure_panel.pack_forget()
        if self.mode_var.get() == 'alarm':
            self.alarm_panel.pack(fill='x', pady=5, before=self.send_frame)
        else:
            self.pressure_panel.pack(fill='x', pady=5, before=self.send_frame)
        self.update_send_button_state()
        self.update_preview()

    def on_alarm_check(self, changed_type):
        if self._mutex_lock:
            return
        self._mutex_lock = True
        try:
            if changed_type == 'alarm':
                for var in self.recover_vars.values():
                    var.set(False)
            else:
                for var in self.alarm_vars.values():
                    var.set(False)
        finally:
            self._mutex_lock = False
        self.update_preview()

    def set_all_alarm_types(self, value):
        if self._mutex_lock:
            return
        self._mutex_lock = True
        try:
            for var in self.alarm_vars.values():
                var.set(value)
            if value:
                for var in self.recover_vars.values():
                    var.set(False)
        finally:
            self._mutex_lock = False
        self.update_preview()

    def set_all_recover_types(self, value):
        if self._mutex_lock:
            return
        self._mutex_lock = True
        try:
            for var in self.recover_vars.values():
                var.set(value)
            if value:
                for var in self.alarm_vars.values():
                    var.set(False)
        finally:
            self._mutex_lock = False
        self.update_preview()

    def get_selected_types(self, is_alarm):
        target = self.alarm_vars if is_alarm else self.recover_vars
        return [tid for tid, var in target.items() if var.get()]

    def get_selected_curve_types(self):
        return [k for k, var in self.pressure_curve_vars.items() if var.get()]

    # ---------- 服务器控制 ----------
    def start_server(self):
        ip = self.local_ip.get().strip()
        try:
            port = int(self.local_port.get())
        except ValueError:
            self.log('❌ 端口必须是整数')
            return
        if self.server and self.server.running:
            self.log('⚠️ 服务器已在运行')
            return
        self.server = UnifiedServer(self)
        self.server.start(ip, port)
        self.update_send_button_state()

    def stop_server(self):
        if self.server:
            self.server.close()
            self.server = None
        self.client_dict.clear()
        self.client_combo['values'] = []
        self.client_combo.set('')
        self.selected_client = None
        self.log('🛑 服务器已停止')
        self.update_send_button_state()

    def stop_send(self):
        if self.server:
            self.server.stop_send()

    def on_send(self):
        if not self.server or not self.server.running:
            self.log('❌ 服务器未启动')
            return
        # 统一入口，服务器内部判断模式
        self.server.send_data(self.repeat_var.get())

    # ---------- 预览 ----------
    def generate_alarm_preview_hex(self, station_no, typeid):
        no_hex = func.int_to_hex(station_no)
        type_hex = func.int_to_hex(typeid)
        timestamp = get_timestamp_str()
        template = f'''
            71 6B 6E 65 74
            02
            01
            8F
            1c 00 00 00
            27
            {no_hex} 00
            {timestamp}
            05 00 FF FF
            00
            02
            {type_hex}
            00 FF
            00 FF
            00 FF
            FF FF FF FF
            00 00 00 00
            FF FF FF FF
        '''
        raw = re.sub(r'#.*', '', template)
        raw = ' '.join(raw.split()).upper()
        return raw

    def generate_pressure_preview_hex(self):
        # 示例一条报文
        hex_data = generate_pressure_packet_hex(1, 0, '00', 2, 400, 1300)
        return hex_data

    def update_preview(self):
        self.preview_text.config(state='normal')
        self.preview_text.delete(1.0, END)
        mode = self.mode_var.get()
        if mode == 'alarm':
            try:
                count = int(self.count_var.get())
            except ValueError:
                count = 0
            alarm_ids = self.get_selected_types(is_alarm=True)
            recover_ids = self.get_selected_types(is_alarm=False)
            packets = []
            if alarm_ids:
                for sid in alarm_ids:
                    for no in range(1, count + 1):
                        packets.append(self.generate_alarm_preview_hex(no, sid))
            elif recover_ids:
                for sid in recover_ids:
                    for no in range(1, count + 1):
                        packets.append(self.generate_alarm_preview_hex(no, sid))
            content = '\n<br>\n'.join(packets) if packets else '请选择报警/恢复类型并设置数量'
        else:
            content = self.generate_pressure_preview_hex() + '\n（仅示例，实际发送时曲线数据随机生成）'
        self.preview_text.insert(END, content)
        self.preview_text.config(state='disabled')

    def log(self, msg):
        self.log_text.insert('end', f'{msg}\n')
        self.log_text.see('end')
        print(msg)

    def on_closing(self):
        if self.server:
            self.server.close()
        self.destroy()


if __name__ == '__main__':
    app = App()
    app.mainloop()