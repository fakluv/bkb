#!/usr/bin/env python3
# 适用于 pysnmp==4.4.12 / Python 3.9
# 监听 127.0.0.1:1161, community=demo123
# OID 前缀: .1.3.6.1.4.1.99999

from pysnmp.entity import engine, config
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.carrier.asyncore.dgram import udp
from pysnmp.proto.api import v2c
from pysnmp.smi import view

# 1) engine
snmpEngine = engine.SnmpEngine()

# 2) transport
config.addTransport(
    snmpEngine,
    udp.domainName,
    udp.UdpTransport().openServerMode(('127.0.0.1', 1161))
)

# 3) v2c community + VACM 读权限
config.addV1System(snmpEngine, 'my-area', 'demo123')
config.addVacmUser(
    snmpEngine, 2, 'my-area', 'noAuthNoPriv',
    (1, 3, 6, 1, 4, 1, 99999)   # 允许读这个子树
)

# 4) context + 自定义 MIB
snmpContext = context.SnmpContext(snmpEngine)
mibBuilder = snmpContext.getMibInstrum().getMibBuilder()
MibScalar, MibScalarInstance = mibBuilder.importSymbols(
    'SNMPv2-SMI', 'MibScalar', 'MibScalarInstance'
)

# ---- 自定义实例类 ----
class DeviceName(MibScalarInstance):
    def getValue(self, name, idx):
        return self.getSyntax().clone('Printer-A1')

class TotalPages(MibScalarInstance):
    def getValue(self, name, idx):
        return self.getSyntax().clone(12345)

class InkLevel(MibScalarInstance):
    def getValue(self, name, idx):
        return self.getSyntax().clone(78)

class DeviceStatus(MibScalarInstance):
    def getValue(self, name, idx):
        return self.getSyntax().clone('online')

class Temperature(MibScalarInstance):
    def getValue(self, name, idx):
        return self.getSyntax().clone(42)

# ---- 注册: 先 MibScalar 定义类型, 再 MibScalarInstance 提供值 ----
base = (1, 3, 6, 1, 4, 1, 99999)

mibBuilder.exportSymbols(
    '__CUSTOM_MIB__',
    MibScalar(base + (1,), v2c.OctetString()),
    DeviceName(base + (1,), (0,), v2c.OctetString()),

    MibScalar(base + (2,), v2c.Integer32()),
    TotalPages(base + (2,), (0,), v2c.Integer32()),

    MibScalar(base + (3,), v2c.Integer32()),
    InkLevel(base + (3,), (0,), v2c.Integer32()),

    MibScalar(base + (4,), v2c.OctetString()),
    DeviceStatus(base + (4,), (0,), v2c.OctetString()),

    MibScalar(base + (5,), v2c.Integer32()),
    Temperature(base + (5,), (0,), v2c.Integer32()),
)

# 5) responders
cmdrsp.GetCommandResponder(snmpEngine, snmpContext)
cmdrsp.NextCommandResponder(snmpEngine, snmpContext)
cmdrsp.BulkCommandResponder(snmpEngine, snmpContext)

# 6) run
print('SNMP v2c agent on 127.0.0.1:1161 community=demo123')
print('walk: snmpwalk -v2c -c demo123 localhost:1161 .1.3.6.1.4.1.99999')
snmpEngine.transportDispatcher.jobStarted(1)
try:
    snmpEngine.transportDispatcher.runDispatcher()
except KeyboardInterrupt:
    snmpEngine.transportDispatcher.closeDispatcher()