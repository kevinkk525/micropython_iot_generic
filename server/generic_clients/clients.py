# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-19 

__updated__ = "2018-12-19"
__version__ = "0.0"

import asyncio
import logging
import time
import math

from server.server_generic import getNetwork as _getNetwork
from server.generic_clients.client import Client, ClientRemovedException

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


class MultipleClientHelper:
    def __init__(self, client_ids: list):
        self.client_ids = client_ids if type(client_ids) == list else [client_ids]

    @staticmethod
    def _clientsInList(client_ids):
        for client in client_ids:
            if client not in _getNetwork().clients:
                return False
        return True

    @staticmethod
    def _getClient(client_id) -> Client:
        if client_id in _getNetwork().clients:
            return _getNetwork().clients[client_id]
        else:
            raise IndexError("Client does not exist")

    async def awaitConnection(self, timeout=math.inf):
        if timeout is None:
            timeout = math.inf
        st = time.time()
        while time.time() - st < timeout:
            if self._clientsInList(self.client_ids):
                tasks = []
                for client_id in self.client_ids:
                    tasks.append(_getNetwork().clients[client_id].connected.wait())
                try:
                    await asyncio.wait_for(asyncio.gather(*tasks), 1)
                except asyncio.TimeoutError:
                    continue
                return True
            else:
                try:
                    await asyncio.wait_for(_getNetwork().new_client.wait(), 1)
                except asyncio.TimeoutError:
                    continue
        raise asyncio.TimeoutError("Timeout waiting for client connections")

    async def _awaitConnection(self, client_id, timeout=math.inf):
        if timeout is None:
            timeout = math.inf
        st = time.time()
        while time.time() - st < timeout:
            if self._clientsInList(client_id):
                try:
                    await asyncio.wait_for(_getNetwork().clients[client_id].connected.wait(), 1)
                except asyncio.TimeoutError:
                    continue
                return True
            else:
                try:
                    await asyncio.wait_for(_getNetwork().new_client.wait(), 1)
                except asyncio.TimeoutError:
                    continue
        raise asyncio.TimeoutError("Timeout waiting for client connection")

    async def readClient(self, client_id, timeout=math.inf, only_with_connection=False):
        if timeout is None:
            timeout = math.inf
        try:
            client = self._getClient(client_id)
        except IndexError as e:
            raise e
        else:
            return await client.read(timeout, only_with_connection)

    async def readAll(self, timeout=math.inf, only_with_connection=False) -> list:
        """
        reads all clients. Timeout should be properly set otherwise it will wait until it got a
        message from every single client that is connected.
        Not connected clients will be ignored if only_with_connection=True, else this will also
        wait for a message of not yet connected clients.
        Clients that don't exist yet (e.g. when using dynamic client creation) will be ignored.
        :param timeout: float
        :param only_with_connection: bool
        :return: list, [ [<client_id>,message], ...], message=None if TimeoutError occurred or Client does not exist
        """
        if timeout is None:
            timeout = math.inf
        tasks = []
        for client_id in self.client_ids:
            try:
                client = self._getClient(client_id)
            except IndexError:
                continue  # client does not exist yet
            else:
                async def wrapper(cl):
                    try:
                        return [cl.client_id, await cl.read(timeout, only_with_connection)]
                    except IndexError:
                        return [cl.client_id, None]
                    except asyncio.TimeoutError:
                        return [cl.client_id, None]

                tasks.append(wrapper(client))
        res = await asyncio.gather(*tasks)
        return res

    async def writeAll(self, message, timeout=math.inf, only_with_connection=False, qos=True):
        """
        Write to all clients of this object the same message.
        If no timeout is specified, will wait forever until all devices are connected and message can be put into buffer.
        This is not recommended with multiple devices.
        If only_with_connection is False, it will return False if Client does not exist yet
        otherwise it will wait for the client until timeout.
        :param message: str
        :param timeout: float
        :param only_with_connection: bool
        :param qos: bool
        :return: list, [ [<client_id>, bool], ...], True/False: message success
        """

        async def wrapper(cl):
            try:
                r = await self.writeClient(cl, message, timeout, only_with_connection, qos)
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

    async def writeClient(self, client_id, message, timeout=math.inf, only_with_connection=False, qos=True):
        """
        Write to the client at client_id.
        If no timeout is specified, will wait forever until device is connected.
        If only_with_connection is False, it will fail if Client does not exist yet as there is no buffer.
        A Client object can be created that will act as a buffer but if the device won't connect, messages will get lost
        as Client has a message limit.
        :param client_id: str
        :param message: str
        :param timeout: float
        :param only_with_connection: bool
        :param qos: bool
        :return: True on success, False on error, Exception if only_with_connection==False and client does not exist
        """
        if timeout is None:
            timeout = math.inf
        if not message.endswith("\n"):
            message += "\n"
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
                    await client.write(message, timeout=timeout, qos=qos)
                    return True
            else:
                try:
                    client = self._getClient(client_id)
                except IndexError as e:
                    raise e
                else:
                    await client.write(message, timeout=timeout, qos=qos)
                    return True
        return False


class ClientHelper:
    """
    This is a generic and general class that does not create any client object or holds any information.
    It just provides an interface for client function for clients that may not exist yet.
    """

    @staticmethod
    def _clientsInList(client_ids):
        for client in client_ids:
            if client not in _getNetwork().clients:
                return False
        return True

    @staticmethod
    def _getClient(client_id) -> Client:
        if client_id in _getNetwork().clients:
            return _getNetwork().clients[client_id]
        else:
            raise IndexError("Client does not exist")

    @staticmethod
    async def awaitConnection(client_ids: list, timeout=math.inf):
        if timeout is None:
            timeout = math.inf
        if type(client_ids) != list:
            client_ids = [client_ids]
        st = time.time()
        while time.time() - st < timeout:
            if ClientHelper._clientsInList(client_ids):
                tasks = []
                for client_id in client_ids:
                    tasks.append(_getNetwork().clients[client_id].connected.wait())
                try:
                    await asyncio.wait_for(asyncio.gather(*tasks), 1)
                except asyncio.TimeoutError:
                    continue
                return True
            else:
                try:
                    await asyncio.wait_for(_getNetwork().new_client.wait(), 1)
                except asyncio.TimeoutError:
                    continue
        raise asyncio.TimeoutError("Timeout waiting for client connection")

    async def read(self, client_id, timeout=math.inf, only_with_connection=False):
        if timeout is None:
            timeout = math.inf
        try:
            client = self._getClient(client_id)
        except IndexError as e:
            raise e
        else:
            return await client.read(timeout, only_with_connection)

    async def write(self, client_id, message, timeout=math.inf, only_with_connection=False, qos=True):
        """
        Write to the client at client_id.
        If no timeout is specified, will wait forever until device is connected.
        If only_with_connection is False, it will fail if Client does not exist yet as there is no buffer.
        A Client object can be created that will act as a buffer but if the device won't connect, messages will get lost
        as Client has a message limit.
        :param client_id: str
        :param message: str
        :param timeout: float
        :param only_with_connection: bool
        :param qos: bool
        :return: True on success, False on error, Exception if only_with_connection==False and client does not exist
        """
        if timeout is None:
            timeout = math.inf
        if not message.endswith("\n"):
            message += "\n"
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
                    await client.write(message, qos=qos)
                    return True
            else:
                try:
                    client = self._getClient(client_id)
                except IndexError as e:
                    raise e
                else:
                    await client.write(message, qos=qos)
                    return True
        return False


def getClientHelper():
    return ClientHelper()
