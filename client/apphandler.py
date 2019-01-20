# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-10 

__updated__ = "2018-12-10"
__version__ = "0.0"

_client = None  # one server connection instance for multiple apps
import gc
import uasyncio as asyncio

gc.collect()
import ujson

gc.collect()
from micropython_iot.client import Client as _ClientIOT
from micropython_iot import Event, Lock  # Stripped down version of asyn.py

gc.collect()


def get_apphandler(*args, **kwargs):
    global _client
    if _client is None:
        _client = AppHandler(*args, **kwargs)
    return _client


class TimeoutError(Exception):
    pass


class AppHandler(_ClientIOT):
    apps = {}
    # TODO: change this into a pointer apps_first and let apps point to each other to prevent
    #  heap reallocation for temporary apps
    connected = Event()

    def __init__(self, loop, my_id, server, port, timeout=1500, verbose=False, led=None):
        self.verbose = verbose
        my_id = my_id if my_id.endswith("\n") else my_id + "\n"
        super().__init__(loop, my_id, server, port, timeout, self._concb, None, verbose, led)
        global _client
        if _client is None:
            _client = self
        loop.create_task(self.start(loop))

    @staticmethod
    def addInstance(app):
        for i in range(0, 256):
            if i not in AppHandler.apps:
                AppHandler.apps[i] = app
                return i

    @staticmethod
    def deleteInstance(app):
        if app.id in AppHandler.apps:
            del AppHandler.apps[app.id]

    @staticmethod
    async def _concb(state):
        print("Connection state:", state)
        apps = AppHandler.apps
        for app in apps:
            if hasattr(apps[app], "concb"):
                apps[app].concb(state)

    async def start(self, loop):
        self.verbose and print('App awaiting connection.')
        await self
        self.connected.set()  # only now the AppHandler can be used
        loop.create_task(self.reader())

    async def reader(self):
        self.verbose and print('Started reader')
        while True:
            # Attempt to read data: in the event of an outage, .readline()
            # pauses until the connection is re-established.
            header, line = await self.readline()
            if header[1] not in self.apps:  # app_id
                # no support for starting apps on client
                print("App does not exist anymore, discarding message")
                line = None
                header = None
                gc.collect()
                continue
            try:
                data = ujson.loads(line)
            except ValueError:
                self.verbose and print("Can't convert data from json")
                continue
            finally:
                del line
                gc.collect()
            line = None
            app = self.apps[header[1]]
            if app.ident != header[0]:
                self.verbose and print("App ident mismatch for id {!s}".format(header[1]))
                header = None
                continue
            gc.collect()
            self.verbose and print('Got', data, 'from server app')
            app.handle(header[2], data)

    async def write(self, app_ident, app_id, app_header, data):
        header = bytearray(3)
        header[0] = app_ident
        header[1] = app_id
        header[2] = app_header
        if type(data) != bytes:
            data = ujson.dumps(data)
        await super().write(header, data, True)
        await asyncio.sleep_ms(20)  # only do a short pause after sending as we are sending to a faster machine
        gc.collect()

    async def stop(self):
        apps = self.apps
        for app in apps:
            await apps[app].stop()
        super().close()

    async def bad_wifi(self):
        # TODO: implement bad_wifi
        await asyncio.sleep(0)
        # raise OSError('No initial WiFi connection.')
        print("No wifi config?")

    async def bad_server(self):
        # TODO: implement bad_server
        await asyncio.sleep(0)
        # raise OSError('No initial server connection.')
        print("No server config?")
