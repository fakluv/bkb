import sys
import socket
import configparser
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QLineEdit, QTextEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QMessageBox, QTabBar,
    QGroupBox, QFormLayout, QSplitter, QStyleFactory, QDialog, QDateTimeEdit,
    QStackedWidget, QFileDialog
)
from PySide6.QtCore import (
    Qt, QDateTime, QSize, QTimer, QSettings, QThread, Signal
)

# ==================== 样式表 ====================
STYLE = """
QMainWindow { background-color: #f5f6fa; color: #2c3e50; }
QWidget { background-color: #ffffff; color: #2c3e50; font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei"; }
QGroupBox {
    border: 1px solid #dcdde1; border-radius: 8px;
    margin-top: 8px; padding-top: 16px;
    font-weight: bold; color: #2c3e50; background-color: #ffffff;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QPushButton {
    background-color: #ffffff; color: #2c3e50; border: 1px solid #b2bec3;
    border-radius: 6px; padding: 6px 16px; font-weight: 500;
}
QPushButton:hover { background-color: #f1f2f6; border-color: #6c7a89; }
QPushButton#sendBtn {
    background-color: #4a90d9; color: white; border-color: #4a90d9;
}
QPushButton#sendBtn:hover { background-color: #6fa3e0; }
QLineEdit, QComboBox, QTextEdit {
    background-color: #f9f9fb; color: #2c3e50; border: 1px solid #d1d5db;
    border-radius: 4px; padding: 4px 8px;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background-color: #ffffff; color: #2c3e50; selection-background-color: #e8eff5;
}
QTableWidget {
    background-color: #ffffff; gridline-color: #e2e6ed; alternate-background-color: #f8f9fc;
}
QHeaderView::section {
    background-color: #f0f2f5; color: #34495e; border: 1px solid #d1d5db;
    padding: 6px; font-weight: bold;
}
QTextEdit { font-family: "Cascadia Code", "Fira Code", monospace; }
QTabBar {
    background: transparent;
    border-bottom: 1px solid #dcdde1;
}
QTabBar::tab {
    background: #f0f2f5; border: 1px solid #dcdde1;
    border-bottom: none;
    padding: 6px 20px; margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    color: #2c3e50; font-weight: 500;
}
QTabBar::tab:selected {
    background: #4a90d9; color: white;
    border-color: #4a90d9;
}
QTabBar::tab:!selected {
    margin-top: 2px;
}
QStackedWidget { background: transparent; border: none; }
*:focus { outline: none; }
"""

DEFAULT_KV_TRACK = [["Tracksection", "occupied"], ["axleCount", "10"]]
DEFAULT_KV_COUNTING = [["countingHead", "activated"], ["wheelsensorSystem", "1"]]


# ==================== 后台 TCP 发送线程 ====================
class SendWorker(QThread):
    progress = Signal(int, int)
    result = Signal(bool, str)
    finished = Signal()

    def __init__(self, ip, port, xml_list):
        super().__init__()
        self.ip = ip
        self.port = port
        self.xml_list = xml_list
        self._abort = False
        self.error_msg = None

    def run(self):
        total = len(self.xml_list)
        for i, xml in enumerate(self.xml_list):
            if self._abort:
                break
            self.progress.emit(i + 1, total)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(5)
                    sock.connect((self.ip, self.port))
                    sock.sendall(xml.encode('utf-8'))
                self.result.emit(True, f"✅ [{i+1}/{total}] 发送成功")
            except Exception as e:
                self.error_msg = str(e)
                self.result.emit(False, f"❌ [{i+1}/{total}] 失败: {e}")
                self._abort = True
                break
        self.finished.emit()


# ==================== 主窗口 ====================
class DiagTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("富豪胜协议工具")
        self.setMinimumSize(800, 600)
        self.resize(1150, 750)
        self.setStyleSheet(STYLE)

        self.base_size = QSize(1150, 750)
        self.base_font_size = 13

        self.single_key_values = [row[:] for row in DEFAULT_KV_TRACK]
        self.batch_key_values = [row[:] for row in DEFAULT_KV_TRACK]
        self.batch_items = []
        self.send_history = []
        self._updating_kv = False
        self._updating_status = False

        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self.apply_scale_on_resize)

        self.settings = QSettings("DIAG_Tool", "Meldung_App")
        self.worker = None

        self.init_ui()
        self.load_settings()
        self.update_xml_preview()

        QTimer.singleShot(0, self._set_initial_splitter_ratio)

    def _set_initial_splitter_ratio(self):
        w = self.width()
        self.splitter.setSizes([int(w * 0.6), int(w * 0.4)])

    # ---------- UI 初始化 ----------
    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        top_bar = QHBoxLayout()
        self.mode_tabs = QTabBar()
        self.mode_tabs.addTab("📄 单报文")
        self.mode_tabs.addTab("📚 批量模式")
        self.mode_tabs.currentChanged.connect(self.on_mode_changed)
        top_bar.addWidget(self.mode_tabs)
        top_bar.addStretch()
        main_layout.addLayout(top_bar)

        self.splitter = QSplitter(Qt.Horizontal)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.stacked_panels = QStackedWidget()
        self.single_panel = self.build_single_panel()
        self.batch_panel = self.build_batch_panel()
        self.stacked_panels.addWidget(self.single_panel)
        self.stacked_panels.addWidget(self.batch_panel)
        left_layout.addWidget(self.stacked_panels)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(6)

        xml_group = QGroupBox("📄 XML 预览")
        xml_layout = QVBoxLayout()
        xml_layout.setContentsMargins(4, 4, 4, 4)
        self.xml_preview = QTextEdit()
        self.xml_preview.setReadOnly(True)
        self.xml_preview.setSizePolicy(self.xml_preview.sizePolicy().horizontalPolicy(),
                                       self.xml_preview.sizePolicy().verticalPolicy())
        self.xml_preview.sizePolicy().setVerticalStretch(1)
        xml_layout.addWidget(self.xml_preview)
        btn_copy = QPushButton("📋 复制 XML")
        btn_copy.clicked.connect(self.copy_xml)
        xml_layout.addWidget(btn_copy)
        xml_group.setLayout(xml_layout)
        right_layout.addWidget(xml_group)

        send_group = QGroupBox("🚀 TCP 发送")
        send_layout = QVBoxLayout()
        send_layout.setContentsMargins(4, 4, 4, 4)
        addr = QHBoxLayout()
        addr.addWidget(QLabel("IP:"))
        self.ip_edit = QLineEdit("127.0.0.1")
        addr.addWidget(self.ip_edit)
        addr.addWidget(QLabel("端口:"))
        self.port_edit = QLineEdit("1070")
        addr.addWidget(self.port_edit)
        send_layout.addLayout(addr)

        self.btn_send_single = QPushButton("📤 发送当前报文")
        self.btn_send_single.setObjectName("sendBtn")
        self.btn_send_single.clicked.connect(self.send_tcp)
        self.btn_batch_send = QPushButton("📤 批量发送全部")
        self.btn_batch_send.clicked.connect(self.batch_send_tcp)
        send_layout.addWidget(self.btn_send_single)
        send_layout.addWidget(self.btn_batch_send)
        send_group.setLayout(send_layout)
        right_layout.addWidget(send_group)

        hist_group = QGroupBox("📜 发送历史")
        hist_layout = QVBoxLayout()
        hist_layout.setContentsMargins(4, 4, 4, 4)
        self.history_text = QTextEdit()
        self.history_text.setReadOnly(True)
        self.history_text.setMaximumHeight(120)
        self.history_text.setSizePolicy(self.history_text.sizePolicy().horizontalPolicy(),
                                        self.history_text.sizePolicy().verticalPolicy())
        self.history_text.sizePolicy().setVerticalStretch(0)
        hist_layout.addWidget(self.history_text)
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self.clear_history)
        hist_layout.addWidget(btn_clear)
        hist_group.setLayout(hist_layout)
        right_layout.addWidget(hist_group)

        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(right_widget)
        self.splitter.setStretchFactor(0, 6)
        self.splitter.setStretchFactor(1, 4)
        main_layout.addWidget(self.splitter)

        self.status_label = QLabel("就绪")
        self.statusBar().addWidget(self.status_label)

        self.btn_batch_send.setVisible(False)

    # ================== 设置记忆 ==================
    def load_settings(self):
        ip = self.settings.value("tcp/ip", "127.0.0.1")
        port = self.settings.value("tcp/port", "1070")
        self.ip_edit.setText(ip)
        self.port_edit.setText(port)

    def closeEvent(self, event):
        self.settings.setValue("tcp/ip", self.ip_edit.text().strip())
        self.settings.setValue("tcp/port", self.port_edit.text().strip())
        event.accept()

    # ================== 等比例缩放 ==================
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start(50)

    def apply_scale_on_resize(self):
        scale_x = self.width() / self.base_size.width()
        scale_y = self.height() / self.base_size.height()
        scale = min(scale_x, scale_y)
        scale = max(scale, 0.8)
        font = self.font()
        font.setPointSizeF(self.base_font_size * scale)
        self.setFont(font)
        self.update()

    # ================== 单报文面板 ==================
    def build_single_panel(self):
        panel = QGroupBox("📝 单报文编辑")
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(4)
        self.seq_single = QLineEdit("1")
        self.name_single = QLineEdit("Gl101")
        self.type_single = QComboBox()
        self.type_single.addItems(["TRACKSECTION", "SIGNAL", "POINT", "CROSSING", "AXLECOUNTER", "COUNTINGHEAD"])
        self.domain_single = QLineEdit("Train station Linz")
        self.status_single = QComboBox()
        self.status_single.addItems(["ok", "error", "warning", "unknown"])
        self.status_single.setCurrentText("ok")
        self.raise_single = QDateTimeEdit(QDateTime.currentDateTime())
        self.raise_single.setDisplayFormat("yyyy-MM-ddTHH:mm:ss.zzz")
        self.send_single = QDateTimeEdit(QDateTime.currentDateTime())
        self.send_single.setDisplayFormat("yyyy-MM-ddTHH:mm:ss.zzz")
        form.addRow("序列号:", self.seq_single)
        form.addRow("名称:", self.name_single)
        form.addRow("类型:", self.type_single)
        form.addRow("域:", self.domain_single)
        form.addRow("状态:", self.status_single)
        form.addRow("RaiseTime:", self.raise_single)
        form.addRow("SendTime:", self.send_single)
        layout.addLayout(form)

        kv_group = QGroupBox("🔑 Key-Value")
        kv_layout = QVBoxLayout()
        kv_layout.setContentsMargins(4, 4, 4, 4)
        self.single_kv_table = QTableWidget(0, 3)
        self.single_kv_table.setHorizontalHeaderLabels(["Key", "Value", ""])
        self.single_kv_table.cellChanged.connect(self.on_single_kv_changed)
        kv_layout.addWidget(self.single_kv_table)
        btn_add_kv = QPushButton("➕")
        btn_add_kv.clicked.connect(self.add_single_kv)
        kv_layout.addWidget(btn_add_kv)
        kv_group.setLayout(kv_layout)
        layout.addWidget(kv_group)
        panel.setLayout(layout)
        self.populate_single_kv_table()
        return panel

    def populate_single_kv_table(self):
        self._updating_kv = True
        self.single_kv_table.setRowCount(len(self.single_key_values))
        for i, (k, v) in enumerate(self.single_key_values):
            self.single_kv_table.setItem(i, 0, QTableWidgetItem(k))
            self.single_kv_table.setItem(i, 1, QTableWidgetItem(v))
            btn = QPushButton("✕")
            btn.clicked.connect(lambda checked, r=i: self.remove_single_kv(r))
            self.single_kv_table.setCellWidget(i, 2, btn)
        self.single_kv_table.resizeColumnsToContents()
        min_width = 120
        for col in [0, 1]:
            if self.single_kv_table.columnWidth(col) < min_width:
                self.single_kv_table.setColumnWidth(col, min_width)
            self.single_kv_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Fixed)
        self.single_kv_table.setColumnWidth(2, 30)
        self.single_kv_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._updating_kv = False

    def on_single_kv_changed(self, row, col):
        if self._updating_kv: return
        if row < len(self.single_key_values):
            item = self.single_kv_table.item(row, col)
            if item:
                self.single_key_values[row][col] = item.text()
                self.update_xml_preview()

    def add_single_kv(self):
        self.single_key_values.append(["newKey", "newValue"])
        self.populate_single_kv_table()
        self.update_xml_preview()

    def remove_single_kv(self, row):
        if len(self.single_key_values) > 1:
            del self.single_key_values[row]
            self.populate_single_kv_table()
            self.update_xml_preview()

    # ================== 批量面板 ==================
    def build_batch_panel(self):
        panel = QGroupBox("📚 批量编辑")
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        bar1 = QHBoxLayout()
        bar1.setSpacing(4)
        bar1.addWidget(QLabel("时间偏移(s):"))
        self.offset_edit = QLineEdit("10")
        btn_offset = QPushButton("应用")
        btn_offset.clicked.connect(self.apply_time_offset)
        bar1.addWidget(self.offset_edit)
        bar1.addWidget(btn_offset)
        lbl_hint = QLabel("容忍不为0时使用，例如从1改为1000")
        lbl_hint.setStyleSheet("color: #8b95a5; font-size: 12px;")
        bar1.addWidget(lbl_hint)
        bar1.addStretch()
        btn_add = QPushButton("➕添加")
        btn_add.clicked.connect(self.add_batch_row)
        bar1.addWidget(btn_add)
        btn_import = QPushButton("📥导入")
        btn_import.clicked.connect(self.open_import_dialog)
        bar1.addWidget(btn_import)
        btn_del = QPushButton("🗑删除选中")
        btn_del.clicked.connect(self.delete_selected_batch)
        bar1.addWidget(btn_del)
        layout.addLayout(bar1)

        bar2 = QHBoxLayout()
        bar2.setSpacing(4)
        bar2.addWidget(QLabel("批量状态:"))
        self.batch_status_combo = QComboBox()
        self.batch_status_combo.addItems(["ok", "error", "warning", "unknown"])
        self.batch_status_combo.setCurrentText("error")
        self.batch_status_combo.currentTextChanged.connect(self.on_batch_status_changed)
        bar2.addWidget(self.batch_status_combo)
        bar2.addStretch()
        layout.addLayout(bar2)

        self.batch_table = QTableWidget(0, 8)
        self.batch_table.setHorizontalHeaderLabels(["", "序列号", "名称", "类型", "域", "状态", "RaiseTime", "SendTime"])
        self.batch_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.batch_table.setColumnWidth(0, 24)
        for col in range(1, self.batch_table.columnCount()):
            self.batch_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        layout.addWidget(self.batch_table)

        kv_group = QGroupBox("🔑 共用 Key-Value")
        kv_layout = QVBoxLayout()
        kv_layout.setContentsMargins(4, 4, 4, 4)
        self.batch_kv_table = QTableWidget(0, 3)
        self.batch_kv_table.setHorizontalHeaderLabels(["Key", "Value", ""])
        self.batch_kv_table.cellChanged.connect(self.on_batch_kv_changed)
        kv_layout.addWidget(self.batch_kv_table)
        btn_add_kv = QPushButton("➕")
        btn_add_kv.clicked.connect(self.add_batch_kv)
        kv_layout.addWidget(btn_add_kv)
        kv_group.setLayout(kv_layout)
        layout.addWidget(kv_group)
        panel.setLayout(layout)
        self.populate_batch_kv_table()
        self.batch_table.horizontalHeader().sectionClicked.connect(self.on_header_clicked)
        return panel

    def on_header_clicked(self, index):
        if index == 0:
            if self.batch_table.rowCount() == 0:
                return
            first_chk = self.batch_table.cellWidget(0, 0)
            if isinstance(first_chk, QCheckBox):
                new_state = not first_chk.isChecked()
                for i in range(self.batch_table.rowCount()):
                    chk = self.batch_table.cellWidget(i, 0)
                    if isinstance(chk, QCheckBox):
                        chk.setChecked(new_state)
        self.update_xml_preview()

    def populate_batch_kv_table(self):
        self._updating_kv = True
        self.batch_kv_table.setRowCount(len(self.batch_key_values))
        for i, (k, v) in enumerate(self.batch_key_values):
            self.batch_kv_table.setItem(i, 0, QTableWidgetItem(k))
            self.batch_kv_table.setItem(i, 1, QTableWidgetItem(v))
            btn = QPushButton("✕")
            btn.clicked.connect(lambda checked, r=i: self.remove_batch_kv(r))
            self.batch_kv_table.setCellWidget(i, 2, btn)
        self.batch_kv_table.resizeColumnsToContents()
        min_width = 120
        for col in [0, 1]:
            if self.batch_kv_table.columnWidth(col) < min_width:
                self.batch_kv_table.setColumnWidth(col, min_width)
            self.batch_kv_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Fixed)
        self.batch_kv_table.setColumnWidth(2, 30)
        self.batch_kv_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._updating_kv = False

    def on_batch_kv_changed(self, row, col):
        if self._updating_kv: return
        if row < len(self.batch_key_values):
            item = self.batch_kv_table.item(row, col)
            if item:
                self.batch_key_values[row][col] = item.text()
                self.update_xml_preview()

    def add_batch_kv(self):
        self.batch_key_values.append(["newKey", "newValue"])
        self.populate_batch_kv_table()
        self.update_xml_preview()

    def remove_batch_kv(self, row):
        if len(self.batch_key_values) > 1:
            del self.batch_key_values[row]
            self.populate_batch_kv_table()
            self.update_xml_preview()

    def add_batch_row(self, item=None):
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        default = {"seq": str(100000 + len(self.batch_items)), "name": f"G{1000 + len(self.batch_items)}",
                   "type": "TRACKSECTION", "domain": "Bhf_Nord", "status": "error", "raise": now, "send": now}
        self.batch_items.append(item or default)
        self.update_batch_table()
        self.update_xml_preview()

    def update_batch_table(self):
        self._updating_status = True
        self.batch_table.setRowCount(len(self.batch_items))
        for i, item in enumerate(self.batch_items):
            chk = QCheckBox()
            self.batch_table.setCellWidget(i, 0, chk)
            self.batch_table.setItem(i, 1, QTableWidgetItem(item["seq"]))
            self.batch_table.setItem(i, 2, QTableWidgetItem(item["name"]))
            type_combo = QComboBox()
            type_combo.addItems(["TRACKSECTION", "SIGNAL", "POINT", "CROSSING", "AXLECOUNTER", "COUNTINGHEAD"])
            type_combo.setCurrentText(item["type"])
            type_combo.currentTextChanged.connect(lambda text, r=i: self.update_batch_field(r, "type", text))
            self.batch_table.setCellWidget(i, 3, type_combo)
            self.batch_table.setItem(i, 4, QTableWidgetItem(item["domain"]))
            status_combo = QComboBox()
            status_combo.addItems(["ok", "error", "warning", "unknown"])
            status_combo.setCurrentText(item["status"])
            status_combo.currentTextChanged.connect(lambda text, r=i: self.update_batch_field(r, "status", text))
            self.batch_table.setCellWidget(i, 5, status_combo)
            self.batch_table.setItem(i, 6, QTableWidgetItem(item["raise"]))
            self.batch_table.setItem(i, 7, QTableWidgetItem(item["send"]))
        self._updating_status = False

    def update_batch_field(self, row, field, value):
        if row < len(self.batch_items):
            self.batch_items[row][field] = value
            self.update_xml_preview()

    def on_batch_status_changed(self, text):
        if self._updating_status:
            return
        selected = []
        for i in range(self.batch_table.rowCount()):
            w = self.batch_table.cellWidget(i, 0)
            if isinstance(w, QCheckBox) and w.isChecked():
                selected.append(i)
        target = selected if selected else list(range(len(self.batch_items)))
        for i in target:
            if i < len(self.batch_items):
                self.batch_items[i]["status"] = text
        self._updating_status = True
        for i in target:
            if i < self.batch_table.rowCount():
                status_combo = self.batch_table.cellWidget(i, 5)
                if isinstance(status_combo, QComboBox):
                    status_combo.setCurrentText(text)
        self._updating_status = False
        self.update_xml_preview()
        self.status_label.setText(f"状态已批量更新为 {text}")

    def delete_selected_batch(self):
        rows = []
        for i in range(self.batch_table.rowCount()):
            w = self.batch_table.cellWidget(i, 0)
            if isinstance(w, QCheckBox) and w.isChecked():
                rows.append(i)
        for i in reversed(rows):
            del self.batch_items[i]
        self.update_batch_table()
        self.update_xml_preview()

    def open_import_dialog(self):
        dlg = ImportDialog(self)
        if dlg.exec():
            items = dlg.get_import_items()
            group_mode = dlg.group_mode_combo.currentIndex()
            auto = dlg.auto_match_check.isChecked()
            replace = dlg.replace_check.isChecked()
            now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            new_items = []
            types = set()
            for name, group, etype in items:
                domain = "Bhf_Nord"
                if group_mode == 0 and group:
                    domain = group
                elif group_mode == 1 and group:
                    name = f"{group}_{name}"
                final_type = etype if auto else "TRACKSECTION"
                new_items.append({"seq": str(100000 + len(new_items)), "name": name,
                                  "type": final_type, "domain": domain, "status": "error",
                                  "raise": now, "send": now})
                types.add(final_type)
            if replace:
                self.batch_items = new_items
            else:
                self.batch_items.extend(new_items)
            if auto and len(types) == 1:
                target = types.pop()
                if target == "COUNTINGHEAD":
                    self.batch_key_values = [row[:] for row in DEFAULT_KV_COUNTING]
                else:
                    self.batch_key_values = [row[:] for row in DEFAULT_KV_TRACK]
                self.populate_batch_kv_table()
            self.update_batch_table()
            self.batch_status_combo.setCurrentText("error")
            self.update_xml_preview()

    def apply_time_offset(self):
        try:
            off = float(self.offset_edit.text())
        except:
            QMessageBox.warning(self, "错误", "请输入有效数字")
            return
        future = datetime.now() + timedelta(seconds=off)
        nt = future.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        for item in self.batch_items:
            item["raise"] = nt
            item["send"] = nt
        self.update_batch_table()
        self.update_xml_preview()

    # ================== XML 构建 ==================
    def build_xml(self, seq, name, etype, domain, status, raise_t, send_t, kvs):
        kv_xml = ""
        for k, v in kvs:
            kv_xml += f"    <keyValue>\n      <key>{self.esc(k)}</key>\n      <value>{self.esc(v)}</value>\n    </keyValue>\n"
        return f"""<DIAG_Meldung>
  <DIAG_Meldung_Event>
    <sequenceNumber>{self.esc(seq)}</sequenceNumber>
    <elementName>{self.esc(name)}</elementName>
    <elementType>{self.esc(etype)}</elementType>
    <elementDomain>{self.esc(domain)}</elementDomain>
    <elementStatus>{self.esc(status)}</elementStatus>
    <raiseTime>{raise_t}</raiseTime>
    <sendTime>{send_t}</sendTime>
{kv_xml}  </DIAG_Meldung_Event>
</DIAG_Meldung>"""

    def esc(self, s):
        return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

    def get_single_xml(self):
        return self.build_xml(self.seq_single.text(), self.name_single.text(),
                              self.type_single.currentText(), self.domain_single.text(),
                              self.status_single.currentText(),
                              self.raise_single.dateTime().toString("yyyy-MM-ddTHH:mm:ss.zzz"),
                              self.send_single.dateTime().toString("yyyy-MM-ddTHH:mm:ss.zzz"),
                              self.single_key_values)

    def get_batch_xmls(self):
        return [self.build_xml(it["seq"], it["name"], it["type"], it["domain"],
                               it["status"], it["raise"], it["send"], self.batch_key_values)
                for it in self.batch_items]

    def update_xml_preview(self):
        if self.mode_tabs.currentIndex() == 0:
            xml = self.get_single_xml()
        else:
            xmls = self.get_batch_xmls()
            xml = "\n------\n".join(xmls) if xmls else "批量列表为空"
        self.xml_preview.setPlainText(xml)

    # ================== 后台发送控制 ==================
    def send_tcp(self):
        if self.mode_tabs.currentIndex() == 0:
            xml = self.get_single_xml()
            if not xml:
                QMessageBox.warning(self, "提示", "无报文")
                return
            xml_list = [xml]
        else:
            xmls = self.get_batch_xmls()
            if not xmls:
                QMessageBox.warning(self, "提示", "无报文")
                return
            xml_list = [xmls[0]]
        self._start_send_thread(xml_list)

    def batch_send_tcp(self):
        if self.mode_tabs.currentIndex() == 0:
            return
        xml_list = self.get_batch_xmls()
        if not xml_list:
            return
        self._start_send_thread(xml_list)

    def _start_send_thread(self, xml_list):
        ip = self.ip_edit.text().strip()
        try:
            port = int(self.port_edit.text().strip())
        except:
            QMessageBox.warning(self, "错误", "端口必须为数字")
            return

        self.btn_send_single.setEnabled(False)
        self.btn_batch_send.setEnabled(False)
        self.status_label.setText("正在发送...")

        self.worker = SendWorker(ip, port, xml_list)
        self.worker.progress.connect(self.on_send_progress)
        self.worker.result.connect(self.on_send_result)
        self.worker.finished.connect(self.on_send_finished)
        self.worker.start()

    def on_send_progress(self, current, total):
        self.status_label.setText(f"发送 {current}/{total}...")

    def on_send_result(self, success, msg):
        self.add_history("发送", msg)

    def on_send_finished(self):
        self.btn_send_single.setEnabled(True)
        self.btn_batch_send.setEnabled(True)
        self.status_label.setText("就绪")
        if self.worker and self.worker.error_msg:
            QMessageBox.warning(self, "连接失败",
                                f"无法连接到 {self.worker.ip}:{self.worker.port}\n{self.worker.error_msg}")

    # ================== 其他工具方法 ==================
    def add_history(self, target, msg):
        self.history_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] {target} - {msg}")

    def clear_history(self):
        self.history_text.clear()

    def copy_xml(self):
        QApplication.clipboard().setText(self.xml_preview.toPlainText())

    def on_mode_changed(self, idx):
        self.stacked_panels.setCurrentIndex(idx)
        self.btn_send_single.setVisible(idx == 0)
        self.btn_batch_send.setVisible(idx == 1)
        self.update_xml_preview()


# ==================== 导入对话框（新增 INI 文件读取） ====================
class ImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量导入")
        self.resize(500, 450)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("支持 INI 文件导入，或手动粘贴内容：\n[轨道区段\\1] → TRACKSECTION\n[计数磁头\\1] → COUNTINGHEAD"))

        # 文件选择按钮
        btn_open = QPushButton("📂 打开 INI 文件")
        btn_open.clicked.connect(self.open_ini_file)
        layout.addWidget(btn_open)

        self.text_edit = QTextEdit()
        layout.addWidget(self.text_edit)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("组名:"))
        self.group_mode_combo = QComboBox()
        self.group_mode_combo.addItems(["作为域", "作为前缀", "忽略"])
        h1.addWidget(self.group_mode_combo)
        h1.addStretch()
        layout.addLayout(h1)

        self.auto_match_check = QCheckBox("自动识别类型和KV")
        self.auto_match_check.setChecked(True)
        layout.addWidget(self.auto_match_check)

        self.replace_check = QCheckBox("替换现有列表")
        self.replace_check.setChecked(True)
        layout.addWidget(self.replace_check)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("导入")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def open_ini_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 INI 配置文件", "", "INI 文件 (*.ini);;所有文件 (*)"
        )
        if not file_path:
            return

        try:
            config = configparser.ConfigParser()
            config.optionxform = str
            # 尝试多种编码读取
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
            content = None
            for enc in encodings:
                try:
                    with open(file_path, 'r', encoding=enc) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            if content is None:
                QMessageBox.warning(self, "读取失败", "无法识别文件编码")
                return
            config.read_string(content)

            lines = []
            for section in config.sections():
                if section == "接口设置":
                    continue
                lines.append(f"[{section}]")
                items = config.items(section)
                total = None
                for k, v in items:
                    if k.strip().lower() == "总数":
                        total = v.strip()
                        break
                if total:
                    lines.append(f"总数={total}")
                for k, v in items:
                    if k.strip().lower() == "总数" or not k.strip():
                        continue
                    lines.append(f"{k.strip()}={v.strip()}")
                lines.append("")

            self.text_edit.setPlainText("\n".join(lines))

        except Exception as e:
            QMessageBox.warning(self, "读取失败", f"无法读取 INI 文件：{e}")
    def get_import_items(self):
        raw = self.text_edit.toPlainText()
        lines = raw.splitlines()
        items = []
        group = ""
        for line in lines:
            line = line.strip()
            if not line: continue
            if line.startswith('[') and line.endswith(']'):
                group = line[1:-1].strip()
                continue
            if line.startswith('总数='): continue
            if '=' in line:
                name = line.split('=', 1)[1].strip()
            else:
                name = line
            if not name: continue
            etype = "TRACKSECTION"
            gl = group.lower()
            if any(k in gl for k in ["轨道区段", "track"]):
                etype = "TRACKSECTION"
            elif any(k in gl for k in ["计数磁头", "计轴", "counting"]):
                etype = "COUNTINGHEAD"
            items.append((name, group, etype))
        return items


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    window = DiagTool()
    window.show()
    sys.exit(app.exec())