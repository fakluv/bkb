import socket
s = socket.socket()
s.settimeout(5)
try:
    s.connect(('192.168.1.213', 9999))
    print('端口可达')
    s.close()
except Exception as e:
    print('端口不通:', e)