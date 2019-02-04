# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-10

__updated__ = "2018-12-10"
__version__ = "0.0"

import logging

logging.basicConfig(level=logging.DEBUG, format="[%(asctime)-15s][%(levelname)-8s][%(name)s] %(message)s")
log = logging.getLogger()
import asyncio
import time

from server.acks_header_clients import clients
from server.server_generic import Network


def callbackNewClient(client: clients.Client):
    async def dynamicReader(client: clients.Client):
        while n.shutdown_requested.is_set() is False:
            try:
                header, message = await client.read(timeout=1)
            except asyncio.TimeoutError:
                continue
            except clients.ClientRemovedException:
                await client.awaitConnection()
                continue
            log.debug("Got new message from client {!r}: {!s}, {!s}".format(client.client_id, header, message))

    asyncio.ensure_future(dynamicReader(client))

    async def dynamicWriter(client: clients.Client):
        count = 0
        while n.shutdown_requested.is_set() is False:
            await client.awaitConnection()
            log.debug("count {!s}".format(count))
            try:
                await client.write(None, [count, time.time()])
            except asyncio.TimeoutError:
                log.debug("Got timeout sending answer")
            count += 1
            await asyncio.sleep(5)

    asyncio.ensure_future(dynamicWriter(client))


n = Network(timeout_client_object=30,
            cb_new_client=callbackNewClient,
            client_class=clients.Client)  # for debug purposes only hold client object for 30s


# Every new client that connects to the server will get a dynamicReader that prints every message
# and a dynamicWriter that periodically sends a list [counter, current time] to the client.
# If the client disconnects, these will be stopped. On reconnection they will be started again.
# This also means that the dynamicWriter counter will be reset to 0 on every client disconnect.

def main():
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(n.init(loop))
    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(n.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
