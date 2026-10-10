import sys
import socket
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QLineEdit, QTextEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QMessageBox, QTabWidget,
    QGroupBox, QFormLayout, QSplitter, QStyleFactory, QDialog, QDateTimeEdit
)
from PySide6.QtCore import Qt, QDateTime

DARK_STYLE = """
QMainWindow { background-color: #1a1d23; color: #cdd6e0; }
QWidget { background-color: #21252b; color: #cdd6e0; font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei"; font-size: 13px; }
QGroupBox { border: 1px solid #3a3f4b; border-radius: 8px; margin-top: 1ex; font-weight: bold; color: #cdd6e0; background-color: #21252b; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
QPushButton { background-color: #2c313a; color: #cdd6e0; border: 1px solid #3a3f4b; border-radius: 6px; padding: 5px 14px; font-weight: 500; }
QPushButton:hover { background-color: #3a3f4b; border-color: #5a5f6b; }
QPushButton#sendBtn { background-color: #4da6ff; color: white; border-color: #4da6ff; }
QPushButton#sendBtn:hover { background-color: #6bb8ff; }
QLineEdit, QComboBox, QTextEdit, QTableWidget { background-color: #1e2128; color: #cdd6e0; border: 1px solid #3a3f4b; border-radius: 4px; padding: 3px 6px; selection-background-color: #4da6ff; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView { background-color: #1e2128; color: #cdd6e0; selection-background-color: #4da6ff; }
QTableWidget { gridline-color: #3a3f4b; selection-background-color: #4da6ff; }
QHeaderView::section { background-color: #252a33; color: #8b95a5; border: 1px solid #3a3f4b; padding: 4px; font-weight: bold; }
QTextEdit { font-family: "Cascadia Code", "Fira Code", "Consolas", monospace; font-size: 12px; color: #abb2bf; }
QTabWidget::pane { border: 1px solid #3a3f4b; border-radius: 4px; }
QTabBar::tab { background: #2c313a; border: 1px solid #3a3f4b; padding: 6px 12px; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
QTabBar::tab:selected { background: #4da6ff; color: white; }
QCheckBox::indicator { width: 16px; height: 16px; }
"""


class DiagTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DIAG Meldung 报文工具 (TCP)")
        self.resize(1200, 800)
        self.setStyleSheet(DARK_STYLE)

        self.single_key_values = [["Tracksection", "occupied"], ["axleCount", "10"]]
        self.batch_key_values = [["Tracksection", "occupied"], ["axleCount", "10"]]
        self.batch_items = []
        self.send_history = []
        self._updating_kv = False  # 防止刷新表格时触发 cellChanged

        self.init_ui()
        self.update_xml_preview()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 模式切换 + 预设
        top_bar = QHBoxLayout()
        self.mode_tabs = QTabWidget()
        self.single_tab = QWidget()
        self.batch_tab = QWidget()
        self.mode_tabs.addTab(self.single_tab, "📄 单报文")
        self.mode_tabs.addTab(self.batch_tab, "📚 批量模式")
        self.mode_tabs.currentChanged.connect(self.on_mode_changed)
        top_bar.addWidget(self.mode_tabs)
        top_bar.addStretch()

        btn_presets = QHBoxLayout()
        btn_default = QPushButton("🔄 TRACKSECTION 默认")
        btn_default.clicked.connect(self.preset_track_default)
        btn_occupied = QPushButton("🚂 轨道占用")
        btn_occupied.clicked.connect(self.preset_track_occupied)
        btn_clear = QPushButton("✅ 轨道空闲")
        btn_clear.clicked.connect(self.preset_track_clear)
        btn_counting = QPushButton("🧲 计轴磁头")
        btn_counting.clicked.connect(self.preset_counting_head)
        btn_presets.addWidget(btn_default)
        btn_presets.addWidget(btn_occupied)
        btn_presets.addWidget(btn_clear)
        btn_presets.addWidget(btn_counting)
        top_bar.addLayout(btn_presets)
        main_layout.addLayout(top_bar)

        # 主分割区域
        splitter = QSplitter(Qt.Horizontal)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        self.single_panel = self.build_single_panel()
        self.batch_panel = self.build_batch_panel()
        left_layout.addWidget(self.single_panel)
        left_layout.addWidget(self.batch_panel)
        self.batch_panel.setVisible(False)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # XML 预览
        xml_group = QGroupBox("📄 XML 预览")
        xml_layout = QVBoxLayout()
        self.xml_preview = QTextEdit()
        self.xml_preview.setReadOnly(True)
        xml_layout.addWidget(self.xml_preview)
        btn_copy_xml = QPushButton("📋 复制 XML")
        btn_copy_xml.clicked.connect(self.copy_xml)
        xml_layout.addWidget(btn_copy_xml)
        xml_group.setLayout(xml_layout)
        right_layout.addWidget(xml_group)

        # TCP 发送
        send_group = QGroupBox("🚀 TCP 发送")
        send_layout = QVBoxLayout()
        addr_layout = QHBoxLayout()
        addr_layout.addWidget(QLabel("目标 IP:"))
        self.ip_edit = QLineEdit("127.0.0.1")
        addr_layout.addWidget(self.ip_edit)
        addr_layout.addWidget(QLabel("端口:"))
        self.port_edit = QLineEdit("9999")
        addr_layout.addWidget(self.port_edit)
        send_layout.addLayout(addr_layout)
        btn_send = QPushButton("📤 发送当前报文")
        btn_send.setObjectName("sendBtn")
        btn_send.clicked.connect(self.send_tcp)
        send_layout.addWidget(btn_send)
        btn_batch_send = QPushButton("📤 批量发送所有报文")
        btn_batch_send.clicked.connect(self.batch_send_tcp)
        send_layout.addWidget(btn_batch_send)
        send_group.setLayout(send_layout)
        right_layout.addWidget(send_group)

        # 历史
        hist_group = QGroupBox("📜 发送历史")
        hist_layout = QVBoxLayout()
        self.history_text = QTextEdit()
        self.history_text.setReadOnly(True)
        self.history_text.setMaximumHeight(120)
        hist_layout.addWidget(self.history_text)
        btn_clear_hist = QPushButton("清空历史")
        btn_clear_hist.clicked.connect(self.clear_history)
        hist_layout.addWidget(btn_clear_hist)
        hist_group.setLayout(hist_layout)
        right_layout.addWidget(hist_group)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)

        self.status_label = QLabel("就绪")
        self.statusBar().addWidget(self.status_label)

    # ---------- 单报文面板 ----------
    def build_single_panel(self):
        panel = QGroupBox("📝 单报文编辑")
        layout = QVBoxLayout()
        form = QFormLayout()
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
        form.addRow("元素名称:", self.name_single)
        form.addRow("元素类型:", self.type_single)
        form.addRow("域:", self.domain_single)
        form.addRow("状态:", self.status_single)
        form.addRow("RaiseTime:", self.raise_single)
        form.addRow("SendTime:", self.send_single)
        layout.addLayout(form)

        kv_group = QGroupBox("🔑 Key-Value 参数")
        kv_layout = QVBoxLayout()
        self.single_kv_table = QTableWidget(0, 3)
        self.single_kv_table.setHorizontalHeaderLabels(["Key", "Value", ""])
        self.single_kv_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.single_kv_table.setColumnWidth(2, 50)
        # ★ 连接 cellChanged 信号
        self.single_kv_table.cellChanged.connect(self.on_single_kv_changed)
        kv_layout.addWidget(self.single_kv_table)
        btn_add_kv = QPushButton("➕ 添加参数")
        btn_add_kv.clicked.connect(self.add_single_kv)
        kv_layout.addWidget(btn_add_kv)
        kv_group.setLayout(kv_layout)
        layout.addWidget(kv_group)
        panel.setLayout(layout)

        self.populate_single_kv_table()
        return panel

    def populate_single_kv_table(self):
        """刷新单报文 KV 表格（不触发 cellChanged）"""
        self._updating_kv = True
        self.single_kv_table.setRowCount(len(self.single_key_values))
        for i, (k, v) in enumerate(self.single_key_values):
            self.single_kv_table.setItem(i, 0, QTableWidgetItem(k))
            self.single_kv_table.setItem(i, 1, QTableWidgetItem(v))
            btn_del = QPushButton("✕")
            btn_del.clicked.connect(lambda checked, row=i: self.remove_single_kv(row))
            self.single_kv_table.setCellWidget(i, 2, btn_del)
        self._updating_kv = False

    def on_single_kv_changed(self, row, col):
        """当用户编辑 Key 或 Value 时更新数据并刷新 XML"""
        if self._updating_kv:
            return
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

    # ---------- 批量面板 ----------
    def build_batch_panel(self):
        panel = QGroupBox("📚 批量报文编辑")
        layout = QVBoxLayout()

        toolbar1 = QHBoxLayout()
        toolbar1.addWidget(QLabel("⏱️ 时间偏移(秒):"))
        self.offset_edit = QLineEdit("10")
        self.offset_edit.setMaximumWidth(60)
        toolbar1.addWidget(self.offset_edit)
        btn_apply_offset = QPushButton("应用偏移")
        btn_apply_offset.clicked.connect(self.apply_time_offset)
        toolbar1.addWidget(btn_apply_offset)
        toolbar1.addStretch()
        btn_add = QPushButton("➕ 手动添加")
        btn_add.clicked.connect(self.add_batch_row)
        toolbar1.addWidget(btn_add)
        btn_import = QPushButton("📥 批量导入")
        btn_import.clicked.connect(self.open_import_dialog)
        toolbar1.addWidget(btn_import)
        btn_del_sel = QPushButton("🗑️ 删除选中")
        btn_del_sel.clicked.connect(self.delete_selected_batch)
        toolbar1.addWidget(btn_del_sel)
        layout.addLayout(toolbar1)

        toolbar2 = QHBoxLayout()
        toolbar2.addWidget(QLabel("批量修改类型:"))
        self.batch_type_combo = QComboBox()
        self.batch_type_combo.addItems(["TRACKSECTION", "SIGNAL", "POINT", "CROSSING", "AXLECOUNTER", "COUNTINGHEAD"])
        toolbar2.addWidget(self.batch_type_combo)
        toolbar2.addWidget(QLabel("状态:"))
        self.batch_status_combo = QComboBox()
        self.batch_status_combo.addItems(["ok", "error", "warning", "unknown"])
        toolbar2.addWidget(self.batch_status_combo)
        btn_apply_type_status = QPushButton("应用修改")
        btn_apply_type_status.clicked.connect(self.apply_batch_type_status)
        toolbar2.addWidget(btn_apply_type_status)
        toolbar2.addStretch()
        layout.addLayout(toolbar2)

        self.batch_table = QTableWidget(0, 8)
        self.batch_table.setHorizontalHeaderLabels(["选择", "序列号", "元素名称", "类型", "域", "状态", "RaiseTime", "SendTime"])
        self.batch_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.batch_table)

        kv_group = QGroupBox("🔑 共用 Key-Value")
        kv_layout = QVBoxLayout()
        self.batch_kv_table = QTableWidget(0, 3)
        self.batch_kv_table.setHorizontalHeaderLabels(["Key", "Value", ""])
        self.batch_kv_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # ★ 连接 cellChanged 信号
        self.batch_kv_table.cellChanged.connect(self.on_batch_kv_changed)
        kv_layout.addWidget(self.batch_kv_table)
        btn_add_kv = QPushButton("➕ 添加参数")
        btn_add_kv.clicked.connect(self.add_batch_kv)
        kv_layout.addWidget(btn_add_kv)
        kv_group.setLayout(kv_layout)
        layout.addWidget(kv_group)
        panel.setLayout(layout)

        self.populate_batch_kv_table()
        return panel

    def populate_batch_kv_table(self):
        """刷新批量 KV 表格（不触发 cellChanged）"""
        self._updating_kv = True
        self.batch_kv_table.setRowCount(len(self.batch_key_values))
        for i, (k, v) in enumerate(self.batch_key_values):
            self.batch_kv_table.setItem(i, 0, QTableWidgetItem(k))
            self.batch_kv_table.setItem(i, 1, QTableWidgetItem(v))
            btn_del = QPushButton("✕")
            btn_del.clicked.connect(lambda checked, row=i: self.remove_batch_kv(row))
            self.batch_kv_table.setCellWidget(i, 2, btn_del)
        self._updating_kv = False

    def on_batch_kv_changed(self, row, col):
        """当用户编辑批量 Key/Value 时更新数据并刷新 XML"""
        if self._updating_kv:
            return
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

    # ---------- 批量数据操作 ----------
    def add_batch_row(self, item=None):
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        default = {
            "seq": str(100000 + len(self.batch_items)),
            "name": f"G{1000 + len(self.batch_items)}",
            "type": "TRACKSECTION",
            "domain": "Bhf_Nord",
            "status": "ok",
            "raise": now,
            "send": now
        }
        self.batch_items.append(item if item else default)
        self.update_batch_table()
        self.update_xml_preview()

    def update_batch_table(self):
        self.batch_table.setRowCount(len(self.batch_items))
        for i, item in enumerate(self.batch_items):
            chk = QCheckBox()
            self.batch_table.setCellWidget(i, 0, chk)
            self.batch_table.setItem(i, 1, QTableWidgetItem(item["seq"]))
            self.batch_table.setItem(i, 2, QTableWidgetItem(item["name"]))
            type_combo = QComboBox()
            type_combo.addItems(["TRACKSECTION", "SIGNAL", "POINT", "CROSSING", "AXLECOUNTER", "COUNTINGHEAD"])
            type_combo.setCurrentText(item["type"])
            type_combo.currentTextChanged.connect(lambda text, row=i: self.update_batch_field(row, "type", text))
            self.batch_table.setCellWidget(i, 3, type_combo)
            self.batch_table.setItem(i, 4, QTableWidgetItem(item["domain"]))
            status_combo = QComboBox()
            status_combo.addItems(["ok", "error", "warning", "unknown"])
            status_combo.setCurrentText(item["status"])
            status_combo.currentTextChanged.connect(lambda text, row=i: self.update_batch_field(row, "status", text))
            self.batch_table.setCellWidget(i, 5, status_combo)
            self.batch_table.setItem(i, 6, QTableWidgetItem(item["raise"]))
            self.batch_table.setItem(i, 7, QTableWidgetItem(item["send"]))
        self.batch_table.resizeColumnsToContents()

    def update_batch_field(self, row, field, value):
        if 0 <= row < len(self.batch_items):
            self.batch_items[row][field] = value
            self.update_xml_preview()

    def delete_selected_batch(self):
        rows_to_delete = []
        for i in range(self.batch_table.rowCount()):
            chk = self.batch_table.cellWidget(i, 0)
            if chk and chk.isChecked():
                rows_to_delete.append(i)
        for i in reversed(rows_to_delete):
            del self.batch_items[i]
        self.update_batch_table()
        self.update_xml_preview()

    def open_import_dialog(self):
        dlg = ImportDialog(self)
        if dlg.exec():
            names = dlg.get_names()
            replace = dlg.replace_check.isChecked()
            now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            new_items = []
            for name in names:
                new_items.append({
                    "seq": str(100000 + len(new_items)),
                    "name": name,
                    "type": "TRACKSECTION",
                    "domain": "Bhf_Nord",
                    "status": "ok",
                    "raise": now,
                    "send": now
                })
            if replace:
                self.batch_items = new_items
            else:
                self.batch_items.extend(new_items)
            self.update_batch_table()
            self.update_xml_preview()
            self.status_label.setText(f"导入 {len(names)} 个名称")

    def apply_time_offset(self):
        try:
            offset = float(self.offset_edit.text())
        except ValueError:
            QMessageBox.warning(self, "错误", "请输入有效的数字偏移")
            return
        future = datetime.now() + timedelta(seconds=offset)
        new_time = future.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        for item in self.batch_items:
            item["raise"] = new_time
            item["send"] = new_time
        self.update_batch_table()
        self.update_xml_preview()
        self.status_label.setText(f"时间已偏移 +{offset} 秒")

    def apply_batch_type_status(self):
        new_type = self.batch_type_combo.currentText()
        new_status = self.batch_status_combo.currentText()
        selected_indices = []
        for i in range(self.batch_table.rowCount()):
            chk = self.batch_table.cellWidget(i, 0)
            if chk and chk.isChecked():
                selected_indices.append(i)
        target_indices = selected_indices if selected_indices else list(range(len(self.batch_items)))
        for i in target_indices:
            if i < len(self.batch_items):
                self.batch_items[i]["type"] = new_type
                self.batch_items[i]["status"] = new_status
        self.update_batch_table()
        if selected_indices:
            for i in selected_indices:
                if i < self.batch_table.rowCount():
                    chk = self.batch_table.cellWidget(i, 0)
                    if chk:
                        chk.setChecked(True)
        self.update_xml_preview()
        self.status_label.setText(f"批量修改类型为 {new_type}，状态为 {new_status}")

    # ---------- XML ----------
    def build_xml(self, seq, name, etype, domain, status, raise_t, send_t, kvs):
        kv_xml = ""
        for k, v in kvs:
            kv_xml += f"    <keyValue>\n      <key>{self.escape_xml(k)}</key>\n      <value>{self.escape_xml(v)}</value>\n    </keyValue>\n"
        return f"""<DIAG_Meldung>
  <DIAG_Meldung_Event>
    <sequenceNumber>{self.escape_xml(seq)}</sequenceNumber>
    <elementName>{self.escape_xml(name)}</elementName>
    <elementType>{self.escape_xml(etype)}</elementType>
    <elementDomain>{self.escape_xml(domain)}</elementDomain>
    <elementStatus>{self.escape_xml(status)}</elementStatus>
    <raiseTime>{raise_t}</raiseTime>
    <sendTime>{send_t}</sendTime>
{kv_xml}  </DIAG_Meldung_Event>
</DIAG_Meldung>"""

    def escape_xml(self, s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    def get_single_xml(self):
        return self.build_xml(
            self.seq_single.text(),
            self.name_single.text(),
            self.type_single.currentText(),
            self.domain_single.text(),
            self.status_single.currentText(),
            self.raise_single.dateTime().toString("yyyy-MM-ddTHH:mm:ss.zzz"),
            self.send_single.dateTime().toString("yyyy-MM-ddTHH:mm:ss.zzz"),
            self.single_key_values
        )

    def get_batch_xmls(self):
        xmls = []
        for item in self.batch_items:
            xmls.append(self.build_xml(
                item["seq"], item["name"], item["type"], item["domain"],
                item["status"], item["raise"], item["send"], self.batch_key_values
            ))
        return xmls

    def update_xml_preview(self):
        if self.mode_tabs.currentIndex() == 0:
            xml = self.get_single_xml()
        else:
            xmls = self.get_batch_xmls()
            xml = "\n------\n".join(xmls) if xmls else "批量列表为空"
        self.xml_preview.setPlainText(xml)

    # ---------- TCP 发送 ----------
    def send_tcp(self):
        xml = self.get_single_xml() if self.mode_tabs.currentIndex() == 0 else (self.get_batch_xmls()[0] if self.get_batch_xmls() else "")
        if not xml:
            QMessageBox.warning(self, "提示", "无报文可发送")
            return
        self._tcp_send(xml)

    def batch_send_tcp(self):
        if self.mode_tabs.currentIndex() == 0:
            QMessageBox.information(self, "提示", "批量发送仅在批量模式下可用")
            return
        xmls = self.get_batch_xmls()
        if not xmls:
            QMessageBox.warning(self, "提示", "批量列表为空")
            return
        for i, xml in enumerate(xmls):
            self.status_label.setText(f"发送第 {i+1}/{len(xmls)} 个报文...")
            QApplication.processEvents()
            self._tcp_send(xml)
        self.status_label.setText(f"批量发送完成，共 {len(xmls)} 个报文")
        self.add_history("批量", f"全部发送 {len(xmls)} 条")

    def _tcp_send(self, xml):
        ip = self.ip_edit.text().strip()
        port_text = self.port_edit.text().strip()
        try:
            port = int(port_text)
        except ValueError:
            QMessageBox.warning(self, "错误", "端口必须为数字")
            return
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((ip, port))
            sock.sendall(xml.encode('utf-8'))
            sock.close()
            self.status_label.setText(f"✅ 发送成功 -> {ip}:{port}")
            self.add_history(f"{ip}:{port}", "成功")
        except Exception as e:
            self.status_label.setText(f"❌ 发送失败: {e}")
            self.add_history(f"{ip}:{port}", f"失败: {e}")

    def add_history(self, target, msg):
        time_str = datetime.now().strftime("%H:%M:%S")
        entry = f"[{time_str}] {target} - {msg}"
        self.send_history.append(entry)
        self.history_text.append(entry)

    def clear_history(self):
        self.send_history.clear()
        self.history_text.clear()

    def copy_xml(self):
        QApplication.clipboard().setText(self.xml_preview.toPlainText())
        self.status_label.setText("XML 已复制到剪贴板")

    # ---------- 预设 ----------
    def preset_track_default(self):
        self.type_single.setCurrentText("TRACKSECTION")
        self.status_single.setCurrentText("ok")
        self.domain_single.setText("Train station Linz")
        self.name_single.setText("Gl101")
        self.single_key_values = [["Tracksection", "occupied"], ["axleCount", "10"]]
        self.populate_single_kv_table()
        self.update_xml_preview()

    def preset_track_occupied(self):
        self.type_single.setCurrentText("TRACKSECTION")
        self.status_single.setCurrentText("error")
        self.domain_single.setText("Bhf_Nord")
        self.single_key_values = [["Tracksection", "occupied"], ["axleCount", "10"]]
        self.populate_single_kv_table()
        self.update_xml_preview()

    def preset_track_clear(self):
        self.type_single.setCurrentText("TRACKSECTION")
        self.status_single.setCurrentText("ok")
        self.domain_single.setText("Train station Linz")
        self.single_key_values = [["Tracksection", "cleard"], ["axleCount", "0"]]
        self.populate_single_kv_table()
        self.update_xml_preview()

    def preset_counting_head(self):
        self.type_single.setCurrentText("COUNTINGHEAD")
        self.status_single.setCurrentText("ok")
        self.domain_single.setText("xml test")
        self.name_single.setText("B")
        self.single_key_values = [["countingHead", "activated"], ["wheelsensorSystem", "1"]]
        self.populate_single_kv_table()
        self.update_xml_preview()

    def on_mode_changed(self, index):
        self.single_panel.setVisible(index == 0)
        self.batch_panel.setVisible(index == 1)
        self.update_xml_preview()


class ImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量导入元素名称")
        self.resize(400, 300)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("每行一个名称，支持“序号=名称”格式\n例如：\n1=ZHG1\nG1007"))
        self.text_edit = QTextEdit()
        layout.addWidget(self.text_edit)
        self.replace_check = QCheckBox("替换现有列表（默认追加）")
        layout.addWidget(self.replace_check)
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("✅ 开始导入")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def get_names(self):
        raw = self.text_edit.toPlainText()
        lines = raw.splitlines()
        names = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if '=' in line:
                name = line.split('=', 1)[1].strip()
            else:
                name = line
            if name:
                names.append(name)
        return names


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    window = DiagTool()
    window.show()
    sys.exit(app.exec())