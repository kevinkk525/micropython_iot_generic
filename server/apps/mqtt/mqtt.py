# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-28

__updated__ = "2018-12-28"
__version__ = "0.0"

from server.apphandler.apphandler import App, AppInstance

from paho.mqtt.client import Client as _MqttClient
from paho.mqtt.client import connack_string
from .subscriptions import SubscriptionHandler
from server.apphandler.client import Client as _Client
import asyncio
import copy

# COMMANDS
CMD_PUB = 1
CMD_SUBS = 2
CMD_UNSUBS = 3
CMD_WILL = 4
CMD_WELC = 5


# TODO: something keeps multiple mqtt instances after connection loss
# TODO: add support for device topic, eg .led/set
# TODO: build qos or retain values into header? only one bit left in 1 byte app_header

class MqttInstance(AppInstance):
    def __init__(self, app, id, client: _Client):
        super().__init__(app, id, client)
        self._subscriptions = SubscriptionHandler("Qos", "OnlyRetained")
        self.mqtt_home = self.app.config["mqtt_home"]  # not yet used
        self.id = client.client_id
        self.will = None
        self.welc = None
        self.mqtt = _MqttClient(client_id=self.id)
        self.mqtt.enable_logger(self.log)
        self.mqtt.username_pw_set(self.app.config["user"], self.app.config["password"])
        self.mqtt.on_connect = self._connected
        self.mqtt.on_message = self._execute_sync
        self.mqtt.on_disconnect = self._on_disconnect
        self._client_connected = True
        self._isconnected = False
        self.loop = asyncio.get_event_loop()
        self._first_connect = True

    def _connected(self, client, userdata, flags, rc):
        self._first_connect = False
        if rc == 0:
            self.log.info("Connection returned result: {!s}".format(connack_string(rc)))
            self._isconnected = True
            if self._first_connect is False:
                asyncio.run_coroutine_threadsafe(self._subscribeTopics(), self.loop)
                if self.welc is not None:
                    self.mqtt.publish(*self.welc)
        else:
            self._isconnected = False
            self.log.error("Error connecting: {!s}".format(connack_string(rc)))

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            self.log.warn("Unexpected disconnection.")
        self._isconnected = False

    async def _subscribeTopics(self):
        for subs in self._subscriptions.subs:
            q = self._subscriptions.subs[subs]["Qos"]
            try:
                self.mqtt.subscribe(subs, q)
            except Exception as e:
                self.log.error("Resubscribing: {!s}".format(e))

    def _execute_sync(self, client, userdata, msg):
        asyncio.run_coroutine_threadsafe(self._execute(msg.topic, msg.payload, msg.retain), self.loop)

    async def _execute(self, topic, msg, retain):
        self.log.debug("mqtt execution: {!s} {!s}".format(topic, msg, retain))
        msg = msg.decode()
        unsub = []
        topics = self._subscriptions.get(topic, "OnlyRetained")
        for t in topics:
            if topics[t] is True:
                self._subscriptions.removeObject(t)
                unsub.append(t)
        if len(unsub) > 0:
            self.mqtt.unsubscribe(unsub)
        try:
            await self.write(0, [topic, list(topics.keys()), msg, retain], timeout=5)
            # header 0 as not used as this is the only message type clients ever receive from this app
        except asyncio.TimeoutError:
            self.log.info("Timeout writing client: {!s},{!s}".format(topic, msg))
        except Exception as e:
            self.log.error("Error writing client: {!s}".format(e))

    def _unsubscribe(self, topics: list):
        if type(topics) != list:
            topics = [topics]
        for t in topics:
            try:
                self._subscriptions.removeObject(t)
            except ValueError as e:
                self.log.warn("Unsubscribe: {!s}".format(e))
        try:
            self.mqtt.unsubscribe(topics)
        except Exception as e:
            self.log.error("Error unsubscribing: {!s}".format(e))

    def _publish(self, topic, msg, qos=0, retain=False):
        self.mqtt.publish(topic, msg, qos, retain)

    async def _getRetainedStateTopic(self, topic: str, qos: int):
        if topic.endswith("/set"):
            state_topic = topic[:-4]
            sub = self._subscriptions.addObject(state_topic)
            sub["Qos"] = qos
            sub["OnlyRetained"] = True
            self.mqtt.subscribe(state_topic, qos)
        else:
            # not a command topic, topic therefore already in subscriptionHandler
            self.mqtt.subscribe(topic, qos)
            return
        await asyncio.sleep(0.1)
        try:
            t = self._subscriptions.removeObject(topic[:-4])
        except ValueError:
            return  # already got the state topic and was removed
        else:
            self.mqtt.unsubscribe(topic)

    def _subscribe(self, topics: list, qos: list, check_state_topic=True):
        if type(qos) != list:
            qos = [qos] * len(topics)
        if type(topics) != list:
            topics = [topics]
        topics_new = copy.deepcopy(topics)
        for topic in topics_new:
            try:
                t = self._subscriptions.get(topic, "Qos", equal=True)
            except ValueError:
                pass
            else:
                if t < qos[topics_new.index(topic)]:
                    self.mqtt.unsubscribe(topic)
                    self.mqtt.subscribe(topic, qos[topics_new.index[topic]])
                    self._subscriptions.set(topic, "Qos", qos[topics_new.index[topic]])
                # remove topic as already subscribed if qos subscribed >= qos requested
                # or subscribe higher qos
                qos.remove(topics.index(topic))
                topics.remove(topic)
                continue
        for topic in topics:
            sub = self._subscriptions.addObject(topic)
            sub["Qos"] = qos[topics.index(topic)]
            sub["OnlyRetained"] = False
            if check_state_topic is True and topic.endswith("/set"):
                asyncio.ensure_future(self._getRetainedStateTopic(topic, sub["Qos"]))
            else:
                self.mqtt.subscribe(topic, sub["Qos"])

    async def stop(self):
        """
        Stop mqtt client, remove instance
        :return:
        """
        if self._client_connected:
            # typically client is not connected anymore except on shutdown
            if self.will is not None:
                self._publish(*self.will)
            self.mqtt.disconnect()
            self.mqtt.loop_stop()
        await super().stop()
        self.mqtt = None

    def start(self):
        """
        Called after creation and when Connection to client is reestablished.
        :return:
        """
        self._client_connected = True
        self._first_connect = True
        self.log.debug("(Re)starting")
        # reconnect handled on first new message to support last will sent with first message

    async def pause(self):
        """
        Connection to client broken, discard all qos==0 messages and duplicates.
        Stop sending new messages.
        :return:
        """
        self.log.debug("Pausing")
        self._first_connect = True
        if self.will is not None:
            self._publish(*self.will)
        self._client_connected = False
        self.mqtt.disconnect()
        self.mqtt.loop_stop()
        # unsubscribe as client will resubscribe anyway and could subscribe to different topics.
        self._subscriptions.removeAll()

    async def handle(self, header_byte, data):
        """
        Handle new messages from client but do it quickly
        :param header_byte:
        :param data:
        :return:
        """
        self.log.debug("Got header {!s}, data {!s}".format(header_byte, data))
        if self._isconnected is False:
            if header_byte == CMD_WILL:  # if first message is will, then it can be send to broker
                if data is not None:
                    self.mqtt.will_set(*data)
            self.log.debug("Connecting")
            self.mqtt.connect(self.app.config["host"], self.app.config["port"], self.app.config["keepalive"])
            self.log.debug("Starting loop")
            self.mqtt.loop_start()
            self.log.debug("Loop started")
        if header_byte == CMD_UNSUBS:
            self._unsubscribe(data)
        elif header_byte == CMD_SUBS:
            self._subscribe(*data)
        elif header_byte == CMD_PUB:
            self._publish(*data)
        elif header_byte == CMD_WILL:
            self.will = data
        elif header_byte == CMD_WELC:
            self.welc = data
            self._publish(*data)
        else:
            self.log.error("No command for header {!s}".format(header_byte))


class Mqtt(App):
    def __init__(self, config):
        super().__init__(config)
        self.AppInstance = MqttInstance

    async def stop(self):
        """Extend with your own code but call stop method of base class to prevent RAM leak and to stop instances"""
        await super().stop()
