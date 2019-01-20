# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-10

__updated__ = "2018-12-10"
__version__ = "0.0"

import logging

logging.basicConfig(level=logging.DEBUG, format="[%(asctime)-15s][%(levelname)-8s][%(name)s] %(message)s")
log = logging.getLogger()

import asyncio
import json
import time

from server.generic_clients import clients
from server.server_generic import Network

n = Network(timeout_client_object=30)  # for debug purposes only hold client object for 30s


async def sendMessages():
    while True:
        cls = clients.MultipleClientHelper(["1", "2", "3"])
        await cls.awaitConnection()
        counter = 0
        while n.shutdown_requested.is_set() is False:
            await cls.writeAll(json.dumps([counter, time.time()]), timeout=1)
            # writes a message to the buffer of each client. If a short connection loss occurs, message
            # will be automatically (re)send to the client.
            counter += 1
            await asyncio.sleep(2)


async def readMultipleClients():
    cls = clients.MultipleClientHelper(["1", "2", "3"])
    await cls.awaitConnection(timeout=None)  # will wait forever until all clients are connected
    while n.shutdown_requested.is_set() is False:
        try:
            message = await cls.readAll(timeout=1)
            # will wait for 1 second to read all clients. If they are not connected, no message will be received
            # Note: If one client sends more often than once per second, buffer will get filled.
            # message = await cls.readAll(timeout=1, only_with_connection=True) will ignore not connected clients
            # and return the messages available from connected clients only
        except asyncio.TimeoutError:
            continue
        for mess in message:
            try:
                mess[1] = json.loads(mess[1])
            finally:
                log.debug("Got new message from client {!r}: {!s}".format(mess[0], mess[1]))


def main():
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(n.init(loop))
    asyncio.ensure_future(readMultipleClients())
    asyncio.ensure_future(sendMessages())
    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(n.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
