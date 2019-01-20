# Author: Kevin Köck
# Copyright Kevin Köck 2019 Released under the MIT license
# Created on 2018-12-20 

__updated__ = "2018-12-20"
__version__ = "0.0"

import logging
import asyncio
import yaml
import importlib
import math
from pathlib import Path
import os

log = logging.getLogger("AppHandler")


# Tested for RAM leak, None found unless subclass of App and AppInstance don't call the base class functions.


# apps should wait for Client.closing Event to listen for shutdown of server or Client object removal
# Client.connected can be awaited but Client.awaitConnection is recommended. After that a Client has logged in
# Currently no way of knowing if the client is currently actually connected
# Currently no way of ensuring a message has been sent to the client, only that it was added to the buffer


# Use apphandler to register apps, load apps, define base classes for apps


class AppInstance:
    def __init__(self, app, id, client):
        self.log = logging.getLogger("{!s}.{!s}.{!s}".format(app.__class__.__name__, client.client_id, id))
        self.app_id = id
        self.client = client
        self.app = app
        self.log.info("Instance created")

    def __del__(self):
        try:
            self.log.debug("Removing Instance Object")
        except Exception:
            pass

    async def stop(self):
        """
        Extend in subclass.
        Will be called once client gets removed.
        """
        if self.app is not None:
            self.log.info("Stopping instance")
            try:
                del self.app.instances[(self.client, self.app_id)]
            except KeyError:
                self.log.warning("Instance not found")
            if self.app_id in self.client.apps:
                del self.client.apps[self.app_id]
            self.client = None
            self.app = None
        else:
            try:
                self.log.error("Stopping although already stopped")
            except Exception:
                pass

    def start(self):
        """
        Extend in subclass.
        Will be called when client gets reconnected.
        """
        self.log.debug("(Re)starting Instance")

    async def pause(self):
        """
        Extend in subclass.
        Will be called when client connection is broken.
        """
        self.log.debug("Pausing instance")

    async def handle(self, header_byte, data):
        """
        Handle message from client, do it quickly or start new task.
        Subclass this.
        :param header_byte: header_byte for the app, if used by the app
        :param data: message
        :return:
        """
        self.log.debug("got header {!s} data {!s}".format(header_byte, data))

    async def write(self, header, message, timeout=math.inf, only_with_connection=False):
        """
        Send a message to the client of this instance.
        If no timeout is specified, will wait forever until device is connected (first connect).
        If only_with_connection is False, it will wait for the connection until timeout.
        :param header: int (one byte), app specific header for additional information next to message
        :param message: message as object (dict, list) or string
        :param timeout: float
        :param only_with_connection: bool
        :return: bool
        """
        if type(header) != int or header > 255:
            self.log.error("Wrong header type: {!s}".format(header))
            return False
        return await self.client.write(self.app.ident, self.app_id, header, message, timeout, only_with_connection)


class App:
    """App base class"""
    instances = {}  # [(client,app_id)]=AppInstance

    def __init__(self, config):
        self.ident = config["ident"]
        self.instanced = config["instanced_app"]
        self.config = config
        self.log = logging.getLogger(self.__class__.__name__)
        self.log.debug("Created app {!s}".format(self.__class__.__name__))
        self.AppInstance = AppInstance  # overwrite with your AppInstance class subclassed from the given one
        self._stopwaiter = asyncio.ensure_future(self._waitStop())

    def getInstance(self, id, client) -> AppInstance:
        # self.log.debug("New instance {!s}".format(id))
        self.instances[(client, id)] = self.AppInstance(self, id, client)
        self.instances[(client, id)].start()
        return self.instances[(client, id)]

    def start(self):
        """extend in subclass"""
        self.log.info("Starting app")

    async def stop(self):
        self.log.info("Stopping App")
        if self._stopwaiter is not None:
            self._stopwaiter.cancel()
        tasks = []
        for app_instance in self.instances:
            tasks.append(asyncio.ensure_future(self.instances[app_instance].stop()))
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), 2)
        except asyncio.TimeoutError:
            self.log.warning("Stopping app took longer than 2s, cancelling")
        self.log.debug("Stop complete")
        if self.ident in AppHandler.global_apps:
            del AppHandler.global_apps[self.ident]
        if self.ident in AppHandler.instanced_apps:
            del AppHandler.instanced_apps[self.ident]

    async def _waitStop(self):
        try:
            await AppHandler.stop_event.wait()
            self.log.debug("Got stop event")
            await self.stop()
        except asyncio.CancelledError:
            self.log.debug("Canceled _waitStop")


class AppHandler:
    global_apps = {}
    instanced_apps = {}
    stop_event = asyncio.Event()  # set by server_generic.Network.shutdown()

    @classmethod
    def getGlobalApp(cls, ident) -> App:
        """
        Get the global app, not an instance of it which could be a client wrapper, if provided by the app
        :param ident: app ident
        :return: App
        """
        if ident not in cls.global_apps:
            app = cls._loadApp(ident)
        else:
            app = cls.global_apps[ident]
        return app

    @classmethod
    def _loadApp(cls, ident):
        log.debug("_loadApp {!s}".format(ident))
        config = None
        path_module = None
        # TODO: check if apps.yaml exists
        pathlist = Path(os.path.realpath(__file__)).parent.parent.glob("*.yaml")
        apps_yaml = None
        for path in pathlist:
            if path.name == "apps.yaml":
                apps_yaml = path
                break
        if apps_yaml is None:
            log.critical("Could not find apps.yaml in server directory")
            raise FileNotFoundError("Could not find apps.yaml")
        with open(str(apps_yaml)) as f:
            apps_available = yaml.load(f)
        pathlist = Path(os.path.realpath(__file__)).parent.parent.joinpath("apps").glob("**/*.yaml")
        for path in pathlist:
            with open(str(path)) as f:
                y = yaml.load(f)
                if y["ident"] == ident:
                    if path.name.rstrip(".yaml") not in apps_available:
                        log.error("Module {!s} not activated in apps.yaml".format(path.name.rstrip(".yaml")))
                        raise ImportError
                    else:
                        config = y
                        config.update(apps_available["mqtt"])
                        path_module = str(
                            path.parent.relative_to(path.parent.parent.parent)).replace("/",
                                                                                        ".").replace(
                            "\\", ".")
                        break
        if config is None:
            log.error("App not available: {!s}".format(ident))
            raise ImportError
        try:
            log.debug("Trying import: {!s}.{!s}".format(path_module, config["module"]))
            module = importlib.import_module(path_module + "." + config["module"])
        except ImportError as e:
            try:
                # TODO: find a better way of dynamically import modules as the main package path differs
                #  in different script starting ways like pycharm, python3 -m server.main_apphandler
                log.debug("Trying import: server.{!s}.{!s}".format(path_module, config["module"]))
                module = importlib.import_module("server." + path_module + "." + config["module"])
            except ImportError as e:
                log.error("App not available: {!s}, Error: {!s}".format(ident, e))
                raise e
            except Exception as e:
                log.critical("Other exception importing module: {!s}".format(e))
                raise e
        except Exception as e:
            log.critical("Other exception importing module: {!s}".format(e))
            raise e
        try:
            cls_module = getattr(module, config["class"])
        except AttributeError as e:
            log.error("App not available: {!s}, Error: {!s}".format(ident, e))
            raise ImportError
        if config["instanced_app"] is True:
            cls.instanced_apps[ident] = cls_module(config)
            cls.instanced_apps[ident].start()
            return cls.instanced_apps[ident]
        else:
            cls.global_apps[ident] = cls_module(config)
            cls.global_apps[ident].start()
            return cls.global_apps[ident]

    @classmethod
    def getAppInstance(cls, ident, id, client) -> App:
        """
        Get an App instance without knowing if it is a global app or an instanced app.
        :param ident: app_identifier
        :param id: unique app_id
        :param client: client object
        :return: app object
        """
        # log.debug("getInstance {!s},{!s},{!s}".format(ident, id, client))
        if ident in cls.global_apps:
            return cls.global_apps[ident].getInstance(id, client)
        elif ident in cls.instanced_apps:
            return cls.instanced_apps[ident].getInstance(id, client)
        else:
            try:
                app = cls._loadApp(ident)
                # log.debug("got app {!s}".format(ident))
                return app.getInstance(id, client)
            except Exception as e:
                log.error(e)
                raise e
