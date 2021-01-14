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

import indigo

requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

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

        self._api_prefix = "https://{}:{}/api/".format(self.address, self.port)
        self._ws_uri = "wss://{}:{}/api/event_ws".format(self.address, self.port)
        
        device.updateStateOnServer(key="status", value="Not Connected")
        device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

        ################################################################################
        # Minimal Websocket Client
        ################################################################################
        
        def ws_client():

            self.logger.info("{}: Connecting to '{}'".format(device.name, self._ws_uri))
            authorization = "Basic " + self.authorization()

            ws = websocket.WebSocketApp(self._ws_uri,
                    header={'Authorization': authorization},
                    on_message = on_message,
                    on_error = on_error,
                    on_close = on_close,
                    on_open = on_open)
                
            self.logger.debug("{}: WebSocketApp created, starting run_forever()".format(device.name))
            ws.run_forever(ping_interval=5, sslopt={"cert_reqs": ssl.CERT_NONE, "check_hostname": False})
 
        def on_message(ws, message):
            self.logger.threaddebug("{}: websocket on_message: {}".format(device.name, message))
            indigo.activePlugin.processReceivedEvent(self.deviceID, message)

        def on_error(ws, error):
            self.logger.debug("{}: websocket on_error: {}".format(device.name, error))
            device.updateStateOnServer(key="status", value="Error")
            device.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)

        def on_open(ws):
            self.logger.debug("{}: websocket on_open".format(device.name))
            device.updateStateOnServer(key="status", value="Connected")
            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

        def on_close(ws):
            self.logger.debug("{}: websocket on_close".format(device.name))
            device.updateStateOnServer(key="status", value="Disconnected")
            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
          
        ################################################################################
                    
        # start up the websocket receiver thread
        
        self.logger.debug("{}: Starting websocket thread".format(device.name))
        self.thread = threading.Thread(target=ws_client).start()


    def __del__(self):
        self.ws.close()
        device = indigo.devices[self.deviceID]
        device.updateStateOnServer(key="status", value="Not Connected")
        device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)      

    ################################################################################
    # API Functions
    ################################################################################

    def authorization(self):
        return base64.b64encode("{}:{}".format(self.username, self.password).encode()).decode()

    def get_info(self):
        resp = requests.get(self._api_prefix + "GetHomeInfo", verify=False, auth=(self.username, self.password))
        json = resp.json()
        if resp.status_code != 200:
            device = indigo.devices[self.deviceID]
            self.logger.warning("{}: Error on GetHomeInfo [{}]({})".format(device.name, resp.status_code, resp.json()["err_msg"]))
            return None
        return json


    def set_mode(self, mode):
        resp = requests.get(self._api_prefix + "SetOperationMode", verify=False, auth=(self.username, self.password), params={"Mode": mode})
        if resp.status_code != 200:
            device = indigo.devices[self.deviceID]
            self.logger.warning("{}: Failed to set operation mode to '{}': [{}]({})".format(device.name, mode, resp.status_code, resp.json()["err_msg"]))
            return None
            
    def list_cameras(self):
        resp = requests.get(self._api_prefix + "ListCameras", verify=False, auth=(self.username, self.password))
        json = resp.json()
        if resp.status_code != 200:
            device = indigo.devices[self.deviceID]
            self.logger.warning("{}: Error on ListCameras [{}]({})".format(device.name, resp.status_code, resp.json()["err_msg"]))
            return None
        return json["camera"]

    def snapshot_camera(self, cam_id, width = 0, height = 0):
        resp = requests.get(
            self._api_prefix + "SnapshotCamera", verify=False, auth=(self.username, self.password),
            params={"CamId": cam_id, "Width": str(width), "Height": str(height)})
        json = resp.json()
        if resp.status_code != 200:
            device = indigo.devices[self.deviceID]
            self.logger.warning("{}: Error on SnapshotCamera [{}]({})".format(device.name, resp.status_code, resp.json()["err_msg"]))
            return None
        return base64.b64decode(json["jpeg_data"])

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
            device = indigo.devices[self.deviceID]
            self.logger.warning("{}: Error on EnableAlert [{}]({})".format(device.name, resp.status_code, resp.json()["err_msg"]))

