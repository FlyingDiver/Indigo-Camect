#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################

import indigo
import logging
import threading
import json
from datetime import datetime, date, time
from camect import Camect
import requests

requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

TS_FORMAT = "%Y-%m-%d %H:%M:%S"
RESTART_TIME = 60.0         # seconds to wait when restarting the connection to a Camect

class Plugin(indigo.PluginBase):

    ########################################
    # Main Plugin methods
    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        pfmt = logging.Formatter('%(asctime)s.%(msecs)03d\t[%(levelname)8s] %(name)20s.%(funcName)-25s%(msg)s',
                                 datefmt='%Y-%m-%d %H:%M:%S')
        self.plugin_file_handler.setFormatter(pfmt)

        try:
            self.logLevel = int(pluginPrefs[u"logLevel"])
        except Exception as err:
            self.logLevel = logging.INFO
        self.indigo_log_handler.setLevel(self.logLevel)
        self.logger.debug(f"logLevel = {self.logLevel}")

        self.camects = {}
        self.camect_info = {}
        self.camect_cameras = {}
        self.alert_triggers = {}
        self.camera_triggers = {}
        self.mode_triggers = {}

    def startup(self):
        self.logger.info(u"Starting Camect")

    def shutdown(self):
        self.logger.info(u"Stopping Camect")

    def deviceStartComm(self, device):

        if device.deviceTypeId == "camect":
            self.logger.info(f"{device.name}: Starting Device")
            self.camects[device.id] = Camect(device.name, device.id,
                                             device.pluginProps.get('address', ''),
                                             device.pluginProps.get('port', '443'),
                                             device.pluginProps.get('username', 'Admin'),
                                             device.pluginProps.get('password', None),
                                             self.callBack
                                             )

            device.updateStateOnServer(key="status", value="None")
            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

            # Make sure it connects.
            info = self.camects[device.id].get_info()
            if not info:
                self.logger.warning(u"Camect get_info returned no data")
                return

            self.camect_info[device.id] = info
            self.logger.debug(f"Camect info:\n{info}")

            key_value_list = [
                {'key': 'name', 'value': info['name']},
                {'key': 'cloud_url', 'value': info['cloud_url']},
                {'key': 'local_https_url', 'value': info['local_https_url']},
                {'key': 'mode', 'value': info['mode']},
                {'key': 'id', 'value': info['id']}
            ]
            device.updateStatesOnServer(key_value_list)

            self.camect_cameras[device.id] = {}
            self.logger.debug("Known Cameras:")
            for cam in self.camects[device.id].list_cameras():
                self.camect_cameras[device.id][cam['id']] = cam

            for cam in self.camect_cameras[device.id].values():
                self.logger.debug(f"{cam['name']}: {cam}")

        else:
            self.logger.warning(f"{device.name}: deviceStartComm: Invalid device type: {device.deviceTypeId}")

    def deviceStopComm(self, device):

        if device.deviceTypeId == "camect":
            self.logger.info(f"{device.name}: Stopping Device")
            del self.camects[device.id]
            device.updateStateOnServer(key="status", value="Stopped")
            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
        else:
            self.logger.warning(f"{device.name}: deviceStopComm: Invalid device type: {device.deviceTypeId}")

    def callBack(self, info):
        if not info:
            self.logger.warning("Camect callBack info is None")
            return

        self.logger.threaddebug(f"Camect callBack info: {info}")
        device = indigo.devices[info['devID']]

        if info['event'] == 'status':
            self.logger.debug(f"{device.name}: Camect Status: {info['status']}")
            device.updateStateOnServer(key="status", value=info['status'])
            return

        elif info['event'] == 'error':
            self.logger.warning(f"{device.name}: Restarting Device, error: {info['error']}")
            indigo.device.enable(device.id, value=False)
            threading.Timer(RESTART_TIME, indigo.device.enable, [device.id], {value: True}).start()
            return

        elif info['event'] != 'message':
            self.logger.warning(f"{device.name}: Unknown Camect callback event: {info['event']}")
            return

        try:
            event = json.loads(info['message'])
        except Exception as err:
            self.logger.error(f"{device.name}: Invalid JSON '{info['message']}': {err}")
            return

        self.logger.debug(f"{device.name}: Camect Event: {event}")

        key_value_list = [
            {'key': 'last_event', 'value': info['message']},
            {'key': 'last_event_time', 'value': datetime.now().strftime(TS_FORMAT)},
            {'key': 'last_event_type', 'value': event['type']}
        ]
        device.updateStatesOnServer(key_value_list)

        if event['type'] == 'alert':
            self.logger.info(f"{device.name}: {event['desc']}")

            key_value_list = [
                {'key': 'last_event_desc', 'value': event['desc']},
                {'key': 'last_event_url', 'value': event['url']},
                {'key': 'last_event_cam_id', 'value': event['cam_id']},
                {'key': 'last_event_cam_name', 'value': event['cam_name']},
                {'key': 'last_event_detected', 'value': ' '.join(event['detected_obj'])}
            ]
            device.updateStatesOnServer(key_value_list)

            self.logger.debug(
                f"Alert event: camectID: {device.id}, cam_id: {event['cam_id']}, detected_obj = {event['detected_obj']}")
            for triggerID in self.alert_triggers:
                trigger = self.alert_triggers[triggerID]
                self.logger.threaddebug(
                    f"Checking Alert trigger {triggerID}: camectID: {trigger.pluginProps['camectID']}, cam_id: {trigger.pluginProps['cameraID']}, object = {trigger.pluginProps['object']}")

                if not ((trigger.pluginProps["camectID"] == "-1") or (
                        trigger.pluginProps["camectID"] == str(device.id))):
                    self.logger.threaddebug(f"Skipping Alert trigger {triggerID}, wrong Camect")
                    continue

                if not ((trigger.pluginProps["cameraID"] == "-1") or (
                        trigger.pluginProps["cameraID"] == event['cam_id'])):
                    self.logger.threaddebug(f"Skipping Alert trigger {triggerID}, wrong camera")
                    continue

                if trigger.pluginProps["object"] == "-1":
                    self.logger.debug(f"Executing Any Object Alert trigger {triggerID}")
                    indigo.trigger.execute(trigger)
                    continue

                for obj in trigger.pluginProps["object"]:
                    if obj in ' '.join(event['detected_obj']):
                        self.logger.debug(f"Executing Alert trigger {triggerID} for object {obj}")
                        indigo.trigger.execute(trigger)
                        break

        elif event['type'] == 'alert_enabled' or event['type'] == 'alert_disabled':
            key_value_list = [
                {'key': 'last_event_cam_id', 'value': event['cam_id']},
                {'key': 'last_event_cam_name', 'value': event['cam_name']}
            ]
            device.updateStatesOnServer(key_value_list)

        elif event['type'] == 'camera_offline' or event['type'] == 'camera_online':
            key_value_list = [
                {'key': 'last_event_cam_id', 'value': event['cam_id']},
                {'key': 'last_event_cam_name', 'value': event['cam_name']}
            ]
            device.updateStatesOnServer(key_value_list)

            self.logger.debug(f"Camera event: camectID: {device.id}, type: {event['type']}")
            for triggerID, trigger in self.camera_triggers.iteritems():
                self.logger.threaddebug(
                    f"Checking Camera trigger {triggerID}: camectID: {trigger.pluginProps['camectID']}")

                if not ((trigger.pluginProps["camectID"] == "-1") or (
                        trigger.pluginProps["camectID"] == str(device.id))):
                    self.logger.threaddebug(f"Skipping Camera trigger {triggerID}, wrong Camect")
                    continue

                if not ((trigger.pluginProps["cameraID"] == "-1") or (
                        trigger.pluginProps["cameraID"] == event['cam_id'])):
                    self.logger.threaddebug(f"Skipping Camera trigger {triggerID}, wrong camera")
                    continue

                if trigger.pluginProps["type"] == event['type']:
                    self.logger.debug(f"Executing Camera trigger {triggerID}")
                    indigo.trigger.execute(trigger)

        elif event['type'] == 'mode':
            key_value_list = [
                {'key': 'mode', 'value': event['desc']}
            ]
            device.updateStatesOnServer(key_value_list)

            self.logger.debug(f"Mode event: camectID: {device.id}, mode: {event['desc']}")
            for triggerID, trigger in self.mode_triggers.iteritems():
                self.logger.threaddebug(
                    f"Checking Mode trigger {triggerID}: camectID: {trigger.pluginProps['camectID']}")

                if (trigger.pluginProps["camectID"] == "-1") or (trigger.pluginProps["camectID"] == str(device.id)):
                    self.logger.debug(f"Executing Mode trigger {triggerID}")
                    indigo.trigger.execute(trigger)

    ########################################
    # Trigger (Event) handling 
    ########################################

    def triggerStartProcessing(self, trigger):
        self.logger.debug(f"{trigger.name}: Adding {trigger.pluginTypeId} Trigger")
        if trigger.pluginTypeId == "alertEvent":
            assert trigger.id not in self.alert_triggers
            self.alert_triggers[trigger.id] = trigger
        elif trigger.pluginTypeId == "modeEvent":
            assert trigger.id not in self.mode_triggers
            self.mode_triggers[trigger.id] = trigger
        elif trigger.pluginTypeId == "cameraEvent":
            assert trigger.id not in self.camera_triggers
            self.camera_triggers[trigger.id] = trigger

    def triggerStopProcessing(self, trigger):
        self.logger.debug(f"{trigger.name}: Removing {trigger.pluginTypeId} Trigger")
        if trigger.pluginTypeId == "alertEvent":
            assert trigger.id in self.alert_triggers
            del self.alert_triggers[trigger.id]
        elif trigger.pluginTypeId == "modeEvent":
            assert trigger.id in self.mode_triggers
            del self.mode_triggers[trigger.id]
        elif trigger.pluginTypeId == "cameraEvent":
            assert trigger.id in self.camera_triggers
            del self.camera_triggers[trigger.id]

    ########################################
    # Plugin Actions object callbacks (pluginAction is an Indigo plugin action instance)
    ########################################

    def setModeCommand(self, pluginAction):
        camectID = int(pluginAction.props['camectID'])
        self.logger.debug(f"setModeCommand, new mode: {pluginAction.props['mode']}")
        self.camects[camectID].set_mode(pluginAction.props['mode'])

    def snapshotCameraCommand(self, pluginAction):
        camectID = int(pluginAction.props['camectID'])
        camect = indigo.devices[camectID]
        cameraID = pluginAction.props['cameraID']
        self.logger.debug(f"snapshotCameraCommand, camectID: {camectID} cameraID: {cameraID}")

        try:
            camera = self.camect_cameras[camectID][cameraID]
        except KeyError as err:
            self.logger.warning(f"{camect.name}: snapshotCameraCommand KeyError: {err}")
            self.logger.debug(f"{camect.name}: snapshotCameraCommand, self.camect_cameras: {self.camect_cameras}")
            return

        if camera['disabled']:
            self.logger.warning(f"{camect.name}: snapshotCameraCommand error, camera '{camera['name']}' is disabled!")
            return

        snapshotPath = self.pluginPrefs.get("snapshotPath", "IndigoWebServer/public")
        snapshotName = pluginAction.props.get('snapshotName', None)
        if not snapshotName or (len(snapshotName) == 0):
            snapshotName = f"snapshot-{camera['id']}"

        self.logger.debug(f"{camect.name}: snapshotCameraCommand, camera: {camera['name']} ({camera['id']})")

        image = self.camects[camectID].snapshot_camera(camera['id'], camera['width'], camera['height'])
        save_path = f"{indigo.server.getInstallFolderPath()}/{snapshotPath}/{snapshotName}.jpg"
        try:
            f = open(save_path, 'wb')
            f.write(image)
            f.close()
        except Exception as err:
            self.logger.warning(f"Error writing image file: {save_path}, err: {err}")

    def disableAlertsCommand(self, pluginAction):
        camectID = int(pluginAction.props['camectID'])
        camect = indigo.devices[camectID]
        cameraID = pluginAction.props['cameraID']
        if cameraID == "-1":
            cameraID = []
        self.logger.debug(
            f"{camect.name}: disableAlertsCommand, camera: {cameraID}, reason: {pluginAction.props['reason']}")
        self.camects[camectID].disable_alert([pluginAction.props['cameraID']], pluginAction.props['reason'])

    def enableAlertsCommand(self, pluginAction):
        camectID = int(pluginAction.props['camectID'])
        camect = indigo.devices[camectID]
        cameraID = pluginAction.props['cameraID']
        if cameraID == "-1":
            cameraID = []
        self.logger.debug(
            f"{camect.name}: enableAlertsCommand, camera: {cameraID}, reason: {pluginAction.props['reason']}")
        self.camects[camectID].enable_alert([pluginAction.props['cameraID']], pluginAction.props['reason'])

    ########################################
    # ConfigUI methods
    ########################################

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if not userCancelled:
            try:
                self.logLevel = int(valuesDict[u"logLevel"])
            except Exception as err:
                self.logLevel = logging.INFO
            self.indigo_log_handler.setLevel(self.logLevel)
            self.logger.debug(f"logLevel = {self.logLevel}")

    def validateEventConfigUi(self, valuesDict, typeId, eventId):
        self.logger.debug(f"validateEventConfigUi typeId = {typeId}, eventId = {eventId}, valuesDict = {valuesDict}")
        return True, valuesDict

    def pickCamect(self, type_filter=None, valuesDict=None, typeId=0, targetId=0):
        self.logger.threaddebug(f"pickCamect typeId = {typeId}, targetId = {targetId}, valuesDict = {valuesDict}")
        if "Any" in type_filter:
            retList = [("-1", "- Any Camect -")]
        else:
            retList = []
        for camectID in self.camects:
            device = indigo.devices[int(camectID)]
            retList.append((device.id, device.name))
        retList.sort(key=lambda tup: tup[1])
        return retList

    def pickCamera(self, type_filter=None, valuesDict=None, typeId=0, targetId=0):
        self.logger.threaddebug(f"pickCamera typeId = {typeId}, targetId = {targetId}, valuesDict = {valuesDict}")
        if "Any" in type_filter:
            retList = [("-1", "- Any Camera -")]
        elif "All" in type_filter:
            retList = [("-1", "- All Cameras -")]
        else:
            retList = []
        try:
            for cam in self.camect_cameras[int(valuesDict['camectID'])].values():
                retList.append((cam["id"], cam["name"]))
        except Exception as err:
            pass
        retList.sort(key=lambda tup: tup[1])
        return retList

    def pickObject(self, type_filter=None, valuesDict=None, typeId=0, targetId=0):
        self.logger.threaddebug(f"pickObject typeId = {typeId}, targetId = {targetId}, valuesDict = {valuesDict}")
        if "Any" in type_filter:
            retList = [("-1", "- Any Object -")]
        elif "All" in type_filter:
            retList = [("-1", "- All Objects -")]
        else:
            retList = []
        try:
            for objName in self.camect_info[int(valuesDict['camectID'])]['object_name']:
                retList.append((objName, objName))
        except Exception as err:
            pass
        retList.sort(key=lambda tup: tup[1])
        return retList

    # doesn't do anything, just needed to force other menus to dynamically refresh
    def menuChanged(self, valuesDict, typeId, devId):
        return valuesDict

    # preload action config dialogs with the first Camect
    def getActionConfigUiValues(self, pluginProps, typeId, devId):
        valuesDict = pluginProps
        errorMsgDict = indigo.Dict()
        if not pluginProps.get('camectID', None):
            valuesDict["camectID"] = self.camects.keys()[0]
        return valuesDict, errorMsgDict

    ########################################
    # Menu Methods
    ########################################

    def dumpConfig(self):
        for devID in self.camect_info:
            device = indigo.devices[devID]
            self.logger.info("{}: Config Data for device {}:\n{}\n{}".format(device.name, device.id,
                                json.dumps(self.camect_info[devID],sort_keys=True, indent=4, separators=(',', ': ')),
                                json.dumps(self.camect_cameras[devID],sort_keys=True, indent=4, separators=(',', ': '))
                            ))
        return True
