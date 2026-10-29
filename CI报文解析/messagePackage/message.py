from  tool import timeTool
class Message:
    head = ''
    len = ''
    messageID = ''
    timeStamp = ''
    sn = ''
    messageStr = ''
    messsageArray = ''

    end = ''
    crc = ''

    index = 0 #读取报文时候的读取标志

    def initWithMessage(self, messageStr, messageArray):
        self.messageStr = messageStr
        self.messageArray = messageArray

        self.head = messageArray[0]
        self.len = ' '.join(messageArray[1:3])
        self.messageID = messageArray[3]
        self.timeStamp = ' '.join(messageArray[4:8])
        self.index = 8
        self.sn = self.getStrFromArrayWithBytesAmount(4)


        self.crc = ' '.join(messageArray[-5:-1])
        self.end = messageArray[-1]

    def showMyInfo(self):
        timeStr = timeTool.timeHexFourBytesToTimeString(self.timeStamp)
        print("帧开始标志: %s   长度: %s   messageID: %s   时间戳: %s (%s)" \
              % (self.head, self.len, self.messageID, self.timeStamp, timeStr))
        print("报文序列号: %s " % (self.sn))
        self.showInfo()
        print("校验码: %s   帧结束标志: %s " % ( self.crc, self.end))

    def showInfo(self):
        print("给子类重写的")



    # 读取数组后面多少个字节作为字符串返回,index 自动叠加
    def getStrFromArrayWithBytesAmount(self, amount):
        backStr = None
        if amount == 1:
            backStr = self.messageArray[self.index]
        elif (self.index + amount) >=  (len(self.messageArray) - 1):
            backStrArr = self.messageArray[self.index : ]
            backStr = ' '.join(backStrArr)
        else:
            backStrArr = self.messageArray[self.index: self.index + amount]
            backStr = ' '.join(backStrArr)
        self.index = self.index + amount
        return backStr
    #读取数组后面多少个字节作为数组返回, index 自动叠加
    def getArrFromArrayDataWithAmount(self, amount ):
        backArr = None
        if amount == 1:
            backArr = [self.messageArray[self.index],]
        elif (self.index + amount) == len(self.messageArray):
            backArr = self.messageArray[self.index:]
        else:
            backArr = self.messageArray[self.index: self.index + amount]
        self.index = self.index + amount
        return backArr

    # 获取数组的后两个字节作为数量,剩下的的计算出读取多少个字节数,返回 该数量字符串和截取数组范围组成的数组,构成的数组
    def getBakTwoBytesForAmountStrAndRestForStatesArrFrom(self, messageArray, pattern, patternNum):
        numStr = messageArray[self.index] + ' ' + messageArray[self.index + 1]
        num = int(messageArray[self.index] + messageArray[self.index + 1], 16)
        self.index = self.index + 2
        dataArr = self.getArrayDataWithAmountIntPatternPatternNum(messageArray, num, pattern, patternNum)
        backArr = [numStr, dataArr]
        return backArr

    # 利用当前index, 读取数组后面 数量Amount   单位长度PatterNum  单位Pattern的数据,返回读取后的数据
    def getArrayDataWithAmountIntPatternPatternNum(self, messageArray, amountInt, pattern, patternNum):
        bytesNum = self.getBytesWithAmountIntPatternAndPatternNum(amountInt, pattern, patternNum)
        backArr = messageArray[self.index: self.index + bytesNum]
        self.index = self.index + bytesNum
        return backArr

    # 根据 数量  pattern('Byte'或者'Bit')  和单组的数量(多少个字节或位)  来计算出需要的字节大小
    def getBytesWithAmountIntPatternAndPatternNum(self, amount, pattern, patternNum):
        bytesNum = 0
        num = amount * patternNum
        if pattern == 'Byte':
            bytesNum = num
        elif pattern == 'Bit':
            if num % 8 == 0:
                bytesNum = int(num / 8)
            else:
                bytesNum = int(num / 8) + 1
        else:
            raise Exception('请输入正确编码格式:"Byte"或者"bit"')
        return bytesNum

    # 打印数组数量,以及状态,默认字节位 首先使用地位,高位补零
    def printExplainStrAmountAndListFrom(self, explainStr, amount, messageArray, pattern, patterenNum):
        print("%s %s  一以下字节中以-%d%s-为一组,表示一个状态一" % (explainStr, amount, patterenNum, pattern))
        amountNum = int(''.join(amount.split()), 16)
        if amountNum == 0:
            return

        if pattern == 'Byte':
            self.printArrayWithGroupAndColumn(messageArray, patterenNum, 10)
        else:
            self.printArrayWithGroupAndColumn(messageArray, 1, 10)
            bytesNum = amountNum * patterenNum
            lastBitNum = bytesNum % 8
            print("以上最后一个字节的Bit有效位为--%d--位,bit位置首先使用低地址,高位补零" % lastBitNum)
        print()
    # 分组打印
    def printArrayWithGroupAndColumn(self, messageArray, groupNum, columnNum):
        columnAmount = groupNum * columnNum
        line = 0
        for index in range(len(messageArray)):
            print("%s " % messageArray[index], end='')
            if (index + 1) % groupNum == 0:
                print("  ", end='')
            if (index + 1) % columnAmount == 0:
                print()
                if (line + 1) % 10 == 0:
                    print()
                line = line + 1
        if len(messageArray) % columnAmount != 0:
            print()
   #获取一个bitStr的位内容介绍
    def getBitStrExplainStrArrAndPartBitStrArrFrom(self, bitStr, bitMeaning, bitNumArr):
        explainArr = []
        partBitArr = []

        index = 0
        for i in range(len(bitNumArr)):
            partBitStr = bitStr[index: index + bitNumArr[i]]
            partBitArr.append(partBitStr)

            explainStr = ''
            if bitNumArr[i] == 1:
                explainStr = "B" + str(7-index)
            else:
                explainStr = "B" + str(7-index) + "-"+"B"+ str(7-index - bitNumArr[i] + 1)
            index = index + bitNumArr[i]
            explainStr = bitMeaning[i]  + ' ' + explainStr + ':'
            explainArr.append(explainStr)
        return [explainArr, partBitArr]



