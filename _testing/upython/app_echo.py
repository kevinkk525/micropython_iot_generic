# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2019-01-02

__updated__ = "2019-01-02"
__version__ = "0.0"

from client.apphandler import get_apphandler, TimeoutError
from client.app_template import App, AppTemporary

import uasyncio as asyncio
from machine import Pin
import gc
import time

server = "192.168.178.10"
port = 8888

loop = asyncio.get_event_loop()

app_handler = get_apphandler(loop, "1", server, port, verbose=True, led=Pin(2, Pin.OUT, value=1))

###
# Echo Client
###
echoApp = App()
echoApp.ident = 0


# send message to server and get it back. Also measure delay between message and response
async def echoClient(app):
    count = 0
    delay = -1
    while True:
        st = time.ticks_ms()
        try:
            header, message = await AppTemporary(app, 0, ["echo message", count, delay, gc.mem_free()])
        except TimeoutError:
            print("TimeoutError waiting for message")
            return
        et = time.ticks_ms()
        delay = et - st
        count = message[1] + 1
        await asyncio.sleep(2)


loop.create_task(echoClient(echoApp))

try:
    loop.run_forever()
finally:
    app_handler.close()
