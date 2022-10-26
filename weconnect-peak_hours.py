#!/usr/bin/python3

import argparse
import configparser
import json
import sys
import os
import requests
from weconnect import weconnect
from weconnect import errors
from weconnect.elements.control_operation import ControlOperation
from weconnect.elements.charging_status import ChargingStatus
from weconnect.elements.plug_status import PlugStatus
from datetime import datetime, timedelta
from datetime import time as dtime
import time


class Config:
    loaded : bool = False
    command : str = ""
    file_path : str = ""
    log_file_path : str = "weconnect_peak_hours.log"
    login : str = ""
    password : str = ""
    vin : str = ""
    charging_ranges = []
    ignore_temperatures = [] 
    ignore_min_power = 0

config = Config()


def Log(message : str):
    PrintAndLog(message, False)

def PrintAndLog(message : str, doPrint = True):
    message_str = str(message)
    line = str(datetime.now()) + " - " + message_str
    if(doPrint):
        print(line)
        sys.stdout.flush()
    log_file = open(os.path.dirname(os.path.realpath(__file__)) + "/" + config.log_file_path, 'a')
    log_file.write(line)
    log_file.write("\n")
    log_file.close()

def ParseArguments():
    parser = argparse.ArgumentParser(description='We connect charge control to avoid peak hours.')
    parser.add_argument('command', choices={'scan', 'status', 'run', 'start', 'stop'}, default='run',
                    help='scan to list the cars, status to display the current state, run to execute the car.')
    parser.add_argument('--config', '-c', default='config.cfg')

    args = parser.parse_args()
    config.command = args.command
    config.file_path = args.config


def LoadConfig():

    config_file = configparser.ConfigParser()
    config_file.read(config.file_path)

    if len(config_file.sections()) == 0:
        PrintAndLog("Fail to open or read config file '"+config.file_path+"'")
        return False

    if 'Access' not in config_file:
        PrintAndLog("Fail to find 'Access section in config file")
        return False

    config.login = config_file['Access']['Login']
    config.password = config_file['Access']['Password']

    config.vin = config_file['Device']['Vin']
    config.charging_ranges = json.loads(config_file['Device']['ChargingRanges'])
    config.ignore_temperatures = json.loads(config_file['Device']['IgnoreTemperatures'])
    config.ignore_min_power = float(config_file['Device']['IgnoreMinPower'])

    config.loaded = True
    return True

weConnect = {}
vehicle = {}

def WeConnectInit():
    global weConnect
    global vehicle
    try:
        weConnect = weconnect.WeConnect(username=config.login, password=config.password, updateAfterLogin=False, loginOnInit=False)
        weConnect.login()
        weConnect.update()
    except errors.AuthentificationError as err:
        PrintAndLog("Login to WeConnect failed")
        PrintAndLog('error' + str(err))
        return False
    except requests.exceptions.ConnectionError as err:
        PrintAndLog("Connection to WeConnect failed, check internet connection")
        PrintAndLog('error' + str(err))
        return False
    if config.vin in weConnect.vehicles:
        vehicle = weConnect.vehicles[config.vin]
    else:
        vehicle = None

    return True

def Scan():
    if not WeConnectInit():
        return False

    for vin, vehicle in weConnect.vehicles.items():
        PrintAndLog(str(vin))
        PrintAndLog("    * Nickname: " + vehicle.nickname.value)
        PrintAndLog("    * Model: " + vehicle.model.value)
        PrintAndLog("    * VIN: " + vehicle.vin.value)

    return True

def Status():
    if not WeConnectInit():
        return False

    if not vehicle:
        PrintAndLog("Fail to find vehicle with VIN "+ config.vin)
        return False

    PrintAndLog("General")
    PrintAndLog("    * Nickname: " + vehicle.nickname.value)
    PrintAndLog("    * Model: " + vehicle.model.value)
    PrintAndLog("    * VIN: " + vehicle.vin.value)

    PrintAndLog("Climatisation")
    PrintAndLog("    * Target temperature: "+ str(vehicle.domains["climatisation"]["climatisationSettings"].targetTemperature_C.value) + "°C")

    PrintAndLog("Charge")
    PrintAndLog("Plug connection state: " + vehicle.domains["charging"]["plugStatus"].plugConnectionState.value.value)
    PrintAndLog("Preferred charge mode: " + vehicle.domains["charging"]["chargeMode"].preferredChargeMode.value.value)
    PrintAndLog("Current SoC: " + str(vehicle.domains["charging"]["batteryStatus"].currentSOC_pct.value) + " %")
    PrintAndLog("Target SoC: " + str(vehicle.domains["charging"]["chargingSettings"].targetSOC_pct.value) + " %")

    PrintAndLog("Charging state: " + vehicle.domains["charging"]["chargingStatus"].chargingState.value.value)
    PrintAndLog("Charge mode: " + vehicle.domains["charging"]["chargingStatus"].chargeMode.value.value)
    PrintAndLog("Charge power: " + str(vehicle.domains["charging"]["chargingStatus"].chargePower_kW.value) + " kW")
    PrintAndLog("charge type: " + vehicle.domains["charging"]["chargingStatus"].chargeType.value.value)

    return True

def WaitForDateTime(target_datetime):
    current_datetime = datetime.now()
    while current_datetime < target_datetime:
        missing_time = target_datetime - current_datetime
        PrintAndLog("Wait for "+str(missing_time) + " to " + str(target_datetime))
        time.sleep(missing_time.total_seconds())
        current_datetime = datetime.now()

def IgnoreStartCharge():
    if not vehicle:
        PrintAndLog("Fail to find vehicle with VIN "+ config.vin)

    target_temperature = vehicle.domains["climatisation"]["climatisationSettings"].targetTemperature_C.value
    if target_temperature in config.ignore_temperatures:
        PrintAndLog("Skip start charge: target temperature in ignore list,  ("+ str(target_temperature) + "°C)")
        return True

    if vehicle.domains["charging"]["plugStatus"].plugConnectionState.value is not PlugStatus.PlugConnectionState.CONNECTED:
        PrintAndLog("Skip start charge: car is not ready for charging")
        return True

    if vehicle.domains["charging"]["chargingStatus"].chargingState.value is not ChargingStatus.ChargingState.READY_FOR_CHARGING:
        PrintAndLog("Skip start charge: car is not ready for charging")
        return True

    if vehicle.domains["charging"]["batteryStatus"].currentSOC_pct.value >=  vehicle.domains["charging"]["chargingSettings"].targetSOC_pct.value:
        PrintAndLog("Skip start charge: target SOC is reach")
        return True

    return False


def IgnoreStopCharge():
    if not vehicle:
        PrintAndLog("Fail to find vehicle with VIN "+ config.vin)

    target_temperature = vehicle.domains["climatisation"]["climatisationSettings"].targetTemperature_C.value
    if target_temperature in config.ignore_temperatures:
        PrintAndLog("Skip stop charge: target temperature in ignore list,  ("+ str(target_temperature) + "°C)")
        return True

    if vehicle.domains["charging"]["plugStatus"].plugConnectionState.value is not PlugStatus.PlugConnectionState.CONNECTED:
        PrintAndLog("Skip stop charge: car is not connected")
        return True

    if vehicle.domains["charging"]["chargingStatus"].chargingState.value is not ChargingStatus.ChargingState.CHARGING:
        PrintAndLog("Skip stop charge: car is not charging")
        return True

    if vehicle.domains["charging"]["chargingStatus"].chargeType.value is not ChargingStatus.ChargeType.AC:
        PrintAndLog("Skip stop charge: not charging in AC ("+ vehicle.domains["charging"]["chargingStatus"].chargeType.value.valule+")")
        return True

    if vehicle.domains["charging"]["chargingStatus"].chargePower_kW.value > config.ignore_min_power:
        PrintAndLog("Skip stop charge: charging faster than ignore limit ("+ str(vehicle.domains["charging"]["chargingStatus"].chargePower_kW.value)+" kW)")
        return True

    return False

def StartCharge():
    try:
        global vehicle
        PrintAndLog("Start charge. Wait 30s before check charge status")
        vehicle.controls.chargingControl.value = ControlOperation.START
        time.sleep(30)
        weConnect.update()
        vehicle = weConnect.vehicles[config.vin]
        return vehicle.domains["charging"]["chargingStatus"].chargingState.value is ChargingStatus.ChargingState.CHARGING
    except Exception as err:
        PrintAndLog("Control command failed")
        PrintAndLog('error' + str(err))
        return False

def StopCharge():
    try:
        global vehicle
        PrintAndLog("Stop charge. Wait 30s before check charge status")
        vehicle.controls.chargingControl.value = ControlOperation.STOP
        time.sleep(30)
        weConnect.update()
        vehicle = weConnect.vehicles[config.vin]
        return vehicle.domains["charging"]["chargingStatus"].chargingState.value is not ChargingStatus.ChargingState.CHARGING
    except Exception as err:
        PrintAndLog("Control command failed")
        PrintAndLog('error' + str(err))
        return False

def PrepareChargeStart(start_datetime, limit_datetime):
    PrintAndLog("Next chart start is "+ str(start_datetime))
    WaitForDateTime(start_datetime)

    Status()
    while limit_datetime > datetime.now():

        if not WeConnectInit():
            PrintAndLog("Fail to connect to start charge. Retry in 5 minutes")

        if IgnoreStartCharge():
            break

        if not StartCharge():
            PrintAndLog("Fail to start charge. Retry in 5 minutes")
        else:
            PrintAndLog("Start charge success")
            Status()
            break

        time.sleep(5*60) # Wait between retry


def PrepareChargeStop(stop_datetime, limit_datetime):
    PrintAndLog("Next chart stop is "+ str(stop_datetime))
    WaitForDateTime(stop_datetime)

    Status()
    while limit_datetime > datetime.now():

        if not WeConnectInit():
            PrintAndLog("Fail to connect to stop charge. Retry in 5 minutes")

        if IgnoreStopCharge():
            break;

        if not StopCharge():
            PrintAndLog("Fail to stop charge. Retry in 5 minutes")
        else:
            PrintAndLog("Stop charge success")
            Status()
            break

        time.sleep(5*60) # Wait between retry

def GetNextChargeStartStop(current_datetime, start_or_stop):
    current_time = current_datetime.time()
    next_charge_datetime = None
    for charge_range in config.charging_ranges:
        start_time = dtime.fromisoformat(charge_range[start_or_stop])
        if start_time >= current_time:
            # charge start/stop the same day
            charge_datetime = datetime.combine(current_datetime.date(), start_time)
        else:
            charge_datetime = datetime.combine(current_datetime.date() + timedelta(days=1), start_time)

        if not next_charge_datetime or charge_datetime < next_charge_datetime:
            next_charge_datetime = charge_datetime
    return next_charge_datetime

def ProcessNextTask():
    current_datetime = datetime.now()
    next_charge_start_datetime = GetNextChargeStartStop(current_datetime, 0)
    next_charge_end_datetime = GetNextChargeStartStop(current_datetime, 1)
    if(next_charge_start_datetime < next_charge_end_datetime):
        PrepareChargeStart(next_charge_start_datetime , next_charge_end_datetime)
    else:
        PrepareChargeStop(next_charge_end_datetime, next_charge_start_datetime)

def Run():
    while not Status(): # To check if connection works
        PrintAndLog("Fail to get run initial status. Retry in 5 minutes")
        time.sleep(5*60) # Wait between retry

    while True:
        ProcessNextTask()

ParseArguments()
LoadConfig()

PrintAndLog("==============")
PrintAndLog("Run command: "+ config.command)
PrintAndLog("--------------")

if config.loaded:
    if config.command == "scan":
        if not Scan():
            PrintAndLog("Fail to scan")
    elif config.command == "run":
            Run()
    elif config.command == "start":
            PrepareChargeStart(datetime.now(), datetime.now() + timedelta(seconds=10))
    elif config.command == "stop":
            PrepareChargeStop(datetime.now(), datetime.now() + timedelta(seconds=10))
    elif config.command == "status":
        if not Status():
            PrintAndLog("Fail to get status")

PrintAndLog("--------------")
PrintAndLog("Command "+ config.command + " done")
PrintAndLog("==============")


"""

weConnect.login()

print('#  update')
weConnect.update()

print('#  print results')
for vin, vehicle in weConnect.vehicles.items():
    del vin
    print(vehicle)
    #vehicle.controls.chargingControl.value = ControlOperation.START
    #vehicle.controls.chargingControl.value = ControlOperation.STOP
    print(vehicle.domains["climatisation"]["climatisationSettings"])
    print("targetTemperature_C: "+ str(vehicle.domains["climatisation"]["climatisationSettings"].targetTemperature_C.value))


    # Stop only if AC
    print("plugConnectionState: " + str(vehicle.domains["charging"]["plugStatus"].plugConnectionState.value))
    print("preferredChargeMode: " + str(vehicle.domains["charging"]["chargeMode"].preferredChargeMode.value))
    print("chargingState: " + str(vehicle.domains["charging"]["chargingStatus"].chargingState.value))
    print("chargeMode: " + str(vehicle.domains["charging"]["chargingStatus"].chargeMode.value))
    print("chargePower_kW: " + str(vehicle.domains["charging"]["chargingStatus"].chargePower_kW.value))
    print("chargeType: " + str(vehicle.domains["charging"]["chargingStatus"].chargeType.value))
    

print('#  done')
"""