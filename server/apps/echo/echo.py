# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-30

__updated__ = "2018-12-30"
__version__ = "0.0"

from server.apphandler.apphandler import App, AppInstance


class EchoInstance(AppInstance):
    def __init__(self, app, id, client):
        super().__init__(app, id, client)

    async def stop(self):
        """
        Stop the Instance.
        Call stop coroutine of base class to ensure that the instance gets removed.
        :return:
        """
        await super().stop()

    def start(self):
        """
        Connection to client reestablished. Continue sending messages.
        :return:
        """
        self.log.debug("(Re)starting")

    async def pause(self):
        """
        Connection to client broken, maybe discard all new messages and duplicates.
        Stop sending new messages.
        :return:
        """
        self.log.debug("Pausing")

    async def handle(self, header_byte, data):
        """
        Handle new messages from client but do it quickly
        :param header_byte:
        :param data:
        :return:
        """
        self.log.debug("Got header {!s}, data {!s}".format(header_byte, data))
        await self.write(header_byte, data)


class Echo(App):
    def __init__(self, config):
        super().__init__(config)
        self.AppInstance = EchoInstance

    async def stop(self):
        """Extend with your own code but call stop method of base class to prevent RAM leak and to stop instances"""
        await super().stop()
