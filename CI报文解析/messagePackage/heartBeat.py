from messagePackage.message import  Message
class HeartBeat(Message):

    @classmethod
    def initWithOneMessage(cls, messageStr, messageArr):
        heart = HeartBeat()
        heart.initWithMessage(messageStr, messageArr)
        return heart
    def showInfo(self):
        print("", end='')