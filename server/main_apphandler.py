# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-27 

__updated__ = "2018-12-27"
__version__ = "0.0"

import logging

fh = logging.FileHandler("server.log", mode="w")
fh.setLevel(logging.INFO)
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
from server.apphandler import clients
from server.server_generic import Network

n = Network(timeout_client_object=30,
            client_class=clients.Client)  # for debug purposes only hold client object for 30s


# TODO: add example for temporary app that deletes itself after answering the request
# TODO: find out why sometimes there are client instances left over (on shutdown multiple stop logs)
#  this seems to be not related to sending message as it just adds to the buffer

def main():
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(n.init(loop))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error("Exception in asyncio loop.run_forever(): {!s}".format(e))
    finally:
        loop.run_until_complete(n.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
