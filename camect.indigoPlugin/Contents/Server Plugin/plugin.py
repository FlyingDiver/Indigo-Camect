#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################

import logging
import indigo
import json
import time

import requests
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

from camect import Camect

################################################################################
class Plugin(indigo.PluginBase):

    ########################################
    # Main Plugin methods
    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        pfmt = logging.Formatter('%(asctime)s.%(msecs)03d\t[%(levelname)8s] %(name)20s.%(funcName)-25s%(msg)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.plugin_file_handler.setFormatter(pfmt)

        try:
            self.logLevel = int(self.pluginPrefs[u"logLevel"])
        except:
            self.logLevel = logging.INFO
        self.indigo_log_handler.setLevel(self.logLevel)
        self.logger.debug(u"logLevel = {}".format(self.logLevel))


    def startup(self):
        self.logger.info(u"Starting Camect")
        
        self.camects = {}
        self.camect_cameras = {}
        self.camect_info = {}
        self.alert_triggers = {}
        self.camera_triggers = {}
        self.mode_triggers = {}

    def shutdown(self):
        self.logger.info(u"Stopping Camect")


    def deviceStartComm(self, device):

        if device.deviceTypeId == "camect":
            self.logger.info(u"{}: Starting Device".format(device.name))
            self.camects[device.id] = Camect(device)
            device.updateStateOnServer(key="status", value="None")
            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
            
            # Make sure it connects.
            info = self.camects[device.id].get_info()
            if not info:
                self.logger.warning(u"Camect get_info returned no data")
                return
                            
            self.camect_info[device.id] = info
            self.logger.debug(u"Camect info:\n{}".format(info))
        
            key_value_list = [
                  {'key':'name',            'value':info['name']},
                  {'key':'cloud_url',       'value':info['cloud_url']},
                  {'key':'local_https_url', 'value':info['local_https_url']},
                  {'key':'mode',            'value':info['mode']},
                  {'key':'id',              'value':info['id']}
            ]
            device.updateStatesOnServer(key_value_list)   

            self.camect_cameras[device.id] = {}
            self.logger.debug(u"Known Cameras:")
            for cam in  self.camects[device.id].list_cameras():
                self.camect_cameras[device.id][cam['id']] = cam
                self.logger.debug("{}: {}".format(cam["name"], cam))

        else:
            self.logger.warning(u"{}: deviceStartComm: Invalid device type: {}".format(device.name, device.deviceTypeId))
            
    def deviceStopComm(self, device):
        
        if device.deviceTypeId == "camect":
            self.logger.info(u"{}: Stopping Device".format(device.name))
            del self.camects[device.id]
            device.updateStateOnServer(key="status", value="None")
            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
        else:
            self.logger.warning(u"{}: deviceStopComm: Invalid device type: {}".format(device.name, device.deviceTypeId))


    def processReceivedEvent(self, devID, event_json):
        device = indigo.devices[devID]
        self.logger.debug(u"{}: Event JSON: {}".format(device.name, event_json))
        
        try:
            event = json.loads(event_json)
        except Exception as err:
            self.logger.error(u"{}: Invalid JSON '{}': {}".format(device.name, event_json, err))

        key_value_list = [
            {'key':'last_event',          'value':event_json},
            {'key':'last_event_type',     'value':event['type']}
        ]
        device.updateStatesOnServer(key_value_list)  

        if event['type'] == 'alert':
            self.logger.info(u"{}: {}".format(device.name, event['desc']))
            
            key_value_list = [
                {'key':'last_event_desc',     'value':event['desc']},
                {'key':'last_event_url',      'value':event['url']},
                {'key':'last_event_cam_id',   'value':event['cam_id']},
                {'key':'last_event_cam_name', 'value':event['cam_name']},
                {'key':'last_event_detected', 'value':' '.join(event['detected_obj'])}
            ]
            device.updateStatesOnServer(key_value_list)  

            self.logger.debug(u"Alert event: camectID: {}, cam_id: {}, detected_obj = {}".format(device.id, event['cam_id'], event['detected_obj']))
            for triggerID in self.alert_triggers:
                trigger = self.alert_triggers[triggerID]
                self.logger.threaddebug(u"Checking Alert trigger {}: camectID: {}, cam_id: {}, object = {}".format(triggerID, trigger.pluginProps['camectID'], trigger.pluginProps['cameraID'], trigger.pluginProps['object']))
                
                if not ((trigger.pluginProps["camectID"] == "-1") or (trigger.pluginProps["camectID"] == str(device.id))):
                    self.logger.threaddebug(u"Skipping Alert trigger {}, wrong Camect".format(triggerID))
                    continue
                    
                if not ((trigger.pluginProps["cameraID"] == "-1") or (trigger.pluginProps["cameraID"] == event['cam_id'])):
                    self.logger.threaddebug(u"Skipping Alert trigger {}, wrong camera".format(triggerID))
                    continue
                    
                if trigger.pluginProps["object"] == "-1":
                    self.logger.debug(u"Executing Any Object Alert trigger {}".format(triggerID))
                    indigo.trigger.execute(trigger)
                    continue

                for obj in trigger.pluginProps["object"]:
                    if obj in ' '.join(event['detected_obj']):
                        self.logger.debug(u"Executing Alert trigger {} for object {}".format(triggerID, obj))
                        indigo.trigger.execute(trigger)
                        break
                
                    
        elif event['type'] == 'alert_enabled' or event['type'] == 'alert_disabled':
            key_value_list = [
                {'key':'last_event_cam_id',   'value':event['cam_id']},
                {'key':'last_event_cam_name', 'value':event['cam_name']}
            ]
            device.updateStatesOnServer(key_value_list)  
            
        elif event['type'] == 'camera_offline' or event['type'] == 'camera_online':
            key_value_list = [
                {'key':'last_event_cam_id',   'value':event['cam_id']},
                {'key':'last_event_cam_name', 'value':event['cam_name']}
            ]
            device.updateStatesOnServer(key_value_list)  
            
            self.logger.debug(u"Camera event: camectID: {}, type: {}".format(device.id, event['type']))
            for triggerID, trigger in self.camera_triggers.iteritems():
                self.logger.threaddebug(u"Checking Camera trigger {}: camectID: {}".format(triggerID, trigger.pluginProps['camectID']))

                if not ((trigger.pluginProps["camectID"] == "-1") or (trigger.pluginProps["camectID"] == str(device.id))):
                    self.logger.threaddebug(u"Skipping Camera trigger {}, wrong Camect".format(triggerID))
                    continue
                    
                if not ((trigger.pluginProps["cameraID"] == "-1") or (trigger.pluginProps["cameraID"] == event['cam_id'])):
                    self.logger.threaddebug(u"Skipping Camera trigger {}, wrong camera".format(triggerID))
                    continue
                    
                if trigger.pluginProps["type"] == event['type']:
                    self.logger.debug(u"Executing Camera trigger {}".format(triggerID))
                    indigo.trigger.execute(trigger)


        elif event['type'] == 'mode':
            key_value_list = [
                {'key':'mode',              'value':event['desc']}
            ]
            device.updateStatesOnServer(key_value_list)  
            
            self.logger.debug(u"Mode event: camectID: {}, mode: {}".format(device.id, event['desc']))
            for triggerID, trigger in self.mode_triggers.iteritems():
                self.logger.threaddebug(u"Checking Mode trigger {}: camectID: {}".format(triggerID, trigger.pluginProps['camectID']))

                if (trigger.pluginProps["camectID"] == "-1") or (trigger.pluginProps["camectID"] == str(device.id)):
                    self.logger.debug(u"Executing Mode trigger {}".format(triggerID))
                    indigo.trigger.execute(trigger)
                
 
  
    ########################################
    # Trigger (Event) handling 
    ########################################

    def triggerStartProcessing(self, trigger):
        self.logger.debug("{}: Adding {} Trigger".format(trigger.name, trigger.pluginTypeId))
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
        self.logger.debug("{}: Removing {} Trigger".format(trigger.name, trigger.pluginTypeId))
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
    # Menu Methods
    ########################################


    ########################################
    # Plugin Actions object callbacks (pluginAction is an Indigo plugin action instance)
    ########################################

    def setModeCommand(self, pluginAction, dev):
        camect = int(pluginAction.props['camectID'])
        self.logger.debug(u"setModeCommand, new mode: {}".format(pluginAction.props['mode']))
        self.camects[camect].set_mode(pluginAction.props['mode'])


    def snapshotCameraCommand(self, pluginAction, dev):
        camectID = int(pluginAction.props['camectID'])
        camect = indigo.devices[camectID]
        camera = self.camect_cameras[camectID][pluginAction.props['cameraID']]

        snapshotPath = self.pluginPrefs.get("snapshotPath", "IndigoWebServer/public")
        snapshotName = pluginAction.props.get('snapshotName', None)
        if not snapshotName or (len(snapshotName) == 0):
            snapshotName = "snapshot-{}".format(camera['id'])

        start = time.time()
        self.logger.debug(u"{}: snapshotCameraCommand, camera ID: {}".format(camect.name, pluginAction.props['cameraID']))
        
        image = self.camects[camectID].snapshot_camera(camera['id'], camera['width'], camera['height'])
        self.logger.debug(u"{}: snapshotCameraCommand fetch completed @ {}".format(camect.name, (time.time() - start)))
        savepath = "{}/{}/{}.jpg".format(indigo.server.getInstallFolderPath(), snapshotPath, snapshotName)
        try:
            f = open(savepath, 'wb')
            f.write(image)
            f.close
        except Exception as err:
            self.logger.warning(u"Error writing image file: {}, err: {}".format(savepath, err))
        self.logger.debug(u"{}: snapshotCameraCommand write completed @ {} to {}".format(camect.name, (time.time() - start), savepath))
        

    def disableAlertsCommand(self, pluginAction, dev):
        camectID = int(pluginAction.props['camectID'])
        camect = indigo.devices[camectID]
        cameraID = pluginAction.props['cameraID']
        if cameraID == "-1":
            cameraID = []
        self.logger.debug(u"{}: disableAlertsCommand, camera: {}, reason: {}".format(camect.name, cameraID, pluginAction.props['reason']))
        self.camects[camectID].disable_alert([pluginAction.props['cameraID']], pluginAction.props['reason'])


    def enableAlertsCommand(self, pluginAction, dev):
        camectID = int(pluginAction.props['camectID'])
        camect = indigo.devices[camectID]
        cameraID = pluginAction.props['cameraID']
        if cameraID == "-1":
            cameraID = []
        self.logger.debug(u"{}: enableAlertsCommand, camera: {}, reason: {}".format(camect.name, cameraID, pluginAction.props['reason']))
        self.camects[camectID].enable_alert([pluginAction.props['cameraID']], pluginAction.props['reason'])


    ########################################
    # ConfigUI methods
    ########################################

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if not userCancelled:
            try:
                self.logLevel = int(valuesDict[u"logLevel"])
            except:
                self.logLevel = logging.INFO
            self.indigo_log_handler.setLevel(self.logLevel)
            self.logger.debug(u"logLevel = {}".format(self.logLevel))
 
    def validateEventConfigUi(self, valuesDict, typeId, eventId):
        self.logger.debug(u"validateEventConfigUi typeId = {}, eventId = {}, valuesDict = {}".format(typeId, eventId, valuesDict))
        return (True, valuesDict)
    
    def pickCamect(self, filter=None, valuesDict=None, typeId=0, targetId=0):
        self.logger.threaddebug(u"pickCamect typeId = {}, targetId = {}, valuesDict = {}".format(typeId, targetId, valuesDict))
        if "Any" in filter:
            retList = [("-1","- Any Camect -")]
        else:
            retList = []
        for camectID in self.camects:
            device = indigo.devices[int(camectID)]
            retList.append((device.id, device.name))
        retList.sort(key=lambda tup: tup[1])
        return retList

    def pickCamera(self, filter=None, valuesDict=None, typeId=0, targetId=0):
        self.logger.threaddebug(u"pickCamera typeId = {}, targetId = {}, valuesDict = {}".format(typeId, targetId, valuesDict))
        if "Any" in filter:
            retList = [("-1","- Any Camera -")]
        elif "All" in filter:
            retList = [("-1","- All Cameras -")]
        else:
            retList = []
        try:
            for cam in self.camect_cameras[int(valuesDict['camectID'])].values():
                retList.append((cam["id"], cam["name"]))
        except:
            pass
        retList.sort(key=lambda tup: tup[1])
        return retList

    def pickObject(self, filter=None, valuesDict=None, typeId=0, targetId=0):
        self.logger.threaddebug(u"pickObject typeId = {}, targetId = {}, valuesDict = {}".format(typeId, targetId, valuesDict))
        if "Any" in filter:
            retList = [("-1","- Any Object -")]
        elif "All" in filter:
            retList = [("-1","- All Objects -")]
        else:
            retList = []
        try:
            for objName in self.camect_info[int(valuesDict['camectID'])]['object_name']:
                retList.append((objName, objName))
        except:
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
        return (valuesDict, errorMsgDict)
      
