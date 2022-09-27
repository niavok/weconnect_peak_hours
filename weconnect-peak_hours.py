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
    parser.add_argument('command', choices={'scan', 'status', 'run'}, default='run',
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

def WeConnectInit():
    global weConnect
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

    vehicle = weConnect.vehicles[config.vin]
    if not vehicle:
        PrintAndLog("Fail to find vehicle with VIN "+ config.vin)

    PrintAndLog("General")
    PrintAndLog("    * Nickname: " + vehicle.nickname.value)
    PrintAndLog("    * Model: " + vehicle.model.value)
    PrintAndLog("    * VIN: " + vehicle.vin.value)

    PrintAndLog("Climatisation")
    PrintAndLog("    * Target temperature: "+ str(vehicle.domains["climatisation"]["climatisationSettings"].targetTemperature_C.value) + "°C")

    PrintAndLog("Charge")
    PrintAndLog("Plug connection state: " + vehicle.domains["charging"]["plugStatus"].plugConnectionState.value.value)
    PrintAndLog("Preferred charge mode: " + vehicle.domains["charging"]["chargeMode"].preferredChargeMode.value.value)

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

def PrepareChargeStart(start_datetime, limit_datetime):
    PrintAndLog("Next chart start is "+ start_datetime.str())
    WaitForDateTime(start_datetime)

    while limit_datetime > datetime.now():

        if not WeConnectInit():
            PrintAndLog("Fail to connect to start charge. Retry in 5 minutes")

        # TODO check if ignore !!!
        ignore ?


        if not StartCharge():
            PrintAndLog("Fail to start charge. Retry in 5 minutes")
        else:
            break

        time.sleep(5*60) # Wait between retry

def PrepareChargeStop(stop_datetime, limit_datetime):
    PrintAndLog("Next chart stop is "+ stop_datetime.str())
    WaitForDateTime(stop_datetime)



    while limit_datetime > datetime.now():

        if not WeConnectInit():
            PrintAndLog("Fail to connect to stop charge. Retry in 5 minutes")

        # TODO check if ignore !!!
        ignore ?


        if not StopCharge():
            PrintAndLog("Fail to stop charge. Retry in 5 minutes")
        else:
            break

        time.sleep(5*60) # Wait between retry

def ProcessNextTask():
    current_datetime = datetime.now()
    next_charge_start_datetime = GetNextChargeStart(current_datetime)
    next_charge_end_datetime = GetNextChargeEnd(current_datetime)
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