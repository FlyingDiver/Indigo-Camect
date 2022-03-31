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

    def __init__(self, *, hub_id, address, port, username, password, delegate):
        self.logger = logging.getLogger("Plugin.Camect")

        self.hub_id = hub_id
        self.delegate = delegate
        self.ready = False
        self.thread_start_delay = 0.0

        self._api_prefix = f"https://{address}:{port}/api/"
        self._ws_uri = f"wss://{address}:{port}/api/event_ws"
        self.authorization = f"Basic {base64.b64encode(f'{username}:{password}'.encode()).decode()}"

        ################################################################################
        # Minimal Websocket Client
        ################################################################################

        def ws_client():
            self.logger.debug(f"Device {self.hub_id} connecting to '{self._ws_uri}'")

            self.ws = websocket.WebSocketApp(self._ws_uri, header={'Authorization': self.authorization},
                                             on_message=on_message,
                                             on_error=on_error,
                                             on_close=on_close,
                                             on_open=on_open)

            self.ws.run_forever(ping_interval=5, sslopt={"cert_reqs": ssl.CERT_NONE, "check_hostname": False})

        def on_open(ws):
            self.logger.debug(f"{self.hub_id}: websocket on_open")
            self.ready = True
            self.delegate.hub_status(dev_id=self.hub_id, status="Connected")

        def on_message(ws, message):
            self.logger.threaddebug(f"{self.hub_id}: websocket on_message: {message}")
            self.delegate.hub_message(dev_id=self.hub_id, message=message)

        def on_close(ws):
            self.logger.debug(f"{self.hub_id}: websocket on_close")
            self.ready = False
            self.delegate.hub_status(dev_id=self.hub_id, status="Closed")

        def on_error(ws, error):
            self.logger.debug(f"{self.hub_id}: websocket on_error: {error}")
            self.ready = False
            self.delegate.hub_error(dev_id=self.hub_id, error=error)

            if self.thread.is_alive():
                self.logger.debug(f"{self.hub_id}: websocket thread is still alive!")

            # try to recover from the error
            self.thread_start_delay += 10.0 if self.thread_start_delay < 50.0 else 60.0   # wait 10 more seconds, max 1 minute

            self.thread = threading.Thread(target=ws_client)
            self.logger.debug(f"{self.hub_id}: restarting websocket thread in {self.thread_start_delay} seconds")
            threading.Timer(self.thread_start_delay, lambda: self.thread.start()).start()

        ################################################################################

        # start up the websocket receiver thread

        self.thread = threading.Thread(target=ws_client).start()
        self.delegate.hub_status(dev_id=self.hub_id, status="Started")

    def __del__(self):
        self.ws.close()

    ################################################################################
    # API Functions
    ################################################################################

    def _do_request(self, api_call, params=None):
        self.logger.debug(f"{self.hub_id}: _do_request api_call = {api_call}, params = {params}")
        try:
            resp = requests.get(self._api_prefix + api_call, timeout=10.0, verify=False, headers={'Authorization': self.authorization}, params=params)
        except requests.exceptions.ConnectionError as err:
            self.delegate.hub_error(dev_id=self.hub_id, error=f"{api_call} request failure")
            return None
        except requests.exceptions.Timeout as err:
            self.delegate.hub_error(dev_id=self.hub_id, error=f"{api_call} timeout")
            return None
        if resp.status_code != 200:
            self.delegate.hub_error(dev_id=self.hub_id, error=f"{api_call} Error, status code: {resp.status_code}")
            self.logger.debug(f"{self.hub_id}: _do_request resp = {resp.text}")
            return None

        return resp

    def get_info(self):
        return self._do_request("GetHomeInfo").json()

    def set_mode(self, mode):
        self._do_request("SetOperationMode")
        return mode

    def list_cameras(self):
        resp_json = self._do_request("ListCameras").json()
        return resp_json["camera"]

    def ptz(self, cam_id, action):
        params = {"CamId": cam_id, "Action": action}
        self._do_request("PTZ", params)
        return

    def snapshot_camera(self, cam_id, width=0, height=0):
        params = {"CamId": cam_id, "Width": str(width), "Height": str(height)}
        resp = self._do_request("SnapshotCamera", params)
        if not resp:
            return None
        return base64.b64decode(resp.json()["jpeg_data"])

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

        resp_json = self._do_request("EnableAlert", params).json()
        return reason
