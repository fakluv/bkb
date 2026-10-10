import os
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import ttkbootstrap as tb
from ttkbootstrap.constants import *
import pandas as pd
import struct
import time
import random

# ============================================================
# 用户可编辑区域：Sheet 名称匹配列表
# ============================================================
# 交换机配置文件中可能的工作表名称（按优先级排序）
CONFIG_SHEET_NAMES = [
    "NEConfigData",
    "NE",
    "设备配置",
    "交换机列表",
    "Sheet1"  # 降级匹配
]

# 端口映射文件中可能的工作表名称（按优先级排序）
MAPPING_SHEET_NAMES = [
    "Sheet2",
    "Sheet1",
    "端口映射",
    "PortMapping",
    "映射表"
]
# ============================================================

# ---------- 后端功能 ----------
def clean_cell(val):
    if pd.isna(val):
        return ""
    s = str(val).strip()
    if s.endswith('.0'):
        s = s[:-2]
    if s.lower() == 'nan':
        return ""
    return s

def parse_port_total(mask: str) -> int:
    """解析端口总数，支持 '24'、'26'、'28'、'8,8,8,T'、'NT' 等格式"""
    if not mask:
        return 0
    if mask.isdigit():
        return int(mask)
    if mask.upper() == "NT":
        return 8
    total = 0
    parts = mask.split(',')
    for part in parts:
        part = part.strip()
        if part.isdigit():
            total += int(part)
        else:
            for ch in part:
                if ch.upper() == 'N':
                    total += 8
                elif ch.upper() == 'T':
                    total += 2
    return total

def load_switches_from_neconfig(file_path: str, sheet_name: str):
    """加载交换机配置，必须指定 sheet_name"""
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
    switches = []
    in_switch = False
    port_nbr_col = None

    # 先找表头确定 PortNbr 列
    for idx, row in df.iterrows():
        a = clean_cell(row[0])
        if a == "[Switch]":
            in_switch = True
            continue
        if not in_switch:
            continue
        if a.startswith("[") and a != "[Switch]":
            break
        if a.upper() == "NO":
            for col_idx, val in enumerate(row):
                if clean_cell(val).upper() == "PORTNBR":
                    port_nbr_col = col_idx
                    break
            break

    if port_nbr_col is None:
        # 智能推断
        sample_row = None
        for idx, row in df.iterrows():
            a = clean_cell(row[0])
            if a.isdigit() and int(a) >= 1000:
                sample_row = row
                break
        if sample_row is not None:
            if len(sample_row) > 10 and clean_cell(sample_row[10]) not in ["", "0"]:
                port_nbr_col = 10
            else:
                port_nbr_col = 9
        else:
            port_nbr_col = 9

    in_switch = False
    for _, row in df.iterrows():
        a = clean_cell(row[0])
        b = clean_cell(row[1]) if len(row) > 1 else ""
        if a == "[Switch]":
            in_switch = True
            continue
        if not in_switch:
            continue
        if a.startswith("[") and a != "[Switch]":
            break
        if a == "":
            continue
        if a.isdigit() and ("//" in b or b.startswith("/")):
            continue
        if a.upper() in ["NO", "TYPE"]:
            continue
        if a.isdigit() and int(a) >= 1000:
            try:
                no = int(a)
                port_mask = clean_cell(row[port_nbr_col]) if len(row) > port_nbr_col else ""
                station = clean_cell(row[6]) if len(row) > 6 else ""
                hostname = clean_cell(row[2]) if len(row) > 2 else ""
                switches.append({
                    "no": no,
                    "station": station,
                    "hostname": hostname,
                    "port_mask": port_mask,
                    "total_ports": parse_port_total(port_mask)
                })
            except Exception as e:
                print(f"跳过行 {row} 原因: {e}")
                continue
    return switches

def load_port_mapping(file_path: str, sheet_name: str):
    """加载端口映射，必须指定 sheet_name"""
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
    mapping = {}
    current = None
    for _, row in df.iterrows():
        a = clean_cell(row[0])
        b = clean_cell(row[1]) if len(row) > 1 else ""
        if a == "" and b == "":
            current = None
            continue
        if a.isdigit() and len(a) >= 4 and ("//" in b or b.startswith("/")):
            current = int(a)
            mapping[current] = {}
            continue
        if current is not None:
            if a.isdigit():
                if b == "" or b.isdigit() or "//" in b or b.startswith("/"):
                    continue
                mapping[current][int(a)] = b
            elif "|" in a:
                parts = a.split('|')
                if len(parts) == 2:
                    p = clean_cell(parts[0])
                    d = clean_cell(parts[1])
                    if p.isdigit():
                        mapping[current][int(p)] = d
    return mapping

def crc32_custom(data: bytes) -> int:
    crc = 0x00000000
    for byte in data:
        crc ^= (byte << 24)
        for _ in range(8):
            if crc & 0x80000000:
                crc = (crc << 1) ^ 0x04C11DB7
            else:
                crc <<= 1
            crc &= 0xFFFFFFFF
    return crc

def build_packet(switches, port_mapping, custom_status=None, nms_version=None):
    HEADER = 0xAA
    END = 0x55
    MSG_ID = 0x10
    NMS_INDEX = 0x00
    AP_NUM = 0

    stamp = int(time.time())
    if nms_version is None:
        nms_version = random.randint(0, 0xFFFFFFFF)

    bit_buffer = bytearray()
    cur_byte = 0
    bit_pos = 0

    def write_bits(value, bit_len):
        nonlocal cur_byte, bit_pos
        for i in range(bit_len-1, -1, -1):
            bit = (value >> i) & 0x01
            if bit:
                cur_byte |= (1 << (7 - bit_pos))
            bit_pos += 1
            if bit_pos == 8:
                bit_buffer.append(cur_byte)
                cur_byte = 0
                bit_pos = 0

    def flush_bits():
        nonlocal cur_byte, bit_pos
        if bit_pos > 0:
            bit_buffer.append(cur_byte)
            cur_byte = 0
            bit_pos = 0

    sw_num = len(switches)
    switch_log = []

    for sw in switches:
        no = sw["no"]
        total_ports = sw["total_ports"]

        if custom_status and no in custom_status:
            sw_status = custom_status[no][0]
        else:
            sw_status = 0b00
        write_bits(sw_status, 2)

        sw_map = port_mapping.get(no, {})
        port_info = []
        for port_no in range(1, total_ports + 1):
            port_status = 0b00
            if custom_status and no in custom_status:
                port_status = custom_status[no][1].get(port_no, port_status)
            write_bits(port_status, 2)
            if port_no in sw_map:
                port_info.append((port_no, sw_map[port_no], port_status))
        switch_log.append({
            "no": no,
            "hostname": sw["hostname"],
            "sw_status": sw_status,
            "port_info": port_info
        })

    flush_bits()
    switch_bytes = bytes(bit_buffer)

    data = bytearray()
    data.append(MSG_ID)
    data.extend(struct.pack(">I", stamp))
    data.append(NMS_INDEX)
    data.extend(struct.pack(">I", nms_version))
    data.extend(struct.pack(">H", AP_NUM))
    data.append(sw_num)
    data.extend(switch_bytes)
    data.append(END)

    data_len = len(data)
    packet = bytearray()
    packet.append(HEADER)
    packet.extend(struct.pack(">H", data_len))
    packet.extend(data)
    crc = crc32_custom(bytes(data))
    packet.extend(struct.pack(">I", crc))

    return bytes(packet), switch_log

# ---------- GUI 类 ----------
class NMSApp(tb.Window):
    def __init__(self):
        super().__init__(themename="cosmo")
        self.title("NMS 报文生成工具 (Sheet列表匹配)")
        self.geometry("1100x750")

        self.folder_path = tk.StringVar()
        self.all_switches = []
        self.port_mapping = {}
        self.selected_indices = set()
        self.switch_status = {}
        self.tree = None
        self.status_var = tk.StringVar(value="就绪")

        self.create_widgets()

    def create_widgets(self):
        top_frame = tb.Frame(self)
        top_frame.pack(pady=10, fill='x', padx=10)

        tb.Label(top_frame, text="数据文件夹:").pack(side='left')
        self.folder_entry = tb.Entry(top_frame, textvariable=self.folder_path, width=50)
        self.folder_entry.pack(side='left', padx=5)
        tb.Button(top_frame, text="浏览...", command=self.select_folder, bootstyle="primary").pack(side='left')
        tb.Button(top_frame, text="加载数据", command=self.load_data, bootstyle="success").pack(side='left', padx=5)

        btn_frame = tb.Frame(self)
        btn_frame.pack(pady=5, fill='x', padx=10)
        tb.Button(btn_frame, text="全选", command=self.select_all, bootstyle="info").pack(side='left', padx=2)
        tb.Button(btn_frame, text="取消全选", command=self.deselect_all, bootstyle="secondary").pack(side='left', padx=2)
        tb.Button(btn_frame, text="全局设置", command=self.global_setting, bootstyle="primary").pack(side='left', padx=2)
        tb.Button(btn_frame, text="生成报文", command=self.generate_packet, bootstyle="warning").pack(side='left', padx=10)

        tree_frame = tb.Frame(self)
        tree_frame.pack(fill='both', expand=True, padx=10, pady=5)

        columns = ("选择", "编号", "主机名", "车站", "端口数", "整机状态", "端口设置")
        self.tree = tb.Treeview(tree_frame, columns=columns, show='headings', height=20)
        self.tree.heading("选择", text="选择")
        self.tree.heading("编号", text="编号")
        self.tree.heading("主机名", text="主机名")
        self.tree.heading("车站", text="车站")
        self.tree.heading("端口数", text="端口数")
        self.tree.heading("整机状态", text="整机状态")
        self.tree.heading("端口设置", text="端口设置")

        self.tree.column("选择", width=60, anchor='center')
        self.tree.column("编号", width=80, anchor='center')
        self.tree.column("主机名", width=200)
        self.tree.column("车站", width=100)
        self.tree.column("端口数", width=80, anchor='center')
        self.tree.column("整机状态", width=120, anchor='center')
        self.tree.column("端口设置", width=120, anchor='center')

        self.tree.bind("<ButtonRelease-1>", self.on_tree_click)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')

        status_frame = tb.Frame(self)
        status_frame.pack(fill='x', padx=10, pady=5)
        tb.Label(status_frame, textvariable=self.status_var, bootstyle="info").pack(side='left')

        self.packet_text = scrolledtext.ScrolledText(self, height=10, wrap=tk.WORD, font=("Consolas", 10))
        self.packet_text.pack(fill='x', padx=10, pady=5)
        copy_btn = tb.Button(self, text="复制报文", command=self.copy_packet, bootstyle="secondary")
        copy_btn.pack(anchor='e', padx=10, pady=2)

    def select_folder(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path.set(folder)

    def find_sheet(self, file_path, name_list):
        """
        根据名称列表匹配工作表，返回匹配到的第一个工作表名，若未找到返回 None。
        """
        try:
            sheets = pd.ExcelFile(file_path).sheet_names
            for pattern in name_list:
                for s in sheets:
                    if pattern in s:
                        return s
            return None
        except Exception:
            return None

    def select_sheet_dialog(self, sheet_list, prompt, default=None):
        """
        弹出选择工作表的对话框，返回选中的 sheet 名称，取消返回 None。
        """
        win = tb.Toplevel(self)
        win.title("选择工作表")
        win.geometry("400x300")
        win.transient(self)
        win.grab_set()

        tb.Label(win, text=prompt, wraplength=350).pack(pady=10)

        listbox = tk.Listbox(win, height=10)
        listbox.pack(fill='both', expand=True, padx=10, pady=5)
        for s in sheet_list:
            listbox.insert(tk.END, s)
        if default and default in sheet_list:
            listbox.selection_set(sheet_list.index(default))

        selected = [None]

        def on_ok():
            sel = listbox.curselection()
            if sel:
                selected[0] = listbox.get(sel[0])
                win.destroy()
            else:
                messagebox.showinfo("提示", "请选择一个工作表")

        def on_cancel():
            win.destroy()

        btn_frame = tb.Frame(win)
        btn_frame.pack(pady=10)
        tb.Button(btn_frame, text="确定", command=on_ok, bootstyle="success").pack(side='left', padx=5)
        tb.Button(btn_frame, text="取消", command=on_cancel, bootstyle="danger").pack(side='left', padx=5)

        self.wait_window(win)
        return selected[0]

    def load_data(self):
        folder = self.folder_path.get()
        if not folder:
            messagebox.showerror("错误", "请先选择文件夹")
            return

        all_files = [f for f in os.listdir(folder) if f.endswith('.xlsx')]
        if not all_files:
            messagebox.showerror("错误", "文件夹中没有 Excel 文件")
            return

        # 文件名模糊匹配
        neconfig_file = None
        relation_file = None
        for f in all_files:
            if '交控' in f or 'DCS' in f:
                neconfig_file = f
            if 'SwitchAndPort' in f or '端口' in f:
                relation_file = f

        if neconfig_file is None:
            for f in all_files:
                try:
                    sheets = pd.ExcelFile(os.path.join(folder, f)).sheet_names
                    if any('NEConfigData' in s or 'NE' in s for s in sheets):
                        neconfig_file = f
                        break
                except:
                    continue

        if relation_file is None:
            for f in all_files:
                try:
                    sheets = pd.ExcelFile(os.path.join(folder, f)).sheet_names
                    if any(s in ['Sheet1', 'Sheet2'] for s in sheets):
                        relation_file = f
                        break
                except:
                    continue

        if neconfig_file is None or relation_file is None:
            messagebox.showerror("错误", "未能自动识别文件，请确保文件夹中包含交换机配置文件和端口映射文件")
            return

        neconfig_path = os.path.join(folder, neconfig_file)
        relation_path = os.path.join(folder, relation_file)

        try:
            # ---- 交换机配置 Sheet 匹配 ----
            sheet_ne = self.find_sheet(neconfig_path, CONFIG_SHEET_NAMES)
            if sheet_ne is None:
                sheets = pd.ExcelFile(neconfig_path).sheet_names
                sheet_ne = self.select_sheet_dialog(sheets, "未匹配到交换机配置Sheet，请手动选择")
                if sheet_ne is None:
                    return

            # ---- 端口映射 Sheet 匹配 ----
            sheet_rel = self.find_sheet(relation_path, MAPPING_SHEET_NAMES)
            if sheet_rel is None:
                sheets = pd.ExcelFile(relation_path).sheet_names
                sheet_rel = self.select_sheet_dialog(sheets, "未匹配到端口映射Sheet，请手动选择")
                if sheet_rel is None:
                    return

            # 加载数据
            self.all_switches = load_switches_from_neconfig(neconfig_path, sheet_name=sheet_ne)
            self.port_mapping = load_port_mapping(relation_path, sheet_name=sheet_rel)

            self.selected_indices.clear()
            self.switch_status.clear()
            self.refresh_tree()
            self.status_var.set(f"加载成功: {len(self.all_switches)} 台交换机, {sum(len(v) for v in self.port_mapping.values())} 条端口映射")
        except Exception as e:
            messagebox.showerror("加载失败", str(e))
            self.status_var.set("加载失败")

    def refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for idx, sw in enumerate(self.all_switches):
            sw_status_str = "正常"
            if idx in self.selected_indices:
                if sw["no"] in self.switch_status:
                    st = self.switch_status[sw["no"]][0]
                    sw_status_str = ["正常", "整机故障", "高负载", "端口异常"][st]
            values = ("☐", sw["no"], sw["hostname"], sw["station"], sw["total_ports"], sw_status_str, "设置端口")
            self.tree.insert("", "end", values=values, tags=(str(idx),))

    def on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        column = self.tree.identify_column(event.x)
        col_index = int(column.replace("#", "")) - 1
        item = self.tree.identify_row(event.y)
        if not item:
            return
        idx = int(self.tree.item(item, "tags")[0])
        sw = self.all_switches[idx]
        no = sw["no"]

        if col_index == 0:
            if idx in self.selected_indices:
                self.selected_indices.remove(idx)
                self.tree.set(item, column="选择", value="☐")
            else:
                self.selected_indices.add(idx)
                self.tree.set(item, column="选择", value="☑")
                if no not in self.switch_status:
                    self.switch_status[no] = (0, {})

        elif col_index == 5:
            if idx not in self.selected_indices:
                messagebox.showinfo("提示", "请先选中该设备")
                return
            menu = tk.Menu(self, tearoff=0)
            options = ["正常", "整机故障", "高负载", "端口异常"]
            for opt in options:
                menu.add_command(label=opt, command=lambda o=opt: self.set_sw_status(idx, o))
            menu.post(self.tree.winfo_pointerx(), self.tree.winfo_pointery())

        elif col_index == 6:
            if idx not in self.selected_indices:
                messagebox.showinfo("提示", "请先选中该设备")
                return
            self.open_port_settings(idx)

    def set_sw_status(self, idx, opt_str):
        no = self.all_switches[idx]["no"]
        status_map = {"正常": 0, "整机故障": 1, "高负载": 2, "端口异常": 3}
        st = status_map[opt_str]
        if no not in self.switch_status:
            self.switch_status[no] = (st, {})
        else:
            self.switch_status[no] = (st, self.switch_status[no][1])
        item = self.tree.get_children()[idx]
        self.tree.set(item, column="整机状态", value=opt_str)

    def open_port_settings(self, idx):
        sw = self.all_switches[idx]
        no = sw["no"]
        mapped_ports = sorted(self.port_mapping.get(no, {}).keys())
        if not mapped_ports:
            messagebox.showinfo("提示", f"交换机 {no} 没有映射端口，无需设置")
            return

        current_port_status = self.switch_status.get(no, (0, {}))[1] if no in self.switch_status else {}

        win = tb.Toplevel(self)
        win.title(f"端口状态设置 - {no} {sw['hostname']} (仅映射端口)")
        win.geometry("400x500")

        frame = tb.Frame(win)
        frame.pack(fill='both', expand=True, padx=10, pady=10)

        canvas = tk.Canvas(frame)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tb.Frame(canvas)
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        port_vars = {}
        for p in mapped_ports:
            row = tb.Frame(scrollable_frame)
            row.pack(fill='x', pady=2)
            device = self.port_mapping[no][p]
            tb.Label(row, text=f"端口 {p} ({device}):").pack(side='left', padx=5)
            var = tk.StringVar(value="正常")
            if p in current_port_status:
                var.set(["正常", "故障", "超标"][current_port_status[p]])
            port_vars[p] = var
            combo = tb.Combobox(row, textvariable=var, values=["正常", "故障", "超标"], state="readonly", width=10)
            combo.pack(side='left', padx=5)

        btn_frame = tb.Frame(win)
        btn_frame.pack(pady=10)
        def save_ports():
            port_dict = {}
            for p, var in port_vars.items():
                val = var.get()
                port_dict[p] = ["正常", "故障", "超标"].index(val)
            if no in self.switch_status:
                self.switch_status[no] = (self.switch_status[no][0], port_dict)
            else:
                self.switch_status[no] = (0, port_dict)
            win.destroy()
            messagebox.showinfo("成功", f"端口状态已保存 (交换机 {no})")

        tb.Button(btn_frame, text="保存", command=save_ports, bootstyle="success").pack(side='left', padx=5)
        tb.Button(btn_frame, text="取消", command=win.destroy, bootstyle="danger").pack(side='left', padx=5)

        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

    def global_setting(self):
        if not self.all_switches:
            messagebox.showinfo("提示", "请先加载数据")
            return

        win = tb.Toplevel(self)
        win.title("全局设置所有设备（仅映射端口）")
        win.geometry("300x200")
        main_frame = tb.Frame(win)
        main_frame.pack(pady=20, padx=20, fill='both')

        tb.Label(main_frame, text="整机状态:").grid(row=0, column=0, sticky='w', pady=5)
        sw_var = tk.StringVar(value="正常")
        sw_combo = tb.Combobox(main_frame, textvariable=sw_var, values=["正常", "整机故障", "高负载", "端口异常"], state="readonly", width=15)
        sw_combo.grid(row=0, column=1, pady=5)

        tb.Label(main_frame, text="统一端口状态 (仅映射端口):").grid(row=1, column=0, sticky='w', pady=5)
        port_var = tk.StringVar(value="正常")
        port_combo = tb.Combobox(main_frame, textvariable=port_var, values=["正常", "故障", "超标"], state="readonly", width=15)
        port_combo.grid(row=1, column=1, pady=5)

        def apply():
            sw_map = {"正常":0, "整机故障":1, "高负载":2, "端口异常":3}
            port_map = {"正常":0, "故障":1, "超标":2}
            sw_status = sw_map[sw_var.get()]
            port_status = port_map[port_var.get()]
            for sw in self.all_switches:
                no = sw["no"]
                mapped_ports = self.port_mapping.get(no, {}).keys()
                if not mapped_ports:
                    continue
                port_dict = {p: port_status for p in mapped_ports}
                self.switch_status[no] = (sw_status, port_dict)
                for idx, s in enumerate(self.all_switches):
                    if s["no"] == no:
                        if idx not in self.selected_indices:
                            self.selected_indices.add(idx)
                            item = self.tree.get_children()[idx]
                            self.tree.set(item, column="选择", value="☑")
                        item = self.tree.get_children()[idx]
                        self.tree.set(item, column="整机状态", value=sw_var.get())
                        break
            win.destroy()
            self.status_var.set(f"全局设置已应用，共 {len(self.all_switches)} 台设备")
            messagebox.showinfo("成功", f"已为所有设备设置整机状态为 '{sw_var.get()}'，端口统一为 '{port_var.get()}'")

        tb.Button(main_frame, text="应用", command=apply, bootstyle="success").grid(row=2, column=0, pady=20)
        tb.Button(main_frame, text="取消", command=win.destroy, bootstyle="danger").grid(row=2, column=1, pady=20)

    def select_all(self):
        for idx in range(len(self.all_switches)):
            self.selected_indices.add(idx)
            item = self.tree.get_children()[idx]
            self.tree.set(item, column="选择", value="☑")
            no = self.all_switches[idx]["no"]
            if no not in self.switch_status:
                self.switch_status[no] = (0, {})
        self.status_var.set(f"已选择 {len(self.selected_indices)} 台设备")

    def deselect_all(self):
        self.selected_indices.clear()
        for idx in range(len(self.all_switches)):
            item = self.tree.get_children()[idx]
            self.tree.set(item, column="选择", value="☐")
        self.status_var.set("已取消所有选择")

    def generate_packet(self):
        if not self.selected_indices:
            messagebox.showinfo("提示", "请至少选择一台交换机")
            return
        selected_switches = []
        for idx in sorted(self.selected_indices):
            sw = self.all_switches[idx]
            selected_switches.append(sw)
        custom_status = {}
        for sw in selected_switches:
            no = sw["no"]
            if no in self.switch_status:
                custom_status[no] = self.switch_status[no]
            else:
                custom_status[no] = (0, {})
        try:
            packet, log = build_packet(selected_switches, self.port_mapping, custom_status)
            hex_str = " ".join(f"{b:02X}" for b in packet)
            self.packet_text.delete(1.0, tk.END)
            self.packet_text.insert(tk.END, hex_str)
            self.status_var.set(f"报文生成成功，总长度 {len(packet)} 字节，共 {len(selected_switches)} 台交换机")
        except Exception as e:
            messagebox.showerror("生成失败", str(e))
            self.status_var.set("生成失败")

    def copy_packet(self):
        text = self.packet_text.get(1.0, tk.END).strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status_var.set("报文已复制到剪贴板")
        else:
            messagebox.showinfo("提示", "没有报文可复制")

if __name__ == "__main__":
    app = NMSApp()
    app.mainloop()