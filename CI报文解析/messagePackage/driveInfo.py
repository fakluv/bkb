from  messagePackage.message import  Message
from  tool.messageTool import  getValueFromHexStr
class DriveInfo(Message):
    ciID = ""
    collectLen = ""
    driveLen = ""
    collectMessage = []
    driveMessage = []

    @classmethod
    def inintWithOneMessage(cls, messageStr, messageArr):
        drive = DriveInfo()
        drive.initWithMessage(messageStr, messageArr)
        drive.ciID = drive.getStrFromArrayWithBytesAmount(2)
        drive.collectLen = drive.getStrFromArrayWithBytesAmount(2)
        drive.driveLen = drive.getStrFromArrayWithBytesAmount(2)

        collectLen = getValueFromHexStr(drive.collectLen)
        drive.collectMessage = drive.getArrFromArrayDataWithAmount(collectLen)
        driveLen = getValueFromHexStr(drive.driveLen)
        drive.driveMessage = drive.getArrFromArrayDataWithAmount(driveLen)

        return drive
    def showInfo(self):
        print("联锁设备编号: %s " % self.ciID)
        print("采集/驱动数据按驱采表定义的顺序传输，字节bit序定义为从每一字节的低bit位向高bit位递增排序")
        print("采集信息: ")
        self.printArrayWithGroupAndColumn(self.collectMessage, 1, 10)
        print("*" * 60)
        print("驱动信息:")
        self.printArrayWithGroupAndColumn(self.driveMessage, 1, 10)


