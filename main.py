import machine
import secrets
import network
import asyncio
import socket
import ubinascii
import urequests as requests
import ujson as json
import utime
from machine import Pin, ADC
from picozero import pico_temp_sensor, pico_led



autoOnHour = 09				# Start time for scheduled watering
autoOnMinute = 00			
durationMinute = 10			# Duration for auto and manual watering times

autoOn = 1					# Preset the auto mode to on
valveState = 0				# Preset the water valve on/off variable to off

rtc = machine.RTC()					# Real time clock
onboard_led = Pin("LED", Pin.OUT)	# Onboard led
onboard_led.value(0)				# Preset lef to off							
temperature_sensor = ADC(4)         # GPIO 4 - connected to the temperature sensor

# Define motor pins (using 2nd motor outputs) OUT3 and OUT4 from motor controller
waterV1=Pin(3,Pin.OUT)  	# GP3/pin5
waterV2=Pin(4,Pin.OUT) 		# GP4/pin6

# Define the manualSwitch pin and settings
manualSwitch = Pin(28, Pin.IN, Pin.PULL_UP) 	# GP28/34
manualSwitchState=manualSwitch.value()			# Preset the state of the manualSwitch (1 not switched/0 switched)
debounceTime=0									# Preset manualSwitch debounce time 



# Open water valve
def water_valveOpen():
    print('DEF water_valveOpen')
    global valveState
    valveState = 1
    onboard_led.value(1)
    waterV1.low()
    waterV2.high()
    utime.sleep(0.25)
    waterV1.low()
    waterV2.low()
    print('  Water value now open \n')
# Close water valve
def water_valveClose():
    print('DEF water_valveClose')
    global valveState
    valveState = 0
    onboard_led.value(0)
    waterV1.high()
    waterV2.low()
    utime.sleep(0.25)
    waterV1.low()
    waterV2.low()
    print('  Water value now closed \n')
# ManualSwitch interrupt handler
def manualSwitch_INT(pin):
    print('DEF manualSwitch_INT')
    global autoOn, manualSwitchState, debounceTime
    if (utime.ticks_ms()-debounceTime) > 500:
        autoOn = 0						# Auto mode off
        manualSwitchState = 0			# Switched = true
        debounceTime=utime.ticks_ms()
        onboard_led.toggle()
        utime.sleep(0.1)
        onboard_led.toggle()
        utime.sleep(0.1)

# Interrupt request handling for manualSwitch
manualSwitch.irq(trigger=Pin.IRQ_FALLING, handler=manualSwitch_INT) 

# Setup start and end times for auto watering
def autoOn_times():
    print('DEF autoOn_times')
    global autoOnTime, autoOffTime
    current_time = utime.localtime()			# Get current time
    # Modify time to reflect user settings 
    autoOnTime = list(current_time)
    autoOnTime[3] = autoOnHour  				# Set hour to autoOnHour
    autoOnTime[4] = autoOnMinute   				# Set minutes to autoOnMinute
    autoOnTime[5] = 0   						# Reset seconds to 0
    autoOnTime[6] = 0   						# Reset microseconds to 0   
    autoOffTime = utime.mktime(autoOnTime) + (durationMinute * 60)		# Get autoOnTime as seconds and add duration
    autoOffTime = utime.localtime(autoOffTime)							# Convert back to tuple
    print("  Auto on time: {:02d}:{:02d}:{:02d}".format(autoOnTime[3], autoOnTime[4], autoOnTime[5]))
    print("  Auto off time: {:02d}:{:02d}:{:02d}".format(autoOffTime[3], autoOffTime[4], autoOffTime[5]),"\n")
# Setup manualEndTime variable and times
def manual_endTime():
    print('DEF manual_endTime')
    global manualSwitchState, manualEndTime
    manualSwitchState = 1				# Reset to not switched
    manualEndTime = utime.mktime(utime.localtime()) + (durationMinute * 60) 	# Get current time as seconds, add duration
    manualEndTime = utime.localtime(manualEndTime)								# Convert back to tuple
    print("  Manual end time: {:02d}:{:02d}:{:02d}".format(manualEndTime[3], manualEndTime[4], manualEndTime[5]),"\n")



def wlan_connect():
    print('DEF wlan_connect')
    global ip
    # Enable station interface mode
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    # Turn off wifi power saving mode
    wlan.config(pm = 0xa11140)
    # Connect to wifi
    wlan.connect(secrets.SSID,secrets.PASSWORD)
    # Wait 10 tries for connect or fail (1 second interval)
    max_wait = 10
    while max_wait > 0:
        if wlan.status() < 0 or wlan.status() >= 3:
            break
        max_wait -= 1
        print('waiting for connection...')
        utime.sleep(1)
    # Show connection error if not status = 3 (3 = connected OK)
    if wlan.status() != 3:
        raise RuntimeError('  network connection failed - status: ',wlan.status())  
    else:
        global ip
        print('  network is connected')
        status = wlan.ifconfig()
        print('  ip = ' + status[0])
        mac = ubinascii.hexlify(network.WLAN().config('mac'),':').decode()
        print('  MAC: ', mac)
        print('  channel: ', wlan.config('channel'))
        print('  SSID: ', wlan.config('essid'))
        print('  txpower: ', wlan.config('txpower'))
        print()
        ip = status[0]
        get_world_time()	# Setup Pico RTC with correct time
        return True   

def get_world_time():
    print('DEF get_world_time')
    global rtc, manualEndTime
    received = None
    URL = "http://worldtimeapi.org/api/timezone/Pacific/Auckland"    
    # Note world time can suggest time based on the IP address
    # URL = "http://worldtimeapi.org/api/ip"   
    retries = 3  # Number of retries
    for _ in range(retries):
        try:
            received = requests.get(URL)
            break
        except OSError as e:
            print('  error: ', e)
            utime.sleep(1)  # Wait for a short duration before retrying    
    if received is None:
        print("Failed to fetch world time after multiple retries.")
        return   
    time_dic = json.loads(received.content)
    
    # Get some useful info from the dowloaded json put into time_dic        
    current_time = time_dic['datetime']
    the_date,the_time = current_time.split('T')
    year, month, mday = [int(x) for x in the_date.split('-')]
    the_time = the_time.split('.')[0]
    hours, minutes, seconds = [int(x) for x in the_time.split(':')]
    year_day = time_dic['day_of_year']
    week_day = time_dic['day_of_week']
    is_dst = time_dic['dst']
    now = (year, month, mday, week_day, hours, minutes, seconds, 0) 
    # Format for rtc.datetime() is year, month, mday, weekday, hours, minutes, seconds, subseconds (weekday is 0-6 for Mon-Sun)
    # Format for time.localtime() is year, month, mday, hour, minute, second, weekday, yearday (weekday is 0-6 for Mon-Sun)
    
    print('  Get time from worldtimeapi.org: ',now)
    print('  Setting Pico rtc.datetime')
    rtc.datetime(now)
    print('  RTC time: ',rtc.datetime())
    print('  Localtime: ',utime.localtime(),'\n')
    received.close()
    # Setup default auto watering schedule
    autoOn_times()
    manualEndTime = ""



# HTML + CSS for webpage
# To auto refresh - <meta http-equiv="refresh" content="5">
html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Raspberry Pi Pico Web Server</title>
  <style>
    html {
      font-family: Arial;
      display: inline-block;
      margin: 0px auto;
      text-align: center;
    }
    h1 {
      font-family: Arial;
      color: #2551cc;
    }
    .button1 {
      border: none;
      color: white;
      padding: 10px 20px;
      text-align: center;
      text-decoration: none;
      display: inline-block;
      font-size: 16px;
      margin: 4px 2px;
      cursor: pointer;
      border-radius: 10px;
      width: 120px;
    }
    .button-green {
      background-color: #339966;
    }
    .button-red {
      background-color: #993300;
    }
    .button-grey {
      background-color: #808080;
    }
    .button-blue {
      background-color: #3366CC; 
    }
    .input-field {
      margin: 10px;
    }
    .input-container {
      margin: 10px;
    }
    .input-container label {
      display: block;
      margin-bottom: 5px;
    }
    .input-container input {
      width: 60px;
      padding: 5px;
      border-radius: 5px;
      border: 1px solid #ccc;
    }
  </style>
</head>
<body>
  <h1>Raspberry Pi Pico Web Server</h1>
  <p>%s</p>
  <p>
    <a href="/water/on"><button class="button1 button-green">Water On</button></a>
  </p>
  <p>
    <a href="/water/off"><button class="button1 button-red">Water Off</button></a>
  </p>
  <p>Auto on time: %02d:%02d<br>
  Auto off time: %02d:%02d<br>
  Duration (min): %02d<br><br>
  
  Manual end time: %s<br><br>
  Pico temperature: %s°C</p>
  
  <div class="input-container">
    <label for="autoHour">Auto On Hour:</label>
    <input type="number" id="autoHour" name="autoHour">
  </div>
  <div class="input-container">
    <label for="autoMinute">Auto On Minute:</label>
    <input type="number" id="autoMinute" name="autoMinute">
  </div>
  <div class="input-container">
    <label for="duration">Duration (min):</label>
    <input type="number" id="duration" name="duration">
  </div>
  <div class="input-container">
    <button id="updateButton" class="button1 button-blue">Update</button>
  </div>
  <p>
    <a href="" id="refreshButton"><button class="button1 button-grey">Refresh</button></a>
  </p>
  <script>
    document.getElementById("refreshButton").onclick = function() {
      window.location.href = "http://" + ip // "http://192.168.1.76"
    };
    document.getElementById("updateButton").onclick = function() {
        var autoHour = document.getElementById("autoHour").value;
        var autoMinute = document.getElementById("autoMinute").value;
        var duration = document.getElementById("duration").value;
        
        // Check if inputs are not empty
        if (autoHour === "" || autoMinute === "" || duration === "") {
            alert("Please fill in all the fields");
            return;
        }

        // Check if inputs are valid integers
        if (!Number.isInteger(parseInt(autoHour)) || !Number.isInteger(parseInt(autoMinute)) || !Number.isInteger(parseInt(duration))) {
            alert("Please enter valid integer values");
            return;
        }

        // Check if inputs are non-negative
        if (parseInt(autoHour) < 0 || parseInt(autoMinute) < 0 || parseInt(duration) < 0) {
            alert("Please enter non-negative values");
            return;
        }

        // Send the request if inputs are valid
        var xhr = new XMLHttpRequest();
        xhr.open("GET", "/update?autoHour=" + autoHour + "&autoMinute=" + autoMinute + "&duration=" + duration, true);
        xhr.send();
        window.location.reload();
    }
  </script>
</body>
</html>
"""



# Asynchronous function to handle client's requests
async def handle_client(reader, writer):
    print('\nASYNC DEF handle_client')    
    global autoOn, manualSwitchState, valveState, state_message, durationMinute, autoOnTime, autoOffTime, displayManualOff, temperature_celsius
    # Read client request, set variables as required
    request_line = await reader.readline()  		# Read the HTTP request line
    #print("  Request:", request_line)  				# Print the received request
    # Skip HTTP request headers
    while await reader.readline() != b"\r\n":
        pass   
    request = str(request_line)        				# Convert request to string
    request_url = request.split()[1]				# Extracted request URL
    print("  Request_url: ",request_url)

    # Handle different request URLs
    if request_url.startswith('/favicon.ico'):
        print('  Exit ASYNC DEF handle_client')		# Exit if function has run a second time	
        return	   
    elif request_url.startswith('/water/on'):
        if valveState == 1:							# Valve already on - exit function
            print('  Water already on')
            return						
        autoOn = 0									# Auto mode is off
        manualSwitchState = 0						# Switched = true    
    elif request_url.startswith('/water/off'):
        if valveState == 0:							# Valve already off - exit function
            print('  Water already off')
            return					
        autoOn = 0									# Auto mode is off
        manualSwitchState = 0						# Switched = true        
    elif request_url.startswith('/update'): 		# Client request to update scheduled times
        # Parse the query parameters
        query_params = request_url.split('?')[1]
        params_dict = dict(param.split('=') for param in query_params.split('&'))
        updateAutoHour = int(params_dict.get('autoHour', autoOnHour))
        updateAutoMinute = int(params_dict.get('autoMinute', autoOnMinute))
        updateDuration = int(params_dict.get('duration', durationMinute))
        # Update the variables with the new values
        autoOnTime[3] = updateAutoHour
        autoOnTime[4] = updateAutoMinute
        durationMinute = updateDuration
        autoOffTime = utime.mktime(autoOnTime) + (durationMinute * 60)		# Get autoOnTime as seconds and add duration
        autoOffTime = utime.localtime(autoOffTime)							# Convert back to tuple
        print("  Updated Auto on time: {:02d}:{:02d}:{:02d}".format(autoOnTime[3], autoOnTime[4], autoOnTime[5]))
        print("  Updated Auto off time: {:02d}:{:02d}:{:02d}".format(autoOffTime[3], autoOffTime[4], autoOffTime[5]),"\n")
 
    # Update sytem as required and return values
    await water_status()   

    # Configure manual off time depending on setting
    if manualEndTime == "":
        displayManualOff = "(Auto mode is on)"       
    else:   
        displayManualOff = "{:02d}:{:02d}:{:02d}".format(manualEndTime[3], manualEndTime[4], manualEndTime[5])    
    
    temperature_celsius = await read_temperature()  # Read temperature in Celsius
    
    # Generate HTML response with current state and temperature, send to client
    response = html % (state_message, autoOnTime[3], autoOnTime[4], autoOffTime[3], autoOffTime[4],durationMinute, displayManualOff, "{:.2f}".format(temperature_celsius))

    writer.write('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')  # Write HTTP response header
    writer.write(response)  											# Write HTML response

    await writer.drain()     											# Drain the writer buffer
    await writer.wait_closed()  										# Wait until writer is closed
    print("  Response sent. Client disconnected")  						# Print message when client is disconnected

async def read_temperature():
    print('ASYNC DEF read_temperature')
    temperature_reading = temperature_sensor.read_u16() * 3.3 / (65535) # Convert ADC reading to voltage
    temperature_celsius = 27 - (temperature_reading - 0.706) / 0.001721 # Convert voltage to temperature
    return temperature_celsius  										# Return temperature in Celsius

# Main schedule loop
async def water_status():
    print('\nASYNC DEF water_status')
    global autoOn, valveState, manualSwitchState, manualEndTime, state_message
    
    onboard_led.toggle()
    utime.sleep(0.5)
    onboard_led.toggle()
    
    current_time = utime.localtime()  
    print("  Current time: {:02d}:{:02d}:{:02d}".format(current_time[3], current_time[4], current_time[5]))
    print("  Auto on time: {:02d}:{:02d}:{:02d}".format(autoOnTime[3], autoOnTime[4], autoOnTime[5]))
    print("  Auto off time: {:02d}:{:02d}:{:02d}\n".format(autoOffTime[3], autoOffTime[4], autoOffTime[5]))

    if current_time[2] != autoOnTime[2]:	# Update scheduled times each day[2]
        print("  Updating scheduled times (new day)")
        autoOn_times()
    
    if autoOn == 1:							# Auto mode on
        if current_time[3] >= autoOnTime[3] and current_time[4] >= autoOnTime[4] and current_time[3] <= autoOffTime[3] and current_time[4] < autoOffTime[4]:    # Inside of scheduled time   
            state_message = "AUTO MODE: Water on"
            if valveState == 0:				# Valve off - turn on
                water_valveOpen()
        else:
            state_message = "AUTO MODE: Water off"
            if valveState == 1:				# Valve on - turn off
                water_valveClose()
        print(" ", state_message)       
    else:									# Auto mode off								           
        if manualSwitchState == 0:			# Switched = true
            manual_endTime()    			# Set new manual end time, reset to Switched = false
            if valveState == 0:				# Valve off - turn on
                state_message = "MANUAL MODE: Water on"
                water_valveOpen()
            else:							# Valve on - turn off
                state_message = "MANUAL MODE: Water off"
                water_valveClose()
            print(" ", state_message)
        else:
            print("  MANUAL MODE: Water on")
            print("  Manual end time: {:02d}:{:02d}:{:02d}".format(manualEndTime[3], manualEndTime[4], manualEndTime[5]),"\n")
            if current_time[3] >= manualEndTime[3] and current_time[4] >= manualEndTime[4] and current_time[5] >= manualEndTime[5]:    # After manual end time
                print("  Manual mode ended: Auto mode reinstated\n")
                manualEndTime = ""
                autoOn = 1					# Auto mode on
                if valveState == 1:			# Valve on - turn off
                    water_valveClose()

async def main():    
    print('ASYNC DEF main\n')
    if not wlan_connect():
        print('Exiting program.')
        return

    # Start the server and run the event loop   
    print('Setting up server')
    server = asyncio.start_server(handle_client, "0.0.0.0", 80)
    asyncio.create_task(server)
    while True:
        # Add other tasks that you might need to do in the loop
        await asyncio.create_task(water_status())
        await asyncio.sleep(5)
        print('  This message will be printed every 5 seconds \n')

# Create an Event Loop
loop = asyncio.get_event_loop()
# Create a task to run the main function
loop.create_task(main())

try:
    water_valveClose()
    # Run the event loop indefinitely
    loop.run_forever()
except Exception as e:
    print('Error occured: ', e)
except KeyboardInterrupt:
    print('Program Interrupted by the user')