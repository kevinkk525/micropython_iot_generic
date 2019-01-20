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

n = Network(timeout_client_object=None, cb_new_client=None)


# for debug purposes only hold client object for 30s
# Note that cb_new_client would not have any effect on the pre-created client object


# These 2 coroutines request a client object before any client has connected.
# They then wait until the client has actually connected and start reading/sending messages.
# The client is a persistent object, that will never get removed after the client disconnects, therfore
# eternally waiting for the client to reconnect.
# Note: Each client object has a buffer size limit and won't grow unchecked if the client stays offline for a long time.
# Note: Every client connecting to the server will be created if
# the Network() is created with timeout_client_object=None.
# Otherwise the clients that connect to the server with having a pre-created Client object like Client "1" will
# only live for that amount of seconds after their disconnect,
# just like a temporary client shown in the file s_app_temporary_clients.py
async def sendMessages():
    while True:
        client1 = clients.getClient("1", timeout_client_object=None)
        await client1.awaitConnection()
        counter = 0
        while not client1.removed:
            await client1.write(json.dumps([counter, time.time()]))
            counter += 1
            await asyncio.sleep(2)
            if n.shutdown_requested.is_set():
                return


async def readClientPersistent():
    client1 = clients.getClient("1", timeout_client_object=None)
    while n.shutdown_requested.is_set() is False and client1.removed is False:
        try:
            message = await client1.read(timeout=1)
        except asyncio.TimeoutError:
            continue
        try:
            message = json.loads(message)
        finally:
            log.debug("Got new message from client {!r}: {!s}".format(client1.client_id, message))
    if client1.removed:
        log.critical("Client 1 has been removed, should not happen as it is persistent")
    elif n.shutdown_requested.is_set():
        return


def main():
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(n.init(loop))
    asyncio.ensure_future(readClientPersistent())
    asyncio.ensure_future(sendMessages())
    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(n.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
