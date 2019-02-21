# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-10

__updated__ = "2018-12-10"
__version__ = "0.0"

import logging

# logging.basicConfig(level=logging.DEBUG, format="[%(asctime)-15s][%(levelname)-8s][%(name)s] %(message)s")
# log = logging.getLogger()
fh = logging.FileHandler("server.log", mode="w")
fh.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("[%(asctime)-15s][%(levelname)-8s][%(name)s] %(message)s")
ch.setFormatter(formatter)
fh.setFormatter(formatter)
log = logging.getLogger("")
log.setLevel(logging.DEBUG)
log.addHandler(ch)
log.addHandler(fh)
import asyncio
import time

from server.acks_header_clients import clients
from server.server_generic import Network


def callbackNewClient(client: clients.Client):
    async def dynamicReader(client: clients.Client):
        count = -1  # first message count is 0
        while n.shutdown_requested.is_set() is False:
            try:
                header, message = await client.read(timeout=2)
            except asyncio.TimeoutError:
                continue
            except clients.ClientRemovedException:
                return  # Reconnect will start this reader
            if message[1] != count + 1:
                client.log.critical("Lost message count {!s}, new message: {!s}".format(count + 1, message))
            count = message[1]
            client.log.info("Got new message from client: {!s}, {!s}".format(header, message))

    asyncio.ensure_future(dynamicReader(client))

    async def dynamicWriter(client: clients.Client):
        count_failed = 0
        latency_added = 0
        count = 0
        while n.shutdown_requested.is_set() is False:
            mess = [count_failed, count, time.time()]
            client.log.info("Sent message to client: {!s}".format(mess))
            st = time.time()
            try:
                # await client.write(None, mess, timeout=2)
                await client.write(None, mess)  # No timeout to check retransmission resilience of the whole system
            except asyncio.TimeoutError:
                count_failed += 1
            except clients.ClientRemovedException:
                return  # Reconnect will start this writer
            else:
                latency = time.time() - st
                latency_added += latency
                count += 1
                client.log.debug(
                    "Latency: {!s}ms, Avg Latency: {!s}ms".format(latency * 1000, latency_added / count * 1000))
            # await asyncio.sleep(2.5)

    asyncio.ensure_future(dynamicWriter(client))


n = Network(timeout_client_object=120,
            timeout_connection=4000,
            port=9999,
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
