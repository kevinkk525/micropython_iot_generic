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
app_handler = apphandler.get_apphandler(loop, b"1", server, port, timeout=1500, verbose=True,
                                        led=Pin(2, Pin.OUT, value=1))

###
# Publisher (no counterpart on server yet)
###

from client.app_template import App

publishApp = App()
publishApp.ident = 3


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


# loop.create_task(publisher(publishApp))

###


###
# Echo Client
###
echoApp = App()
echoApp.ident = 0


# send message to server and get it back. Also measure delay between message and response
async def echoClient(self):
    count = 0
    delay = 999
    while True:
        st = time.ticks_ms()
        await self.write(["echo message", count, delay])
        while self.data is None:
            await asyncio.sleep_ms(100)
        message = self.data
        et = time.ticks_ms()
        delay = et - st
        count = message[1] + 1


loop.create_task(echoClient(echoApp))


###


###
# Get request (no counterpart on server yet)
###

# gets the current time from the internet
async def getTime():
    await asyncio.sleep(1)
    st = time.ticks_ms()
    t = await apphandler.AppTemporary("http://just-the-time.appspot.com/", 3, timeout=5, ident=2)
    et = time.ticks_ms()
    print("Current time:", t, "request took {!s}ms".format(et - st))
    # not yet implemented as a GET App


# loop.create_task(getTime())


###
# MQTT Client
###

from client.apps.mqtt import Mqtt

mqtt = Mqtt(["home/test/status", "last_will", 0, False], ["home/test/status", "welcome_message", 0, False])


def mqtt_cb(topic, message, retained):
    print("Got message", message, "from topic", topic)


async def subscribe():
    await mqtt.subscribe("home/test/cb", mqtt_cb)
    await asyncio.sleep(1)
    await mqtt.publish("home/test/cb", "callback message")


loop.create_task(subscribe())
###


try:
    loop.run_forever()
finally:
    app_handler.close()
