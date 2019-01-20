# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-19 

__updated__ = "2018-12-19"
__version__ = "0.0"

import logging
import math
import time
import asyncio

from server.server_generic import getNetwork as _getNetwork
from server.apphandler.client import Client
from server.acks_header_clients import clients as header_clients

log = logging.getLogger("ClientHelpers")


def getClient(client_id, *args, **kwargs) -> Client:
    if _getNetwork() is None:
        raise TypeError("No network initialized")
    if client_id in _getNetwork().clients:
        return _getNetwork().clients[client_id]
    client = Client(client_id, *args, **kwargs)
    # basically a future client object without a transport/socket
    _getNetwork().clients[client_id] = client
    return client


class MultipleClientHelper(header_clients.MultipleClientHelper):
    def __init__(self, client_ids: list):
        super().__init__(client_ids)

    async def readClient(self, client_id, timeout=math.inf, only_with_connection=False):
        raise NotImplementedError("This method can't be used with apphandler")  # as apphandler gets all messages

    async def readAll(self, timeout=math.inf, only_with_connection=False):
        raise NotImplementedError("This method can't be used with apphandler")  # as apphandler gets all messages

    async def writeAll(self, app_ident, app_id, header, message, timeout=math.inf, only_with_connection=False,
                       qos=True):
        """
        Write to all clients of this object the same message.
        If no timeout is specified, will wait forever until all devices are connected and message can be put into buffer.
        This is not recommended with multiple devices.
        If only_with_connection is False, it will return False if Client does not exist yet
        otherwise it will wait for the client until timeout.
        :param app_ident: app identification number
        :param app_id: unique app instance id
        :param header: int (one byte) or bytearray, app specific header, if used
        :param message: str
        :param timeout: float
        :param only_with_connection: bool
        :param qos: bool
        :return: list, [ [<client_id>, bool], ...], True/False: message success
        """

        async def wrapper(cl):
            try:
                r = await self.writeClient(cl, app_ident, app_id, header, message, timeout, only_with_connection, qos)
                return [cl, r]
            except asyncio.TimeoutError:
                return [cl, False]
            except IndexError:
                return [cl, False]

        tasks = []
        for client_id in self.client_ids:
            tasks.append(wrapper(client_id))
        res = await asyncio.gather(*tasks)
        return res

    async def writeClient(self, client_id, app_ident, app_id, header, message, timeout=math.inf,
                          only_with_connection=False, qos=True):
        """
        Write to the client at client_id.
        If no timeout is specified, will wait forever until device is connected.
        If only_with_connection is False, it will fail if Client does not exist yet as there is no buffer.
        A Client object can be created that will act as a buffer but if the device won't connect, messages will get lost
        as Client has a message limit.
        :param client_id: str
        :param app_ident: app identification number
        :param app_id: unique app instance id
        :param header: int (one byte) or bytearray, app specific header, if used
        :param message: str
        :param timeout: float
        :param only_with_connection: bool
        :param qos: bool
        :return: True on success, False on error, Exception if only_with_connection==False and client does not exist
        """
        if timeout is None:
            timeout = math.inf
        st = time.time()
        while time.time() - st < timeout:
            if only_with_connection is True:
                try:
                    await self._awaitConnection([client_id], timeout)
                except asyncio.TimeoutError:
                    return False
                else:
                    try:
                        client = self._getClient(client_id)
                    except IndexError:
                        log.critical(
                            "Client {!s} not found although connection awaited, should not happen".format(client_id))
                        return False
                    await client.write(app_ident, app_id, header, message, timeout, qos=qos)
                    return True
            else:
                try:
                    client = self._getClient(client_id)
                except IndexError as e:
                    raise e
                else:
                    await client.write(app_ident, app_id, header, message, timeout, qos=qos)
                    return True
        return False


class ClientHelper(header_clients.ClientHelper):
    """
    This is a generic and general class that does not create any client object or holds any information.
    It just provides an interface for client function for clients that may not exist yet.
    """

    async def read(self, client_id, timeout=math.inf, only_with_connection=False):
        raise NotImplementedError("This method can't be used with apphandler")  # as apphandler gets all messages

    async def writeClient(self, client_id, app_ident, app_id, message, header=0, timeout=math.inf,
                          only_with_connection=False, qos=True):
        """
        Write to the client at client_id.
        If no timeout is specified, will wait forever until device is connected.
        If only_with_connection is False, it will fail if Client does not exist yet as there is no buffer.
        A Client object can be created that will act as a buffer but if the device won't connect, messages will get lost
        as Client has a message limit.
        :param client_id: str
        :param app_ident: app identification number
        :param app_id: unique app instance id
        :param message: str
        :param header: int (one byte), app specific header, if used
        :param timeout: float
        :param only_with_connection: bool
        :param qos: qos
        :return: True on success, False on error, Exception if only_with_connection==False and client does not exist
        """
        if timeout is None:
            timeout = math.inf
        st = time.time()
        while time.time() - st < timeout:
            if only_with_connection is True:
                try:
                    await self.awaitConnection([client_id], timeout)
                except asyncio.TimeoutError:
                    return False
                else:
                    try:
                        client = self._getClient(client_id)
                    except IndexError:
                        log.critical(
                            "Client {!s} not found although connection awaited, should not happen".format(client_id))
                        return False
                    await client.write(app_ident, app_id, header, message, timeout, qos=qos)
                    return True
            else:
                try:
                    client = self._getClient(client_id)
                except IndexError as e:
                    raise e
                else:
                    await client.write(app_ident, app_id, header, message, timeout, qos=qos)
                    return True
        return False


def getClientHelper():
    return ClientHelper()
