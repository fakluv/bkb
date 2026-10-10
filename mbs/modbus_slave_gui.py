#!/usr/bin/env python3
"""
Modbus TCP 从站仿真 - PySide6 GUI 版（地址修复版）
依赖：pyside6, pymodbus>=3.10.0
"""
import sys
import logging
import threading
import inspect
import asyncio
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QSpinBox,
    QComboBox, QPushButton, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QGroupBox, QFormLayout, QMessageBox,
    QDialog, QDialogButtonBox, QScrollArea, QGridLayout
)
from PySide6.QtCore import QObject, Signal, Qt, QRect
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QIcon

from pymodbus.server import ModbusTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.datastore.context import ModbusDeviceContext


# ---------- 自绘图标 ----------
def create_logo():
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    circle_rect = QRect(2, 2, size - 4, size - 4)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(0, 90, 170))
    painter.drawEllipse(circle_rect)
    inner_margin = 14
    inner_rect = QRect(inner_margin, inner_margin,
                       size - 2 * inner_margin, size - 2 * inner_margin)
    painter.setBrush(Qt.white)
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(inner_rect, 4, 4)
    painter.setPen(QColor(0, 90, 170))
    font = QFont("Arial", 24, QFont.Bold)
    painter.setFont(font)
    painter.drawText(inner_rect, Qt.AlignCenter, "M")
    painter.setBrush(QColor(0, 200, 80))
    painter.setPen(Qt.white)
    painter.drawEllipse(QRect(4, 4, 12, 12))
    painter.end()
    pixmap.save("modbus_icon.ico")
    return QIcon(pixmap)


# ---------- 日志处理器 ----------
class GUILogHandler(logging.Handler, QObject):
    log_signal = Signal(str)

    def __init__(self):
        super().__init__()
        QObject.__init__(self)
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    def emit(self, record):
        msg = self.format(record)
        self.log_signal.emit(msg)


# ---------- 寄存器编辑对话框 ----------
class RegisterEditorDialog(QDialog):
    def __init__(self, start_addr, count, current_values=None, parent=None):
        super().__init__(parent)
        self.start_addr = start_addr  # 0-based PDU 地址，与主站一致
        self.count = count
        self.values = list(current_values) if current_values else [0] * count
        self.spinboxes = []
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("自定义寄存器值")
        self.resize(800, 500)
        layout = QVBoxLayout(self)

        batch_layout = QHBoxLayout()
        batch_layout.addWidget(QLabel("全部填充为:"))
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(0, 65535)
        self.batch_spin.setValue(0)
        batch_layout.addWidget(self.batch_spin)
        btn_apply = QPushButton("应用")
        btn_apply.clicked.connect(self.batch_fill)
        batch_layout.addWidget(btn_apply)
        btn_reset = QPushButton("重置为0")
        btn_reset.clicked.connect(self.reset_all_to_zero)
        batch_layout.addWidget(btn_reset)
        batch_layout.addStretch()
        layout.addLayout(batch_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.grid = QGridLayout(container)
        self.grid.setSpacing(4)

        num_groups = (self.count + 9) // 10
        for g in range(num_groups):
            start = self.start_addr + g * 10
            end = min(self.start_addr + self.count - 1, start + 9)
            title = QLabel(f"{start}-{end}")
            title.setAlignment(Qt.AlignCenter)
            title.setStyleSheet("font-weight: bold;")
            self.grid.addWidget(title, 0, g)

        for i in range(self.count):
            group = i // 10
            row = (i % 10) + 1
            addr = self.start_addr + i  # 显示 0-based 地址，与主站一致
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(2, 2, 2, 2)
            cell_layout.setSpacing(4)
            addr_label = QLabel(str(addr))
            addr_label.setFixedWidth(60)
            addr_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            spin = QSpinBox()
            spin.setRange(0, 65535)
            spin.setValue(self.values[i])
            spin.setFixedWidth(80)
            cell_layout.addWidget(addr_label)
            cell_layout.addWidget(spin)
            self.spinboxes.append(spin)
            self.grid.addWidget(cell, row, group)

        scroll.setWidget(container)
        layout.addWidget(scroll)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.collect_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def batch_fill(self):
        val = self.batch_spin.value()
        for spin in self.spinboxes:
            spin.setValue(val)

    def reset_all_to_zero(self):
        self.batch_spin.setValue(0)
        for spin in self.spinboxes:
            spin.setValue(0)

    def collect_and_accept(self):
        self.values = [spin.value() for spin in self.spinboxes]
        self.accept()


# ---------- 主窗口 ----------
class ModbusSlaveGUI(QWidget):
    server_stopped = Signal()

    def __init__(self):
        super().__init__()
        self.loop = None
        self.task = None
        self.thread = None
        self.running = False
        self.custom_values = None
        self._server = None
        self.server_stopped.connect(self.on_server_stopped)
        self.init_ui()
        self.setup_logging()

    def init_ui(self):
        self.setWindowTitle("Modbus TCP 从站仿真工具")
        self.setMinimumWidth(520)

        group_config = QGroupBox("服务器配置")
        form = QFormLayout()
        self.edit_host = QLineEdit("0.0.0.0")
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1, 65535)
        self.spin_port.setValue(502)
        self.combo_fc = QComboBox()
        self.combo_fc.addItems(["3 (保持寄存器)", "4 (输入寄存器)"])
        self.spin_addr = QSpinBox()
        self.spin_addr.setRange(0, 65535)
        self.spin_addr.setValue(30001)
        self.spin_count = QSpinBox()
        self.spin_count.setRange(1, 10000)
        self.spin_count.setValue(400)
        self.spin_count.valueChanged.connect(self.on_count_changed)
        form.addRow("监听 IP:", self.edit_host)
        form.addRow("监听端口:", self.spin_port)
        form.addRow("寄存器类型:", self.combo_fc)
        form.addRow("起始地址(0-based):", self.spin_addr)  # 标注地址类型
        form.addRow("寄存器数量:", self.spin_count)
        group_config.setLayout(form)

        self.btn_edit_regs = QPushButton("自定义寄存器值...")
        self.btn_edit_regs.clicked.connect(self.open_register_editor)

        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("启动服务器")
        self.btn_stop = QPushButton("停止服务器")
        self.btn_stop.setEnabled(False)
        self.btn_start.clicked.connect(self.start_server)
        self.btn_stop.clicked.connect(self.stop_server)
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)

        group_log = QGroupBox("运行日志")
        log_layout = QVBoxLayout()
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(500)
        log_layout.addWidget(self.log_text)
        group_log.setLayout(log_layout)

        main_layout = QVBoxLayout()
        main_layout.addWidget(group_config)
        main_layout.addWidget(self.btn_edit_regs)
        main_layout.addLayout(btn_layout)
        main_layout.addWidget(group_log)
        self.setLayout(main_layout)

    def on_count_changed(self, new_count):
        if self.custom_values is not None:
            self.custom_values = None
            self.log_text.appendPlainText("[提示] 寄存器数量已改变，之前自定义的寄存器值已清除。")

    def open_register_editor(self):
        start = self.spin_addr.value()
        count = self.spin_count.value()
        cur = self.custom_values if (self.custom_values and len(self.custom_values) == count) else None
        dlg = RegisterEditorDialog(start, count, cur, self)
        if dlg.exec() == QDialog.Accepted:
            self.custom_values = dlg.values
            self.log_text.appendPlainText("[提示] 已保存自定义寄存器值。")
        else:
            self.log_text.appendPlainText("[提示] 已取消自定义编辑。")

    def setup_logging(self):
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        for h in logger.handlers[:]:
            logger.removeHandler(h)
        self.gui_handler = GUILogHandler()
        self.gui_handler.log_signal.connect(self.append_log)
        logger.addHandler(self.gui_handler)

    def append_log(self, message):
        self.log_text.appendPlainText(message)

    def get_config(self):
        fc_text = self.combo_fc.currentText()
        fc = 3 if "3" in fc_text else 4
        return {
            "host": self.edit_host.text().strip(),
            "port": self.spin_port.value(),
            "fc": fc,
            "start_addr": self.spin_addr.value(),
            "count": self.spin_count.value(),
        }

    def start_server(self):
        if self.running:
            QMessageBox.information(self, "提示", "服务器已在运行中")
            return
        cfg = self.get_config()
        if not cfg["host"]:
            QMessageBox.critical(self, "错误", "请输入有效的监听 IP")
            return

        # ========== 新增：地址范围合法性校验 ==========
        if cfg["start_addr"] + cfg["count"] > 65536:
            QMessageBox.critical(
                self, "错误",
                f"地址范围超出限制！\n"
                f"起始地址 {cfg['start_addr']} + 数量 {cfg['count']} = {cfg['start_addr']+cfg['count']}\n"
                f"Modbus 0-based 地址最大为 65535"
            )
            return

        if self.custom_values and len(self.custom_values) == cfg["count"]:
            values = self.custom_values
            logging.info("使用自定义寄存器值。")
        else:
            values = [0] * cfg["count"]
            logging.info("未设置自定义值，所有寄存器默认值为 0。")

        self.running = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

        self.thread = threading.Thread(
            target=self.run_server, args=(cfg, values), daemon=True
        )
        self.thread.start()

    def run_server(self, cfg, values):
        """在新线程中运行事件循环，启动服务器"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop

        # ========== 核心修复：地址映射转换 ==========
        # GUI 输入为 0-based PDU 地址（与主站一致）
        pdu_start = cfg["start_addr"]
        count = cfg["count"]
        # PyModbus 数据块为 1-based 地址，需要 +1 转换
        block_start = pdu_start + 1

        # 默认数据块（用于未配置的寄存器类型）
        default_block = ModbusSequentialDataBlock(1, [0] * 10)

        if cfg["fc"] == 3:
            hr_block = ModbusSequentialDataBlock(block_start, values)
            ir_block = default_block
            logging.info(f"保持寄存器块 - PDU起始地址: {pdu_start}, 数量: {count}, 内部块地址: {block_start}")
        else:
            ir_block = ModbusSequentialDataBlock(block_start, values)
            hr_block = default_block
            logging.info(f"输入寄存器块 - PDU起始地址: {pdu_start}, 数量: {count}, 内部块地址: {block_start}")

        store = ModbusDeviceContext(
            di=default_block, co=default_block, hr=hr_block, ir=ir_block
        )

        sig = inspect.signature(ModbusServerContext.__init__)
        params = list(sig.parameters.keys())
        if 'devices' in params:
            context = ModbusServerContext(devices=store, single=True)
        elif 'slaves' in params:
            context = ModbusServerContext(slaves=store, single=True)
        else:
            context = ModbusServerContext(store, single=True)

        async def serve_async():
            server = ModbusTcpServer(context, address=(cfg["host"], cfg["port"]))
            self._server = server
            await server.serve_forever()

        logging.info(f"服务器启动: {cfg['host']}:{cfg['port']}, 功能码={cfg['fc']}, "
                     f"PDU起始地址={pdu_start}, 数量={count}")

        self.task = loop.create_task(serve_async())
        # 任务完成时停止循环
        self.task.add_done_callback(lambda _: loop.call_soon_threadsafe(loop.stop))

        try:
            loop.run_forever()
        except Exception as e:
            logging.error(f"服务器运行异常: {e}")
        finally:
            # 取消所有待处理任务（避免 pending task destroyed 警告）
            self._cleanup_loop(loop)
            # 重置状态并通知 UI
            self.loop = None
            self.task = None
            self._server = None
            self.running = False
            self.server_stopped.emit()
            logging.info("服务器已停止")

    def _cleanup_loop(self, loop):
        """安全清理事件循环中所有待处理任务"""
        try:
            # 取消服务任务（如果还在运行）
            if self.task and not self.task.done():
                self.task.cancel()
            # 收集当前循环中的所有任务
            pending = asyncio.all_tasks(loop)
            if not pending:
                return
            for t in pending:
                t.cancel()
            # 等待所有任务完成取消
            loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
        except Exception:
            pass
        finally:
            loop.close()

    def on_server_stopped(self):
        """服务器停止后恢复按钮状态（主线程执行）"""
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def stop_server(self):
        """请求停止服务器：取消服务任务，触发循环退出"""
        if self.loop and self.loop.is_running():
            logging.info("正在关闭服务器...")
            if self.task and not self.task.done():
                # 在线程安全环境下取消任务，让 serve_forever 抛出 CancelledError
                self.loop.call_soon_threadsafe(self.task.cancel)
        else:
            # 循环已经不在运行，直接重置界面状态
            self.running = False
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)

    def closeEvent(self, event):
        if self.running:
            self.stop_server()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(create_logo())
    win = ModbusSlaveGUI()
    win.show()
    sys.exit(app.exec())