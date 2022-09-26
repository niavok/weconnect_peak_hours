The script require python3 and weconnect pip module


'''
pip3 install weconnect
'''


Fill config.cfg from template with a dummy VIN.
To find the VIN, use the scan command.

'''
python weconnect-peak_hours.py scan
'''

Complete the config script.

Check the current status with the status command.
'''
python weconnect-peak_hours.py status
'''

Run the charge programing with the run command.

'''
python weconnect-peak_hours.py run
'''