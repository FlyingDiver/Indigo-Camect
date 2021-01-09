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
        self.triggers = {}
        

    def shutdown(self):
        self.logger.info(u"Stopping Camect")


    def deviceStartComm(self, device):

        if device.deviceTypeId == "camect":
            self.logger.info(u"{}: Starting Device".format(device.name))
            self.camects[device.id] = Camect(device)
            device.updateStateOnServer(key="status", value="None")
            device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
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
 

    ########################################
    # Plugin Actions object callbacks
    ########################################

    def pickCamect(self, filter=None, valuesDict=None, typeId=0, targetId=0):
        if "Any" in filter:
            retList = [("-1","- Any Camect -")]
        else:
            retList = []
        for camectID in self.camects:
            device = indigo.devices[int(camectID)]
            retList.append((device.id, device.name))
        retList.sort(key=lambda tup: tup[1])
        return retList

    ################################################################################
    # For initial testing only
    ################################################################################
                  

    def sendTextAction(self, pluginAction):
        self.camects[pluginAction.deviceId].sendText(pluginAction.props["text"])
