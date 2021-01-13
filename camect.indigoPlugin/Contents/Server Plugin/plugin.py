#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################

import logging
import indigo
import json

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

        self.logger.info(u"{}: {}".format(device.name, event['desc']))

        if event['type'] == 'alert':
            key_value_list = [
                {'key':'last_event',          'value':event_json},
                {'key':'last_event_type',     'value':event['type']},
                {'key':'last_event_desc',     'value':event['desc']},
                {'key':'last_event_url',      'value':event['url']},
                {'key':'last_event_cam_id',   'value':event['cam_id']},
                {'key':'last_event_cam_name', 'value':event['cam_name']},
                {'key':'last_event_detected', 'value':' '.join(event['detected_obj'])}
            ]
            device.updateStatesOnServer(key_value_list)  

            self.logger.debug(u"Alert event: camectID: {}, cam_id: {}, detected_obj = {}".format(device.id, event['cam_id'], event['detected_obj']))
            for trigger in self.alert_triggers.values():
                self.logger.debug(u"Alert trigger: camectID: {}, cam_id: {}, detected_obj = {}".format(trigger.pluginProps['camectID'], trigger.pluginProps['cam_id'], trigger.pluginProps['object']))
                
                if ((trigger.pluginProps["camectID"] == "-1") or (trigger.pluginProps["camectID"] == str(device.id)))     and \
                   ((trigger.pluginProps["cameraID"] == "-1") or (trigger.pluginProps["cameraID"] == event['cam_id']))    and \
                   ((trigger.pluginProps["cameraID"] == "-1") or (trigger.pluginProps["object"]   in event['detected_obj'])):
                    indigo.trigger.execute(trigger)
                    
        elif event['type'] == 'mode':
            key_value_list = [
                {'key':'last_event',        'value':event_json},
                {'key':'last_event_type',   'value':event['type']},
                {'key':'mode',              'value':event['desc']}
            ]
            device.updateStatesOnServer(key_value_list)  
            
            for trigger in self.mode_triggers.values():
                self.logger.debug(u"Mode trigger: {}".format(trigger.pluginProps))
                self.logger.debug(u"Alert camectID: {}".format(device.id))

                if (trigger.pluginProps["camectID"] == "-1") or (trigger.pluginProps["camectID"] == str(device.id)):
                    indigo.trigger.execute(trigger)

 
  
    ########################################
    # Trigger (Event) handling 
    ########################################

    def triggerStartProcessing(self, trigger):
        self.logger.debug("{}: Adding {} Trigger".format(trigger.name, trigger.pluginTypeId))
        if trigger.pluginTypeId == "alertEvent":
            assert trigger.id not in self.alert_triggers
            self.alert_triggers[trigger.id] = trigger
        if trigger.pluginTypeId == "modeEvent":
            assert trigger.id not in self.mode_triggers
            self.mode_triggers[trigger.id] = trigger

    def triggerStopProcessing(self, trigger):
        self.logger.debug("{}: Removing {} Trigger".format(trigger.name, trigger.pluginTypeId))
        if trigger.pluginTypeId == "alertEvent":
            assert trigger.id in self.alert_triggers
            del self.alert_triggers[trigger.id]
        if trigger.pluginTypeId == "modeEvent":
            assert trigger.id in self.mode_triggers
            del self.mode_triggers[trigger.id]

  
    ########################################
    # Menu Methods
    ########################################


    ########################################
    # Plugin Actions object callbacks (pluginAction is an Indigo plugin action instance)
    ########################################

    def disableAlertsCommand(self, pluginAction, dev):
        self.logger.debug(u"{}: disableAlertsCommand, pluginAction: {}".format(dev.name, pluginAction))


    def enableAlertsCommand(self, pluginAction, dev):
        self.logger.debug(u"{}: enableAlertsCommand, pluginAction: {}".format(dev.name, pluginAction))


    def setModeCommand(self, pluginAction, dev):
        camect = int(pluginAction.props['camectID'])
        self.logger.debug(u"setModeCommand, new mode: {}".format(pluginAction.props['mode']))
        self.camects[camect].set_mode(pluginAction.props['mode'])


    def snapshotCameraCommand(self, pluginAction, dev):
        camect = int(pluginAction.props['camectID'])
        camera = self.camect_cameras[camect][pluginAction.props['cameraID']]
        image = self.camects[camect].snapshot_camera(camera['id'], camera['width'], camera['height'])
        path = "{}/IndigoWebServer/snapshot-{}.jpg".format(indigo.server.getInstallFolderPath(), camera['id'])
        f = open(path, 'wb')
        f.write(image)
        f.close

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


    def getActionConfigUiValues(self, pluginProps, typeId, devId):
        self.logger.debug(u"getActionConfigUiValues, typeId = {}, devId = {}, pluginProps = {}".format(typeId, devId, pluginProps))
        valuesDict = pluginProps
        errorMsgDict = indigo.Dict()
        if typeId == "yourActionId":  # where yourActionId is the ID for the action used in Actions.xml
            valuesDict["testLifxLamp"] = someDefaultValue  # probably based on devId?
        return (valuesDict, errorMsgDict)
      
    def getMenuActionConfigUiValues(self, menuId):
        self.logger.debug(u"getMenuActionConfigUiValues, menuId = {}".format(menuId))
        valuesDict = indigo.Dict()
        errorMsgDict = indigo.Dict()
        if menuId == "yourMenuItemId":
            valuesDict["someFieldId"] = someDefaultValue
        return (valuesDict, errorMsgDict)
      
    def getDeviceConfigUiValues(self, pluginProps, typeId, devId):
        self.logger.debug(u"getDeviceConfigUiValues, typeId = {}, devId = {}, pluginProps = {}".format(typeId, devId, pluginProps))
        valuesDict = indigo.Dict(pluginProps)
        errorsDict = indigo.Dict()
        if len(valuesDict) == 0:
            if typeId == "foo":
                valuesDict["bar"] = "123"
        return (valuesDict, errorsDict)

    def getPrefsConfigUiValues(self):
        self.logger.debug(u'getPrefsConfigUiValues')
        prefsConfigUiValues = self.pluginPrefs
        for key in prefsConfigUiValues:
            if prefsConfigUiValues[key] == '':
                prefsConfigUiValues[key] = u'None'
        return prefsConfigUiValues
      

