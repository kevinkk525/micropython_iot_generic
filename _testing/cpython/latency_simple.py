import time
import socket
import json
import struct


def connect():
    s = socket.socket()
    s.connect(("192.168.178.10", 8888))
    s.send("1\n".encode())
    return s


def write(s, app_ident, id, app_header, data):
    header = bytearray(4)
    header[0] = app_ident
    header[1] = id
    header[2] = app_header
    data = "{}{}\n".format("{:08x}".format(struct.unpack("<I", header)[0]), json.dumps(data))
    s.send(data.encode())


def latency(s=None, i=0):
    if s is None:
        s = connect()
    a = time.time()
    write(s, 0, 1, 0, {"hi": "response", "count": i})
    r = b""
    while True:
        r += s.recv(1024)
        if r.find(b"response") != -1:
            break
        time.sleep(0.01)
    b = time.time()
    # print("Latency: {!s}ms".format((b-a)*1000))
    return s, (b - a) * 1000


def latencyMultiple(i, s=None):
    a = time.time()
    if s is None:
        s = connect()
    tmp = a
    a = time.time()
    print("Connect took {!s}ms".format((a - tmp) * 1000))
    for j in range(0, i):
        s, l = latency(s, j)
    b = time.time()
    print("Latency over {!s} messages: {!s}ms".format(i, (b - a) * 1000 / i))
    return s


if __name__ == "__main__":
    print("Starting latency measurement")
    s = latencyMultiple(200)
    s.close()
    time.sleep(0.5)
    s = latencyMultiple(200)
    s.close()
