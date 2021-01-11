#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################

import logging
import indigo
import json

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
        self.triggers = {}

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

            self.camect_cameras[device.id] = self.camects[device.id].list_cameras()
            self.logger.debug(u"Known Cameras:")
            for cam in self.camect_cameras[device.id]:
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


    def processReceivedEvent(self, devID, event):
        device = indigo.devices[devID]
        self.logger.debug(u"{}: Event JSON: {}".format(device.name, event))
        device.updateStateOnServer(key='last_event', value=event)
        
        try:
            evt = json.loads(event)
        except Exception as err:
            self.logger.error("Invalid JSON '{}': {}".format(event, err))
             
        # Now do any triggers

        for trigger in self.triggers.values():
            if (trigger.pluginProps["camectID"] == "-1") or (trigger.pluginProps["camectID"] == str(device.id)):
                if trigger.pluginTypeId == "eventReceived":
                    indigo.trigger.execute(trigger)
                                        
                else:
                    self.logger.error("{}: Unknown Trigger Type {}".format(trigger.name, trigger.pluginTypeId))
    

  
    ########################################
    # Trigger (Event) handling 
    ########################################

    def triggerStartProcessing(self, trigger):
        self.logger.debug("{}: Adding Trigger".format(trigger.name))
        assert trigger.id not in self.triggers
        self.triggers[trigger.id] = trigger

    def triggerStopProcessing(self, trigger):
        self.logger.debug("{}: Removing Trigger".format(trigger.name))
        assert trigger.id in self.triggers
        del self.triggers[trigger.id]

  
    ########################################
    # Menu Methods
    ########################################



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
        self.logger.debug(u"pickCamect typeId = {}, targetId = {}, valuesDict = {}".format(typeId, targetId, valuesDict))
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
        self.logger.debug(u"pickCamera typeId = {}, targetId = {}, valuesDict = {}".format(typeId, targetId, valuesDict))
        if "Any" in filter:
            retList = [("-1","- Any Camera -")]
        else:
            retList = []
        try:
            for cam in self.camect_cameras[int(valuesDict['camectID'])]:
                retList.append((cam["id"], cam["name"]))
        except:
            pass
        retList.sort(key=lambda tup: tup[1])
        return retList

    def pickObject(self, filter=None, valuesDict=None, typeId=0, targetId=0):
        self.logger.debug(u"pickObject typeId = {}, targetId = {}, valuesDict = {}".format(typeId, targetId, valuesDict))
        if "Any" in filter:
            retList = [("-1","- Any Object -")]
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

