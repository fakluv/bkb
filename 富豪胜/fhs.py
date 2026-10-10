import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
import socket
import time
import threading
from datetime import datetime

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("DIAG 报文批量发送与生成工具")
        self.root.geometry("750x700")
        self.root.resizable(True, True)

        # ---------- 连接设置 ----------
        frame_conn = tk.LabelFrame(root, text="服务器连接", padx=10, pady=10)
        frame_conn.pack(fill="x", padx=10, pady=5)

        tk.Label(frame_conn, text="IP 地址:").grid(row=0, column=0, sticky="w")
        self.ip_entry = tk.Entry(frame_conn, width=20)
        self.ip_entry.insert(0, "127.0.0.1")
        self.ip_entry.grid(row=0, column=1, padx=5)

        tk.Label(frame_conn, text="端口:").grid(row=0, column=2, sticky="w")
        self.port_entry = tk.Entry(frame_conn, width=8)
        self.port_entry.insert(0, "8080")
        self.port_entry.grid(row=0, column=3, padx=5)

        # ---------- 报文输入 ----------
        frame_msg = tk.LabelFrame(root, text="报文内容（多个报文用 ------ 分隔）", padx=10, pady=10)
        frame_msg.pack(fill="both", expand=True, padx=10, pady=5)

        self.msg_text = scrolledtext.ScrolledText(frame_msg, wrap=tk.WORD, height=12)
        self.msg_text.pack(fill="both", expand=True)
        self.msg_text.insert(tk.END, "在此粘贴或生成 DIAG 报文...\n多个报文用 ------ 分隔")

        # ---------- 控制按钮 ----------
        frame_btn = tk.Frame(root)
        frame_btn.pack(fill="x", padx=10, pady=5)

        self.send_btn = tk.Button(frame_btn, text="🚀 批量发送", command=self.start_send,
                                  bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        self.send_btn.pack(side="left", padx=5)

        self.gen_btn = tk.Button(frame_btn, text="📝 生成报文", command=self.open_generator,
                                 bg="#2196F3", fg="white", font=("Arial", 10, "bold"))
        self.gen_btn.pack(side="left", padx=5)

        self.clear_btn = tk.Button(frame_btn, text="🧹 清空日志", command=self.clear_log)
        self.clear_btn.pack(side="left", padx=5)

        # ---------- 日志输出 ----------
        frame_log = tk.LabelFrame(root, text="发送日志", padx=10, pady=10)
        frame_log.pack(fill="both", expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(frame_log, wrap=tk.WORD, state="disabled", height=8)
        self.log_text.pack(fill="both", expand=True)

        self.worker_thread = None

    # ==================== 日志方法 ====================
    def log(self, message):
        self.root.after(0, self._append_log, message)

    def _append_log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state="disabled")

    # ==================== 发送逻辑 ====================
    def start_send(self):
        ip = self.ip_entry.get().strip()
        port_str = self.port_entry.get().strip()

        if not ip:
            messagebox.showwarning("输入错误", "请输入服务器 IP 地址")
            return
        try:
            port = int(port_str)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showwarning("输入错误", "端口号必须为 1~65535 的整数")
            return

        raw = self.msg_text.get("1.0", tk.END)
        messages = [msg.strip() for msg in raw.split("------") if msg.strip()]

        if not messages:
            messagebox.showwarning("无报文", "未检测到有效报文（请确保报文间使用 ------ 分隔）")
            return

        self.send_btn.config(state="disabled", text="发送中...")
        self.log(f"⏳ 正在连接 {ip}:{port}，共 {len(messages)} 条报文...")

        self.worker_thread = threading.Thread(target=self.send_messages,
                                              args=(ip, port, messages), daemon=True)
        self.worker_thread.start()

    def send_messages(self, ip, port, messages):
        total = len(messages)
        success = 0
        for idx, msg in enumerate(messages, 1):
            try:
                start = time.time()
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(5)
                    sock.connect((ip, port))
                    sock.sendall(msg.encode("utf-8") + b"\n")
                elapsed = (time.time() - start) * 1000
                preview = msg[:50].replace("\n", " ")
                self.log(f"✅ [{idx}/{total}] 成功 ({elapsed:.1f}ms) - {preview}...")
                success += 1
            except socket.timeout:
                self.log(f"⏱️ [{idx}/{total}] 连接超时")
            except ConnectionRefusedError:
                self.log(f"🚫 [{idx}/{total}] 连接被拒绝，请检查服务器是否启动")
            except Exception as e:
                self.log(f"❌ [{idx}/{total}] 发送失败: {e}")

        self.log(f"\n📊 发送完成：成功 {success}/{total}")
        self.root.after(0, self.on_send_finished)

    def on_send_finished(self):
        self.send_btn.config(state="normal", text="🚀 批量发送")

    # ==================== 报文生成窗口 ====================
    def open_generator(self):
        """打开报文生成对话框"""
        gen_win = tk.Toplevel(self.root)
        gen_win.title("报文生成器")
        gen_win.geometry("500x550")
        gen_win.resizable(False, False)
        gen_win.grab_set()  # 模态

        # 类型选择
        type_frame = tk.LabelFrame(gen_win, text="报文类型", padx=10, pady=10)
        type_frame.pack(fill="x", padx=10, pady=5)
        self.gen_type = tk.StringVar(value="TRACKSECTION")
        tk.Radiobutton(type_frame, text="TRACKSECTION (轨道区段)", variable=self.gen_type,
                       value="TRACKSECTION", command=self.on_type_change).pack(anchor="w")
        tk.Radiobutton(type_frame, text="COUNTINGHEAD (计数磁头)", variable=self.gen_type,
                       value="COUNTINGHEAD", command=self.on_type_change).pack(anchor="w")

        # 公共参数
        common_frame = tk.LabelFrame(gen_win, text="公共参数", padx=10, pady=10)
        common_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(common_frame, text="起始序号:").grid(row=0, column=0, sticky="e")
        self.seq_start = tk.Entry(common_frame, width=8)
        self.seq_start.insert(0, "1")
        self.seq_start.grid(row=0, column=1, sticky="w")

        tk.Label(common_frame, text="元素域 (domain):").grid(row=1, column=0, sticky="e", pady=5)
        self.domain_entry = tk.Entry(common_frame, width=30)
        self.domain_entry.insert(0, "Train station Linz")
        self.domain_entry.grid(row=1, column=1, sticky="w", pady=5)

        tk.Label(common_frame, text="状态 (status):").grid(row=2, column=0, sticky="e")
        self.status_combo = ttk.Combobox(common_frame, values=["ok", "error"], width=8)
        self.status_combo.current(0)
        self.status_combo.grid(row=2, column=1, sticky="w")

        # 时间选项
        self.auto_raise = tk.BooleanVar(value=True)
        tk.Checkbutton(common_frame, text="raiseTime 自动 (当前时间)", variable=self.auto_raise,
                       command=self.toggle_raise_time).grid(row=3, column=0, columnspan=2, sticky="w", pady=2)
        self.raise_time_entry = tk.Entry(common_frame, width=25)
        self.raise_time_entry.grid(row=4, column=1, sticky="w")
        self.raise_time_entry.config(state="disabled")

        self.auto_send = tk.BooleanVar(value=True)
        tk.Checkbutton(common_frame, text="sendTime 自动 (当前时间)", variable=self.auto_send,
                       command=self.toggle_send_time).grid(row=5, column=0, columnspan=2, sticky="w", pady=2)
        self.send_time_entry = tk.Entry(common_frame, width=25)
        self.send_time_entry.grid(row=6, column=1, sticky="w")
        self.send_time_entry.config(state="disabled")

        # 类型专属参数（动态切换）
        self.specific_frame = tk.LabelFrame(gen_win, text="专属参数", padx=10, pady=10)
        self.specific_frame.pack(fill="x", padx=10, pady=5)

        # TRACKSECTION 专属
        self.track_frame = tk.Frame(self.specific_frame)
        tk.Label(self.track_frame, text="轨道状态 (value):").pack(side="left")
        self.track_value = ttk.Combobox(self.track_frame, values=["cleard", "occupied"], width=12)
        self.track_value.current(0)
        self.track_value.pack(side="left", padx=5)

        # COUNTINGHEAD 专属
        self.count_frame = tk.Frame(self.specific_frame)
        tk.Label(self.count_frame, text="计数磁头状态:").grid(row=0, column=0, sticky="e")
        self.chead_value = ttk.Combobox(self.count_frame, values=["activated", "deactivated", "error"], width=12)
        self.chead_value.current(0)
        self.chead_value.grid(row=0, column=1, padx=5)

        tk.Label(self.count_frame, text="车轮传感器系统:").grid(row=1, column=0, sticky="e", pady=5)
        self.ws_value = tk.Entry(self.count_frame, width=12)
        self.ws_value.insert(0, "1")
        self.ws_value.grid(row=1, column=1, padx=5, pady=5)

        # 默认显示 TRACKSECTION
        self.track_frame.pack()
        self.count_frame.pack_forget()

        # 元素名称列表（批量核心）
        name_frame = tk.LabelFrame(gen_win, text="元素名称列表（每行一个，将生成多条报文）", padx=10, pady=10)
        name_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.name_list = scrolledtext.ScrolledText(name_frame, height=6, wrap=tk.WORD)
        self.name_list.pack(fill="both", expand=True)
        self.name_list.insert(tk.END, "G2405\nG2403\nG2401")  # 示例

        # 按钮
        btn_frame = tk.Frame(gen_win)
        btn_frame.pack(fill="x", padx=10, pady=10)
        tk.Button(btn_frame, text="生成并添加到发送区", bg="#4CAF50", fg="white",
                  command=lambda: self.generate_messages(gen_win)).pack(side="left", padx=5)
        tk.Button(btn_frame, text="取消", command=gen_win.destroy).pack(side="right", padx=5)

    def on_type_change(self):
        """根据类型切换专属参数面板"""
        if self.gen_type.get() == "TRACKSECTION":
            self.count_frame.pack_forget()
            self.track_frame.pack()
        else:
            self.track_frame.pack_forget()
            self.count_frame.pack()

    def toggle_raise_time(self):
        if self.auto_raise.get():
            self.raise_time_entry.config(state="disabled")
        else:
            self.raise_time_entry.config(state="normal")

    def toggle_send_time(self):
        if self.auto_send.get():
            self.send_time_entry.config(state="disabled")
        else:
            self.send_time_entry.config(state="normal")

    def current_timestamp(self):
        """返回当前时间字符串，精确到毫秒"""
        now = datetime.now()
        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}"

    def generate_messages(self, gen_win):
        """生成报文并添加到主窗口输入区"""
        # 读取名称列表
        names = self.name_list.get("1.0", tk.END).strip().splitlines()
        names = [n.strip() for n in names if n.strip()]
        if not names:
            messagebox.showwarning("缺少名称", "请至少输入一个元素名称！", parent=gen_win)
            return

        # 读取公共参数
        try:
            seq = int(self.seq_start.get().strip())
        except ValueError:
            messagebox.showerror("参数错误", "起始序号必须为整数", parent=gen_win)
            return

        domain = self.domain_entry.get().strip()
        status = self.status_combo.get()

        # 时间处理
        if self.auto_raise.get():
            raise_time_func = lambda: self.current_timestamp()
        else:
            fixed_raise = self.raise_time_entry.get().strip()
            if not fixed_raise:
                messagebox.showerror("参数错误", "请输入 raiseTime", parent=gen_win)
                return
            raise_time_func = lambda: fixed_raise

        if self.auto_send.get():
            send_time_func = lambda: self.current_timestamp()
        else:
            fixed_send = self.send_time_entry.get().strip()
            if not fixed_send:
                messagebox.showerror("参数错误", "请输入 sendTime", parent=gen_win)
                return
            send_time_func = lambda: fixed_send

        msg_type = self.gen_type.get()
        messages = []

        for i, name in enumerate(names):
            seq_now = seq + i
            raise_t = raise_time_func()
            send_t = send_time_func()

            if msg_type == "TRACKSECTION":
                value = self.track_value.get()
                xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<DIAG_Meldung>
  <DIAG_Meldung_Event>
    <sequenceNumber>{seq_now}</sequenceNumber>
    <elementName>{name}</elementName>
    <elementType>TRACKSECTION</elementType>
    <elementDomain>{domain}</elementDomain>
    <elementStatus>{status}</elementStatus>
    <raiseTime>{raise_t}</raiseTime>
    <sendTime>{send_t}</sendTime>
    <keyValue>
      <key>Tracksection</key>
      <value>{value}</value>
    </keyValue>
  </DIAG_Meldung_Event>
</DIAG_Meldung>'''
            else:  # COUNTINGHEAD
                chead = self.chead_value.get()
                ws = self.ws_value.get().strip()
                if not ws.isdigit():
                    messagebox.showerror("参数错误", "车轮传感器系统必须为数字", parent=gen_win)
                    return
                xml = f'''<DIAG_Meldung>
  <DIAG_Meldung_Event>
    <sequenceNumber>{seq_now}</sequenceNumber>
    <elementName>{name}</elementName>
    <elementType>COUNTINGHEAD</elementType>
    <elementDomain>{domain}</elementDomain>
    <elementStatus>{status}</elementStatus>
    <raiseTime>{raise_t}</raiseTime>
    <sendTime>{send_t}</sendTime>
    <keyValue>
      <key>countingHead</key>
      <value>{chead}</value>
    </keyValue>
    <keyValue>
      <key>wheelsensorSystem</key>
      <value>{ws}</value>
    </keyValue>
  </DIAG_Meldung_Event>
</DIAG_Meldung>'''
            messages.append(xml.strip())

        # 追加到主输入框
        separator = "\n------\n"
        full_text = separator.join(messages)
        current = self.msg_text.get("1.0", tk.END).rstrip()
        if current and not current.endswith("\n"):
            current += "\n"
        self.msg_text.delete("1.0", tk.END)
        self.msg_text.insert(tk.END, current + full_text + "\n")

        # 自动滚动到底部
        self.msg_text.see(tk.END)

        self.log(f"✅ 已生成 {len(messages)} 条报文并添加到发送区")
        gen_win.destroy()
        messagebox.showinfo("生成成功", f"成功生成 {len(messages)} 条报文！\n请查看下方“报文内容”文本框末尾。")

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()