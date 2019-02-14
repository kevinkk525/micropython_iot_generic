# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-27 

__updated__ = "2018-12-31"
__version__ = "0.1"

import time
import asyncio
import math

from server.server_generic import getNetwork as _getNetwork
import logging

log = logging.getLogger("Client")


# TODO: add timeout to receiving keepalives to close the connection server-side if no keepalive received
# TODO: apparently still some client instances not removed if client reconnects during sleeping phase

class ClientRemovedException(Exception):
    pass


def _checkRemoved(f):
    def _checkRemovedWrap(self, *args, **kwargs):
        if self.removed:
            raise ClientRemovedException("Client Object has been removed")
        else:
            return f(self, *args, **kwargs)

    return _checkRemovedWrap


def _checkRemovedAsync(f):
    async def _checkRemovedWrap(self, *args, **kwargs):
        if self.removed:
            raise ClientRemovedException("Client Object has been removed")
        else:
            return await f(self, *args, **kwargs)

    return _checkRemovedWrap


class Client:
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
        if timeout_client_object is None:
            timeout_client_object = math.inf
        self.client_id = client_id if client_id is None else str(client_id)
        self.lines_received = []
        self.len_rx_buffer = len_rx_buffer
        self.len_tx_buffer = len_tx_buffer
        self.new_message_rx = asyncio.Event()
        self.new_message_tx = asyncio.Event()
        self.output_buffer = []
        self.keepalive_task = None
        self.writer_task = None
        self.await_client_timeout_task = None
        self.await_shutdown_task = None
        self.connected = asyncio.Event()  # gets set once the client sends his id
        self.closing = asyncio.Event()
        self.transport = None  # will be set by ClientConnection
        self._removed = False  # if object has been removed. Will raise errors if tried to access.
        self.timeout_client = timeout_client_object
        self.timeout_connection = timeout_connection
        self.last_connection_time = None  # Client can be created without an active connection
        self.last_rx_time = None
        self.log = logging.getLogger("{!s}".format(self))
        self.log.debug("Client created")

    def __str__(self):
        return 'Client.{!s}'.format(self.client_id)

    def __repr__(self):
        return '"Client {!s}"'.format(self.client_id)

    @classmethod
    def readID(cls, message: bytes) -> str:
        """
        Returns client_id according to protocol implementation
        :param message: message without newline termination
        :return: client_id str
        """
        return message.decode()  # generic client just receives the plain client_id

    @property
    def removed(self):
        return self._removed

    @property
    @_checkRemoved
    def is_connected(self):
        if self.client_id is None:
            raise ValueError("Can't check connection state for Client with id None")
        if self.client_id in _getNetwork().clients:
            if _getNetwork().clients[self.client_id].connected.is_set():
                return True
        return False

    # @_checkRemovedAsync
    async def awaitConnection(self, timeout=math.inf):
        if timeout is None:
            timeout = math.inf
        if self.client_id is None:
            raise ValueError("Can't wait for client with id None")
        st = time.time()
        while time.time() - st < timeout:
            while self.client_id in _getNetwork().clients:
                if time.time() - st > timeout:
                    break
                try:
                    await asyncio.wait_for(_getNetwork().clients[self.client_id].connected.wait(), 1)
                except asyncio.TimeoutError:
                    continue
                return True
            while self.client_id not in _getNetwork().clients:
                if time.time() - st > timeout:
                    break
                try:
                    await asyncio.wait_for(_getNetwork().new_client.wait(), 1)
                except asyncio.TimeoutError:
                    continue
        raise asyncio.TimeoutError("Timeout waiting for client connection")

    async def _await_removal(self):
        self.log.debug("Awaiting removal")
        self.connected.clear()
        if self.timeout_client == math.inf:
            self.log.debug("Client is persistent, won't remove")
            return  # won't remove Client object
        self.log.debug("Sleeping {!s}".format(self.timeout_client))
        try:
            await asyncio.sleep(self.timeout_client)
        except asyncio.CancelledError:
            self.log.debug("Awaiting removal canceled")
            return
        self.log.debug("Done sleeping")
        if self.await_shutdown_task is not None and not self.await_shutdown_task.done():
            self.await_shutdown_task.cancel()
        self.closing.set()
        await asyncio.sleep(3)  # give apps time to receive and process information
        self.log.debug("Client removed from client list")
        try:
            _getNetwork().clients.pop(self.client_id)
        except KeyError:
            pass
        # self.log.debug("Client list: {!s}".format(_getNetwork().clients))
        self._removed = True

    # @_checkRemoved
    async def stop(self):
        self.connected.clear()
        if self.closing.is_set() is False:
            self.log.debug("Cancelling all tasks")
            if self.await_client_timeout_task is None or self.await_client_timeout_task.done():
                self.await_client_timeout_task = asyncio.ensure_future(self._await_removal())
        if self.writer_task is not None:
            self.writer_task.cancel()
        if self.keepalive_task is not None:
            self.keepalive_task.cancel()
        self.lines_received = []
        self.output_buffer = []
        self._removeTransport()

    def _removeTransport(self):
        if self.transport is not None:
            self.log.debug("Closing transport")
            try:
                self.transport.close()
            except Exception as e:
                self.log.debug("Exception closing transport: {!s}".format(e))
            self.transport = None

    async def _await_shutdown(self):
        # self.log.debug("Started awaiting network shutdown")
        while self._removed is False:
            try:
                await asyncio.wait_for(_getNetwork().shutdown_requested.wait(), 1)
            except asyncio.TimeoutError:
                continue
            self.log.debug("Received shutdown signal")
            self.closing.set()
            if self.await_client_timeout_task is not None and not self.await_client_timeout_task.done():
                self.await_client_timeout_task.cancel()
            await asyncio.sleep(3)
            await self.stop()
            try:
                _getNetwork().clients.pop(self.client_id)
            except KeyError:
                pass
            # self.log.debug("Client list: {!s}".format(_getNetwork().clients))
            self._removed = True
            return
        self.log.debug("await shutdown, client already removed")

    @_checkRemoved
    def start(self, init_message: bytes):
        """
        starts the client object reader,writer,keepalive, etc.
        :param init_message: initial message for login with client_id. Not used in generic_client
        :return:
        """
        self.log.debug("Starting")
        self.last_connection_time = time.time()
        self.last_rx_time = time.time()
        self.new_message_rx.clear()
        self.connected.set()
        if self.await_client_timeout_task is not None:
            self.await_client_timeout_task.cancel()
        if self.keepalive_task is None or self.keepalive_task.done():
            self.keepalive_task = asyncio.ensure_future(self._keepalive())
        self.writer_task = asyncio.ensure_future(self._write())
        if self.await_shutdown_task is None or self.await_shutdown_task.done():
            self.await_shutdown_task = asyncio.ensure_future(self._await_shutdown())

    @_checkRemovedAsync
    async def read(self, timeout=math.inf, only_with_connection=False) -> str:
        """
        Reads one message. Awaits until timeout.
        If only_with_connection is True, will return messages if buffer is not empty, otherwise raise Exception
        :param timeout: float (None will be math.inf)
        :param only_with_connection: bool
        :return: str
        """
        return (await self._read(timeout, only_with_connection)).decode()

    async def _read(self, timeout, only_with_connection) -> bytes:
        """
        Reads one message. Awaits until timeout.
        If only_with_connection is True, will return messages if buffer is not empty, otherwise raise Exception
        :param timeout: float (None will be math.inf)
        :param only_with_connection: bool
        :return: bytes
        """
        if timeout is None:
            timeout = math.inf
        if only_with_connection and self.connected.is_set() is False and len(self.lines_received) == 0:
            raise IndexError("No messages available")
        st = time.time()
        while time.time() - st < timeout:
            if self._removed:
                raise ClientRemovedException
            if len(self.lines_received) == 0:
                try:
                    await asyncio.wait_for(self.new_message_rx.wait(), 1)
                except asyncio.TimeoutError:
                    continue
                else:
                    self.new_message_rx.clear()
            else:
                self.log.debug("lines_received: {!s}".format(self.lines_received))
                return self.lines_received.pop(0)
        raise asyncio.TimeoutError("Timeout waiting for a new message")

    async def _keepalive(self):
        self.log.debug("Keepalive started")
        to = self.timeout_connection / 1000 * 2 / 3
        try:
            while self.transport is not None and not self.transport.transport.is_closing():
                try:
                    self.transport.transport.write(b"\n")
                except Exception as e:
                    self.log.debug("Got exception sending keepalive: {!s}".format(e))
                    return
                if (time.time() - self.last_rx_time) > (self.timeout_connection / 1000):
                    self.log.warn("RX timeout")
                    asyncio.ensure_future(self.stop())  # separate task as stop() cancels _keepalive
                await asyncio.sleep(to)
        except asyncio.CancelledError:
            self.log.debug("keepalive canceled")

    @_checkRemovedAsync
    async def write(self, message, timeout=math.inf, only_with_connection=False):
        """
        If no timeout is specified, will wait forever until device is connected.
        If only_with_connection is False, it will wait for the connection until timeout.
        :param message: str/bytes
        :param timeout: float
        :param only_with_connection: bool
        :return: True on success, False on error, Exception if only_with_connection==False and timeout
        """
        if timeout is None:
            timeout = math.inf
        if not message.endswith("\n" if type(message) == str else b"\n"):
            message += "\n" if type(message) == str else b"\n"
        st = time.time()
        while time.time() - st < timeout:
            if self._removed:
                raise ClientRemovedException
            if only_with_connection is True:
                try:
                    await asyncio.wait_for(self.connected.wait(), 1)
                except asyncio.TimeoutError:
                    continue
                else:
                    self.output_buffer.append(message)
                    self.new_message_tx.set()
                    while len(self.output_buffer) > self.len_tx_buffer:
                        self.output_buffer.pop(0)
                    return True
            else:
                self.output_buffer.append(message)
                self.new_message_tx.set()
                while len(self.output_buffer) > self.len_tx_buffer:
                    self.output_buffer.pop(0)
                return True
        return False

    def __del__(self):
        try:
            self.log.debug("Removing client object")
        except Exception:
            pass

    async def _write(self):
        self.log.debug("writer started")
        try:
            while self.connected.is_set():
                try:
                    await asyncio.wait_for(self.new_message_tx.wait(), 1)
                except asyncio.TimeoutError:
                    pass
                else:
                    if self.transport is not None and not self.transport.transport.is_closing():
                        while len(self.output_buffer):
                            self.log.debug("Writing message {!s}".format(self.output_buffer[0]))
                            message = self.output_buffer[0]
                            if type(message) == str:
                                message = message.encode()
                            try:
                                self.transport.transport.write(message)
                            except Exception as e:
                                self.log.debug(
                                    "Got exception sending message {!s}: {!s}".format(self.output_buffer[0], e))
                                return
                            self.output_buffer.pop(0)
                            # place throttle event/release event here
                        self.new_message_tx.clear()
                    else:
                        break
        except asyncio.CancelledError:
            self.log.debug("_write coro canceled")
