# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-13 

__updated__ = "2018-12-13"
__version__ = "1.0"


class _Subscription:
    def __init__(self, topic, cbs):
        self.topic = topic
        self.cbs = cbs
        self.next = None


class SubscriptionHandler:
    """
    Handles subscriptions for applications like mqtt. Every subscription has an identifier called "topic" and callbacks.
    Values are organized as a tuple of single cbs.
    This is not done using a python list as a list has to be reallocated on the heap every time an item gets added.
    """

    def __init__(self):
        self.ifirst = None

    def get(self, topic, index=None):
        """
        Get cbs of topic. Index is optional for when multiple cbs are stored or all should be received
        :param topic: str, topic of subscription
        :param index: int, index within stored tuple
        :return: value (e.g. callback), or tuple of cbs
        """
        obj = self.__getObject(topic)
        if obj is not None:
            cbs = obj.cbs[index] if index is not None and type(obj.cbs) == tuple else obj.cbs
            return cbs
        raise IndexError("Object {!s} does not exist".format(topic))

    def set(self, topic, cbs):
        """
        Set cbs of a topic to given cbs. Will always overwrite.
        :param topic: str, topic of subscription
        :param cbs: tuple of cbs or single value (e.g. callback)
        :return:
        """
        obj = self.__getObject(topic)
        if obj is not None:
            obj.cbs = cbs
        else:
            raise IndexError("Object {!s} does not exist".format(topic))

    def __getObject(self, topic):
        obj = self.ifirst
        while obj is not None:
            if obj.topic == topic:
                return obj
            obj = obj.next
        return None

    def add(self, topic, cbs):
        """
        Adds a new object to the subscriptions. If an object with this topic already exists, the cbs will be added.
        :param topic: str
        :param cbs: tuple of cbs or a single value (e.g. callback)
        :return:
        """
        obj = self.__getObject(topic)
        if obj is not None:
            cbs = cbs if type(cbs) == tuple else tuple([cbs])
            if type(obj.cbs) != tuple:
                obj.cbs = tuple([obj.cbs]) + cbs
            else:
                obj.cbs += cbs
        else:
            obj = self.ifirst
            if obj is None:
                self.ifirst = _Subscription(topic, cbs)
                return
            while obj.next is not None:
                obj = obj.next
            obj.next = _Subscription(topic, cbs)

    def delete(self, topic):
        """
        Delete object with given topic
        :param topic: str
        :return:
        """
        obj = self.__getObject(topic)
        if obj is None:
            return
        if obj == self.ifirst:
            self.ifirst = None
            del obj
            return
        i = self.ifirst
        while i.next != obj:
            i = i.next
        i.next = obj.next
        del obj

    def print(self):
        for obj in self:
            print(obj)

    def __iter__(self):
        """
        Iterates over the topic of each subscription
        :return: str
        """
        obj = self.ifirst
        while obj is not None:
            yield obj.topic
            obj = obj.next
