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


def callbackNewClient(client: clients.Client):
    async def dynamicReader(client: clients.Client):
        while not client.removed and not n.shutdown_requested.is_set():
            try:
                message = await client.read(timeout=1)
            except asyncio.TimeoutError:
                continue
            try:
                message = json.loads(message)
            except:
                pass
            finally:
                log.debug("Got new message from client {!r}: {!s}".format(client.client_id, message))

    asyncio.ensure_future(dynamicReader(client))

    async def dynamicWriter(client: clients.Client):
        count = 0
        while not client.removed and not n.shutdown_requested.is_set():
            await client.write(json.dumps([count, time.time()]))  # puts message into output_buffer
            count += 1
            await asyncio.sleep(5)

    asyncio.ensure_future(dynamicWriter(client))


n = Network(timeout_client_object=30,
            cb_new_client=callbackNewClient)  # for debug purposes only hold client object for 30s


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
