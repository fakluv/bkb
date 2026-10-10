import struct
import time
import random
import socket
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk

# ================== 核心协议生成函数 ==================
def generate_vibration_frame(switch_id, timestamp, freq, vib_type, direction, curves):
    """
    生成单个道岔扳动/过车振动曲线信息帧（协议 3.3.2.2.13）
    curves: list of (curve_type, point_count) 或 (curve_type, [占位列表])
    """
    data = bytearray()
    data.append(0x71)
    data.extend(struct.pack('<H', switch_id))
    data.extend(struct.pack('<I', timestamp))
    data.append(freq & 0xFF)
    data.append(vib_type & 0xFF)
    data.append(direction & 0xFF)
    data.extend(b'\xFF\xFF\xFF\xFF')
    data.append(len(curves) & 0xFF)

    for ctype, points in curves:
        data.append(ctype & 0xFF)
        data.extend(b'\xFF\xFF\xFF\xFF')
        raw = bytearray()
        for _ in range(len(points)):
            int_val = random.randint(-19, 19)
            raw.extend(struct.pack('<h', int_val))
        data.extend(struct.pack('<H', len(raw)))
        data.extend(raw)

    data_len = len(data)
    frame = bytearray()
    frame.extend(b'qknet')
    frame.append(0x02)
    frame.append(0x01)
    frame.append(0x8F)
    frame.extend(struct.pack('<I', data_len))
    frame.extend(data)
    frame.extend(b'\xFF\xFF\xFF\xFF')
    return bytes(frame)

# ================== GUI 主类 ==================
class VibrationServerGUI:
    def __init__(self, root):
        self.root = root
        root.title("道岔振动数据服务器")
        root.geometry("700x650")

        # 控制变量
        self.server_running = False
        self.server_thread = None
        self.tcp_server = None
        self.clients = []          # 当前连接的客户端socket列表
        self.stop_event = threading.Event()

        # ---------- 参数配置区域 ----------
        frame_config = ttk.LabelFrame(root, text="参数配置", padding=10)
        frame_config.pack(fill="x", padx=10, pady=5)

        # 第一行：转辙机数量 & 起始编号
        row1 = ttk.Frame(frame_config)
        row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="转辙机数量:").pack(side="left")
        self.num_switches = tk.IntVar(value=28)
        ttk.Spinbox(row1, from_=1, to=100, textvariable=self.num_switches, width=6).pack(side="left", padx=5)

        ttk.Label(row1, text="起始编号 (16进制):").pack(side="left", padx=(15,0))
        self.base_id = tk.StringVar(value="0x0001")
        ttk.Entry(row1, textvariable=self.base_id, width=8).pack(side="left", padx=5)

        # 第二行：采集频率 & 振动类型
        row2 = ttk.Frame(frame_config)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="采集频率 (0x):").pack(side="left")
        self.freq = tk.StringVar(value="0x0A")
        ttk.Entry(row2, textvariable=self.freq, width=6).pack(side="left", padx=5)

        ttk.Label(row2, text="振动类型:").pack(side="left", padx=(15,0))
        self.vib_type = tk.IntVar(value=1)
        ttk.Combobox(row2, textvariable=self.vib_type, values=[1, 2], state="readonly", width=6).pack(side="left", padx=5)

        # 第三行：方向
        row3 = ttk.Frame(frame_config)
        row3.pack(fill="x", pady=2)
        ttk.Label(row3, text="方向 (扳动:0定反/1反定/2定定/3反反/..., 过车:0定位/1反位):").pack(side="left")
        self.direction = tk.IntVar(value=0)
        ttk.Spinbox(row3, from_=0, to=8, textvariable=self.direction, width=4).pack(side="left", padx=5)

        # 第四行：每条曲线点数 & 启用轴
        row4 = ttk.Frame(frame_config)
        row4.pack(fill="x", pady=2)
        ttk.Label(row4, text="每条曲线点数:").pack(side="left")
        self.points = tk.IntVar(value=20)
        ttk.Spinbox(row4, from_=1, to=500, textvariable=self.points, width=6).pack(side="left", padx=5)

        ttk.Label(row4, text="启用轴:").pack(side="left", padx=(15,0))
        self.enable_x = tk.BooleanVar(value=True)
        ttk.Checkbutton(row4, text="X", variable=self.enable_x).pack(side="left")
        self.enable_y = tk.BooleanVar(value=True)
        ttk.Checkbutton(row4, text="Y", variable=self.enable_y).pack(side="left")
        self.enable_z = tk.BooleanVar(value=True)
        ttk.Checkbutton(row4, text="Z", variable=self.enable_z).pack(side="left")

        # 第五行：监听IP和端口
        row5 = ttk.Frame(frame_config)
        row5.pack(fill="x", pady=2)
        ttk.Label(row5, text="监听IP:").pack(side="left")
        self.host = tk.StringVar(value="192.168.2.132")
        ttk.Entry(row5, textvariable=self.host, width=14).pack(side="left", padx=5)
        ttk.Label(row5, text="端口:").pack(side="left", padx=(15,0))
        self.port = tk.IntVar(value=9999)
        ttk.Spinbox(row5, from_=1024, to=65535, textvariable=self.port, width=6).pack(side="left", padx=5)

        # 按钮
        btn_frame = ttk.Frame(frame_config)
        btn_frame.pack(fill="x", pady=8)
        self.start_btn = ttk.Button(btn_frame, text="启动服务器", command=self.start_server)
        self.start_btn.pack(side="left", padx=5)
        self.stop_btn = ttk.Button(btn_frame, text="停止服务器", command=self.stop_server, state="disabled")
        self.stop_btn.pack(side="left", padx=5)

        # ---------- 日志显示 ----------
        log_frame = ttk.LabelFrame(root, text="日志输出", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=18, state='normal')
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("info", foreground="blue")

        # 退出时清理
        root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def log(self, msg, tag=None):
        self.log_text.insert(tk.END, msg + "\n", tag)
        self.log_text.see(tk.END)

    # ---------- 服务器线程函数 ----------
    def server_loop(self, host, port, params):
        """在独立线程中运行TCP服务器，持续监听直到stop_event被设置"""
        self.tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.tcp_server.bind((host, port))
            self.tcp_server.listen(5)
            self.tcp_server.settimeout(1.0)   # 超时以便检查stop_event
            self.log(f"服务器启动，监听 {host}:{port}")
            self.root.after(0, lambda: self.start_btn.config(state="disabled"))
            self.root.after(0, lambda: self.stop_btn.config(state="normal"))

            while not self.stop_event.is_set():
                try:
                    conn, addr = self.tcp_server.accept()
                    self.clients.append(conn)
                    self.log(f"客户端 {addr} 已连接")
                    # 启动一个处理客户端发送数据的线程
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(conn, addr, params),
                        daemon=True
                    )
                    client_thread.start()
                except socket.timeout:
                    continue
                except OSError:
                    break

        except Exception as e:
            self.log(f"服务器错误: {e}", "error")
        finally:
            # 清理
            self.stop_server()
            self.log("服务器线程已结束")

    def handle_client(self, conn, addr, params):
        """处理单个客户端：循环发送帧直到客户端断开或stop_event被设置"""
        try:
            while not self.stop_event.is_set():
                # 构造参数
                timestamp = int(time.time())
                curves = []
                if params['ENABLE_X']:
                    curves.append((0x00, [0] * params['POINTS_PER_CURVE']))
                if params['ENABLE_Y']:
                    curves.append((0x01, [0] * params['POINTS_PER_CURVE']))
                if params['ENABLE_Z']:
                    curves.append((0x02, [0] * params['POINTS_PER_CURVE']))
                if not curves:
                    curves.append((0x00, [0] * params['POINTS_PER_CURVE']))

                # 生成所有转辙机的帧
                all_frames = bytearray()
                for idx in range(params['NUM_SWITCHES']):
                    switch_id = params['BASE_SWITCH_ID'] + idx
                    frame = generate_vibration_frame(
                        switch_id, timestamp,
                        params['FREQ'], params['VIB_TYPE'], params['DIRECTION'],
                        curves
                    )
                    all_frames.extend(frame)

                conn.sendall(all_frames)
                self.log(f"向 {addr} 发送 {len(all_frames)} 字节，时间戳: {timestamp}")

                time.sleep(1)
        except (BrokenPipeError, ConnectionResetError):
            self.log(f"客户端 {addr} 已断开")
        except Exception as e:
            self.log(f"客户端处理异常: {e}", "error")
        finally:
            if conn in self.clients:
                self.clients.remove(conn)
            conn.close()

    # ---------- 启动/停止 ----------
    def start_server(self):
        if self.server_running:
            return
        # 读取参数
        try:
            num = self.num_switches.get()
            base = int(self.base_id.get(), 16) if self.base_id.get().startswith("0x") else int(self.base_id.get())
            freq = int(self.freq.get(), 16) if self.freq.get().startswith("0x") else int(self.freq.get())
            vib = self.vib_type.get()
            dir_val = self.direction.get()
            pts = self.points.get()
            x = self.enable_x.get()
            y = self.enable_y.get()
            z = self.enable_z.get()
            host = self.host.get().strip()
            port = self.port.get()
        except Exception as e:
            self.log(f"参数解析错误: {e}", "error")
            return

        params = {
            'NUM_SWITCHES': num,
            'BASE_SWITCH_ID': base,
            'FREQ': freq,
            'VIB_TYPE': vib,
            'DIRECTION': dir_val,
            'POINTS_PER_CURVE': pts,
            'ENABLE_X': x,
            'ENABLE_Y': y,
            'ENABLE_Z': z,
        }
        self.log(f"启动参数: {params}")

        self.server_running = True
        self.stop_event.clear()
        self.server_thread = threading.Thread(
            target=self.server_loop,
            args=(host, port, params),
            daemon=True
        )
        self.server_thread.start()

    def stop_server(self):
        self.stop_event.set()
        self.server_running = False
        # 关闭服务器socket
        if self.tcp_server:
            try:
                self.tcp_server.close()
            except:
                pass
            self.tcp_server = None
        # 关闭所有客户端连接
        for conn in self.clients[:]:
            try:
                conn.close()
            except:
                pass
        self.clients.clear()
        self.log("服务器已停止")
        self.root.after(0, lambda: self.start_btn.config(state="normal"))
        self.root.after(0, lambda: self.stop_btn.config(state="disabled"))

    def on_closing(self):
        self.stop_server()
        self.root.destroy()


# ================== 启动GUI ==================
if __name__ == "__main__":
    root = tk.Tk()
    app = VibrationServerGUI(root)
    root.mainloop()