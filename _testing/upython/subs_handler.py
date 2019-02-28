# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-13 

__updated__ = "2018-12-13"
__version__ = "1.0"

import gc
import time

memory = gc.mem_free()
gc.collect()


def timeit(f):
    myname = str(f).split(' ')[1]

    def new_func(*args, **kwargs):
        t = time.ticks_us()
        result = f(*args, **kwargs)
        delta = time.ticks_diff(time.ticks_us(), t)
        print('[Time] Function {}: {:6.3f}ms'.format(myname, delta / 1000))
        return result

    return new_func


def printMemory(info=""):
    global memory
    memory_new = gc.mem_free()
    print("[RAM] [{!s}] {!s}".format(info, memory_new - memory))
    memory = memory_new


def creating():
    gc.collect()
    printMemory("Start")
    from client.subs_handler import SubscriptionHandler
    gc.collect()
    printMemory("After import")
    global handler
    handler = SubscriptionHandler()
    gc.collect()
    printMemory("After handler creation")


@timeit
def addObjects():
    for j in range(0, 3):
        for i in range(0, 10):
            handler.add("home/235j094s4eg/device{!s}/htu{!s}".format(j, i), "func{!s}".format(i))


@timeit
def getObject():
    return handler.get("home/235j094s4eg/device2/htu9")


@timeit
def addObjectsList():
    for j in range(0, 3):
        for i in range(0, 10):
            a.append(("home/235j094s4eg/device{!s}/htu{!s}".format(j, i), "func{!s}".format(i)))


@timeit
def getObjectList():
    for i in a:
        if i[0] == "home/235j094s4eg/device3/htu9":
            return i[1]


def speedtest():
    creating()
    gc.collect()
    printMemory("after creation with no Objects")
    addObjects()
    gc.collect()
    printMemory("30 Objects")
    print(getObject())
    gc.collect()
    printMemory("Subscription test done")

    print("Comparison to list")
    global a
    a = []

    gc.collect()
    printMemory("List created")
    addObjectsList()
    gc.collect()
    printMemory("Added 30 objects to list")
    print(getObjectList())
    gc.collect()
    printMemory("List comparison done")


speedtest()


def test():
    def wrapResult(func, arg, expected):
        try:
            res = func(arg)
        except Exception as e:
            res = type(e)
        equals = expected == res
        print("Success:", equals, "Expected result:", expected, "Result:", res)

    from client.subs_handler import SubscriptionHandler

    print("Testing SubscriptionHandler functionality")
    t = SubscriptionHandler()

    topic = "home/login/#"
    t.add(topic, "sendConfig")
    wrapResult(t.get, "home/login/test", IndexError)
    wrapResult(t.get, "home/login", IndexError)
    wrapResult(t.get, "home/login/#", "sendConfig")

    topic = "home/login"
    t.add(topic, "nothing")
    t.add(topic, "nothing2")
    wrapResult(t.get, "home/login", ("nothing", "nothing2"))

    t.set(topic, "nothing")
    wrapResult(t.get, "home/login", "nothing")

    t.delete(topic)
    wrapResult(t.get, "home/login", IndexError)

    print("\nFunctional tests done\n")


test()

print("Test finished")

"""
>>> from micropython_iot_generic._testing.upython import subs_handler
[RAM] [Start] 512
[RAM] [After import] -592
[RAM] [After handler creation] -32
[RAM] [after creation with no Objects] 128
[Time] Function addObjects: 522.896ms
[RAM] [30 Objects] -3840
[Time] Function getObject:  1.655ms
func9
[RAM] [Subscription test done] 0
Comparison to list
[RAM] [List created] -32
[Time] Function addObjectsList: 468.785ms
[RAM] [Added 30 objects to list] -2992
[Time] Function getObjectList:  2.550ms
None
[RAM] [List comparison done] 0
Testing SubscriptionHandler functionality
Success: True Expected result: <class 'IndexError'> Result: <class 'IndexError'>
Success: True Expected result: <class 'IndexError'> Result: <class 'IndexError'>
Success: True Expected result: ('sendConfig', False) Result: sendConfig
Success: True Expected result: ('nothing', 'nothing2') Result: ('nothing', 'nothing2')
Success: True Expected result: nothing Result: nothing
Success: True Expected result: <class 'IndexError'> Result: <class 'IndexError'>

Functional tests done

Test finished

Functional tests done

Test finished
"""
