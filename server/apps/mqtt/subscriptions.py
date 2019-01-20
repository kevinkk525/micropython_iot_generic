# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-31 

__updated__ = "2018-12-31"
__version__ = "0.0"

from paho.mqtt.matcher import MQTTMatcher


def _match_topic(subscription: str, topic: str) -> bool:
    """Test if topic matches subscription."""
    matcher = MQTTMatcher()
    matcher[subscription] = True
    try:
        next(matcher.iter_match(topic))
        return True
    except StopIteration:
        return False


class SubscriptionHandler:
    def __init__(self, *args):
        self.subs = {}
        for arg in args:
            setattr(self, "get{!s}".format(arg), self.__wrapper_get(arg))
            setattr(self, "set{!s}".format(arg), self.__wrapper_set(arg))

    def __wrapper_get(self, key):
        def get(identifier, equal=False):
            return self.get(identifier, key, equal)

        return get

    def __wrapper_set(self, key):
        def set(identifier, value):
            return self.set(identifier, key, value)

        return set

    def get(self, identifier, key, equal=False):
        if equal:
            if identifier in self.subs:
                if key in self.subs[identifier]:
                    return self.subs[identifier][key]
            else:
                raise ValueError("Identifier does not exist: {!s}".format(identifier))
        ret = {}
        found = False
        for sub in self.subs:
            if _match_topic(sub, identifier):
                found = True
                if key in self.subs[sub]:
                    ret[sub] = self.subs[sub][key]
        if found is False:
            raise ValueError("Identifier does not exist: {!s}".format(identifier))
        if len(ret) == 0:
            raise ValueError("Key does not exist: {!s}".format(key))
        return ret

    def getObject(self, identifier):
        if identifier in self.subs:
            return self.subs[identifier]

    def set(self, identifier, key, value):
        if identifier not in self.subs:
            raise ValueError("Identifier does not exist: {!s}".format(identifier))
        self.subs[identifier][key] = value

    def addObject(self, identifier, values: dict = None):
        if values is None:
            values = {}
        if identifier in self.subs:
            raise ValueError("Identifier already exists: {!s}".format(identifier))
        self.subs[identifier] = values
        return values

    def removeObject(self, identifier):
        if identifier not in self.subs:
            raise ValueError("Identifier does not exist: {!s}".format(identifier))
        del self.subs[identifier]

    def removeAll(self):
        self.subs = {}
