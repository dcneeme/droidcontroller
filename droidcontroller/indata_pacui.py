import time
import json
import re

class InDataPacui():
    ''' Example implementation of InData to pacui.json converter
    '''

    def __init__(self, indata):
        self.indata = indata


    def getJSON(self):
        print("getJSON");
        dev = ''
        loc = ''
        typename=''
        devaddr = '1'
        chan_names=[]
        chan_types=[]
        indicator = ['ON', '?', 'OFF']
        mon_status = 0
        lan_status = 0
        usb_status = 2
        vent_status = 0
        import socket
        lanip = socket.gethostbyname(socket.gethostname())

        datasnapshot = self.indata.copy()
        mbstatus = {}

        try:
            lanip = datasnapshot.read('lanip')['value'][0]
        except:
            pass

        mon_status = datasnapshot.read("DI100")['status'] # N
        lan_status = datasnapshot.read("DI101")['status'] # N
        usb_status = datasnapshot.read("DI102")['status'] # N
        vent_status = datasnapshot.read("DI8")['status'] # N
        
        mbstatus['modbusproxy_status'] = {}
        mbstatus['modbusproxy_status']['indicator'] = []
        mbstatus['modbusproxy_status']['indicator'].append({"name":"MON "+indicator[mon_status], "status":str(mon_status)})
        mbstatus['modbusproxy_status']['indicator'].append({"name":"LAN "+indicator[lan_status], "status":str(lan_status)})
        mbstatus['modbusproxy_status']['indicator'].append({"name":"USB "+indicator[usb_status], "status":str(usb_status)})
        mbstatus['modbusproxy_status']['indicator'].append({"name":"VENT "+indicator[vent_status], "status":str(vent_status)})
        
        mbstatus['modbusproxy_status']['info'] = []
        mbstatus['modbusproxy_status']['info'].append({"name":"WLAN IP address", "value":lanip})
        localtime = time.asctime( time.localtime(time.time()) )
        mbstatus['modbusproxy_status']['info'].append({"name":"TIME", "value":localtime})

        mbstatus['device_status'] = []
        devstatus = { "name":"DC5888-3", "address":"1", "status":"3",
                "location":"iMX233-OLinuXino-MAXI", "channel_data":[] }
        for type in [ 'TI', 'AI', 'DI' ]: # helpful if unknown number of different channels in use
            chstatus = {"typenum":"1", "typename":str(type), "data":[] }
            for key in sorted(datasnapshot.data.keys()):
                m = re.match(r"(?P<type>..)(?P<reg>\d+)", key)
                if (m != None):
                    if (m.groupdict()['type'] != type):
                        continue
                    addrstatus = {}
                    addrstatus = datasnapshot.read(key)['value']
                    addrstatus['address'] = m.groupdict()['reg']
                    chstatus['data'].append(addrstatus)
            devstatus['channel_data'].append(chstatus)
        mbstatus['device_status'].append(devstatus)

        mbstatus['debug'] = str(datasnapshot)

        return json.dumps(mbstatus, indent=4)
