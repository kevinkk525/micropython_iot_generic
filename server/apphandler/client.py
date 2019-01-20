# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-27 

__updated__ = "2018-12-27"
__version__ = "0.0"

import asyncio
from server.acks_header_clients.client import Client as ClientHeader
import logging
import math
from .apphandler import AppHandler

log = logging.getLogger("Client")


class Client(ClientHeader):
    def __init__(self, client_id=None, len_rx_buffer=100, len_tx_buffer=100, timeout_connection=1500,
                 timeout_client_object=3600):
        """
        Client object holding all buffers and API.
        If buffer overflows, oldest messages will be dropped.
        timeout_client: After this amount of ms without a sent keepalive, the connection will be closed
        timeout_client_object: After this amount of seconds, the client object will be removed resulting in
        an error if still accessed after removal. If Client object should be persistent, use math.inf as argument.
        :param client_id: str
        :param len_rx_buffer: int
        :param len_tx_buffer: int
        :param timeout_connection: int, defaults to 1500ms or if created by Network object to its value
        :param timeout_client_object: int, defaults to 3600s or if created by Network object to its value.
        """
        super().__init__(client_id, len_rx_buffer, len_tx_buffer, timeout_connection, timeout_client_object)
        self.apps = {}
        self.reader_task = None
        self._shutdown_task = asyncio.ensure_future(self._shutdown())

    def start(self, init_message: bytes):
        """
        starts the client object reader,writer,keepalive, etc.
        :param init_message: initial message for login with client_id. Used for its header.
        :return:
        """
        # TODO: implement reading login header for checking if esp did reset or lost wifi.
        #  Also pass to callback for apphandler that can pass it to apps that might behave
        #  differently with a reset client
        super().start(init_message)
        if self.reader_task is None or self.reader_task.done():
            self.reader_task = asyncio.ensure_future(self._reader_app())
        for app in self.apps:
            self.apps[app].start()

    async def _shutdown(self):
        """Client will be removed so clean up and stop everything"""
        await self.closing.wait()
        tasks = []
        for app in self.apps:
            tasks.append(asyncio.ensure_future(self.apps[app].stop()))
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), 3)
        except asyncio.TimeoutError:
            log.warning("App shutdown takes longer than 3 seconds, cancelling")
        if self.reader_task is not None:
            self.reader_task.cancel()

    async def stop(self):
        """Just means that the connection to the client is broken"""
        await super().stop()
        tasks = []
        for app in self.apps:
            tasks.append(asyncio.ensure_future(self.apps[app].pause()))
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), 3)
        except asyncio.TimeoutError:
            log.warning("App pausing takes longer than 3 seconds, cancelling")

    async def read(self, timeout=math.inf, only_with_connection=False):
        raise NotImplementedError(".read() not available for apphandler")

    async def _reader_app(self):
        self.log.debug("_reader started")
        try:
            while True:
                header, data = await super().read()
                self.log.debug("App got {!s} {!s}".format(header, data))
                if header is None:
                    self.log.error("Received no header with message: {!s}".format(data))
                    continue
                if header[1] not in self.apps:
                    try:
                        app = AppHandler.getAppInstance(header[0], header[1], self)
                        self.apps[header[1]] = app
                    except ModuleNotFoundError as e:
                        continue
                    except Exception as e:
                        continue
                else:
                    app = self.apps[header[1]]
                await app.handle(header[2], data)
        except asyncio.CancelledError:
            try:
                self.log.debug("_reader canceled")
            except Exception as e:
                pass  # logger already removed during removal of objects on shutdown?

    async def write(self, app_ident, app_id, app_header, message, timeout=math.inf, only_with_connection=False, qos=0):
        header = bytearray(2)
        header[0] = app_ident
        header[1] = app_id
        if type(app_header) == bytearray:
            header.extend(header)
        elif type(app_header) == int:
            if app_header < 256:
                header.append(app_header)
            else:
                raise TypeError("App_header should be bytearray or int<256, not {!s}".format(app_header))
        return await super().write(header, message, timeout, only_with_connection, qos)
