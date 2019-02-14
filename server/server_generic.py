# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-15 

__updated__ = "2018-12-15"
__version__ = "0.0"

import asyncio
import logging
import math
import time
from server.apphandler.apphandler import AppHandler

# server tested with 800 concurrent (dis)connects at a time, sending one message,
# causing ~70% cpu usage on one 2GHz arm core with ~40MB RAM usage.
# Running this for several hours did not show any RAM leak.

# TODO: initiated connections to the server without sending a message stay open
# TODO: keepalive should only send if no new message within timeframe

log = logging.getLogger("")
_network = None


def getNetwork():
    if _network is not None:
        return _network
    raise TypeError("Network not initialized")


class Network:
    def __init__(self, hostname=None, port=None, timeout_connection=1500, timeout_client_object=3600,
                 cb_new_client=None, client_class=None):
        """
        :param hostname: hostname to listen to, defaults to 0.0.0.0
        :param port: port is actually needed, but defaults to 8888
        :param timeout_connection: timeout in ms of the connection object.
        If no keepalive was possible during that time, connection will be closed
        :param timeout_client_object: timeout in s of the client object that survives a connection loss.
        The client object containing any apps and not yet sent messages will be deleted
        """
        if timeout_client_object is None:
            timeout_client_object = math.inf
        if hostname is not None:
            self.hostname = hostname
        else:
            self.hostname = "0.0.0.0"
        if port is not None:
            self.port = port
        else:
            self.port = 8888
        self.timeout_connection = timeout_connection
        self.timeout_client = timeout_client_object
        self.loop = None
        self.server = None
        self.server_task = None
        self.clients = {}
        self.shutdown_requested = asyncio.Event()
        self.new_client = asyncio.Event()
        self.cb_new_client = cb_new_client
        global _network
        _network = self
        if client_class is None:
            from server.generic_clients.client import Client
            self.Client = Client
        else:
            self.Client = client_class

    async def shutdown(self):
        log.info("Shutting down network")
        self.shutdown_requested.set()
        AppHandler.stop_event.set()
        await asyncio.sleep(5)  # time for clients to shut down
        self.server.close()

    async def init(self, loop):
        self.server = await loop.create_server(lambda: ClientConnection(self), self.hostname, self.port)
        log.info("Server created")
        self.loop = loop
        asyncio.ensure_future(self._resetNewClientEvent())

    async def _resetNewClientEvent(self):
        while not self.shutdown_requested.is_set():
            try:
                await asyncio.wait_for(self.new_client.wait(), 1)
                self.new_client.clear()
            except asyncio.TimeoutError:  # makes it react to shutdown_requested in time without canceling externally
                pass


class ClientConnection(asyncio.Protocol):
    def __init__(self, network: Network):
        self.input_buffer = b""
        self.network = network
        self.transport = None
        self.loop = network.loop
        self.ip = None
        self.client_id = None
        self.client = None

    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        log.info('Connection from {}, {!s}'.format(peername, transport))
        self.ip = peername
        self.transport = transport
        sock = transport.get_extra_info("socket")
        import socket
        sock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
        # sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        # sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 5)
        # sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 1)
        # sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 1)

    def connection_lost(self, exc):
        log.info("Connection to client {!r}, {!s} lost, exception {!s}".format(self.client_id, self.ip, exc))
        if self.client is not None:
            asyncio.ensure_future(self.client.stop())

    def data_received(self, data):
        # log.debug("Got data: {!s}, len {!s}".format(data, len(data)))
        message = self.input_buffer + data
        self.input_buffer = b""
        if message.find(b"\n") == -1:
            self.input_buffer = message
            return
        tmp = message.split(b"\n")
        if message.endswith(b"\n") is False:
            self.input_buffer = tmp.pop(-1)
        for i in range(0, tmp.count(b"")):
            tmp.remove(b"")  # sometimes keepalives are read too but as nothing is done with these, just remove them
        message = tmp.pop(0) if len(tmp) > 0 else b""  # as keepalive has been removed
        if self.client_id is None:
            if message == b"":
                return  # new connection does not start with keepalive
            try:
                client_id = getNetwork().Client.readID(message)
            except TypeError as e:
                log.error(e)
                self.close()
                return
            log.debug("Logged in as {!s}".format(client_id))
            self.client_id = client_id
            if self.client_id in self.network.clients:
                cl = self.network.clients[self.client_id]
                if cl.transport is not None:
                    cl.transport.client = None  # otherwise transport will stop client on connection loss.
                    try:
                        cl.transport.close()
                    except:
                        pass
                    del cl.transport
                cl.transport = self
                cl.lines_received += tmp
                while len(cl.lines_received) > cl.len_rx_buffer:
                    cl.lines_received.pop(0)
                cl.start(message)
                self.client = cl
                return
            client = _network.Client(self.client_id, timeout_connection=self.network.timeout_connection,
                                     timeout_client_object=self.network.timeout_client)
            client.transport = self
            self.network.clients[self.client_id] = client
            self.client = client
            # log.debug("Client list on creation: {!s}".format(self.network.clients))
            if self.network.cb_new_client is not None:
                self.network.cb_new_client(client)
            client.start(message)
            if len(tmp) > 0:
                self.client.lines_received += tmp
                while len(self.client.lines_received) > self.client.len_rx_buffer:
                    self.client.lines_received.pop(0)
                self.client.new_message_rx.set()
            return
        if self.client is None:
            log.warn("Connection {!s} does not have client object {!r} anymore but received data".format(self.ip,
                                                                                                         self.client_id))
            self.close()
            return
        if self.client.closing.is_set():
            return  # Not accepting new messages if server is being shut down
        self.client.last_rx_time = time.time()
        self.client.log.debug("Got data: {!s}, len {!s}".format(data, len(data)))
        if message != b"":
            self.client.lines_received.append(message)
            if len(tmp) > 0:
                self.client.lines_received += tmp
                while len(self.client.lines_received) > self.client.len_rx_buffer:
                    self.client.lines_received.pop(0)
            self.client.new_message_rx.set()

    def __del__(self):
        log.debug("Removing transport object to client {!r}, ip {!s}".format(self.client_id, self.ip))

    def close(self):
        log.debug("Closing transport {!s} to client {!r}".format(self.ip, self.client_id))
        try:
            self.transport.close()
        except Exception as e:
            log.debug("Exception closing transport socket: {!s}".format(e))
