# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2019-01-02 

__updated__ = "2019-01-02"
__version__ = "0.0"

from micropython_iot_generic.client import apphandler
from micropython_iot_generic.client.apps.mqtt import Mqtt

import uasyncio as asyncio
from machine import Pin
import gc
import time

server = "192.168.178.10"
port = 8888

loop = asyncio.get_event_loop()

app_handler = apphandler.AppHandler(loop, b"1\n", server, port, timeout=1500, verbose=True,
                                    led=Pin(2, Pin.OUT, value=1))

###
# MQTT Client
###
mqtt = Mqtt(["home/test/status", "OFFLINE", 0, False], ["home/test/status", "ONLINE", 0, False])


def cb(topic, msg, retain):
    print("CB", topic, msg, retain)


async def coro(topic, msg, retain):
    print("CORO", topic, msg, retain)


def every(topic, msg, retain):
    print("Every", topic, msg, retain)


def delay(topic, msg, retain):
    b = time.ticks_ms()
    print("Got message with delay of", b - int(msg), "ms")


def led(topic, msg, retain):
    print("LED:", topic, msg, retain)


async def main():
    print("started")
    # await mqtt.publish("home/test/status", "ONLINE", False, 0)
    await mqtt.subscribe("home/test/cb", cb)
    await mqtt.subscribe("home/test/coro", coro)
    await mqtt.subscribe("home/test/#", every)
    await mqtt.subscribe("home/test/delay", delay)
    await asyncio.sleep(1)
    a = time.ticks_ms()
    await mqtt.publish("home/test/delay", a)
    await asyncio.sleep(1)
    await mqtt.publish("home/test/led", "ON", retain=True)
    await asyncio.sleep(1)
    await mqtt.subscribe("home/test/led/set", led, check_retained_state_topic=True)
    while True:
        await asyncio.sleep(2)
        await mqtt.publish("home/test/ram", gc.mem_free())
        gc.collect()


loop.create_task(main())

try:
    loop.run_forever()
finally:
    app_handler.close()
