# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2019-01-02 

__updated__ = "2019-01-02"
__version__ = "0.0"

import time
import socket
import json
import struct


def timeit(f):
    myname = str(f).split(' ')[1]

    def new_func(*args, **kwargs):
        t = time.ticks_us()
        result = f(*args, **kwargs)
        delta = time.ticks_diff(time.ticks_us(), t)
        print('[Time] Function {}: {:6.3f}ms'.format(myname, delta / 1000))
        return result

    return new_func


@timeit
def connect():
    """around 5-10ms"""
    s = socket.socket()
    s.connect(("192.168.178.10", 8888))
    s.setblocking(False)
    s.send("1\n".encode())
    return s


@timeit
def create_header(app_ident, id, app_header):
    """around 0.4ms"""
    header = bytearray(4)
    header[0] = app_ident
    header[1] = id
    header[2] = app_header
    return header


@timeit
def transform_header(header):
    """around 1ms"""
    return b"{:08x}".format(struct.unpack("<I", header)[0])


@timeit
def json_data(data):
    """around 5ms"""
    return json.dumps(data).encode()


@timeit
def merge_data(header, data):
    # around 12ms
    # return "{}{}\n".format(header, data).encode() # header: str, data: str
    # around 8ms
    # return (header + data + "\n").encode() # header: str, data: str
    # around 0.3 ms
    return header + data + b"\n"


@timeit
def transform_split(app_ident, id, app_header, data):
    """takes around 31ms"""
    header = create_header(app_ident, id, app_header)
    header = transform_header(header)
    data = json_data(data)
    data = merge_data(header, data)
    return data


@timeit
def transform(app_ident, id, app_header, data):
    """takes around 6ms, previous version with ubinascii and strings needed at least 20ms"""
    header = bytearray(4)
    header[0] = app_ident
    header[1] = id
    header[2] = app_header
    data = b"{:08x}".format(struct.unpack("<I", header)[0]) + json.dumps(data).encode() + b"\n"
    return data


@timeit
def write(s, data):
    """around 0.5ms"""
    s.send(data)


@timeit
def recv(s):
    """around 150ms in blocking mode although server needs only a few ms at most"""
    try:
        return s.recv(2048)
    except OSError:
        return b""


@timeit
def find(r):
    """around 0.3ms"""
    if r.find(b"response") != -1:
        return True
    return False


@timeit
def latency(s=None, i=0):
    """On esp8266 around 170ms but with split transform more, on unix port around 50ms"""
    if s is None:
        s = connect()
    data = transform(0, 1, 0, {"hi": "response", "count": i})
    write(s, data)
    r = b""
    while True:
        time.sleep_ms(10)
        r += recv(s)
        if find(r):
            break
    return s


@timeit
def latencySplit(s=None, i=0):
    """On esp8266 around 170ms but with split transform more, on unix port around 50ms"""
    if s is None:
        s = connect()
    data = transform_split(0, 1, 0, {"hi": "response", "count": i})
    write(s, data)
    r = b""
    while True:
        time.sleep_ms(10)
        r += recv(s)
        if find(r):
            break
    return s


@timeit
def latencyMultiple(i, s=None):
    """Average latency over 50 messages: 180ms"""
    a = time.ticks_ms()
    if s is None:
        s = connect()
    for j in range(0, i):
        s = latency(s, j)
    b = time.ticks_ms()
    print("Latency over {!s} messages: {!s}ms".format(i, (b - a) / i))
    return s


print("Starting latency measurement")
s = latency()
s.close()
print("\n")
time.sleep_ms(100)
s = latencySplit()
s.close()
# s = latencyMultiple(50)
# s.close()
# time.sleep(0.5)
# s = latencyMultiple(50)
# s.close()
