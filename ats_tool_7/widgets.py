# widgets.py
import tkinter as tk
from tkinter import ttk
import re
import sys
import os


class CheckboxTreeview(ttk.Treeview):
    def __init__(self, master=None, **kwargs):
        ttk.Treeview.__init__(self, master, **kwargs)
        style = ttk.Style()
        style.configure('Treeview', indent=15)
        self.checked = set()
        self.bind('<Button-1>', self.on_click)

        # 加载复选框图标（若存在）
        self.img_checked = None
        self.img_unchecked = None
        self._load_images()

    def _load_images(self):
        try:
            if getattr(sys, 'frozen', False):
                # 先尝试从 _MEIPASS 加载
                if hasattr(sys, '_MEIPASS'):
                    base_dir = sys._MEIPASS
                    check_path = os.path.join(base_dir, 'check.png')
                    uncheck_path = os.path.join(base_dir, 'uncheck.png')
                    if os.path.exists(check_path) and os.path.exists(uncheck_path):
                        self.img_checked = tk.PhotoImage(file=check_path)
                        self.img_unchecked = tk.PhotoImage(file=uncheck_path)
                        self._keep_images = (self.img_checked, self.img_unchecked)
                        return
                # 若 _MEIPASS 中不存在，尝试从 EXE 目录加载（外部文件）
                base_dir = os.path.dirname(sys.executable)
                check_path = os.path.join(base_dir, 'check.png')
                uncheck_path = os.path.join(base_dir, 'uncheck.png')
                if os.path.exists(check_path) and os.path.exists(uncheck_path):
                    self.img_checked = tk.PhotoImage(file=check_path)
                    self.img_unchecked = tk.PhotoImage(file=uncheck_path)
                    self._keep_images = (self.img_checked, self.img_unchecked)
                    return
            else:
                # 开发环境从脚本目录加载
                base_dir = os.path.dirname(os.path.abspath(__file__))
                check_path = os.path.join(base_dir, 'check.png')
                uncheck_path = os.path.join(base_dir, 'uncheck.png')
                if os.path.exists(check_path) and os.path.exists(uncheck_path):
                    self.img_checked = tk.PhotoImage(file=check_path)
                    self.img_unchecked = tk.PhotoImage(file=uncheck_path)
                    self._keep_images = (self.img_checked, self.img_unchecked)
                    return
        except Exception as e:
            print(f"加载图片失败: {e}")
        self.img_checked = None
        self.img_unchecked = None

    def _get_clean_text(self, item):
        """获取节点文本（去除所有前缀）"""
        text = self.item(item, 'text')
        if text.startswith('☑ ') or text.startswith('☐ '):
            return text[2:]
        return text

    def insert(self, parent, index, **kwargs):
        orig_text = kwargs.pop('text', '')
        if self.img_checked is not None:
            display = orig_text          # 图像模式：文本不带前缀
        else:
            display = f"☐ {orig_text}"   # 文本模式：加未选中前缀
        item = ttk.Treeview.insert(self, parent, index, text=display, **kwargs)
        if self.img_checked is not None:
            self.item(item, image=self.img_unchecked)
        return item

    def toggle(self, item):
        """递归切换当前节点及其所有子节点"""
        if item in self.checked:
            self.checked.remove(item)
            new_checked = False
        else:
            self.checked.add(item)
            new_checked = True

        self._apply_state(item, new_checked)
        for child in self.get_children(item):
            self.toggle(child)

        if hasattr(self, 'check_callback') and self.check_callback:
            self.check_callback()

    def _apply_state(self, item, checked):
        """为单个节点应用状态（图像或文本）"""
        clean_text = self._get_clean_text(item)
        if self.img_checked is not None:
            self.item(item, image=self.img_checked if checked else self.img_unchecked)
            self.item(item, text=clean_text)      # 图像模式：文本无前缀
        else:
            prefix = "☑ " if checked else "☐ "
            self.item(item, text=f"{prefix}{clean_text}")

    def on_click(self, event):
        region = self.identify_region(event.x, event.y)
        if region == "tree":
            item = self.identify_row(event.y)
            if item:
                element = self.identify_element(event.x, event.y)
                if element == "image":   # 点击复选框图标
                    self.toggle(item)
                # 其他区域（文本、空白）不做勾选切换，让 Treeview 处理选择/展开

    def set_all_checked(self, checked):
        """全选/清空所有节点（包括父节点）"""
        def set_recursive(item):
            # 更新当前节点
            if checked:
                self.checked.add(item)
            else:
                self.checked.discard(item)
            self._apply_state(item, checked)
            # 递归子节点
            for child in self.get_children(item):
                set_recursive(child)

        for root in self.get_children(''):
            set_recursive(root)

        # 触发一次回调（预览更新）
        if hasattr(self, 'check_callback') and self.check_callback:
            self.check_callback()

    def get_all_leaf_items(self):
        leaves = []
        def recurse(item):
            children = self.get_children(item)
            if not children:
                leaves.append(item)
            else:
                for child in children:
                    recurse(child)
        recurse('')
        return leaves

    def get_checked_devices(self):
        """只返回叶子节点（实际设备）的勾选信息"""
        devices = []
        for item in self.checked:
            if not self.get_children(item):   # 只取叶子
                text = self._get_clean_text(item)
                parent = self.parent(item)
                if parent:
                    parent_text = self._get_clean_text(parent)
                    station = parent_text
                else:
                    station = "未知"
                match = re.search(r'(.+) \(ID:(\d+)\)', text)
                if match:
                    name = match.group(1)
                    dev_id = int(match.group(2))
                    devices.append((dev_id, name, station))
                else:
                    if ' - ' in text:
                        parts = text.split(' - ', 1)
                        try:
                            dev_id = int(parts[0].strip())
                            name = parts[1].strip()
                            devices.append((dev_id, name, station))
                        except:
                            pass
        return devices

    # 以下加载方法完全不变（原样保留）
    def load_alarm_devices(self, devices, use_tree=False):
        self.delete(*self.get_children())
        self.checked.clear()
        if use_tree:
            stations = {}
            for dev in devices:
                site = dev['site']
                stations.setdefault(site, []).append(dev)
            for site, sdevs in stations.items():
                site_id = self.insert('', 'end', text=site, open=False)
                for dev in sorted(sdevs, key=lambda x: x['inner_id']):
                    dev_text = f"{dev['name']} (ID:{dev['inner_id']})"
                    self.insert(site_id, 'end', text=dev_text)
        else:
            for dev in sorted(devices, key=lambda x: x['inner_id']):
                dev_text = f"{dev['name']} (ID:{dev['inner_id']}) - {dev['site']}"
                self.insert('', 'end', text=dev_text)

    def load_perf_devices(self, devices):
        self.delete(*self.get_children())
        self.checked.clear()
        stations = {}
        for dev in devices:
            station = dev['station']
            stations.setdefault(station, []).append(dev)
        for station, dev_list in stations.items():
            station_id = self.insert('', 'end', text=station, open=False)
            for dev in sorted(dev_list, key=lambda x: x['id']):
                dev_text = f"{dev['id']} - {dev['name']}"
                self.insert(station_id, 'end', text=dev_text)

    def load_station_devices(self, signal_devices, section_devices, switch_devices, psd_devices, em_brake_devices):
        self.delete(*self.get_children())
        self.checked.clear()

        signal_root = self.insert('', 'end', text="信号机设备", open=False)
        stations = {}
        for sig in signal_devices:
            stations.setdefault(sig['station'], []).append(sig)
        for station, sigs in stations.items():
            station_id = self.insert(signal_root, 'end', text=station, open=False)
            for sig in sorted(sigs, key=lambda x: x['signal_id']):
                dev_text = f"{sig['name']} (ID:{sig['signal_id']})"
                self.insert(station_id, 'end', text=dev_text)

        section_root = self.insert('', 'end', text="逻辑区段设备", open=False)
        stations = {}
        for sec in section_devices:
            stations.setdefault(sec['station'], []).append(sec)
        for station, secs in stations.items():
            station_id = self.insert(section_root, 'end', text=station, open=False)
            for sec in sorted(secs, key=lambda x: x['section_id']):
                dev_text = f"{sec['name']} (ID:{sec['section_id']})"
                self.insert(station_id, 'end', text=dev_text)

        switch_root = self.insert('', 'end', text="道岔设备", open=False)
        stations = {}
        for sw in switch_devices:
            stations.setdefault(sw['station'], []).append(sw)
        for station, sws in stations.items():
            station_id = self.insert(switch_root, 'end', text=station, open=False)
            for sw in sorted(sws, key=lambda x: x['switch_id']):
                dev_text = f"{sw['name']} (ID:{sw['switch_id']})"
                self.insert(station_id, 'end', text=dev_text)

        psd_root = self.insert('', 'end', text="屏蔽门设备", open=False)
        for psd in sorted(psd_devices, key=lambda x: x['psd_id']):
            if psd.get('name') and psd['name']:
                text = f"{psd['name']} (ID:{psd['psd_id']}) "
            else:
                text = f"ID：{psd['psd_id']} （所属站台：{psd['station']}）"
            self.insert(psd_root, 'end', text=text)

        eb_root = self.insert('', 'end', text="紧急停车按钮设备", open=False)
        for eb in sorted(em_brake_devices, key=lambda x: x['eb_id']):
            dev_text = f"ID：{eb['eb_id']} （所属站台：{eb['station']}）"
            self.insert(eb_root, 'end', text=dev_text)