import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import subprocess
import threading
import queue
import sys
import os

# ---------- 验证函数（复用原脚本逻辑） ----------
def validate_ip_part(ip_part):
    try:
        ip_part = int(ip_part)
        return 0 <= ip_part <= 255
    except ValueError:
        return False

def validate_ip_prefix(ip_prefix):
    parts = ip_prefix.split('.')
    if len(parts) != 3:
        return False
    return all(validate_ip_part(part) for part in parts)

def validate_subnet_mask(mask):
    parts = mask.split('.')
    if len(parts) != 4:
        return False
    if not all(validate_ip_part(part) for part in parts):
        return False
    binary = ''.join(f'{int(part):08b}' for part in parts)
    if '01' in binary:
        return False
    return True

# ---------- 主 GUI 类 ----------
class IPManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("IP 地址批量管理工具")
        self.root.geometry("650x550")
        self.root.resizable(False, False)

        # 队列用于线程间通信
        self.msg_queue = queue.Queue()

        # 创建界面
        self.create_widgets()

        # 定期检查队列更新日志
        self.root.after(100, self.process_queue)

    def create_widgets(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 网卡名称
        ttk.Label(main_frame, text="网卡名称:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.entry_name = ttk.Entry(main_frame, width=40)
        self.entry_name.grid(row=0, column=1, sticky=tk.W, pady=5)

        # IP 前缀
        ttk.Label(main_frame, text="IP 前缀 (前三段):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.entry_prefix = ttk.Entry(main_frame, width=40)
        self.entry_prefix.grid(row=1, column=1, sticky=tk.W, pady=5)
        self.entry_prefix.insert(0, "192.168.1")

        # 起始 IP 第四位
        ttk.Label(main_frame, text="起始 IP 第四位:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.entry_start = ttk.Entry(main_frame, width=40)
        self.entry_start.grid(row=2, column=1, sticky=tk.W, pady=5)
        self.entry_start.insert(0, "1")

        # IP 数量
        ttk.Label(main_frame, text="IP 数量:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.entry_count = ttk.Entry(main_frame, width=40)
        self.entry_count.grid(row=3, column=1, sticky=tk.W, pady=5)
        self.entry_count.insert(0, "10")

        # 子网掩码
        ttk.Label(main_frame, text="子网掩码:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.entry_mask = ttk.Entry(main_frame, width=40)
        self.entry_mask.grid(row=4, column=1, sticky=tk.W, pady=5)
        self.entry_mask.insert(0, "255.255.255.0")

        # 操作类型
        ttk.Label(main_frame, text="操作类型:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.action_var = tk.StringVar(value="add")
        radio_frame = ttk.Frame(main_frame)
        radio_frame.grid(row=5, column=1, sticky=tk.W, pady=5)
        ttk.Radiobutton(radio_frame, text="添加 IP", variable=self.action_var, value="add",
                        command=self.toggle_mask_entry).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(radio_frame, text="删除 IP", variable=self.action_var, value="delete",
                        command=self.toggle_mask_entry).pack(side=tk.LEFT, padx=5)

        # 执行按钮
        self.btn_execute = ttk.Button(main_frame, text="开始执行", command=self.start_execution)
        self.btn_execute.grid(row=6, column=0, columnspan=2, pady=15)

        # 日志输出区域
        log_frame = ttk.LabelFrame(main_frame, text="执行日志", padding="5")
        log_frame.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, width=70, height=18, state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 清空日志按钮
        self.btn_clear = ttk.Button(main_frame, text="清空日志", command=self.clear_log)
        self.btn_clear.grid(row=8, column=0, columnspan=2, pady=5)

        # 初始状态：删除时禁用掩码输入框
        self.toggle_mask_entry()

    def toggle_mask_entry(self):
        """根据操作类型启用/禁用子网掩码输入框"""
        if self.action_var.get() == "add":
            self.entry_mask.config(state='normal')
        else:
            self.entry_mask.config(state='disabled')

    def clear_log(self):
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')

    def log_message(self, msg):
        """将消息加入队列，由主线程更新日志"""
        self.msg_queue.put(msg)

    def process_queue(self):
        """处理队列中的消息，更新日志控件"""
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                self.log_text.config(state='normal')
                self.log_text.insert(tk.END, msg + '\n')
                self.log_text.see(tk.END)
                self.log_text.config(state='disabled')
        except queue.Empty:
            pass
        self.root.after(100, self.process_queue)

    def start_execution(self):
        """验证输入并启动后台线程执行"""
        # 获取输入
        name = self.entry_name.get().strip()
        prefix = self.entry_prefix.get().strip()
        start_str = self.entry_start.get().strip()
        count_str = self.entry_count.get().strip()
        mask = self.entry_mask.get().strip()
        action = self.action_var.get()

        # 验证网卡名称
        if not name:
            messagebox.showerror("错误", "请输入网卡名称")
            return

        # 验证IP前缀
        if not validate_ip_prefix(prefix):
            messagebox.showerror("错误", "IP前缀格式无效，必须是xxx.xxx.xxx格式")
            return

        # 验证起始IP
        try:
            start = int(start_str)
        except ValueError:
            messagebox.showerror("错误", "起始IP必须是数字")
            return
        if start < 0 or start > 255:
            messagebox.showerror("错误", "起始IP第四位必须在0-255之间")
            return

        # 验证数量
        try:
            count = int(count_str)
        except ValueError:
            messagebox.showerror("错误", "IP数量必须是数字")
            return
        if count <= 0:
            messagebox.showerror("错误", "IP数量必须大于0")
            return

        if start + count - 1 > 255:
            messagebox.showerror("错误", "IP地址范围超出255限制")
            return

        # 添加模式下验证子网掩码
        if action == "add":
            if not mask:
                messagebox.showerror("错误", "添加模式下必须填写子网掩码")
                return
            if not validate_subnet_mask(mask):
                messagebox.showerror("错误", "子网掩码格式无效")
                return

        # 禁用按钮，防止重复执行
        self.btn_execute.config(state='disabled')

        # 启动后台线程
        thread = threading.Thread(target=self.execute_commands,
                                  args=(name, prefix, start, count, mask, action),
                                  daemon=True)
        thread.start()

    def execute_commands(self, name, prefix, start, count, mask, action):
        """后台执行 netsh 命令"""
        success_count = 0
        fail_count = 0

        self.log_message("=" * 50)
        self.log_message(f"开始执行 {('添加' if action == 'add' else '删除')} 操作")
        self.log_message(f"网卡: {name}")
        self.log_message(f"IP前缀: {prefix}")
        self.log_message(f"起始: {start}")
        self.log_message(f"数量: {count}")
        if action == 'add':
            self.log_message(f"子网掩码: {mask}")
        self.log_message("=" * 50)

        for i in range(count):
            ip_suffix = start + i
            ip_address = f"{prefix}.{ip_suffix}"

            if action == 'add':
                command = f'netsh interface ipv4 add address "{name}" {ip_address} {mask}'
            else:
                command = f'netsh interface ipv4 delete address "{name}" address={ip_address}'

            try:
                result = subprocess.run(command, shell=True, capture_output=True,
                                        text=True, encoding='utf-8-sig')
                if result.returncode == 0:
                    self.log_message(f"成功 {action}: {ip_address}")
                    success_count += 1
                else:
                    self.log_message(f"失败 {action}: {ip_address}")
                    if result.stderr:
                        self.log_message(f"  错误信息: {result.stderr.strip()}")
                    fail_count += 1
            except Exception as e:
                self.log_message(f"异常 {action}: {ip_address}")
                self.log_message(f"  异常信息: {str(e)}")
                fail_count += 1

        self.log_message("=" * 50)
        self.log_message(f"{('添加' if action == 'add' else '删除')}完成！")
        self.log_message(f"成功: {success_count} 个")
        self.log_message(f"失败: {fail_count} 个")

        # 重新启用按钮
        self.root.after(0, lambda: self.btn_execute.config(state='normal'))

# ---------- 入口 ----------
if __name__ == "__main__":
    root = tk.Tk()
    app = IPManagerApp(root)
    root.mainloop()