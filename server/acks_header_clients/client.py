# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2019-01-10 

__updated__ = "2019-01-10"
__version__ = "0.0"

from server.generic_clients.client import Client as ClientGeneric, ClientRemovedException
import logging
import math
import json
import binascii
import time
import asyncio

log = logging.getLogger("Client")


# TODO: implement multiple concurrent writes or mabye not as esp can't handle it anyway.

# Create message ID's. Initially 0 then 1 2 ... 254 255 1 2
def gmid():
    mid = 0
    while True:
        yield mid
        mid = (mid + 1) & 0xff
        mid = mid if mid else 1


# Return True if a message ID has not already been received
def isnew(mid, lst=bytearray(32)):
    if mid == -1:
        for idx in range(32):
            lst[idx] = 0
        return
    idx = mid >> 3
    bit = 1 << (mid & 7)
    res = not (lst[idx] & bit)
    lst[idx] |= bit
    lst[(idx + 16 & 0x1f)] = 0
    return res


class Client(ClientGeneric):
    def __init__(self, client_id=None, len_rx_buffer=100, len_tx_buffer=100, timeout_connection=1500,
                 timeout_client_object=3600):
        """
        Client object holding all buffers and API.
        If buffer overflows, oldest messages will be dropped.
        timeout_client: After this amount of ms without a sent keepalive, the connection will be closed
        timeout_client_object: After this amount of seconds, the client object will be removed resulting in
        an error if still accessed after removal. If Client object should be persistent, use math.inf as argument.
        :param client_id: str
        :param len_rx_buffer: int
        :param len_tx_buffer: int
        :param timeout_connection: int, defaults to 1500ms or if created by Network object to its value
        :param timeout_client_object: int, defaults to 3600s or if created by Network object to its value.
        """
        super().__init__(client_id, len_rx_buffer, len_tx_buffer, timeout_connection, timeout_client_object)
        self._getmid = gmid()
        self._ok = False
        self._ack_mid = -1  # last received ACK mid
        self._tx_mid = 0  # sent mid, used for keeping messages in order
        self._recv_mid = bytearray(32)  # for deduping
        self._last_tx_time = 0
        self._rx_messages = []
        self._rx_message_event = asyncio.Event()
        self._reader_task = None
        self._tx_mid_offset = 0  # offset needed to jump mids if a sending process raises a timeout

    def start(self, init_message: bytes):
        """
        Init_message is preheader+client_id
        :param init_message:
        :return:
        """
        # ACK for client_id indirectly handled by starting to send keepalives
        # TODO: check header for clean connection flag etc.
        super().start(init_message)
        self._reader_task = asyncio.ensure_future(self._reader())

    @classmethod
    def readID(cls, message: bytes) -> str:
        """
        Returns client_id according to protocol implementation
        :param message: message without newline termination
        :return: client_id str
        """
        try:
            if binascii.unhexlify(message[0:2])[0] == 0x2C:  # only need first preheader value to check protocol
                return message[10:].decode()
        except Exception as e:
            raise TypeError("Message {!s} does not have the correct protocol, error {!s}".format(message, e))

    async def read(self, timeout=math.inf, only_with_connection=False) -> (bytearray, any):
        """
        Reads one message. Awaits until timeout.
        If only_with_connection is True, will return messages if buffer is not empty, otherwise raise Exception
        :param timeout: float (None will be math.inf)
        :param only_with_connection: bool
        :return: header, message (json.decode)
        """
        if timeout is None:
            timeout = math.inf
        if only_with_connection and self.connected.is_set() is False and len(self._rx_messages) == 0:
            raise IndexError("No messages available")
        st = time.time()
        while time.time() - st < timeout:
            if self._removed:
                raise ClientRemovedException
            if len(self._rx_messages) == 0:
                try:
                    await asyncio.wait_for(self._rx_message_event.wait(), 1)
                except asyncio.TimeoutError:
                    continue
                else:
                    self._rx_message_event.clear()
            else:
                # self.log.debug("_rx_messages: {!s}".format(self._rx_messages))
                return self._rx_messages.pop(0)
        raise asyncio.TimeoutError("Timeout waiting for a new message")

    async def _reader(self):
        try:
            while True:
                preheader = None
                header = None
                line = await super()._read(timeout=math.inf, only_with_connection=False)
                # self.log.debug("Got line: {!s}".format(line))
                if len(line) < 10:
                    self.log.error("Line is too short: {!s}".format(line))
                    continue
                try:
                    preheader = bytearray(binascii.unhexlify(line[:10]))  # 5 byte header=10 byte binascii
                except Exception as e:
                    self.log.error("Error converting preheader {!s}: {!s}".format(line, e))
                    continue
                mid = preheader[0]
                if preheader[4] & 0x2C == 0x2C:  # ACK
                    # self.log.debug("Got ack mid {!s}".format(mid))
                    self._ack_mid = mid
                    continue
                if not mid:
                    isnew(-1, self._recv_mid)
                if isnew(mid, self._recv_mid) is False:
                    self.log.warn("Dumping dupe mid {!s}".format(preheader[0]))  # TODO: info
                    if preheader[4] & 0x01 == 1:  # qos==True, send ACK even if dupe
                        await self._write_ack(mid)
                    continue
                if preheader[1] > 0:
                    try:
                        header = bytearray(binascii.unhexlify(line[10:10 + preheader[1] * 2]))
                    except Exception as e:
                        self.log.error("Error converting header {!s}: {!s}".format(line, e))
                        continue
                    data = line[10 + preheader[1] * 2:]
                else:
                    header = None
                    data = line[10:]
                try:
                    data = data.decode()
                except UnicodeDecodeError:
                    self.log.error("Can't decode data: {!s}".format(data))
                    continue
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    self.log.warn("Can't decode json data: {!s}".format(data))
                    continue  # will reset connection if qos as no ACK is sent back
                except Exception as e:
                    self.log.critical("Error converting from json: {!s}".format(e))
                    self.log.critical("Data: {!s}".format(data))
                self._rx_messages.append((header, data))
                self._rx_message_event.set()
                if preheader[4] & 0x01 == 1:  # qos==True, send ACK even if dupe
                    await self._write_ack(mid)  # does not need much time, so no new task
        except asyncio.CancelledError:
            self.log.debug("Stopped _reader")

    async def _write_ack(self, mid):
        """
        write ACK message, does not count towards self._last_tx time or wait for mid match.
        :param mid: mid of message to acknowledge
        :return:
        """
        preheader = bytearray(5)
        preheader[0] = mid
        preheader[1] = preheader[2] = preheader[3] = 0
        preheader[4] = 0x2C  # ACK
        preheader = "{}\n".format(binascii.hexlify(preheader).decode())
        if self.connected.is_set():
            async with self.output_lock:
                try:
                    self.transport.transport.write(preheader.encode())
                    return True
                except Exception as e:
                    self.log.warn("Got exception sending ACK {!s}: {!s}".format(preheader, e))
                    return False
        else:
            return False

    async def stop(self):
        if self._reader_task is not None or self._reader_task.done() is False:
            self._reader_task.cancel()
        await super().stop()

    async def write(self, header: bytearray, message, timeout=math.inf, only_with_connection=False, qos=True):
        """
        If no timeout is specified, will wait forever until device is connected.
        If only_with_connection is False, it will wait for the connection until timeout.
        :param header:
        :param message:
        :param timeout:
        :param only_with_connection:
        :param qos:
        :return:
        """
        if type(message) not in (bytes, str):
            try:
                message = json.dumps(message)
            except Exception as e:
                self.log.error("Could not convert message, {!s}".format(e))
                return False
        if type(message) == str:
            message = message.encode()
        if timeout is None:
            timeout = math.inf
        preheader = bytearray(5)
        preheader[0] = next(self._getmid)
        preheader[1] = 0 if header is None else len(header)
        preheader[2] = len(message) & 0xFF
        preheader[3] = (len(message) >> 8) & 0xFF  # allows for 65535 message length
        preheader[4] = 0  # special internal usages, e.g. for esp_link
        mid = preheader[0]
        if qos:
            preheader[4] |= 0x01  # qos==True, request ACK
        preheader = binascii.hexlify(preheader)
        try:
            message = preheader + (binascii.hexlify(header) if header is not None else b"") + message
        except Exception as e:
            self.log.error("Could not merge message, {!s}".format(e))
            return False
        # disconnect on timeout waiting for sending slot is wrong. Only disconnect on ACK timeout.
        st = time.time()
        try:
            while self._tx_mid != mid and time.time() - st < timeout:
                await asyncio.sleep(0.05)
                continue
        except asyncio.CancelledError:
            self.log.info("Waiting for writing slot for mid {!s}, got canceled".format(mid))
            self._tx_mid_offset += 1
            raise
        if self._tx_mid != mid:
            self.log.info("Timeout waiting for sending slot {!s}".format(mid))
            self._tx_mid_offset += 1
            raise asyncio.TimeoutError
        try:
            if qos:
                while time.time() - st < timeout:
                    if self._removed:
                        return False
                    if self.connected.is_set():
                        self.log.debug("Writing message {!s}, {!s}, {!s}".format(preheader, header, message))
                        ret = await self._write_qos(message)
                        if ret is False:
                            continue
                    else:
                        if only_with_connection is True:
                            self.log.info("Not connected, can't send")
                            return False
                        await asyncio.sleep(0.5)
                        continue
                    st_ack = time.time()
                    while time.time() - st_ack < 1:  # 1 second to receive ACK, typically <400ms needed, client not busy
                        if mid != self._ack_mid:
                            await asyncio.sleep(0.05)
                        else:
                            break
                    if self._ack_mid != mid:
                        if self.connected.is_set():
                            self.log.warn("Did not receive ACK {!s} in time".format(mid))
                            # await self.stop() # Possible deadlock if multiple concurrent writes are active
                    else:
                        return True
                self.log.debug("Timeout sending message {!s}".format(message))
                raise asyncio.TimeoutError
            else:
                ret = await self._write_qos(message)  # also used for qos False
                return ret
        except asyncio.CancelledError:
            self.log.info("Write mid {!s} got externally canceled".format(mid))
            raise
        finally:
            self._tx_mid += 1
            self._tx_mid += self._tx_mid_offset
            self._tx_mid_offset = 0
            if self._tx_mid >= 256:
                self._tx_mid = self._tx_mid - 255  # reset to 1+offset

    async def _write_qos(self, message):
        """
        :param message: str/bytes
        :return: True on success, False on error, Exception if only_with_connection==False and timeout
        """
        if not message.endswith("\n" if type(message) == str else b"\n"):
            message += "\n" if type(message) == str else b"\n"
        if time.time() - self._last_tx_time < 0.05:  # 50ms between each transmission
            await asyncio.sleep(time.time() - self._last_tx_time)
        async with self.output_lock:
            # self.log.debug("Writing message {!s}".format(message))
            if type(message) == str:
                message = message.encode()
            try:
                self.transport.transport.write(message)
            except Exception as e:
                self.log.info("Got exception sending message {!s}: {!s}".format(message, e))
                return False
            self._last_tx_time = time.time()
            return True
