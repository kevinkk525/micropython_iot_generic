# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-12 

__updated__ = "2018-12-12"
__version__ = "0.0"

import uasyncio as asyncio
from client import apphandler
from machine import Pin
import gc
import time

server = "192.168.178.10"
port = 8888

loop = asyncio.get_event_loop()
# app_handler = apphandler.get_apphandler(loop, 1, server, port, timeout=1500, verbose=True, led=Pin(2, Pin.OUT, value=1))
# either way works
app_handler = apphandler.AppHandler(loop, 1, server, port, timeout=1500, verbose=True, led=Pin(2, Pin.OUT, value=1))

###
# Publisher
###

publishApp = apphandler.App(ident=2)


# send [(re)connects, message count, mem_free]
async def publisher(self):
    print('Started writer')
    data = [0, 0, 0]
    count = 0
    while True:
        data[0] = app_handler.connects
        data[1] = count
        count += 1
        gc.collect()
        data[2] = gc.mem_free()
        print('Sent', data, 'to server app\n')
        # .write() behaves as per .readline()
        await self.write(data)
        await asyncio.sleep(5)


loop.create_task(publisher(publishApp))

###


###
# Echo Client
###
echoApp = apphandler.App(ident=1)


# send message to server and get it back with incremented count. Also measure delay between message and response
async def echoClient(self):
    count = 0
    delay = 999
    while True:
        st = time.ticks_ms()
        await self.write(["echo message", count, delay])
        message = await self
        et = time.ticks_ms()
        delay = et - st
        count = message[1] + 1


loop.create_task(echoClient(echoApp))


###


###
# Get request
###

# gets the current time from the internet
async def getTime():
    await asyncio.sleep(1)
    st = time.ticks_ms()
    t = await apphandler.AppTemporary("http://just-the-time.appspot.com/", 3, timeout=5)
    et = time.ticks_ms()
    print("Current time:", t, "request took {!s}ms".format(et - st))
    # not yet implemented as a GET App


loop.create_task(getTime())
###


###
# MQTT Client
###

# from .apps.mqtt import Mqtt

# mqtt = Mqtt(["home/test/will", "Died", False])


try:
    loop.run_forever()
finally:
    app_handler.close()
