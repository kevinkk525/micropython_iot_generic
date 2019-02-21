# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2019-01-23

__updated__ = "2019-02-08"
__version__ = "0.1"

import serial
import logging
import sys
import time
import asyncio


# This library does not work reliable on my odroid c2


async def read(port, imp_statement=None, start_client=True):
    portname = port if port.rfind("/") == -1 else port[port.rfind("/") + 1:]
    fh = logging.FileHandler(portname + ".log", mode="w")
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter("[%(asctime)-15s] %(message)s")
    ch.setFormatter(formatter)
    fh.setFormatter(formatter)
    log = logging.getLogger("")
    log.setLevel(logging.DEBUG)
    log.addHandler(ch)
    log.addHandler(fh)
    imp_statement = imp_statement or "from micropython_iot.examples import c_app"
    while True:
        try:
            with serial.Serial(port, 115200, timeout=10) as ser:
                if start_client:
                    ser.write("{}\r\n".format(imp_statement).encode())
                    start_client = False
                while True:
                    try:
                        line = ser.readline()
                        if line != b"":
                            log.info(line.rstrip())
                        await asyncio.sleep(0.001)
                    except serial.serialutil.SerialException:
                        continue
                        # await asyncio.sleep(0.05)
        except Exception as e:
            log.critical(e)
        await asyncio.sleep(0.1)


def readMultiple(ports, imp_statement=None, start_client=True):
    ports = ports.split(",")
    print("Ports", ports)
    for port in ports:
        asyncio.ensure_future(read(port, imp_statement, start_client))
    loop = asyncio.get_event_loop()
    loop.run_forever()


def readSync(port, imp_statement=None, start_client=True):
    portname = port if port.rfind("/") == -1 else port[port.rfind("/") + 1:]
    fh = logging.FileHandler(portname + ".log", mode="w")
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter("[%(asctime)-15s] %(message)s")
    ch.setFormatter(formatter)
    fh.setFormatter(formatter)
    log = logging.getLogger("")
    log.setLevel(logging.DEBUG)
    log.addHandler(ch)
    log.addHandler(fh)
    imp_statement = imp_statement or "from micropython_iot.examples import c_app"
    while True:
        try:
            with serial.Serial(port, 115200, timeout=10) as ser:
                if start_client:
                    ser.write("{}\r\n".format(imp_statement).encode())
                    start_client = False
                while True:
                    try:
                        line = ser.readline()
                        if line != b"":
                            log.info(line.rstrip())
                        time.sleep(0.001)
                    except serial.serialutil.SerialException:
                        continue
                        # time.sleep(0.05)
        except Exception as e:
            log.critical(e)
        time.sleep(0.1)


# readMultiple(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None, sys.argv[3] if len(sys.argv) > 3 else True)
readSync(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None, sys.argv[3] if len(sys.argv) > 3 else True)
