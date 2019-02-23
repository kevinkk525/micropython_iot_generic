# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-10 

__updated__ = "2019-02-22"
__version__ = "0.1"

_client = None  # one server connection instance for multiple apps
import gc
import uasyncio as asyncio
from micropython_iot.client import Client
from micropython_iot import Event, Lock  # Stripped down version of asyn.py

gc.collect()


def get_apphandler(*args, **kwargs):
    global _client
    if _client is None:
        _client = AppHandler(*args, **kwargs)
    return _client


class TimeoutError(Exception):
    pass


class AppHandler(Client):
    _af = None
    _ac = bytearray(1)
    connected = Event()

    def __init__(self, loop, my_id, server, port, timeout=5000, verbose=False, led=None):
        super().__init__(loop, my_id, server, port, timeout=timeout,
                         conn_cb=self._concb, verbose=verbose, led=led)
        global _client
        if _client is None:
            _client = self
        self._reader_task = self._reader()
        loop.create_task(self._reader_task)

    @classmethod
    def addInstance(cls, app):
        while True:
            i = cls._af
            if i is None:
                cls._af = app
            else:
                # search for available id
                while True:
                    if i.id == cls._ac[0]:
                        break
                    if i.next is not None:
                        i = i.next
                    else:
                        break
                if i.id == cls._ac:
                    cls._ac[0] += 1
                    continue
                i.next = app
            cls._ac[0] += 1
            return cls._ac[0] - 1

    @classmethod
    def deleteInstance(cls, app):
        i = cls._af
        p = None
        while i is not None:
            if i == app:
                if i == cls._af:
                    cls._af = None
                    if i.next is not None:
                        cls._af = i.next
                    return
                p.next = i.next
                return
            p = i
            i = i.next

    @classmethod
    async def _concb(cls, state):
        print("Connection state:", state)
        i = cls._af
        while i is not None:
            if hasattr(i, "concb"):
                i.concb(state)
            i = i.next

    async def read(self):
        raise NotImplementedError("read not available for apphandler")

    async def _reader(self):
        self._verbose and print('App awaiting connection.')
        await self
        self.connected.set()  # only now the AppHandler can be used
        self._verbose and print('Started reader')
        read = super().read  # performance optimization
        while True:
            # Attempt to read data: in the event of an outage, .readline()
            # pauses until the connection is re-established.
            header, line = await read()
            i = self._af
            f = False
            while i is not None:
                if i.id == header[1]:  # app_id
                    f = True
                    if i.ident != header[0]:
                        self._verbose and print("App ident mismatch for id {!s}".format(header[1]))
                        break
                    self._verbose and print('Got', line, 'from server app')
                    i.handle(header[2], line)
                    break
                i = i.next
            if f is False:
                # no support for starting apps on client
                print("App does not exist anymore, discarding message")
            gc.collect()

    async def write(self, app_ident, app_id, app_header, data, qos=True):
        header = bytearray(3)
        header[0] = app_ident
        header[1] = app_id
        header[2] = app_header
        await super().write(header, data, qos)
        gc.collect()

    async def stop(self):
        asyncio.cancel(self._reader_task)
        i = self._af
        while i is not None:
            if hasattr(i, "concb"):
                i.stop()
            i = i.next
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
