import tkinter as tk
from tkinter import ttk, scrolledtext
import sys
from io import StringIO

# 导入原有解析模块
from tool import messageTool
from messagePackage.deviceState import DeviceState
from messagePackage.driveInfo import DriveInfo
from messagePackage.version import Version
from messagePackage.heartBeat import HeartBeat


class CIGui:
    def __init__(self, root):
        self.root = root
        self.root.title("CI报文解析工具")
        self.root.geometry("900x700")

        # 样式
        style = ttk.Style()
        style.configure("TLabel", font=("微软雅黑", 10))
        style.configure("TButton", font=("微软雅黑", 10))
        style.configure("TText", font=("Consolas", 10))

        # --- 输入区域 ---
        lbl_input = ttk.Label(root, text="请输入 CI 报文：")
        lbl_input.pack(pady=(10, 0))

        self.input_text = scrolledtext.ScrolledText(root, height=5, font=("Consolas", 10))
        self.input_text.pack(fill=tk.X, padx=10, pady=5)
        geshi = "[2026-08-15 13:00:00,064]:[CI,70.32.240.28] {}"
        self.input_text.insert("1.0", geshi)

        # --- 按钮区域 ---
        btn_frame = ttk.Frame(root)
        btn_frame.pack(pady=5)

        btn_parse = ttk.Button(btn_frame, text="解析报文", command=self.parse_message)
        btn_parse.pack(side=tk.LEFT, padx=5)

        btn_clear = ttk.Button(btn_frame, text="清空输入", command=self.clear_input)
        btn_clear.pack(side=tk.LEFT, padx=5)

        btn_clear_out = ttk.Button(btn_frame, text="清空输出", command=self.clear_output)
        btn_clear_out.pack(side=tk.LEFT, padx=5)

        # 示例报文（可选）
        btn_example = ttk.Button(btn_frame, text="填入示例", command=self.fill_example)
        btn_example.pack(side=tk.LEFT, padx=5)

        # --- 输出区域 ---
        lbl_output = ttk.Label(root, text="解析结果：")
        lbl_output.pack(pady=(10, 0))

        self.output_text = scrolledtext.ScrolledText(root, height=25, font=("Consolas", 10), state=tk.NORMAL)
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 状态栏
        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        status_bar = ttk.Label(root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, ipady=2)

    def parse_message(self):
        raw = self.input_text.get("1.0", tk.END).strip()
        if not raw:
            self.output_text.insert(tk.END, "❌ 请输入CI报文！\n")
            return

        # 清除输出
        self.output_text.delete("1.0", tk.END)
        self.status_var.set("正在解析...")
        self.root.update()

        # 重定向 stdout 到 StringIO
        old_stdout = sys.stdout
        sys.stdout = mystdout = StringIO()

        try:
            # 复制 main.py 的解析逻辑
            messageStr = messageTool.deletTimePrefixFrom(raw)
            if not messageStr:
                print("报文格式错误：未找到第二个 ']'，无法剥离时间前缀。")
            else:
                messageArr = messageStr.split()
                if len(messageArr) < 4:
                    print("报文太短，至少需要 4 个字段。")
                else:
                    msg_id = messageArr[3]
                    if msg_id == "40":
                        device = DeviceState.inintWithOneMessage(messageStr, messageArr)
                        device.showMyInfo()
                    elif msg_id == '41':
                        version = Version.initWithOneMessage(messageStr, messageArr)
                        version.showMyInfo()
                    elif msg_id == '43':
                        driveInfo = DriveInfo.inintWithOneMessage(messageStr, messageArr)
                        driveInfo.showMyInfo()
                    elif msg_id == '42':
                        heart = HeartBeat.initWithOneMessage(messageStr, messageArr)
                        heart.showMyInfo()
                    else:
                        print("报文类型有误，请核对后重新输入！")
        except Exception as e:
            print(f"解析时发生异常：{e}")
        finally:
            sys.stdout = old_stdout

        output = mystdout.getvalue()
        if output:
            self.output_text.insert(tk.END, output)
        else:
            self.output_text.insert(tk.END, "解析完成，无输出内容。\n")

        self.status_var.set("解析完成")

    def clear_input(self):
        self.input_text.delete("1.0", tk.END)

    def clear_output(self):
        self.output_text.delete("1.0", tk.END)

    def fill_example(self):
        # 此处可填入您常用的示例报文，若无则跳过
        example = '[2026-08-15 13:00:00,064]:[CI,70.32.240.28]  {7E 00 1C 40 ...}'  # 请替换为真实示例
        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", example)


if __name__ == "__main__":
    root = tk.Tk()
    app = CIGui(root)
    root.mainloop()