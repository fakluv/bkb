import sys
import os

# 如果是 PyInstaller 打包后的环境，将 _MEIPASS 添加到 sys.path
if getattr(sys, 'frozen', False):
    # 当以 exe 运行时，_MEIPASS 是临时解压目录
    base_path = sys._MEIPASS
    # 将 base_path 添加到模块搜索路径的最前面
    sys.path.insert(0, base_path)
    # 调试：打印路径信息（可删除）
    print(f"Running from MEIPASS: {base_path}")
    # 检查 ttkbootstrap 是否存在
    ttkbootstrap_path = os.path.join(base_path, 'ttkbootstrap')
    if os.path.exists(ttkbootstrap_path):
        print(f"ttkbootstrap found at: {ttkbootstrap_path}")
    else:
        print("ttkbootstrap NOT found at MEIPASS!")

# 现在导入 ttkbootstrap
import ttkbootstrap
import tkinter as tk
from app import IntegratedApp

if __name__ == "__main__":
    root = ttkbootstrap.Window(themename="yeti")
    root.title("ATS 设备报文生成工具 - 集成版")
    app = IntegratedApp(root)
    root.mainloop()