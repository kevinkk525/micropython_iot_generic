# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2019-01-04 

__updated__ = "2019-01-04"
__version__ = "0.0"

import gc
import uasyncio as asyncio
import time

gc.collect()
a = gc.mem_free()
from micropython_iot_generic.client.client import IOT

gc.collect()
b = gc.mem_free()
print("IOT took", b - a, "Bytes of RAM")

# from client.client import IOT
from machine import Pin

loop = asyncio.get_event_loop()


def result(header, message):
    b = time.ticks_ms()
    print(header, message, "delay:", b - int(message))


gc.collect()
a = gc.mem_free()
cl = IOT("1", "192.168.178.10", 8888, 3000, result, 5000, print, verbose=True, led=Pin(2, Pin.OUT, value=1))
gc.collect()
b = gc.mem_free()
print("Creating IOT() took", b - a, "Bytes of RAM")


async def main():
    await cl.connect()
    header = bytearray(4)
    header[0] = 0  # app echo
    cnt = 0
    for i in range(10):
        await cl.write(header, "{!s}".format(time.ticks_ms()))
        cnt += 1
        await asyncio.sleep(1)


loop.run_until_complete(main())
