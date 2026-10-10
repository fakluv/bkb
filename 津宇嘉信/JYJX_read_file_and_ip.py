#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
津宇嘉信2-报文模拟工具 (支持码位表自动解析 + 抽测模式 + 点名称 + 查看抽取信息/校验)
命令字 4041 / 4043 / 4143 / 4044 / 4241 报文生成与 UDP 连续发送
左侧文件列表，单击选择，支持模糊搜索，布局紧凑
新增运行日志区
新增抽测模式：模拟量默认0，报警默认恢复；随机均匀抽取，比例可自定义
新增：读取点名称，抽测时显示抽到的数字与对应名称
新增：查看抽取信息对话框（两页：抽测模式 / 全量模式）
     - 抽测模式页：选择命令字，展示抽测项，4044 逐条 SQL 校验
     - 全量模式页：仅用于 4044，校验全量报警，逐条 SQL 校验
"""

import sys
import random
import struct
import socket
import os
import re
import openpyxl
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QComboBox, QTextEdit, QGroupBox, QFileDialog,
    QMessageBox, QDoubleSpinBox, QCheckBox, QListWidget, QListWidgetItem,
    QSizePolicy, QDialog, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, QSettings, QTimer, QThread, Signal
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor, QIcon

try:
    import pymysql
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False

# ==================== 数据库连接配置 ====================
DB_USER = "root"
DB_PASSWORD = "mysql"
DB_NAME = "base"
DB_TIMEOUT = 3

# ==================== 公共函数 ====================
def calc_length_field(lenid: int) -> int:
    l = lenid & 0x0FFF
    b2 = (l >> 8) & 0x0F
    b1 = (l >> 4) & 0x0F
    b0 = l & 0x0F
    s = b2 + b1 + b0
    check = (16 - (s & 0x0F)) & 0x0F
    high_byte = (check << 4) & 0xF0
    low_byte = l & 0xFF
    return (high_byte << 8) | low_byte

def calc_checksum(data_bytes: bytes) -> int:
    total = sum(data_bytes) & 0xFFFF
    total_mod = total % 65535
    if total_mod == 0:
        return 0
    return (65536 - total_mod) & 0xFFFF

def float_to_bytes(value: float) -> bytes:
    return struct.pack('<f', value)

def hex_dump(msg: bytes) -> str:
    return ' '.join(f'{b:02X}' for b in msg)

def pick_uniform_positions(n: int, k: int):
    """
    在 0 ~ n-1 中尽量均匀地随机抽取 k 个位置。
    """
    if n <= 0:
        return []
    k = max(1, min(k, n))
    step = n / k
    positions = []
    for i in range(k):
        lo = int(i * step)
        hi = int((i + 1) * step) - 1
        if hi < lo:
            hi = lo
        if hi > n - 1:
            hi = n - 1
        positions.append(random.randint(lo, hi))
    return sorted(set(positions))

# ==================== 报文生成函数 ====================
def build_4041_message(num_lines: int, input_type: int, data_floats: list) -> bytes:
    lines_ascii = b'02'
    type_ascii = f"{input_type:02X}".encode('ascii')
    floats_ascii = b''
    for val in data_floats:
        raw = struct.pack('<f', val)
        floats_ascii += raw.hex().upper().encode('ascii')
    info_ascii = lines_ascii + type_ascii + floats_ascii

    lenid = len(info_ascii)
    length_val = calc_length_field(lenid)
    length_ascii = f"{length_val:04X}".encode('ascii')

    cid_ascii = b'4041'
    data_for_checksum = cid_ascii + length_ascii + info_ascii
    chksum_val = calc_checksum(data_for_checksum)
    chksum_ascii = f"{chksum_val:04X}".encode('ascii')

    return b'\x7E' + data_for_checksum + chksum_ascii + b'\x0D'

def build_4043_message(num_contacts: int, states: list) -> bytes:
    info_ascii = b''.join(f'{s:02X}'.encode('ascii') for s in states)
    lenid = len(info_ascii)
    length_val = calc_length_field(lenid)
    length_ascii = f"{length_val:04X}".encode('ascii')

    cid_ascii = b'4043'
    data_for_checksum = cid_ascii + length_ascii + info_ascii
    chksum_val = calc_checksum(data_for_checksum)
    chksum_ascii = f"{chksum_val:04X}".encode('ascii')

    return b'\x7E' + data_for_checksum + chksum_ascii + b'\x0D'

def build_4143_message(modules_data: list) -> bytes:
    p = len(modules_data)
    data_info_raw = bytes([p])
    for mod in modules_data:
        data_info_raw += bytes(mod)
    info_ascii = b''.join(f'{b:02X}'.encode('ascii') for b in data_info_raw)
    lenid = len(info_ascii)
    length_val = calc_length_field(lenid)
    length_ascii = f'{length_val:04X}'.encode('ascii')
    cid1_ascii = b'41'
    cid2_ascii = b'43'
    data_for_checksum = cid1_ascii + cid2_ascii + length_ascii + info_ascii
    chksum_val = calc_checksum(data_for_checksum)
    chksum_ascii = f'{chksum_val:04X}'.encode('ascii')
    return b'\x7E' + data_for_checksum + chksum_ascii + b'\x0D'

def build_4044_message(num_lines: int, input_type: int, alarm_states: list) -> bytes:
    lines_str = "02"
    type_str = f"{input_type:02d}"
    states_str = ''.join(f"{s:02X}" for s in alarm_states)
    info_ascii = (lines_str + type_str + states_str).encode('ascii')

    lenid = len(info_ascii)
    length_val = calc_length_field(lenid)
    length_ascii = f"{length_val:04X}".encode('ascii')

    cid1_ascii = b'40'
    cid2_ascii = b'44'
    data_for_checksum = cid1_ascii + cid2_ascii + length_ascii + info_ascii
    chksum_val = calc_checksum(data_for_checksum)
    chksum_ascii = f"{chksum_val:04X}".encode('ascii')

    return b'\x7E' + data_for_checksum + chksum_ascii + b'\x0D'

def build_4241_message(float_values: list) -> bytes:
    info_ascii_bytes = b''
    for val in float_values:
        raw_bytes = float_to_bytes(val)
        for b in raw_bytes:
            info_ascii_bytes += f'{b:02X}'.encode('ascii')
    lenid = len(info_ascii_bytes)
    length_val = calc_length_field(lenid)
    length_ascii = f'{length_val:04X}'.encode('ascii')
    cid1_ascii = b'42'
    cid2_ascii = b'41'
    data_for_checksum = cid1_ascii + cid2_ascii + length_ascii + info_ascii_bytes
    chksum_val = calc_checksum(data_for_checksum)
    chksum_ascii = f'{chksum_val:04X}'.encode('ascii')
    return b'\x7E' + data_for_checksum + chksum_ascii + b'\x0D'

# ==================== 站点配置解析 ====================
def parse_station_file(filepath):
    wb = openpyxl.load_workbook(filepath, data_only=True)
    result = {}

    cmd_sheets = [s for s in wb.sheetnames if s in ('4041', '4043', '4044', '4241', '4143')]
    if cmd_sheets:
        for cmd in cmd_sheets:
            ws = wb[cmd]
            rows = list(ws.iter_rows(values_only=True))
            start_row = 0
            for i, row in enumerate(rows):
                if row and row[0] is not None and str(row[0]).strip().isdigit():
                    start_row = i
                    break
            points = []
            for i in range(start_row, len(rows)):
                row = rows[i]
                if not row or row[0] is None:
                    continue
                idx = str(row[0]).strip()
                if not idx.isdigit():
                    continue
                name = ''
                if len(row) > 1 and row[1] is not None:
                    name = str(row[1]).strip()
                if not name:
                    name = f"点{idx}"
                points.append({'name': name, 'upper': None, 'lower': None})
            if points:
                result[cmd] = {'count': len(points), 'points': points}
        return result

    ws = wb.active
    i = 1
    rows = list(ws.iter_rows(values_only=True))
    while i < len(rows):
        row = rows[i]
        if row and row[0] == '@' and isinstance(row[1], (int, float)):
            cmd = str(row[2]) if row[2] else ''
            count = int(row[3]) if row[3] and isinstance(row[3], (int, float)) else 0
            i += 1
            data_rows = []
            if i < len(rows) and rows[i] and rows[i][0] == '#':
                i += 1
                while i < len(rows) and rows[i] and rows[i][0] != '@':
                    data_rows.append(rows[i])
                    i += 1
            points = []
            for dr in data_rows:
                if not dr or dr[0] is None:
                    continue
                idx = str(dr[0]).strip()
                name = ''
                if len(dr) > 1 and dr[1] is not None:
                    name = str(dr[1]).strip()
                if not name:
                    name = f"点{idx}"
                upper = None
                lower = None
                if len(dr) > 3 and dr[3] is not None:
                    try:
                        upper = float(dr[3])
                    except (TypeError, ValueError):
                        upper = None
                if len(dr) > 4 and dr[4] is not None:
                    try:
                        lower = float(dr[4])
                    except (TypeError, ValueError):
                        lower = None
                points.append({'name': name, 'upper': upper, 'lower': lower})

            if cmd in ('4041', '4241'):
                result[cmd] = {'count': len(points), 'points': points}
            else:
                result[cmd] = {'count': count, 'points': points}
        else:
            i += 1
    return result

# ==================== Logo ====================
def create_logo():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(0, 120, 215))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, 60, 60)
    painter.setPen(Qt.white)
    font = painter.font()
    font.setPointSize(18)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "JYJX")
    painter.end()
    return QIcon(pixmap)

# ==================== 校验工作线程 ====================
class ValidateWorker(QThread):
    """
    每个 device_name 一条 SQL：
      SELECT device_name FROM alarm_history
      WHERE sys_no = 6 AND station_no = %s AND device_name = %s
    """
    row_status = Signal(int, str)   # (行号, 'pass' / 'fail')
    done = Signal()

    def __init__(self, db_host, station_no, items):
        super().__init__()
        self.db_host = db_host
        self.station_no = station_no
        self.items = list(items)    # [(row_idx, device_name), ...]
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        conn = None
        try:
            conn = pymysql.connect(
                host=self.db_host,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                charset='utf8',
                connect_timeout=DB_TIMEOUT
            )
        except Exception:
            # 连不上数据库，全部标记不通过
            for row_idx, _ in self.items:
                if self._stop:
                    break
                self.row_status.emit(row_idx, 'fail')
            self.done.emit()
            return

        for row_idx, name in self.items:
            if self._stop:
                break
            status = 'fail'
            try:
                with conn.cursor() as cursor:
                    sql = (
                        "SELECT device_name FROM alarm_history "
                        "WHERE sys_no = 6 AND station_no = %s AND device_name = %s and recover_time is null"
                    )
                    cursor.execute(sql, (self.station_no, name))
                    if cursor.fetchone():
                        status = 'pass'
            except Exception:
                status = 'fail'
            self.row_status.emit(row_idx, status)

        try:
            conn.close()
        except Exception:
            pass
        self.done.emit()

# ==================== 查看抽取信息/校验 对话框 ====================
class SampleInfoDialog(QDialog):
    """
    两个页面：
      - 抽测模式：选择命令字，展示抽测项；4044 自动逐条 SQL 校验
      - 全量模式：仅 4044，展示全量告警，逐条 SQL 校验
    校验结果颜色：通过=绿色，不通过=红色，正在校验中=蓝色
    """

    CMD_LABELS = {
        '4041': '模拟量输入',
        '4143': '模块状态',
        '4044': '告警',
        '4241': '模拟量输出',
    }

    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window
        self.setWindowTitle("抽测信息 / 数据校验")
        self.resize(900, 680)

        self.worker_sample = None
        self.worker_full = None
        self._full_started = False

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_sample_tab(), "抽测模式")
        self.tabs.addTab(self._build_full_tab(), "全量模式")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)

        # 底部按钮
        btn_row = QHBoxLayout()
        self.btn_copy = QPushButton("复制当前表")
        self.btn_copy.clicked.connect(self._copy_current_table)
        btn_row.addWidget(self.btn_copy)
        btn_row.addStretch()
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_close)
        layout.addLayout(btn_row)

        # 初始化抽测表
        self.refresh_sample_table()

    # -------------------- 抽测模式页 --------------------
    def _build_sample_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("命令字:"))
        self.cb_cmd = QComboBox()
        self.cb_cmd.addItem("4041 模拟量输入", "4041")
        self.cb_cmd.addItem("4143 模块状态", "4143")
        self.cb_cmd.addItem("4044 告警", "4044")
        self.cb_cmd.addItem("4241 模拟量输出", "4241")
        # 默认选中 4044
        self.cb_cmd.setCurrentIndex(2)
        self.cb_cmd.currentIndexChanged.connect(self.on_sample_cmd_changed)
        top_row.addWidget(self.cb_cmd)
        top_row.addStretch()

        self.lbl_sample_status = QLabel("")
        self.lbl_sample_status.setStyleSheet("color: gray;")
        top_row.addWidget(self.lbl_sample_status)
        layout.addLayout(top_row)

        self.table_sample = QTableWidget()
        self.table_sample.setColumnCount(3)
        self.table_sample.setHorizontalHeaderLabels(["序号", "名称", "校验结果"])
        self.table_sample.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_sample.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_sample.setAlternatingRowColors(True)
        self.table_sample.verticalHeader().setVisible(False)
        self.table_sample.setFont(QFont("Microsoft YaHei", 10))
        hdr = self.table_sample.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(self.table_sample)

        return tab

    def on_sample_cmd_changed(self):
        # 切换命令字 → 清空列表并重新加载
        self.refresh_sample_table()

    def _stop_sample_worker(self):
        if self.worker_sample is not None:
            try:
                self.worker_sample.stop()
                self.worker_sample.wait(3000)
            except Exception:
                pass
            self.worker_sample = None

    def refresh_sample_table(self):
        # 停止旧线程
        self._stop_sample_worker()

        # 清空列表
        self.table_sample.setRowCount(0)

        cmd = self.cb_cmd.currentData()
        positions = self.mw.sample_positions.get(cmd, []) or []
        count = self.mw._get_count(cmd)
        names = self.mw._get_point_names(cmd, count)

        if not positions:
            self.lbl_sample_status.setText(f"{cmd} {self.CMD_LABELS[cmd]}：暂无抽取信息")
            return

        self.table_sample.setRowCount(len(positions))
        for i, p in enumerate(positions):
            name = names[p] if p < len(names) else f"点{p+1}"
            item_idx = QTableWidgetItem(str(p + 1))
            item_idx.setTextAlignment(Qt.AlignCenter)
            item_name = QTableWidgetItem(name)
            item_status = QTableWidgetItem("")
            self.table_sample.setItem(i, 0, item_idx)
            self.table_sample.setItem(i, 1, item_name)
            self.table_sample.setItem(i, 2, item_status)

            if cmd == '4044':
                item_status.setText("正在校验中")
                item_status.setForeground(QColor("blue"))
                item_status.setTextAlignment(Qt.AlignCenter)

        if cmd == '4044':
            self._start_sample_validate(positions, names)
        else:
            self.lbl_sample_status.setText(
                f"{cmd} {self.CMD_LABELS[cmd]}：共抽取 {len(positions)} 项（无需校验）"
            )

    def _start_sample_validate(self, positions, names):
        if self.mw.current_station_no is None:
            for i in range(self.table_sample.rowCount()):
                it = self.table_sample.item(i, 2)
                if it is not None:
                    it.setText("未获取到站点编号")
                    it.setForeground(QColor("gray"))
            self.lbl_sample_status.setText("无法校验：未获取到站点编号 station_no")
            return

        db_host = self.mw.cb_target_ip.currentText().strip()
        if not db_host:
            self.lbl_sample_status.setText("无法校验：目标 IP 为空")
            return

        items = []
        for i, p in enumerate(positions):
            name = names[p] if p < len(names) else f"点{p+1}"
            items.append((i, name))

        self.lbl_sample_status.setText(f"4044 告警：正在逐条校验 {len(items)} 项...")

        self.worker_sample = ValidateWorker(db_host, self.mw.current_station_no, items)
        self.worker_sample.row_status.connect(self._on_sample_row_status)
        self.worker_sample.done.connect(self._on_sample_done)
        self.worker_sample.start()

    def _on_sample_row_status(self, row_idx, status):
        if row_idx >= self.table_sample.rowCount():
            return
        item = self.table_sample.item(row_idx, 2)
        if item is None:
            item = QTableWidgetItem()
            item.setTextAlignment(Qt.AlignCenter)
            self.table_sample.setItem(row_idx, 2, item)
        if status == 'pass':
            item.setText("通过")
            item.setForeground(QColor("green"))
        else:
            item.setText("不通过")
            item.setForeground(QColor("red"))

    def _on_sample_done(self):
        pass_n = fail_n = 0
        for r in range(self.table_sample.rowCount()):
            it = self.table_sample.item(r, 2)
            if it is None:
                continue
            if it.text() == "通过":
                pass_n += 1
            elif it.text() == "不通过":
                fail_n += 1
        self.lbl_sample_status.setText(
            f"4044 告警：校验完成，通过 {pass_n}，不通过 {fail_n}"
        )

    # -------------------- 全量模式页 --------------------
    def _build_full_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top_row = QHBoxLayout()
        info = QLabel("全量模式：仅适用于 4044 告警，逐条 SQL 校验全部告警点")
        info.setStyleSheet("color: gray;")
        top_row.addWidget(info)
        top_row.addStretch()

        self.btn_full_revalidate = QPushButton("重新校验")
        self.btn_full_revalidate.clicked.connect(self.start_full_validate)
        top_row.addWidget(self.btn_full_revalidate)

        self.lbl_full_status = QLabel("")
        self.lbl_full_status.setStyleSheet("color: gray;")
        top_row.addWidget(self.lbl_full_status)
        layout.addLayout(top_row)

        self.table_full = QTableWidget()
        self.table_full.setColumnCount(3)
        self.table_full.setHorizontalHeaderLabels(["序号", "名称", "校验结果"])
        self.table_full.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_full.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_full.setAlternatingRowColors(True)
        self.table_full.verticalHeader().setVisible(False)
        self.table_full.setFont(QFont("Microsoft YaHei", 10))
        hdr = self.table_full.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(self.table_full)

        return tab

    def _on_tab_changed(self, idx):
        # 首次切到全量模式时自动开始校验
        if idx == 1 and not self._full_started:
            self._full_started = True
            self.start_full_validate()

    def _stop_full_worker(self):
        if self.worker_full is not None:
            try:
                self.worker_full.stop()
                self.worker_full.wait(3000)
            except Exception:
                pass
            self.worker_full = None

    def start_full_validate(self):
        self._stop_full_worker()
        self.table_full.setRowCount(0)

        count = self.mw.spin_4044_count.value()
        if count <= 0:
            self.lbl_full_status.setText("4044 告警数量为 0")
            return

        names = self.mw._get_point_names('4044', count)

        self.table_full.setRowCount(count)
        for i in range(count):
            item_idx = QTableWidgetItem(str(i + 1))
            item_idx.setTextAlignment(Qt.AlignCenter)
            item_name = QTableWidgetItem(names[i])
            item_status = QTableWidgetItem("正在校验中")
            item_status.setForeground(QColor("blue"))
            item_status.setTextAlignment(Qt.AlignCenter)
            self.table_full.setItem(i, 0, item_idx)
            self.table_full.setItem(i, 1, item_name)
            self.table_full.setItem(i, 2, item_status)

        if self.mw.current_station_no is None:
            for i in range(count):
                it = self.table_full.item(i, 2)
                it.setText("未获取到站点编号")
                it.setForeground(QColor("gray"))
            self.lbl_full_status.setText("无法校验：未获取到站点编号 station_no")
            return

        db_host = self.mw.cb_target_ip.currentText().strip()
        if not db_host:
            self.lbl_full_status.setText("无法校验：目标 IP 为空")
            return

        items = [(i, names[i]) for i in range(count)]
        self.lbl_full_status.setText(f"正在逐条校验 {count} 项...")

        self.worker_full = ValidateWorker(db_host, self.mw.current_station_no, items)
        self.worker_full.row_status.connect(self._on_full_row_status)
        self.worker_full.done.connect(self._on_full_done)
        self.worker_full.start()

    def _on_full_row_status(self, row_idx, status):
        if row_idx >= self.table_full.rowCount():
            return
        item = self.table_full.item(row_idx, 2)
        if item is None:
            item = QTableWidgetItem()
            item.setTextAlignment(Qt.AlignCenter)
            self.table_full.setItem(row_idx, 2, item)
        if status == 'pass':
            item.setText("通过")
            item.setForeground(QColor("green"))
        else:
            item.setText("不通过")
            item.setForeground(QColor("red"))

    def _on_full_done(self):
        pass_n = fail_n = 0
        for r in range(self.table_full.rowCount()):
            it = self.table_full.item(r, 2)
            if it is None:
                continue
            if it.text() == "通过":
                pass_n += 1
            elif it.text() == "不通过":
                fail_n += 1
        self.lbl_full_status.setText(f"校验完成：通过 {pass_n}，不通过 {fail_n}")

    # -------------------- 通用 --------------------
    def _copy_current_table(self):
        idx = self.tabs.currentIndex()
        table = self.table_sample if idx == 0 else self.table_full
        headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
        lines = ["\t".join(headers)]
        for r in range(table.rowCount()):
            row_data = []
            for c in range(table.columnCount()):
                it = table.item(r, c)
                row_data.append(it.text() if it else "")
            lines.append("\t".join(row_data))
        QApplication.clipboard().setText("\n".join(lines))
        self.mw.log_message("已复制当前表格内容到剪贴板", "info")

    def closeEvent(self, event):
        self._stop_sample_worker()
        self._stop_full_worker()
        event.accept()

# ==================== 主窗口 ====================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("津宇嘉信2-报文模拟工具 (码位表自动加载 + 抽测模式)")
        self.setWindowIcon(create_logo())
        self.resize(1150, 800)
        self.setMinimumSize(1000, 700)

        self.settings = QSettings("BDMS", "报文生成器")
        self.site_data = {}
        self.current_file = None
        self.all_file_items = []
        self.current_station_no = None

        self.sample_mode = False
        self.sample_ratio = 33
        self.sample_positions = {
            '4041': [],
            '4143': [],
            '4044': [],
            '4241': [],
        }

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)

        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(6)

        # 左侧：文件列表
        left_widget = QWidget()
        left_widget.setFixedWidth(260)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(3)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("模糊搜索站点...")
        self.search_edit.textChanged.connect(self.filter_site_list)
        left_layout.addWidget(self.search_edit)

        self.list_sites = QListWidget()
        self.list_sites.setSelectionMode(QListWidget.SingleSelection)
        self.list_sites.itemClicked.connect(self.on_site_selected)
        self.list_sites.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.list_sites.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_layout.addWidget(self.list_sites)

        btn_layout = QHBoxLayout()
        self.btn_load = QPushButton("加载文件")
        self.btn_load.clicked.connect(self.load_site_file)
        btn_layout.addWidget(self.btn_load)
        self.btn_folder = QPushButton("选择文件夹")
        self.btn_folder.clicked.connect(self.select_folder)
        btn_layout.addWidget(self.btn_folder)
        self.btn_scan = QPushButton("扫描目录")
        self.btn_scan.clicked.connect(self.scan_current_dir)
        btn_layout.addWidget(self.btn_scan)
        left_layout.addLayout(btn_layout)
        top_layout.addWidget(left_widget)

        # 右侧：标签页
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        # ---- 抽测模式工具条 ----
        sample_bar = QHBoxLayout()
        sample_bar.setContentsMargins(0, 0, 0, 0)
        sample_bar.setSpacing(6)
        self.cb_sample_mode = QCheckBox("抽测模式")
        self.cb_sample_mode.setToolTip(
            "开启后：模拟量默认 0，报警默认恢复，模块默认正常；\n"
            "点击各页“随机抽取”按钮生成抽测点，位置均匀分布"
        )
        sample_bar.addWidget(self.cb_sample_mode)

        sample_bar.addWidget(QLabel("抽取比例:"))
        self.spin_sample_ratio = QSpinBox()
        self.spin_sample_ratio.setRange(1, 100)
        self.spin_sample_ratio.setValue(33)
        self.spin_sample_ratio.setSuffix(" %")
        self.spin_sample_ratio.setToolTip("抽取数量 = 点数 × 比例（四舍五入，至少 1 个，不超过总点数）")
        sample_bar.addWidget(self.spin_sample_ratio)

        self.btn_view_sample = QPushButton("查看抽取信息")
        self.btn_view_sample.setToolTip(
            "打开抽测信息/校验对话框：\n"
            " - 抽测模式页：选择命令字，查看抽测项；4044 逐条 SQL 校验\n"
            " - 全量模式页：仅 4044，校验全量报警"
        )
        self.btn_view_sample.clicked.connect(self.show_sample_info)
        sample_bar.addWidget(self.btn_view_sample)

        sample_bar.addWidget(QLabel("|"))
        self.lbl_sample_hint = QLabel(
            "抽测：模拟量默认 0 / 报警默认恢复 / 模块默认正常，4043 不参与抽测"
        )
        self.lbl_sample_hint.setStyleSheet("color: gray;")
        sample_bar.addWidget(self.lbl_sample_hint)
        sample_bar.addStretch()
        right_layout.addLayout(sample_bar)

        self.tabs = QTabWidget()
        self.tab_4041 = QWidget()
        self.tab_4043 = QWidget()
        self.tab_4143 = QWidget()
        self.tab_4044 = QWidget()
        self.tab_4241 = QWidget()

        self.tabs.addTab(self.tab_4041, "命令字 4041 (模拟量输入)")
        self.tabs.addTab(self.tab_4043, "命令字 4043 (接触器状态)")
        self.tabs.addTab(self.tab_4143, "命令字 4143 (模块状态)")
        self.tabs.addTab(self.tab_4044, "命令字 4044 (告警)")
        self.tabs.addTab(self.tab_4241, "命令字 4241 (模拟量输出)")

        self.init_tab_4041()
        self.init_tab_4043()
        self.init_tab_4143()
        self.init_tab_4044()
        self.init_tab_4241()

        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.tabs.currentChanged.connect(lambda: self.tabs.updateGeometry())
        right_layout.addWidget(self.tabs)

        self.cb_sample_mode.stateChanged.connect(self.on_sample_mode_toggled)
        self.spin_sample_ratio.valueChanged.connect(self.on_sample_ratio_changed)

        # 底部报文操作
        bottom_group = QGroupBox("报文操作")
        bottom_layout = QVBoxLayout(bottom_group)
        bottom_layout.setContentsMargins(6, 6, 6, 6)
        bottom_layout.setSpacing(4)

        udp_group = QGroupBox("UDP 连续发送")
        udp_layout = QFormLayout(udp_group)
        udp_layout.setLabelAlignment(Qt.AlignRight)
        udp_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        udp_layout.setSpacing(3)
        udp_layout.setContentsMargins(6, 6, 6, 6)

        self.cb_target_ip = QComboBox()
        self.cb_target_ip.setEditable(True)
        self.cb_target_ip.setInsertPolicy(QComboBox.InsertAtTop)
        history = self.settings.value("udp_history", [])
        if isinstance(history, str):
            history = [history]
        for ip in history:
            self.cb_target_ip.addItem(ip)
        if history:
            self.cb_target_ip.setCurrentText(history[-1])
        udp_layout.addRow("目标 IP:", self.cb_target_ip)

        self.le_local_ip = QLineEdit()
        self.le_local_ip.setPlaceholderText("选择站点后自动填充")
        udp_layout.addRow("本机 IP:", self.le_local_ip)

        self.spin_port = QSpinBox()
        self.spin_port.setRange(1, 65535)
        self.spin_port.setValue(10030)
        udp_layout.addRow("目标端口:", self.spin_port)

        self.dspin_interval = QDoubleSpinBox()
        self.dspin_interval.setRange(0.1, 60.0)
        self.dspin_interval.setSingleStep(0.1)
        self.dspin_interval.setValue(1.0)
        self.dspin_interval.setSuffix(" 秒")
        udp_layout.addRow("发送间隔:", self.dspin_interval)

        self.btn_start_stop = QPushButton("开始发送")
        self.btn_start_stop.clicked.connect(self.toggle_send)
        udp_layout.addRow(self.btn_start_stop)

        bottom_layout.addWidget(udp_group)

        self.hex_output = QTextEdit()
        self.hex_output.setFont(QFont("Courier New", 10))
        self.hex_output.setReadOnly(True)
        self.hex_output.setMinimumHeight(100)
        bottom_layout.addWidget(self.hex_output)

        btn_layout2 = QHBoxLayout()
        self.copy_btn = QPushButton("复制报文")
        self.copy_btn.clicked.connect(self.copy_hex)
        btn_layout2.addWidget(self.copy_btn)
        btn_layout2.addStretch()
        bottom_layout.addLayout(btn_layout2)

        right_layout.addWidget(bottom_group)

        # 运行日志区
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setMinimumHeight(120)
        log_layout.addWidget(self.log_text)
        right_layout.addWidget(log_group)

        top_layout.addWidget(right_widget)
        main_layout.addWidget(top_widget)

        self.current_message = b''
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.udp_send_once)
        self.is_sending = False
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.log_message("程序启动，正在扫描当前目录...", "info")
        self.scan_current_dir()

    # ---------- 日志 ----------
    def log_message(self, msg: str, level: str = "info"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        color_map = {
            "info": "black",
            "warning": "orange",
            "error": "red",
            "sample": "#0066CC"
        }
        color = color_map.get(level, "black")
        formatted = f'<span style="color:gray;">[{timestamp}]</span> <span style="color:{color};">{msg}</span>'
        self.log_text.append(formatted)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    # ---------- 点名称 ----------
    def _get_point_names(self, cmd: str, count: int):
        pts = (self.site_data.get(cmd, {}) or {}).get('points', []) or []
        names = []
        for i in range(count):
            nm = ''
            if i < len(pts):
                nm = pts[i].get('name', '') or ''
            names.append(nm if nm else f"点{i+1}")
        return names

    # ---------- 查看抽取信息 / 校验对话框 ----------
    def show_sample_info(self):
        dialog = SampleInfoDialog(self)
        dialog.exec()

    # ---------- 抽测模式 ----------
    def on_sample_mode_toggled(self, state):
        self.sample_mode = bool(state)
        for btn in (self.btn_sample_4041, self.btn_sample_4143,
                    self.btn_sample_4044, self.btn_sample_4241):
            btn.setEnabled(self.sample_mode)

        if not self.sample_mode:
            for k in self.sample_positions:
                self.sample_positions[k] = []
            for lbl in (self.lbl_4041_sample, self.lbl_4143_sample,
                        self.lbl_4044_sample, self.lbl_4241_sample):
                lbl.setText("未抽取")
            self.log_message("抽测模式已关闭，恢复全量随机报文", "info")
        else:
            self.log_message(
                f"抽测模式已开启（抽取比例 {self.spin_sample_ratio.value()}%）："
                "模拟量默认 0，告警默认恢复，模块默认正常；"
                "点击各页“随机抽取”按钮生成抽测点（4043 不参与）", "info"
            )
        self.update_current_tab_message()

    def on_sample_ratio_changed(self, value):
        self.sample_ratio = value
        if self.sample_mode:
            self.log_message(f"抽取比例已更新为 {value}%，点击“随机抽取”按钮重新抽取", "info")

    def _get_count(self, cmd: str) -> int:
        if cmd == '4041':
            return self.spin_4041_count.value()
        if cmd == '4143':
            return self.spin_4143_count.value()
        if cmd == '4044':
            return self.spin_4044_count.value()
        if cmd == '4241':
            return self.spin_4241_count.value()
        return 0

    def do_sample(self, cmd: str):
        count = self._get_count(cmd)
        if count <= 0:
            return
        ratio = self.spin_sample_ratio.value() / 100.0
        k = int(round(count * ratio))
        k = max(1, min(k, count))
        positions = pick_uniform_positions(count, k)
        self.sample_positions[cmd] = positions

        names = self._get_point_names(cmd, count)

        labels = {
            '4041': '模拟量输入',
            '4143': '模块状态',
            '4044': '告警',
            '4241': '模拟量输出',
        }
        items = [f"{p+1}({names[p]})" for p in positions]
        detail = ', '.join(items)

        self.log_message(
            f"【抽测】{cmd} {labels.get(cmd, '')}：共 {count} 个点，"
            f"按 {self.spin_sample_ratio.value()}% 抽取 {len(positions)} 个；"
            f"抽中：{detail}",
            "sample"
        )

        lbl = getattr(self, f'lbl_{cmd}_sample', None)
        if lbl is not None:
            show = detail if len(detail) <= 90 else detail[:87] + '...'
            lbl.setText(f"已抽 {len(positions)}/{count}：{show}")

        self.update_current_tab_message()

    def reset_sample_if_needed(self, cmd: str):
        if self.sample_positions.get(cmd):
            self.sample_positions[cmd] = []
            lbl = getattr(self, f'lbl_{cmd}_sample', None)
            if lbl is not None:
                lbl.setText("未抽取")
            self.log_message(f"[{cmd}] 点数已变化，抽测位置已重置，请重新点击“随机抽取”", "warning")

    # ---------- 自动填充本机 IP + station_no ----------
    def auto_fill_local_ip_from_db(self, filepath):
        if not HAS_PYMYSQL:
            msg = "缺少 pymysql 库，无法自动获取本机 IP。请运行 pip install pymysql"
            self.log_message(msg, "warning")
            self.statusBar().showMessage(msg, 5000)
            return
        db_host = self.cb_target_ip.currentText().strip()
        if not db_host:
            msg = "目标 IP 为空，无法连接数据库，请手动填写本机 IP"
            self.log_message(msg, "warning")
            self.statusBar().showMessage(msg, 5000)
            return
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        match = re.search(r'-([^\-]+?)码位表', base_name)
        if match:
            keyword = match.group(1)
        else:
            parts = base_name.rsplit('-', 1)
            if len(parts) > 1:
                keyword = parts[0].split('-')[-1]
            else:
                keyword = base_name
        keyword = re.sub(r'V\d+\.\d+\.\d+.*', '', keyword).strip()
        if not keyword:
            keyword = base_name
        self.log_message(f"正在从数据库匹配站点关键词：{keyword} ...", "info")
        try:
            connection = pymysql.connect(
                host=db_host,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                charset='utf8',
                connect_timeout=DB_TIMEOUT
            )
            with connection.cursor() as cursor:
                sql = """
                    SELECT b.STATION_NO, IP, STATION_NAME
                    FROM dic_mss_netaddress_config a
                    RIGHT JOIN dic_station b ON a.STATION_NO = b.STATION_NO
                    WHERE a.SYS_NO = 6
                      AND a.MASTER = 1
                      AND STATION_NAME LIKE %s
                """
                cursor.execute(sql, (f'%{keyword}%',))
                result = cursor.fetchone()
                if result and result[1]:
                    ip = result[1]
                    self.le_local_ip.setText(ip)
                    self.current_station_no = result[0]
                    msg = f"本机 IP 已自动填入：{ip}（匹配站点：{result[2]}，站点编号：{result[0]}）"
                    self.log_message(msg, "info")
                    self.statusBar().showMessage(msg, 5000)
                else:
                    self.current_station_no = None
                    msg = f"未找到站点名包含“{keyword}”的记录，请手动填写 IP"
                    self.log_message(msg, "warning")
                    self.statusBar().showMessage(msg, 8000)
            connection.close()
        except Exception as e:
            msg = f"数据库查询失败：{e}"
            self.log_message(msg, "error")
            self.statusBar().showMessage(msg, 8000)

    # ---------- 站点列表操作 ----------
    def scan_current_dir(self):
        files = [f for f in os.listdir('.') if f.endswith(('.xlsx', '.xls')) and os.path.isfile(f)]
        self._populate_site_list(files)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择包含码位表的文件夹")
        if not folder:
            return
        try:
            files = [f for f in os.listdir(folder) if f.endswith(('.xlsx', '.xls')) and os.path.isfile(os.path.join(folder, f))]
            full_paths = [os.path.join(folder, f) for f in files]
            self._populate_site_list(full_paths)
        except Exception as e:
            self.log_message(f"读取文件夹失败：{e}", "error")
            QMessageBox.critical(self, "扫描错误", f"无法读取文件夹：{e}")

    def _populate_site_list(self, file_list):
        self.list_sites.clear()
        self.all_file_items = []
        valid_paths = []
        for item in file_list:
            if os.path.isabs(item) and os.path.exists(item):
                valid_paths.append(item)
            else:
                local_path = os.path.join('.', item)
                if os.path.exists(local_path):
                    valid_paths.append(local_path)
        if not valid_paths:
            item = QListWidgetItem("（未找到有效文件）")
            item.setFlags(Qt.NoItemFlags)
            self.list_sites.addItem(item)
            return
        for path in sorted(valid_paths, key=lambda p: os.path.basename(p)):
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.UserRole, path)
            self.list_sites.addItem(item)
            self.all_file_items.append(item)
        if self.list_sites.count() > 0:
            self.list_sites.setCurrentRow(0)
            self.on_site_selected(self.list_sites.item(0))

    def filter_site_list(self, text):
        text = text.strip().lower()
        for item in self.all_file_items:
            if text == "":
                item.setHidden(False)
            else:
                matched = text in item.text().lower()
                item.setHidden(not matched)
        current = self.list_sites.currentItem()
        if current and current.isHidden():
            for i in range(self.list_sites.count()):
                if not self.list_sites.item(i).isHidden():
                    self.list_sites.setCurrentRow(i)
                    self.on_site_selected(self.list_sites.item(i))
                    break

    def on_site_selected(self, item):
        if not item:
            return
        file_path = item.data(Qt.UserRole)
        if not file_path or not os.path.exists(file_path):
            return
        self.load_and_apply_site(file_path)

    def load_site_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "选择码位表文件", "", "Excel Files (*.xlsx *.xls)")
        if filepath:
            for item in self.all_file_items:
                if item.data(Qt.UserRole) == filepath:
                    self.list_sites.setCurrentItem(item)
                    self.on_site_selected(item)
                    return
            item = QListWidgetItem(os.path.basename(filepath))
            item.setData(Qt.UserRole, filepath)
            self.list_sites.addItem(item)
            self.all_file_items.append(item)
            self.list_sites.setCurrentItem(item)
            self.load_and_apply_site(filepath)

    def load_and_apply_site(self, filepath):
        try:
            data = parse_station_file(filepath)
            self.site_data = data
            self.current_file = filepath
            self.apply_site_config()
            msg = f"已加载站点文件：{os.path.basename(filepath)}"
            self.log_message(msg, "info")
            self.statusBar().showMessage(msg, 3000)
        except Exception as e:
            msg = f"解析文件出错：{e}"
            self.log_message(msg, "error")
            QMessageBox.critical(self, "加载失败", msg)
        finally:
            self.update_current_tab_message()
            self.auto_fill_local_ip_from_db(filepath)

    def apply_site_config(self):
        if '4041' in self.site_data:
            self.spin_4041_count.setValue(self.site_data['4041']['count'])
        if '4043' in self.site_data:
            self.spin_4043_count.setValue(self.site_data['4043']['count'])
        if '4241' in self.site_data:
            self.spin_4241_count.setValue(self.site_data['4241']['count'])
        if '4143' in self.site_data:
            self.spin_4143_count.setValue(self.site_data['4143']['count'])
        if '4044' in self.site_data:
            self.spin_4044_count.setValue(self.site_data['4044']['count'])
        for cmd in ('4041', '4143', '4044', '4241'):
            self.reset_sample_if_needed(cmd)
        self.update_current_tab_message()

    # ---------- 标签页 4041 ----------
    def init_tab_4041(self):
        layout = QVBoxLayout(self.tab_4041)
        layout.setContentsMargins(6, 6, 6, 6)
        form = QFormLayout()
        form.setVerticalSpacing(6)

        self.cb_4041_type = QComboBox()
        self.cb_4041_type.addItem("单相 (0x01)", 0x01)
        self.cb_4041_type.addItem("三相 (0x03)", 0x03)
        self.cb_4041_type.currentIndexChanged.connect(self.on_4041_param_changed)
        form.addRow("输入类型:", self.cb_4041_type)

        self.spin_4041_count = QSpinBox()
        self.spin_4041_count.setRange(1, 65535)
        self.spin_4041_count.setValue(2)
        self.spin_4041_count.valueChanged.connect(self.on_4041_param_changed)
        self.spin_4041_count.valueChanged.connect(lambda v: self.on_count_changed('4041'))
        form.addRow("设备数量 (模拟量点数):", self.spin_4041_count)

        self.ds_4041_min = QDoubleSpinBox()
        self.ds_4041_min.setRange(-10000, 10000)
        self.ds_4041_min.setValue(200.0)
        self.ds_4041_min.valueChanged.connect(self.on_4041_param_changed)
        self.ds_4041_max = QDoubleSpinBox()
        self.ds_4041_max.setRange(-10000, 10000)
        self.ds_4041_max.setValue(400.0)
        self.ds_4041_max.valueChanged.connect(self.on_4041_param_changed)
        h = QHBoxLayout()
        h.setSpacing(4)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(QLabel("最小值"))
        h.addWidget(self.ds_4041_min)
        h.addWidget(QLabel("最大值"))
        h.addWidget(self.ds_4041_max)
        h.addStretch()
        form.addRow("全局范围 (未加载站点时使用):", h)

        self.cb_4041_use_site = QCheckBox("使用站点每个点的独立范围 (加载后自动启用)")
        self.cb_4041_use_site.setChecked(True)
        self.cb_4041_use_site.stateChanged.connect(self.on_4041_param_changed)
        form.addRow(self.cb_4041_use_site)

        layout.addLayout(form)

        sample_row = QHBoxLayout()
        sample_row.setSpacing(6)
        self.btn_sample_4041 = QPushButton("随机抽取模拟量")
        self.btn_sample_4041.setEnabled(False)
        self.btn_sample_4041.clicked.connect(lambda: self.do_sample('4041'))
        sample_row.addWidget(self.btn_sample_4041)
        self.lbl_4041_sample = QLabel("未抽取")
        self.lbl_4041_sample.setStyleSheet("color: #0066CC;")
        self.lbl_4041_sample.setWordWrap(True)
        sample_row.addWidget(self.lbl_4041_sample, 1)
        layout.addLayout(sample_row)

    def on_4041_param_changed(self):
        if self.tabs.currentIndex() == 0:
            self.update_current_tab_message()

    def on_count_changed(self, cmd):
        self.reset_sample_if_needed(cmd)
        self.update_current_tab_message()

    # ---------- 标签页 4043 ----------
    def init_tab_4043(self):
        layout = QVBoxLayout(self.tab_4043)
        layout.setContentsMargins(6, 6, 6, 6)
        form = QFormLayout()
        form.setVerticalSpacing(6)

        self.spin_4043_count = QSpinBox()
        self.spin_4043_count.setRange(1, 65535)
        self.spin_4043_count.setValue(4)
        self.spin_4043_count.valueChanged.connect(self.on_4043_param_changed)
        form.addRow("接触器数量:", self.spin_4043_count)

        self.cb_4043_mode = QComboBox()
        self.cb_4043_mode.addItem("全部闭合 (00)", 0x00)
        self.cb_4043_mode.addItem("全部断开 (05)", 0x05)
        self.cb_4043_mode.addItem("随机混合", -1)
        self.cb_4043_mode.currentIndexChanged.connect(self.on_4043_param_changed)
        form.addRow("状态模式:", self.cb_4043_mode)

        layout.addLayout(form)

        tip = QLabel("（4043 不参与抽测模式，始终按上方设置生成全量报文）")
        tip.setStyleSheet("color: gray;")
        layout.addWidget(tip)

    def on_4043_param_changed(self):
        if self.tabs.currentIndex() == 1:
            self.update_current_tab_message()

    # ---------- 标签页 4143 ----------
    def init_tab_4143(self):
        layout = QVBoxLayout(self.tab_4143)
        layout.setContentsMargins(6, 6, 6, 6)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self.spin_4143_count = QSpinBox()
        self.spin_4143_count.setRange(1, 255)
        self.spin_4143_count.setValue(8)
        self.spin_4143_count.valueChanged.connect(self.on_4143_param_changed)
        self.spin_4143_count.valueChanged.connect(lambda v: self.on_count_changed('4143'))
        form.addRow("模块个数:", self.spin_4143_count)
        self.cb_4143_work = QComboBox()
        self.cb_4143_work.addItem("工作 (0xE3)", 0xE3)
        self.cb_4143_work.addItem("备用 (0xE4)", 0xE4)
        self.cb_4143_work.currentIndexChanged.connect(self.on_4143_param_changed)
        form.addRow("工作状态:", self.cb_4143_work)
        self.cb_4143_fault = QComboBox()
        self.cb_4143_fault.addItem("正常 (0x00)", 0x00)
        self.cb_4143_fault.addItem("故障 (0x01)", 0x01)
        self.cb_4143_fault.currentIndexChanged.connect(self.on_4143_param_changed)
        form.addRow("故障状态:", self.cb_4143_fault)
        self.cb_4143_protect = QComboBox()
        self.cb_4143_protect.addItem("工作 (0x00)", 0x00)
        self.cb_4143_protect.addItem("保护 (0x02)", 0x02)
        self.cb_4143_protect.currentIndexChanged.connect(self.on_4143_param_changed)
        form.addRow("保护状态:", self.cb_4143_protect)
        self.cb_4143_comm = QComboBox()
        self.cb_4143_comm.addItem("正常 (0x00)", 0x00)
        self.cb_4143_comm.addItem("中断 (0xE2)", 0xE2)
        self.cb_4143_comm.currentIndexChanged.connect(self.on_4143_param_changed)
        form.addRow("通信状态:", self.cb_4143_comm)
        layout.addLayout(form)

        sample_row = QHBoxLayout()
        sample_row.setSpacing(6)
        self.btn_sample_4143 = QPushButton("随机抽取模块")
        self.btn_sample_4143.setEnabled(False)
        self.btn_sample_4143.clicked.connect(lambda: self.do_sample('4143'))
        sample_row.addWidget(self.btn_sample_4143)
        self.lbl_4143_sample = QLabel("未抽取")
        self.lbl_4143_sample.setStyleSheet("color: #0066CC;")
        self.lbl_4143_sample.setWordWrap(True)
        sample_row.addWidget(self.lbl_4143_sample, 1)
        layout.addLayout(sample_row)

    def on_4143_param_changed(self):
        if self.tabs.currentIndex() == 2:
            self.update_current_tab_message()

    # ---------- 标签页 4044 ----------
    def init_tab_4044(self):
        layout = QVBoxLayout(self.tab_4044)
        layout.setContentsMargins(6, 6, 6, 6)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self.cb_4044_type = QComboBox()
        self.cb_4044_type.addItems(["单相 (0x01)", "三相 (0x03)"])
        self.cb_4044_type.currentIndexChanged.connect(self.on_4044_param_changed)
        form.addRow("输入类型:", self.cb_4044_type)
        self.spin_4044_count = QSpinBox()
        self.spin_4044_count.setRange(1, 65535)
        self.spin_4044_count.setValue(256)
        self.spin_4044_count.valueChanged.connect(self.on_4044_param_changed)
        self.spin_4044_count.valueChanged.connect(lambda v: self.on_count_changed('4044'))
        form.addRow("告警数量:", self.spin_4044_count)
        self.cb_4044_alarm = QComboBox()
        self.cb_4044_alarm.addItem("恢复 (0x00)", 0x00)
        self.cb_4044_alarm.addItem("告警 (0x05)", 0x05)
        self.cb_4044_alarm.currentIndexChanged.connect(self.on_4044_param_changed)
        form.addRow("告警状态:", self.cb_4044_alarm)
        layout.addLayout(form)

        # 只保留“随机抽取报警”，数据校验按钮已移除
        sample_row = QHBoxLayout()
        sample_row.setSpacing(6)
        self.btn_sample_4044 = QPushButton("随机抽取报警")
        self.btn_sample_4044.setEnabled(False)
        self.btn_sample_4044.clicked.connect(lambda: self.do_sample('4044'))
        sample_row.addWidget(self.btn_sample_4044)

        self.lbl_4044_sample = QLabel("未抽取")
        self.lbl_4044_sample.setStyleSheet("color: #0066CC;")
        self.lbl_4044_sample.setWordWrap(True)
        sample_row.addWidget(self.lbl_4044_sample, 1)
        layout.addLayout(sample_row)

        tip = QLabel("（数据校验请点击顶部“查看抽取信息” → 抽测模式 / 全量模式）")
        tip.setStyleSheet("color: gray;")
        layout.addWidget(tip)

    def on_4044_param_changed(self):
        if self.tabs.currentIndex() == 3:
            self.update_current_tab_message()

    # ---------- 标签页 4241 ----------
    def init_tab_4241(self):
        layout = QVBoxLayout(self.tab_4241)
        layout.setContentsMargins(6, 6, 6, 6)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        self.spin_4241_count = QSpinBox()
        self.spin_4241_count.setRange(1, 65535)
        self.spin_4241_count.setValue(213)
        self.spin_4241_count.valueChanged.connect(self.on_4241_param_changed)
        self.spin_4241_count.valueChanged.connect(lambda v: self.on_count_changed('4241'))
        form.addRow("浮点数个数:", self.spin_4241_count)
        self.ds_4241_min = QDoubleSpinBox()
        self.ds_4241_min.setRange(-10000, 10000)
        self.ds_4241_min.setValue(0.0)
        self.ds_4241_min.valueChanged.connect(self.on_4241_param_changed)
        self.ds_4241_max = QDoubleSpinBox()
        self.ds_4241_max.setRange(-10000, 10000)
        self.ds_4241_max.setValue(50.0)
        self.ds_4241_max.valueChanged.connect(self.on_4241_param_changed)
        h = QHBoxLayout()
        h.setSpacing(4)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(QLabel("最小值"))
        h.addWidget(self.ds_4241_min)
        h.addWidget(QLabel("最大值"))
        h.addWidget(self.ds_4241_max)
        h.addStretch()
        form.addRow("全局范围 (未加载站点时使用):", h)
        self.cb_4241_use_site = QCheckBox("使用站点每个点的独立范围 (加载后自动启用)")
        self.cb_4241_use_site.setChecked(True)
        self.cb_4241_use_site.stateChanged.connect(self.on_4241_param_changed)
        form.addRow(self.cb_4241_use_site)
        layout.addLayout(form)

        sample_row = QHBoxLayout()
        sample_row.setSpacing(6)
        self.btn_sample_4241 = QPushButton("随机抽取模拟量")
        self.btn_sample_4241.setEnabled(False)
        self.btn_sample_4241.clicked.connect(lambda: self.do_sample('4241'))
        sample_row.addWidget(self.btn_sample_4241)
        self.lbl_4241_sample = QLabel("未抽取")
        self.lbl_4241_sample.setStyleSheet("color: #0066CC;")
        self.lbl_4241_sample.setWordWrap(True)
        sample_row.addWidget(self.lbl_4241_sample, 1)
        layout.addLayout(sample_row)

    def on_4241_param_changed(self):
        if self.tabs.currentIndex() == 4:
            self.update_current_tab_message()

    # ---------- 更新报文 ----------
    def update_current_tab_message(self):
        idx = self.tabs.currentIndex()
        try:
            if idx == 0:  # 4041
                count = self.spin_4041_count.value()
                input_type = self.cb_4041_type.currentData()
                if self.sample_mode:
                    positions = set(self.sample_positions.get('4041', []))
                    minv = self.ds_4041_min.value()
                    maxv = self.ds_4041_max.value()
                    if minv > maxv:
                        minv, maxv = maxv, minv
                    shared_val = random.uniform(minv, maxv) if positions else 0.0
                    data_floats = [shared_val if i in positions else 0.0 for i in range(count)]
                else:
                    use_site = self.cb_4041_use_site.isChecked()
                    site_ok = False
                    if use_site and '4041' in self.site_data and 'points' in self.site_data['4041']:
                        points = self.site_data['4041']['points']
                        if all(p.get('upper') is not None and p.get('lower') is not None for p in points):
                            site_ok = True
                    if site_ok:
                        pts = self.site_data['4041']['points']
                        if len(pts) < count:
                            pts = pts * (count // len(pts) + 1)
                        data_floats = []
                        for i in range(count):
                            pt = pts[i % len(pts)]
                            low = pt['lower']
                            high = pt['upper']
                            if low > high:
                                low, high = high, low
                            if abs(high - low) < 0.001:
                                val = low
                            else:
                                val = random.uniform(low, high)
                            data_floats.append(val)
                    else:
                        minv = self.ds_4041_min.value()
                        maxv = self.ds_4041_max.value()
                        if minv > maxv:
                            minv, maxv = maxv, minv
                        data_floats = [random.uniform(minv, maxv) for _ in range(count)]
                msg = build_4041_message(count, input_type, data_floats)

            elif idx == 1:  # 4043
                count = self.spin_4043_count.value()
                mode = self.cb_4043_mode.currentData()
                if mode == -1:
                    states = [random.choice([0x00, 0x05]) for _ in range(count)]
                else:
                    states = [mode] * count
                msg = build_4043_message(count, states)

            elif idx == 2:  # 4143
                count = self.spin_4143_count.value()
                if self.sample_mode:
                    positions = set(self.sample_positions.get('4143', []))
                    modules = []
                    for addr in range(1, count + 1):
                        if (addr - 1) in positions:
                            modules.append([addr, 0xE3, 0x01, 0x00, 0x00])
                        else:
                            modules.append([addr, 0xE3, 0x00, 0x00, 0x00])
                else:
                    work = self.cb_4143_work.currentData()
                    fault = self.cb_4143_fault.currentData()
                    protect = self.cb_4143_protect.currentData()
                    comm = self.cb_4143_comm.currentData()
                    modules = [[addr, work, fault, protect, comm] for addr in range(1, count + 1)]
                msg = build_4143_message(modules)

            elif idx == 3:  # 4044
                input_type = 0x03 if self.cb_4044_type.currentIndex() == 1 else 0x01
                alarm_count = self.spin_4044_count.value()
                if self.sample_mode:
                    positions = set(self.sample_positions.get('4044', []))
                    alarm_states = [0x05 if i in positions else 0x00 for i in range(alarm_count)]
                else:
                    alarm_val = self.cb_4044_alarm.currentData()
                    alarm_states = [alarm_val] * alarm_count
                msg = build_4044_message(alarm_count, input_type, alarm_states)

            elif idx == 4:  # 4241
                count = self.spin_4241_count.value()
                if self.sample_mode:
                    positions = set(self.sample_positions.get('4241', []))
                    minv = self.ds_4241_min.value()
                    maxv = self.ds_4241_max.value()
                    if minv > maxv:
                        minv, maxv = maxv, minv
                    shared_val = random.uniform(minv, maxv) if positions else 0.0
                    floats = [shared_val if i in positions else 0.0 for i in range(count)]
                else:
                    use_site = self.cb_4241_use_site.isChecked()
                    site_ok = False
                    if use_site and '4241' in self.site_data and 'points' in self.site_data['4241']:
                        points = self.site_data['4241']['points']
                        if all(p.get('upper') is not None and p.get('lower') is not None for p in points):
                            site_ok = True
                    if site_ok:
                        pts = self.site_data['4241']['points']
                        if len(pts) < count:
                            pts = pts * (count // len(pts) + 1)
                        floats = []
                        for i in range(count):
                            pt = pts[i % len(pts)]
                            low = pt['lower']
                            high = pt['upper']
                            if low > high:
                                low, high = high, low
                            if abs(high - low) < 0.001:
                                val = low
                            else:
                                val = random.uniform(low, high)
                            floats.append(val)
                    else:
                        minv, maxv = self.ds_4241_min.value(), self.ds_4241_max.value()
                        if minv > maxv:
                            minv, maxv = maxv, minv
                        floats = [random.uniform(minv, maxv) for _ in range(count)]
                msg = build_4241_message(floats)
            else:
                return

            self.current_message = msg
            self.hex_output.setText(hex_dump(msg))
        except Exception as e:
            self.log_message(f"生成报文出错：{e}", "error")
            self.hex_output.setText(f"生成出错: {e}")

    def on_tab_changed(self, index):
        self.update_current_tab_message()

    def copy_hex(self):
        if not self.current_message:
            QMessageBox.information(self, "提示", "尚未生成报文")
            return
        QApplication.clipboard().setText(hex_dump(self.current_message))
        self.log_message("报文已复制到剪贴板", "info")
        QMessageBox.information(self, "已复制", "报文已复制到剪贴板")

    # ---------- UDP 发送 ----------
    def toggle_send(self):
        if self.is_sending:
            self.timer.stop()
            self.is_sending = False
            self.btn_start_stop.setText("开始发送")
            self.log_message("UDP 发送已停止", "info")
        else:
            if not self.current_message:
                QMessageBox.warning(self, "提示", "报文尚未生成，请检查参数")
                return
            target_ip = self.cb_target_ip.currentText().strip()
            if not target_ip:
                QMessageBox.warning(self, "输入错误", "目标 IP 不能为空")
                return
            local_ip = self.le_local_ip.text().strip()
            if not local_ip:
                QMessageBox.warning(self, "输入错误", "本机 IP 不能为空，请填写")
                return
            port = self.spin_port.value()
            interval_ms = int(self.dspin_interval.value() * 1000)

            history = self.settings.value("udp_history", [])
            if isinstance(history, str):
                history = [history]
            if target_ip not in history:
                history.append(target_ip)
                self.settings.setValue("udp_history", history)
                self.cb_target_ip.addItem(target_ip)

            self._target_ip = target_ip
            self._local_ip = local_ip
            self._port = port

            self.timer.start(interval_ms)
            self.is_sending = True
            self.btn_start_stop.setText("停止发送")
            self.log_message(f"开始 UDP 发送：目标 {target_ip}:{port}，间隔 {interval_ms}ms", "info")
            self.udp_send_once()

    def udp_send_once(self):
        try:
            self.update_current_tab_message()
            hex_str = ''.join(self.hex_output.toPlainText().split())
            data_bytes = bytes.fromhex(hex_str)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind((self._local_ip, 0))
            sock.sendto(data_bytes, (self._target_ip, self._port))
            sock.close()
            self.log_message(f"报文已发送至 {self._target_ip}:{self._port}", "info")
        except Exception as e:
            msg = f"UDP 发送异常：{e}"
            self.log_message(msg, "error")
            self.timer.stop()
            self.is_sending = False
            self.btn_start_stop.setText("开始发送")
            QMessageBox.critical(self, "发送失败", msg)

    def closeEvent(self, event):
        if self.timer.isActive():
            self.timer.stop()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())