#!/usr/bin/env python3
"""
Modbus TCP 从站仿真 (pymodbus 3.10.0) - 动态适配参数
"""
import logging
import inspect
from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.datastore.context import ModbusDeviceContext  # 直接使用已知可用的类

# ==================== 在这里修改配置 ====================
HOST = "192.168.0.35"
PORT = 502
FC = 4                        # 3=保持寄存器，4=输入寄存器
START_ADDR = 30001           # 起始地址（0‑based）
COUNT = 400
VALUE = 65534
# ========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 创建数据块
default_block = ModbusSequentialDataBlock(0, [0] * 10)
if FC == 3:
    hr_block = ModbusSequentialDataBlock(START_ADDR, [VALUE] * COUNT)
    ir_block = default_block
    logger.info("启用保持寄存器 (功能码 03)")
elif FC == 4:
    ir_block = ModbusSequentialDataBlock(START_ADDR, [VALUE] * COUNT)
    hr_block = default_block
    logger.info("启用输入寄存器 (功能码 04)")
else:
    raise ValueError("功能码仅支持 3 或 4")

store = ModbusDeviceContext(
    di=default_block,
    co=default_block,
    hr=hr_block,
    ir=ir_block,
)

# 动态探测 ModbusServerContext 的正确初始化方式
sig = inspect.signature(ModbusServerContext.__init__)
params = list(sig.parameters.keys())
logger.info(f"ModbusServerContext.__init__ 参数: {params}")

if 'slaves' in params:
    context = ModbusServerContext(slaves=store, single=True)
elif 'slave' in params:
    context = ModbusServerContext(slave=store, single=True)
else:
    # 第一个位置参数可能就是 slaves
    context = ModbusServerContext(store, single=True)

logger.info("=== Modbus TCP 从站启动 ===")
logger.info(f"{HOST}:{PORT}  |  FC={FC}  |  起始={START_ADDR}  数量={COUNT}  值={VALUE}")
StartTcpServer(context=context, address=(HOST, PORT))