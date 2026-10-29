from tool import  messageTool
from messagePackage.deviceState import  DeviceState
from messagePackage.driveInfo import DriveInfo
from messagePackage.version import Version
from messagePackage.heartBeat import HeartBeat

messageStr = input("请输入CI报文:")

messageStr = messageTool.deletTimePrefixFrom(messageStr)
messageArr = messageStr.split()

if messageArr[3] == "40":
    device = DeviceState.inintWithOneMessage(messageStr, messageArr)
    device.showMyInfo()
elif messageArr[3] == '41':
    version = Version.initWithOneMessage(messageStr, messageArr)
    version.showMyInfo()
elif messageArr[3] == '43':
    driveInfo = DriveInfo.inintWithOneMessage(messageStr, messageArr)
    driveInfo.showMyInfo()
elif messageArr[3] == '42':
    heart = HeartBeat.initWithOneMessage(messageStr, messageArr)
    heart.showMyInfo()
else:
    print("报文类型有误,请核对后重新输入!")




