#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################

import logging
import indigo
import threading

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
        

    def shutdown(self):
        self.logger.info(u"Stopping Camect")


    def deviceStartComm(self, device):
        self.logger.info(u"{}: Starting Device".format(device.name))


    def deviceStopComm(self, device):
        self.logger.info(u"{}: Stopping Device".format(device.name))


        
  
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
    # This routine will validate the device configuration dialog when the user attempts to save the data
    ########################################

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        self.logger.debug(u"validateDeviceConfigUi, devId={}, typeId={}, valuesDict = {}".format(devId, typeId, valuesDict))
        errorMsgDict = indigo.Dict()
        
        return True        


    ################################################################################
    #
    # UI List methods
    #
    ################################################################################

