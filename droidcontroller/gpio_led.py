# make gpio channel meanings selectable
import os, traceback
import logging
log = logging.getLogger(__name__)

try:
    import iMX233_GPIO as GPIO
except:
    print('could not import iMX233_GPIO for GPIOLED')
    #traceback.print_exc()
            
class GPIOLED:
    ''' Olinuxino LED control, needs archlinux as OSTYPE env variable 
    import iMX233_GPIO as GPIO
    import time
    GPIO.setoutput(GPIO.LED)
    GPIO.output(GPIO.LED, 0)
    time.sleep(1)
    GPIO.output(GPIO.LED, 1) # roheline "cpu"
    {0, 0, "PIN9"},
    {0, 1, "PIN10"},
    {0, 2, "PIN11"},
    {0, 3, "PIN12"},
    {0, 4, "PIN13"},
    {0, 5, "PIN14"},
    {0, 6, "PIN15"},
    {0, 7, "PIN16"},
    {0, 16, "PIN17"},
    {0, 17, "PIN18"},
    {1, 18, "PIN23"},
    {1, 20, "PIN24"},
    {1, 19, "PIN25"},
    {1, 21, "PIN26"},
    {1, 28, "PIN27"},
    {0, 25, "PIN28"},
    {0, 23, "PIN29"},
    {2, 27, "PIN31"},
    {2, 1, "LED"} 
    '''

    def __init__(self):
        GPIO.setoutput(GPIO.PIN15) # set to output green OK (commLED) 
        GPIO.setoutput(GPIO.PIN17) # set to output red Fault (alarmLED)
        self.cpuLED(1) # always output
        self.commLED(1)
        self.alarmLED(1)
        
            
    def cpuLED(self, state):
        ''' green LED '''
        try:
            GPIO.output(GPIO.LED, (state&1)) # roheline "cpu"
            return 0
        except:
            print('error with cpuLED() param',state)
            traceback.print_exc()
            return 1
            
    def commLED(self, state): # olinuxino gpio pin10
        ''' Parameter 1 lights LED. 0 turns off. Via PIN15 '''
        try:
            GPIO.output(GPIO.PIN15, (state&1)) # only 0 or 1 allowed
            return 0
        except:
            print('error with commLED() param',state)
            traceback.print_exc()
            return 1

    def alarmLED(self, state): # olinuxino gpio pin11
        ''' Parameter 1 lights LED. 0 turns off. Via PIN17 '''
        try:
            GPIO.output(GPIO.PIN17, (state&1)) # only 0 or 1 allowed
            return 0
        except:
            print('error with alarmLED() param',state)
            traceback.print_exc()
            return 1
        