# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2019-01-11 

__updated__ = "2019-01-11"
__version__ = "0.0"

from .apphandler import AppHandler, TimeoutError, get_apphandler
import uasyncio as asyncio
import time
import gc


class App:
    def __init__(self):
        """
        Handles identification of app and provides an interface for sending and receiving messages.
        Only use callback or async reader. If callback is used, async reader won't receive any data.
        Don't use callback for temporary apps like a GET request.
        Use this class only for permanent apps like a mqtt client.
        Use coroutine "AppTemporary" for temporary apps like a GET request.
        Change the app ident to a unique int between 0-255
        """
        self.id = AppHandler.addInstance(self)  # get id for app
        self.ident = -1  # integer app identifier, has to be the same on the server so he knows where to route data to
        # id and ident needed as it is possible to have multiple GET requests that have the same ident
        # identifying the type of App but different id to distinguish the sources
        self.active = True

        ####
        # Optional, either use data for awaiting app or callback
        self.data = None
        ####

    def handle(self, header: int, data: any):
        """
        Gets called every time the AppHandler receives a message for this app.
        In this case, adds new data to self.data so that it can be awaited
        :param header: header int (one byte)
        :param data: str/json.loads
        :return:
        """
        self.data = (header, data)

    def concb(self, state):
        """
        Gets called every time the client connection changes.
        Does not need to exist
        :param state: bool
        :return:
        """
        pass

    async def write(self, header: int, data: any):
        """
        Implement in the same way
        :param header: int (0-255)
        :param data: any
        :return:
        """
        if header is None:
            header = 0
        if self.active:
            await AppHandler.connected  # wait until AppHandler is connected, waits forever
            await get_apphandler().write(self.ident, self.id, header, data)
            return True
        return False

    async def stop(self):
        """
        Implement in the same way
        :return:
        """
        self.active = False
        await asyncio.sleep_ms(500)  # wait for all readings to time out
        AppHandler.deleteInstance(self)
        #####
        # Optional if not used anywhere. just reduced possible leftovers in RAM
        self.data = None
        gc.collect()
        #####


async def AppTemporary(AppClass, header, message, timeout=120):
    """
    Use this for an App like a GET request that just sends a message and waits for one answer.
    Either use this function and provide an AppClass or copy it and adapt to your needs
    if you need an adaption.
    :param AppClass: Class of an App. Just used as generic wrapper.
    :param header: header of message if used by app. This function is very generic as an example.
    :param message: what you want to send to the server
    :param timeout: seconds, timeout waiting for an answer
    :return: server response
    """
    app = AppClass()
    await app.write(header, message)
    try:
        """
        used for waiting for an answer to a sent request or just generally waiting for a new message
        but with a timeout to make it easier to stop listening.
        """
        s = time.ticks_ms()
        while True:
            if time.ticks_ms() - s < timeout * 1000 and app.active:
                await asyncio.sleep_ms(50)
                if app.data is not None:
                    data = app.data
                    break
            else:
                raise TimeoutError("Timeout waiting for a message")  # or app has been deleted
    except TimeoutError as e:
        raise e
    finally:
        await app.stop()
        del app
        gc.collect()
    return data
