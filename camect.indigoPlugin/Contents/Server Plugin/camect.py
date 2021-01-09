# Modified from the original to work with Python 2 and Indigo

import base64
import json
import logging
import ssl
import sys
import time
import urllib3

import requests
import websocket
import threading

import indigo

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class Error(Exception):
    pass

########################################
class Camect:
########################################

    def __init__(self, device):
        self.logger = logging.getLogger("Plugin.Camect")

        self.deviceID = device.id
    
        self.address = device.pluginProps.get(u'address', "")
        self.port = device.pluginProps.get(u'port', '443')
        self.username = device.pluginProps.get(u'username', 'admin')
        self.password = device.pluginProps.get(u'password', None)

        device.updateStateOnServer(key="status", value="Not Connected")
        device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

        self._api_prefix = "https://{}:{}/api/".format(self.address, self.port)
#        self._ws_uri = "wss://{}:{}/api/event_ws".format(self.address, self.port)
        self._ws_uri = "ws://{}:{}/".format(self.address, self.port)
        
        # Make sure it connects.
#        self.get_info()

    ################################################################################
    # Minimal Websocket Client
    ################################################################################
        
        def recv_ws():
            while True:
                try:
                    frame = self.ws.recv_frame()
                except websocket.WebSocketException as err:
                    self.logger.error("WebSocketException: {}".format(err))
                    device.updateStateOnServer(key="status", value="Disconnected")
                    device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                    break
                    
                if not frame:
                    device.updateStateOnServer(key="status", value="Invalid Frame")
                    device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                    raise websocket.WebSocketException("Not a valid frame %s" % frame)
                    
                if frame.opcode == websocket.ABNF.OPCODE_CLOSE:
                    self.logger.error("WebSocket Closed")
                    device.updateStateOnServer(key="status", value="Disconnected")
                    device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                    break

                elif frame.opcode == websocket.ABNF.OPCODE_PING:
                    self.logger.threaddebug("WebSocket Ping")
                    self.ws.pong(frame.data)
                    continue

                self.logger.threaddebug("websocket received event: {}".format(frame.data))
                indigo.activePlugin.processReceivedEvent(self.deviceID, frame.data)

            self.logger.error("recv_ws loop ended")
                    
        self.logger.info("{}: Connecting to '{}'".format(device.name, self._ws_uri))
        authorization = "Basic " + self.authorization()
        self.ws = websocket.create_connection(self._ws_uri, headers={"Authorization": authorization}, sslopt={"cert_reqs": ssl.CERT_NONE, "check_hostname": False})
#        self.ws = websocket.create_connection(self._ws_uri, sslopt={"cert_reqs": ssl.CERT_NONE, "check_hostname": False})
#        self.ws = websocket.create_connection(self._ws_uri)
        self.logger.debug("{}: Connection OK".format(device.name))
        self.thread = threading.Thread(target=recv_ws).start()
        self.logger.debug("{}: Thread OK".format(device.name))
        device.updateStateOnServer(key="status", value="Connected")
        device.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)


    def __del__(self):
        device = indigo.devices[self.deviceID]
        device.updateStateOnServer(key="status", value="Not Connected")
        device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)      

    ################################################################################
    # For initial testing only
    ################################################################################
                  
    def sendText(self, message):
#        self.logger.debug("sendText: {}".format(message))
        self.ws.send(message)


    ################################################################################
    # API Functions
    ################################################################################

    def add_event_listener(self, cb):
        self._evt_loop.call_soon_threadsafe(self.evt_listeners_.append, cb)

    def del_event_listener(self, cb):
        self._evt_loop.call_soon_threadsafe(self.evt_listeners_.remove, cb)

    def authorization(self):
        return base64.b64encode("{}:{}".format(self.username, self.password).encode()).decode()

    def get_id(self):
        info = self.get_info()
        if info:
            return info["id"]
        return ""

    def get_name(self):
        info = self.get_info()
        if info:
            return info["name"]
        return ""

    def get_mode(self):
        info = self.get_info()
        if info:
            return info["mode"]
        return ""

    def get_cloud_url(self, path):
        info = self.get_info()
        if info:
            return info["cloud_url"] + path
        return ""

    def get_cloud_websocket_url(self, expiration_secs = 24 * 3600):
        return self.get_cloud_url("webrtc/ws").replace("https://", "wss://") + '?access_token=' + self.generate_access_token(expiration_secs)

    # The returned URL needs internet and may not work in certain network environment.
    def get_local_https_url(self, path):
        info = self.get_info()
        if info:
            return info["local_https_url"] + path + "?X-AUTHORIZATION=" + self.authorization()
        return ""

    # The returned URL needs internet and may not work in certain network environment.
    def get_local_websocket_url(self):
        return self.get_local_https_url("webrtc/ws").replace("https://", "wss://")

    # The returned URL has invalid TLS certificate.
    def get_unsecure_https_url(self, path):
        return "https://{}/{}?X-AUTHORIZATION={}".format(self._server_addr, path, self.authorization())

    # The returned URL has invalid TLS certificate.
    def get_unsecure_websocket_url(self):
        return self.get_unsecure_https_url("webrtc/ws").replace("https://", "wss://")

    def get_info(self):
        resp = requests.get(self._api_prefix + "GetHomeInfo", verify=False, auth=(self.username, self.password))
        json = resp.json()
        if resp.status_code != 200:
            raise Error("Failed to get home info: [%d](%s)" % (resp.status_code, json["err_msg"]))
        return json

    def set_name(self, name):
        resp = requests.get(self._api_prefix + "SetHomeName", verify=False, auth=(self.username, self.password), params={"Name": name})
        if resp.status_code != 200:
            raise Error("Failed to set home name to '{}': [{}]({})".format(name, resp.status_code, resp.json()["err_msg"]))

    def set_mode(self, mode):
        resp = requests.get(self._api_prefix + "SetOperationMode", verify=False, auth=(self.username, self._assword), params={"Mode": mode})
        if resp.status_code != 200:
            raise Error("Failed to set operation mode to '{}': [{}]({})".format(mode, resp.status_code, resp.json()["err_msg"]))

    def list_cameras(self):
        resp = requests.get(self._api_prefix + "ListCameras", verify=False, auth=(self.username, self.password))
        json = resp.json()
        if resp.status_code != 200:
            raise Error("Failed to get home info: [{}]({})".format(resp.status_code, json["err_msg"]))
        return json["camera"]

    def snapshot_camera(self, cam_id, width = 0, height = 0):
        resp = requests.get(
            self._api_prefix + "SnapshotCamera", verify=False, auth=(self.username, self.password),
            params={"CamId": cam_id, "Width": str(width), "Height": str(height)})
        json = resp.json()
        if resp.status_code != 200:
            raise Error("Failed to snapshot camera: [{}]({})".format(resp.status_code, json["err_msg"]))
        return base64.b64decode(json["jpeg_data"])

    def generate_access_token(self, expiration_secs = 24 * 3600):
        """Generates a token that could be used to establish P2P connection with home server w/o
        login.

        NOTE: Please keep the returned token safe.
        To invalidate the token, change the user's password.
        """
        expiration_ts = int(time.time()) + expiration_secs
        resp = requests.get(
            self._api_prefix + "GenerateAccessToken", verify=False,
            auth=(self.username, self.password), params={"ExpirationTs": str(expiration_ts)})
        json = resp.json()
        if resp.status_code != 200:
            raise Error("Failed to generate access token: [{}]({})".format(resp.status_code, json["err_msg"]))
        return json["token"]

    def disable_alert(self, cam_ids, reason):
        """ Disable alerts for camera(s) or the home if "cam_ids" is empty.
        """
        self._enable_alert(cam_ids, False, reason)

    def enable_alert(self, cam_ids, reason):
        """ Enable alerts for camera(s) or the home if "cam_ids" is empty.

        NOTE: This method can only undo disable_alert. It has no effect if disable_alert was not
        called before.
        Please make sure that "reason" is same as you called disable_alert.
        """
        self._enable_alert(cam_ids, True, reason)

    def _enable_alert(self, cam_ids, enable, reason):
        params = { "Reason": reason }
        if enable:
            params["Enable"] = "1"
        for i in range(len(cam_ids)):
            key = "CamId[%d]" % (i)
            params[key] = cam_ids[i]
        resp = requests.get(self._api_prefix + "EnableAlert", verify=False, auth=(self.username, self.password), params=params)
        json = resp.json()
        if resp.status_code != 200:
            self.logger.error(
                "Failed to enable/disable alert: [%d](%s)", resp.status_code, json["err_msg"])

#     def start_hls(self, cam_id: str):
#         """ Start HLS the camera. Returns the HLS URL.
# 
#         The URL expires after it's been idle for 1 minute.
#         NOTE: This is an experimental feature, only available for pro units now.
#         """
#         resp = requests.get(
#             self._api_prefix + "StartStreaming", verify=False, auth=(self._user, self._password),
#             params={ "Type": "1", "CamId": cam_id, "StreamingHost": self._server_addr })
#         json = resp.json()
#         if resp.status_code != 200:
#             self.logger.error(
#                 "Failed to start HLS: [%d](%s)", resp.status_code, json["err_msg"])
#         return json["hls_url"]

