import time
import socket
import struct
import json


def write(s, app_ident, id, app_header, data):
    header = bytearray(8)
    header[0] = app_ident
    header[1] = id
    header[2] = app_header
    data = "{}{}\n".format("{:08x}".format(struct.unpack("<I", header)[0]), json.dumps(data))
    s.send(data.encode())


def test(i, r=100):
    s = []
    for j in range(0, i):
        s.append(socket.socket())
        s[-1].connect(("192.168.178.10", 8888))
        s[-1].send("{!s}\n".format(j).encode())
    print("Connected and initialized")
    time.sleep(2)
    for k in range(0, r):
        c = 0
        for j in range(0, i):
            write(s[j], 0, 1, 0, {"hi": "response", "count": k})
        while c < 1:
            for j in range(0, i):
                r = s[j].recv(4096)
                if r.find(b'"count": ' + str(k).encode()) != -1:
                    c += 1
            time.sleep(0.01)
    print("Done")
    for j in range(0, i):
        s[j].close()
    time.sleep(0.5)


if __name__ == "__main__":
    while True:
        test(500, 50)
        time.sleep(45)
