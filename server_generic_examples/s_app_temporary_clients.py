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

n = Network(timeout_client_object=30, cb_new_client=None)


# for debug purposes only hold client object for 30s
# Note that cb_new_client would not have any effect on the pre-created client object


# These 2 coroutines request a client object before any client has connected.
# They then wait until the client has actually connected and start reading/sending messages.
# The client is a temporary object, that only lives timeout_client_object seconds after the client disconnects
# but won't get removed before it even connected. Therefore these coros can wait forever until the
# client connects but will exit the while loop "while not client1.removed" after 10s after the client
# disconnects as the client object will be removed then along with all its buffers.
# This is to keep the server clean if clients disconnect for longer periods.
# 10 seconds is just for demonstration, a more meaningful timeout would be 1h, depending on the use-case.
# Note: Each client object has a buffer size limit and won't grow unchecked.
# If the client gets removed after the disconnect and the while loop exits, the coros create a new
# client object and wait for the connection again.
async def sendMessages():
    while True:
        client1 = clients.getClient("1", timeout_client_object=10)
        await client1.awaitConnection()
        counter = 0
        while not client1.removed:
            await client1.write(json.dumps([counter, time.time()]))
            counter += 1
            await asyncio.sleep(2)
            if n.shutdown_requested.is_set():
                return


async def readClientTemporary():
    while True:
        client1 = clients.getClient("1", timeout_client_object=10)
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
            log.debug("Client 1 has been removed, creating it again")
        elif n.shutdown_requested.is_set():
            return


def main():
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(n.init(loop))
    asyncio.ensure_future(readClientTemporary())
    asyncio.ensure_future(sendMessages())
    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(n.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
