from  messagePackage.message import  Message
from  tool import messageTool
class Version(Message):
    ciID = ''
    versionNum = ''
    deviceArr = [] #里面的每个元素是一个数组,该数组由 设备编号, 设备版本号(十六进制) 设备版本字符(ascII)  三个元素够成

    @classmethod
    def initWithOneMessage(cls, messageStr, messageArr):
        version = Version()
        version.initWithMessage(messageStr, messageArr)
        version.ciID = version.getStrFromArrayWithBytesAmount(2)
        version.versionNum = version.getStrFromArrayWithBytesAmount(2)

        versionNum = messageTool.getValueFromHexStr(version.versionNum)
        for i in range(versionNum):
            deviceID = version.getStrFromArrayWithBytesAmount(2)
            deviceVersionArr = version.getArrFromArrayDataWithAmount(4)
            deviceVersionStr = ' '.join(deviceVersionArr)
            ascIIcharStr = ''
            for j in range(len(deviceVersionArr)):
                numStr = deviceVersionArr[j]
                ascIIchar = chr(int(numStr, 16))
                ascIIcharStr = ascIIcharStr + ascIIchar
            device  = [deviceID, deviceVersionStr, ascIIcharStr]
            version.deviceArr.append(device)

        return version

    def showInfo(self):
        versionNum = messageTool.getValueFromHexStr(self.versionNum)
        print("联锁设备编号: %s   版本信息总数: %s (%d)" % (self.ciID, self.versionNum, versionNum))

        for i in range(len(self.deviceArr)):
            device = self.deviceArr[i]
            print("  设备%-3d ID: %s  版本: %s (%s)   "  % (i+1, device[0], device[1], device[2]))
            if (i + 1) % 10 == 0:
                print("*" * 60)


