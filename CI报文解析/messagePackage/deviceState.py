from messagePackage.message import Message
from tool import  messageTool
class DeviceState(Message):
    ciID = ''

    ciInfo1 = []  #各设备通信状态
    ciState = []
    ciStateByteMeaning = []

    ciandDriveMachine = []
    ciandDriveMachineByteMeaning = []

    ciandZC = []
    ciandZCbyteMeaning = []

    ciandLEU = []
    ciandLEUbyteMeaning = []

    ciandSation = []
    ciandSationByteMeaning = []

    ciandCentralStaion = []
    ciandCentralStaionByteMeaning = []

    restCIInfo1 = []
    restCIInfo1ByteMeaning = []

    ciInfo2 = []  #CI码位数据

    byteMeaning = [ '联锁I系的状态', '联锁II系的状态', '联锁I系与I系驱采机的网络状态', '联锁I系与II系驱采机的网络状态', '联锁II系与I系驱采机的网络状态', '联锁II系与II系驱采机的网络状态', '联锁I系、II系与ZC的通信状态', '联锁I系与接口机通信状态', '联锁II系与接口机通信状态', '联锁I系与站间1通信状态', '联锁I系与站间2通信状态', '联锁I系与站间3通信状态', '联锁I系与站间4通信状态', '联锁I系与站间5通信状态', '联锁II系与站间1通信状态', '联锁II系与站间2通信状态', '联锁II系与站间3通信状态', '联锁II系与站间4通信状态', '联锁II系与站间5通信状态', '集中站现地A机与ATS主机的通信状态', '集中站现地B机与ATS主机的通信状态','集中站现地A机与ATSB机的通信状态','集中站现地B机与ATSB机的通信状态', '预留']
    bitMeaningBetweenCIAndDriveMachineI = ['I系_驱采机8', 'I系_驱采机4', 'I系_驱采机7', 'I系_驱采机3', 'I系_驱采机6', 'I系_驱采机2', 'I系_驱采机5', 'I系_驱采机1']
    bitMeaningBetweenCIAndDriveMachineII = ['II系_驱采机4', 'II系_驱采机8', 'II系_驱采机3', 'II系_驱采机7', 'II系_驱采机2', 'II系_驱采机6', 'II系_驱采机1', 'II系_驱采机5']
    driveMachineState = {'0':'网络中断', '1':'网络好'}

    bitMeaningBetweenCIAndZC = ['联锁I系与ZC机A通道状态', '联锁II系与ZC机A通道状态', '联锁I系与ZC机B通道状态', '联锁II系与ZC机B通道状态', '预留']
    zcBitArr = [1,1,1,1,4]
    zcSate = {'0':"故障", '1':"正常"}

    bitMeaningBetweenCIAndLEU = ['联锁与通信机A机A通道', '联锁与通信机B机A通道', '联锁与通信机A机B通道', '联锁与通信机B机B通道', '通信机-A机状态', '通信机-B机状态']
    leuBitArr = [1,1,1,1,2,2]
    leuPassState = {'0': '故障', '1': '正常'}
    leuMachineState = {'00': '离线（故障）', '01': '备用（正常）', '10': '主用（正常）', '11': '未使用'}

    bitMeaningBetweenCIandStation = ['联锁与站间I系A通道', '联锁与站间II系A通道', '联锁与站间I系B通道', '联锁与站间II系B通道', '邻站I系状态', '邻站II系状态']
    stationBitArr = [1,1,1,1,2,2]
    stationState = {'00': '离线', '01': '备用', '10': '主用', '11': '未使用'}
    stationPassState = {'0': '故障', '1': '正常'}

    bitMeaningBetweenCentralSationAndATS = ['现地与ATS网关2网通信状态', '现地与ATS网关1网通信状态','预留']
    centralSationBitArr = [2,2,4]
    centralStationState = {'01':"连通",'10':'断开', '00':'无效','11':'无效'}

    @classmethod
    def inintWithOneMessage(cls, messageStr, meeesageArr):
        device = DeviceState()
        device.initWithMessage(messageStr, meeesageArr)
        device.ciID = device.getStrFromArrayWithBytesAmount(2)
        device.ciInfo1= device.getArrFromArrayDataWithAmount(50)

        length = messageTool.getValueFromHexStr(device.len)
        device.ciInfo2 = device.getArrFromArrayDataWithAmount(length - 65)
        device.separateData()
        return device
    def separateData(self):
        self.ciState = self.ciInfo1[0:2]
        self.ciStateByteMeaning = self.byteMeaning[0:2]
        self.ciandDriveMachine = self.ciInfo1[2:6]
        self.ciandDriveMachineByteMeaning = self.byteMeaning[2:6]
        self.ciandZC = self.ciInfo1[6:7]
        self.ciandZCbyteMeaning = self.byteMeaning[6:7]
        self.ciandLEU = self.ciInfo1[7:9]
        self.ciandLEUbyteMeaning = self.byteMeaning[7:9]
        self.ciandSation = self.ciInfo1[9:19]
        self.ciandSationByteMeaning = self.byteMeaning[9:19]
        self.ciandCentralStaion = self.ciInfo1[19:23]
        self.ciandCentralStaionByteMeaning = self.byteMeaning[19:23]
        self.restCIInfo1 = self.ciInfo1[23:]
        self.restCIInfo1ByteMeaning = self.byteMeaning[23:]
    def showInfo(self):
        print("联锁设备编号: %s " % self.ciID)
        self.separateData()
        self.showCIState()
        self.showCIandDriveMachine()
        self.showCIandZC()
        self.showCIandLEU()
        self.showCIandStaion()
        self.showCIandCentralStaion()
        self.showRestCIinfo1()

        self.showCIinfo2()
    def showCIState(self):
        ciStateDic = {"55":"主控", 'aa':'非主控', "AA":'非主控'}
        for i in range(len(self.ciState)):
            print("%s: %s (%s)" % (self.ciStateByteMeaning[i], self.ciState[i], ciStateDic[self.ciState[i]]))
    def showCIandDriveMachine(self):
        for i in range(len(self.ciandDriveMachine)):
            bitStrWhite = messageTool.hexStringToNumBitStringWihtSpace(self.ciandDriveMachine[i], 8)
            bitStr = messageTool.hexStringToNumBitString(self.ciandDriveMachine[i], 8)
            print("%19s: %s  -%s-" % (self.ciandDriveMachineByteMeaning[i], self.ciandDriveMachine[i], bitStrWhite), end = '')
            bitArr = []
            if i %2 == 1:
                bitArr = self.bitMeaningBetweenCIAndDriveMachineII
            else:
                bitArr = self.bitMeaningBetweenCIAndDriveMachineI
            for j in range(len(bitArr)):
                print(" %8s--B%d:%s-%-4s   " % (bitArr[j], 7-j,  bitStr[j], self.driveMachineState[bitStr[j]]), end = '')
            print()
    def showCIandZC(self):
        self.printADeviceArrStateWith(self.ciandZC, self.ciandZCbyteMeaning, self.bitMeaningBetweenCIAndZC, self.zcBitArr, [self.zcSate])
    def showCIandLEU(self):
        self.printADeviceArrStateWith(self.ciandLEU, self.ciandLEUbyteMeaning, self.bitMeaningBetweenCIAndLEU, self.leuBitArr, [self.leuPassState, self.leuMachineState])
    def showCIandStaion(self):
        self.printADeviceArrStateWith(self.ciandSation, self.ciandSationByteMeaning, self.bitMeaningBetweenCIandStation, self.stationBitArr, [self.stationPassState, self.stationState])
    def showCIandCentralStaion(self):
        self.printADeviceArrStateWith(self.ciandCentralStaion, self.ciandCentralStaionByteMeaning, self.bitMeaningBetweenCentralSationAndATS, self.centralSationBitArr, [self.centralStationState])
    def showRestCIinfo1(self):
        print("ciInfo1预留字节24-50: %s " % (' '.join(self.restCIInfo1)))

    def showCIinfo2(self):
        print("*" * 150)
        print("CI码位数据开始:")

        for i in range(len(self.ciInfo2)):
            byteStr = messageTool.hexStringToNumBitString(self.ciInfo2[i], 8)
            bitStr = byteStr[::-1]
            print("    ", end='')
            for j in range(8):
                print("bit-%-4d: %s     " % (8*i + j, bitStr[j]), end= '')
            print()
            if( i + 1 ) % 10 == 0:
                print()
        print("CI码位数据结束")
        print("*" * 150)
    # staticDicArr 这个数组的中所有字典键必须唯一
    def printADeviceArrStateWith(self, aDeviceArr, aDeviceByteMeaning,aDeviceBitMeaning, aDeviceBitNumArr, stateDicArr):
        print()
        for i in range(len(aDeviceArr)):
            bitStrWhite = messageTool.hexStringToNumBitStringWihtSpace(aDeviceArr[i], 8)
            bitStr = messageTool.hexStringToNumBitString(aDeviceArr[i], 8)
            print("%22s: %s  -%s- " % (aDeviceByteMeaning[i], aDeviceArr[i], bitStrWhite), end='')
            backArr = self.getBitStrExplainStrArrAndPartBitStrArrFrom(bitStr, aDeviceBitMeaning,
                                                                      aDeviceBitNumArr)
            explainArr = backArr[0]
            partBitArr = backArr[1]
            for i in range(len(explainArr)):
                state = ''
                for item in stateDicArr:
                    if partBitArr[i] in item:
                        state = item[partBitArr[i]]
                        break
                print(" %14s%s-%-3s  " % (explainArr[i], partBitArr[i], state), end='')
            print()











