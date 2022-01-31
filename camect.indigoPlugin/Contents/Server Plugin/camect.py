# Based on https://github.com/camect/camect-py
# Modified from the original to work with Python 2 and Indigo

import base64
import json
import logging
import ssl
import sys
import time

import requests
import websocket
import threading

requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)


########################################
class Camect:
    ########################################

    def __init__(self, hub_name, hub_devID, address, port, username, password, callback):
        self.logger = logging.getLogger("Plugin.Camect")

        self.hub_name = hub_name
        self.hub_devID = hub_devID
        self.username = username
        self.password = password
        self.callback = callback

        self._api_prefix = f"https://{address}:{port}/api/"
        self._ws_uri = f"wss://{address}:{port}/api/event_ws"

        self.authorization = "Basic " + base64.b64encode(f"{self.username}:{self.password}".encode()).decode()

        self.logger.threaddebug(
            f"{self.hub_name}: Camect object initialized, hubID = {self.hub_devID}, auth = {self.authorization}, callback = {self.callback}")

        ################################################################################
        # Minimal Websocket Client
        ################################################################################

        def ws_client():
            self.logger.threaddebug(f"{self.hub_name}: Connecting to '{self._ws_uri}'")

            self.ws = websocket.WebSocketApp(self._ws_uri, header={'Authorization': self.authorization},
                                             on_message=on_message,
                                             on_error=on_error,
                                             on_close=on_close,
                                             on_open=on_open)

            self.ws.run_forever(ping_interval=5, sslopt={"cert_reqs": ssl.CERT_NONE, "check_hostname": False})

        def on_message(ws, message):
            self.logger.threaddebug(f"{self.hub_name}: websocket on_message: {message}")
            self.callback({"name": self.hub_name, "devID": self.hub_devID, "event": "message", "message": message})

        def on_error(ws, error):
            self.logger.threaddebug(f"{self.hub_name}: websocket on_error: {error}")
            self.callback({"name": self.hub_name, "devID": self.hub_devID, "event": "error", "error": error})

        def on_open(ws):
            self.logger.threaddebug(f"{self.hub_name}: websocket on_open")
            self.callback({"name": self.hub_name, "devID": self.hub_devID, "event": "status", "status": "Connected"})

        def on_close(ws):
            self.logger.threaddebug(f"{self.hub_name}: websocket on_close")
            self.callback({"name": self.hub_name, "devID": self.hub_devID, "event": "status", "status": "Disconnected"})

        ################################################################################

        # start up the websocket receiver thread

        self.logger.threaddebug(f"{self.hub_name}: Starting websocket thread")
        self.thread = threading.Thread(target=ws_client).start()
        self.callback({"name": self.hub_name, "devID": self.hub_devID, "event": "status", "status": "Created"})

    def __del__(self):
        self.ws.close()

    ################################################################################
    # API Functions
    ################################################################################

    def get_info(self):
        try:
            resp = requests.get(self._api_prefix + "GetHomeInfo", verify=False, auth=(self.username, self.password))
        except Exception as err:
            self.logger.warning(f"{self.hub_name}: Error on GetHomeInfo: {err})")
            self.callback({"name": self.hub_name, "devID": self.hub_devID, "event": "error",
                           "error": "GetHomeInfo request failure"})
            return None

        resp_json = resp.json()
        if resp.status_code != 200:
            self.logger.warning(f"{self.hub_name}: Error on GetHomeInfo [{resp.status_code}]({resp.json()['err_msg']})")
            self.callback({"name": self.hub_name, "devID": self.hub_devID, "event": "error", "error": "Get Info Error"})
            return None
        return resp_json

    def set_mode(self, mode):
        resp = requests.get(self._api_prefix + "SetOperationMode", verify=False, auth=(self.username, self.password),
                            params={"Mode": mode})
        if resp.status_code != 200:
            self.logger.warning(f"{self.hub_name}: Failed to set operation mode to '{mode}': [{resp.status_code}]({resp.json()['err_msg']})")
            self.callback({"name": self.hub_name, "event": "error", "error": "Set Mode Error"})
            return None
        return mode

    def list_cameras(self):
        resp = requests.get(self._api_prefix + "ListCameras", verify=False, auth=(self.username, self.password))
        resp_json = resp.json()
        if resp.status_code != 200:
            self.logger.warning(f"{self.hub_name}: Error on ListCameras [{resp.status_code}]({resp.json()['err_msg']})")
            self.callback({"name": self.hub_name, "event": "error", "error": "List Cameras Error"})
            return None
        return resp_json["camera"]

    def snapshot_camera(self, cam_id, width=0, height=0):
        resp = requests.get(
            self._api_prefix + "SnapshotCamera", verify=False, auth=(self.username, self.password),
            params={"CamId": cam_id, "Width": str(width), "Height": str(height)})
        resp_json = resp.json()
        if resp.status_code != 200:
            self.callback({"name": self.hub_name, "event": "error", "error": "Snapshot Error"})
            self.logger.warning(f"{self.hub_name}: Error on SnapshotCamera [{resp.status_code}]({resp.json()['err_msg']})")
            return None
        return base64.b64decode(resp_json["jpeg_data"])

    def disable_alert(self, cam_ids, reason):
        """ Disable alerts for camera(s) or the home if "cam_ids" is empty.
        """
        return self._enable_alert(cam_ids, False, reason)

    def enable_alert(self, cam_ids, reason):
        """ Enable alerts for camera(s) or the home if "cam_ids" is empty.

        NOTE: This method can only undo disable_alert. It has no effect if disable_alert was not
        called before.
        Please make sure that "reason" is same as you called disable_alert.
        """
        return self._enable_alert(cam_ids, True, reason)

    def _enable_alert(self, cam_ids, enable, reason):
        params = {"Reason": reason}
        if enable:
            params["Enable"] = "1"
        for i in range(len(cam_ids)):
            key = f"CamId[{i:d}]"
            params[key] = cam_ids[i]
        resp = requests.get(self._api_prefix + "EnableAlert", verify=False, auth=(self.username, self.password),
                            params=params)
        resp_json = resp.json()
        if resp.status_code != 200:
            self.logger.warning(f"{self.hub_name}: Error on EnableAlert [{resp.status_code}]({resp.json()['err_msg']})")
            return None
        return reason
