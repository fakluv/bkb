import time
import datetime

#****4字节十六进制数字 与 时间年月日时分秒 的转化*****************************
def hexToSpaceHex(hexNum):   #16进制的数字的字符串转化为每两位加一个空格的字符串
    spaceHex = ""
    hexStr = str(hexNum)
    for index in range(len(hexStr)):
        spaceHex = spaceHex + hexStr[index]
        if index % 2 == 1:
            spaceHex = spaceHex + " "
    return spaceHex

def timeStrToFourBytesHex(tmStr): #获取某个时间字符串转为十六进制,须按照时间字符串，如2022 09 28 01 02 56格式输入
    tmStrWithoutSpace = ''.join(tmStr.split()) #删掉字符串中的空白
    tmArray = time.strptime(tmStrWithoutSpace, '%Y%m%d%H%M%S')  # 将时间字符串格式化为时间元组
    tmStrStamp = time.strftime('%Y-%m-%d %H:%M:%S', tmArray)
    stamp_tm = time.mktime(tmArray)  # 将时间元组转化为时间戳（位浮点数）
    stamp_tm = int(stamp_tm)  # 将浮点数转化为一个整数
    return_tm = hex(stamp_tm)  # 将整数转化为十六进制整数形式的字符串
    return_tm = return_tm[2:]  # 从第二位开始截取字符串
    return_tm = hexToSpaceHex(return_tm)
    print("时间：" + tmStrStamp + " 十六进制表示为：" + return_tm)
    return(return_tm)

def timeHexFourBytesToTimeString(hexStr):  #将十六进制时间转化为时间字符串
    if len(hexStr) < 1:
        print("要转化的十六进制时间字符串为空")
        return ''
    hexStrWithoutSpace = ''.join(hexStr.split())  #删掉字符串中的空白
    tmDec = int(hexStrWithoutSpace, 16)     # 将十六进制字符串转化为十进制整数
    tmInt = float(tmDec)   #整数转化为浮点数
    tmArray = time.localtime(tmInt)  #将浮点数转为时间元祖
    tmStr = time.strftime('%Y-%m-%d--%H:%M:%S', tmArray)  # 将时间类型按照格式转化为字符串
    hexStr = hexToSpaceHex(hexStrWithoutSpace)
    #print("十六进制时间：" + hexStr + " 时间字符串表示为：" + tmStr)
    return(tmStr)

def getNowToHex():  #获取当前时间转为4字节 十六进制
    now_tm = datetime.datetime.now()  # 获取当前时间
    now_tm = now_tm.strftime('%Y%m%d%H%M%S')  #将时间格式化为一个字符串，按年月日时分秒格式
    return_tm = timeStrToHex(now_tm)  # 调用函数将当前时间字符串转化为十六进制
    return(return_tm)

#****6字节十六进制 与 时间年月日时分秒 的转化
def timeStrToSixBytesHex(tmStr):#获取某个时间字符串转为十六进制,须按照时间字符串，如2022 09 28 01 02 56格式输入
    tmArr = tmStr.split()
    hexArr = []
    for index in rang(len(tmArr)):
        tmArr[index] = int(tmArr[index])
    tmArr[0] = tmArr[0] - 1970
    tmArr[1] = tmArr[1] + 1

    for index in  range(len(tmArr)):
        hexStr = hex(tmStr[index])[2:]
        hexArr.append(hexStr)
    return (' '.join(hexArr))

def timehexSixBytesToTimeStr(hexStr):
    timeArr = hexStr.split()
    for index in range(len(timeArr)):
        timeArr[index] = int(timeArr[index], 16)
    date = datetime.datetime(timeArr[0] + 1970, timeArr[1] + 1, timeArr[2], timeArr[3], timeArr[4], timeArr[5])
    timeStr  = date.strftime('%Y%m%d%H%M%S')  # 将时间格式化为一个字符串，按年月日时分秒格式
    return timeStr





