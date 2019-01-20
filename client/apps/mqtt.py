# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-10

__updated__ = "2019-01-02"
__version__ = "1.1"

from ..apphandler import get_apphandler
from .. import subs_handler
import uasyncio as asyncio
from micropython import const

type_gen = type((lambda: (yield))())  # Generator type

# IDENT to identify app on server
IDENT = const(1)

# COMMANDS
CMD_PUB = const(1)
CMD_SUBS = const(2)
CMD_UNSUBS = const(3)
CMD_WILL = const(4)
CMD_WELC = const(5)


class Mqtt:
    def __init__(self, will=None, welc=None):
        ####
        # Proxy has credentials to mqtt broker and will connect automatically
        ####
        self.id = get_apphandler().addInstance(self)  # get id for app
        self.ident = IDENT  # identification number for type of app
        # id and ident needed as it is possible to have multiple GET requests that have the same ident
        # identifying the type of App but different id to distinguish the sources
        self.active = True
        self._subs = subs_handler.SubscriptionHandler()
        self._cbs = 0  # currently active callbacks, could be used for flow control between host, not implemented yet
        self._will = will  # topic,payload,qos,retain
        self._welc = welc
        if will is not None:
            asyncio.get_event_loop().create_task(self._write(CMD_WILL, [will[0], will[1], will[2], will[3]]))
        if welc is not None:
            asyncio.get_event_loop().create_task(self._write(CMD_WELC, [welc[0], welc[1], welc[2], welc[3]]))
        self._old_state = True
        self.print_error = print  # change this function if you use a different way of logging

    async def _wrapper(self, cb, data):
        self._cbs += 1
        res = cb(data[0], data[2], data[3])
        if type(res) == type_gen:
            await res
        self._cbs -= 1

    def handle(self, header: int, data: any):
        """
        quick callback adding new data to uasyncio loop.
        If wildcard subscriptions are active, it's possible to receive multiple subscription topics at once
        :param header: currently unused
        :param data: list, 0:topic, 1:subscription_topic(s), 2:message, 3:retain
        :return:
        """
        # header not used as only receiving published messages. no other use-case
        topics = data[1]
        if type(topics) != list:
            topics = [topics]
        for topic in topics:
            try:
                cbs, qos = self._subs.get(topic)
            except IndexError:
                if topic.endswith("/set") is False:
                    try:
                        cbs, qos = self._subs.get(topic + "/set")
                        # Assume that retained state topic is not subscribed on client as it only receives one message
                    except IndexError:
                        self.print_error("Topic {!s} not subscribed".format(topic))
                        return
                else:
                    self.print_error("Topic {!s} not subscribed".format(topic))
                    return
            cbs = cbs if type(cbs) == tuple else [cbs]
            loop = asyncio.get_event_loop()
            for cb in cbs:
                loop.create_task(self._wrapper(cb, data))

    def concb(self, state):
        if state is True and self._old_state is False:
            # assume new connection needs subscribing to all topics again
            asyncio.get_event_loop().create_task(self._resubscribe())
        self._old_state = state

    async def _resubscribe(self):
        will = self._will
        if will is not None:
            await self._write(CMD_WILL, [will[0], will[1], will[2], will[3]])
        welc = self._welc
        if welc is not None:
            await self._write(CMD_WELC, [welc[0], welc[1], welc[2], welc[3]])
        for subs, qos in self._subs:
            await self._write(CMD_SUBS, [subs, qos, False])

    async def subscribe(self, topic, callback_coro, qos=0, check_retained_state_topic=True):
        """
        :param topic: topic to subscribe to
        :param callback_coro: coroutine to run on message to this topic
        :param qos: qos the server will subscribe to.
        :param check_retained_state_topic: when subscribing to button/set as a command topic,
        check topic button first to be able to restore the current state
        :return:
        """
        self._subs.add(topic, callback_coro, qos)
        await self._write(CMD_SUBS, [topic, qos, check_retained_state_topic])

    async def publish(self, topic, msg, qos=0, retain=False):
        """
        :param topic: where to publish to
        :param msg: message to be published
        :param retain: if published as retained
        :param qos: qos the server will publish with
        :return:
        """
        await self._write(CMD_PUB, [topic, msg, qos, retain])

    def schedulePublish(self, topic, msg, qos=0, retain=False):
        asyncio.get_event_loop().create_task(self.publish(topic, msg, qos, retain))

    async def unsubscribe(self, topic, cb=None):
        if cb is None:
            self._subs.delete(topic)
            await self._write(CMD_UNSUBS, [topic])
        else:
            cbs, qos = self._subs.get(topic)
            if type(cbs) == tuple:
                cbs = list(cbs)
                cbs.remove(cb)  # can throw an error if cb is not in list
                self._subs.set(topic, cbs)
            elif cbs == cb or cbs == [cb]:  # TODO: check format a single cb is saved as
                await self._write(CMD_UNSUBS, [topic])
                self._subs.delete(topic)
            else:
                raise AttributeError("callback not subscribed")

    async def _write(self, header, data):
        """
        Implement in the same way
        :param header: int
        :param data: any (json.dumps)
        :return:
        """
        if header is None:
            header = 0
        if self.active:
            await get_apphandler().connected  # wait until AppHandler is connected, waits forever
            await get_apphandler().write(self.ident, self.id, header, data)
            return True
        return False

    async def stop(self):
        """makes actually not much sense when using an mqtt client. Theoretically remove subscriptions"""
        self.print_error("Stop not implemented")
        self.active = False
        await asyncio.sleep_ms(500)  # wait for all readings to time out
        get_apphandler().deleteInstance(self)