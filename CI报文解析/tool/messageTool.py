


#从一对大括号中截取报文生成一条报文字符串
def getNumInBraceFromOneMessage(oneMessage):
    startNum = oneMessage.find("{")
    endNum = oneMessage.rfind('}')
    if  startNum == -1 or endNum == -1 :
        print("输入报文大括号不匹配")
        return None
    numInBrace = oneMessage[startNum+1:endNum]
    return numInBrace

#删除第二个']'前面的字符串,即在报文前出现两个中括号报文的时候,用来删去前缀
def deletTimePrefixFrom(oneMessageStr):
    first = oneMessageStr.find(']')
    if first == -1 :
        print("报文没有]符号,请查看报文或者重新设计解析规则:%s",oneMessageStr)
        return ''
    second = oneMessageStr.find(']', first + 1,)
    if second == -1 :
        print("报文没有第二个]符号,请查看报文或者重新设计解析规则:%s",oneMessageStr)
        return ''
    oneMessageWithoutTime = oneMessageStr[second+1:]
    return oneMessageWithoutTime
def getSignedIntWithBitStr( bitStr):
    bitStr = ''.join(bitStr.split())
    sum  = 0
    if bitStr[0] == '1':
        bitStr = bitStr[1:]
        sum = 0 - int(bitStr, 2)
    else:
        sum = int(bitStr, 2)
    return sum

#获取16进制字符串的十进制值,可包含空白
def getValueFromHexStr(hexStr):
    hexStr = ''.join(hexStr.split())
    num = int(hexStr, 16)
    return  num
#将一个16进制的数字字符串,转化为bitNum位的二进制
def hexStringToNumBitString(hexStr,bitNum):
    hexStr = ''.join(hexStr.split())
    hexNum = int(hexStr,16)
    bitNum = int(bitNum)
    bitStr = bin(hexNum)[2:]
    bitStr = bitStr.rjust(bitNum,'0')
    return (bitStr)
#将一个16进制的数字字符串,转化为bitNum位的二进制,4位加一个空格
def hexStringToNumBitStringWihtSpace(hexStr, bitNum):
    numStr = hexStringToNumBitString(hexStr,bitNum)
    back = ''
    for i in range(len(numStr)):
        if (i + 1) % 4 == 0 and  (i+1) != len(numStr):
            back = ' ' + numStr[0-1-i] + back
        else:
            back = numStr[0-1-i] + back
    return back
#array["说明", 开始位置, 结束位置],从右边开始,包含边缘
def getBitStrWithBitMark(bitStr, array):
    bitStr = ''.join(bitStr.split())
    backStr = ''
    for i in range(len(bitStr)):
        stamp = 0
        for j in range( int( len(array) /3 ) ):
            if i == array[3*j + 1]:
                if i == array[3*j + 2]:
                    backStr =  array[3*j]+'('+bitStr[0-i-1]+')' + backStr
                else:
                    backStr = bitStr[0-i-1] +')' + backStr
                stamp = 1
                break

            elif i == array[3*j + 2]:
                stamp = 1
                backStr =  array[3 * j] + '(' + bitStr[0-i-1] + backStr
                break
        if stamp == 0:
            backStr =  bitStr[0-i-1] + backStr
    return backStr
#将一个二进制的数字字符串,转化为 每两位的二进制字符串  的数列, 最后一位为单数则补一个零
def getTwoBitStrArrFromBitStr(bitStr):
    bitStr = ''.join(bitStr.split())
    numArr = []
    for index in range(len(bitStr)):
        if index % 2 == 1:
            twoBitStr = bitStr[index - 1] + bitStr[index]
            numArr.append(twoBitStr)

    lastIndex = len(bitStr) - 1
    if lastIndex % 2 == 0:
        numArr.append('0' + bitStr[lastIndex])
    return numArr


#将一个二进制的数字字符串,转化为 每两位的十进制值为一个元素 的数列
def getTwoBitValueArrFromBitStr(bitStr):
    numArr = []
    for index in range(len(bitStr)):
        if index % 2 == 1:
            twoBitStr = bitStr[index - 1] + bitStr[index]
            numArr.append(int(twoBitStr, 2))

    lastIndex = len(bitStr) - 1
    if lastIndex % 2 == 0:
        numArr.append(int(bitStr[lastIndex]), 2)
    return numArr

#从一个二进制数字字符串中截取,当中特定位置,startBit,endBit 按照的是该数字字符串中二进制的位置,
#从右边是低位开始,包含start位和end位,如果只获取一位,则须让endBit == startBit
def getBitStrFromRightStartAndEnd(bitStr, startBit, endBit):
    bitStr = ''.join(bitStr.split())
    if endBit - startBit >= len(bitStr):
        raise Exception("倒序获取二进制字符串中的值转化十进制的时候,获取的长度超出字符串限制")
    numBitStr = ''
    if startBit == endBit:
        numBitStr = bitStr[0 - endBit - 1]
    else:

        startBit = 0 - startBit - 1 + 1
        endBit = 0 - endBit - 1

        if startBit == 0:
            numBitStr = bitStr[endBit:]
        else:
            numBitStr = bitStr[endBit:startBit]
    return numBitStr
#从右边开始, 获取二进制字符串中包含start位和end位的十进制数值 
def getBitValueFromRightStartAndEnd(bitStr,startBit,endBit):
    numBitStr = getBitStrFromRightStartAndEnd(bitStr, startBit, endBit)
    num = int(numBitStr, 2)
    return num

#获取二进制字符串中的某几位的字符串,从左边是低位开始, 如果只获取一位,须让startBit = endBt
def getBitStrFromLeftStartAndEnd(bitStr, startBit, endBit):
    bitStr = ''.join(bitStr.split())
    if endBit - startBit >= len(bitStr):
        raise Exception("倒序获取二进制字符串中的值转化十进制的时候,获取的长度超出字符串限制")
    numBitStr = ''
    if startBit == endBit:
        numBitStr = bitStr[startBit]
    else:
        if endBit == len(bitStr) - 1:
            numBitStr = bitStr[startBit:]
        else:
            numBitStr = bitStr[startBit: endBit + 1]
    return numBitStr
    
def getBitValueFromLeftStartAndEnd(bitStr, startBit, endBit):
    numBitStr = getBitStrFromRightStartAndEnd(bitStr, startBit, endBit)
    num = int(numBitStr, 2)
    return num
    




# 4字节十六进制 与  浮点数 的转化
import struct

#浮点数 转为 4字节的十六进制数字
def getFourBytesHexFromFloat(numF):
    numF = float(numF)
    bytesNum = struct.pack('f', numF)  # 将浮点数234.56转化为4字节 十进制数
    bytesHex = []
    # 将bytesNume 中的十进制数字用十六进制表示,放进bytesHex里面
    for i in bytesNum:
        bytesHex.append(hex(i)[2:])
    numHexStr = ' '.join(bytesHex)
    return numHexStr

#4字节的十六进制数字 转为 浮点数,4字节的十六进制数字以空格隔开
def getFloatFromFoutBytesHexStr(hexStr):
    numList = hexStr.split()
    for i in range(len(numList)):
        numList[i] = int(numList[i], 16)
    bytesNum = struct.pack('4B', numList[0], numList[1], numList[2], numList[3])
    num = struct.unpack('f', bytesNum)[0]
    return num






