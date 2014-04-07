import time
import json
import re

class InDataPacui():
    ''' Example implementation of InData to pacui.json converter
    This version gets data from sql tables
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
        
        mon_status = get_svc('dichannels','MOS') # mon_status = 0
        lan_status = get_svc('dichannels','WLS') # lan_status = 0
        usb_status = get_svc('dichannels','USS') # usb_status = 2
        
        import socket
        lanip = socket.gethostbyname(socket.gethostname())

        datasnapshot = self.indata.copy()
        mbstatus = {}

        try:
            lanip = datasnapshot.read('lanip')['value'][0]
        except:
            pass

        mbstatus['modbusproxy_status'] = {}
        mbstatus['modbusproxy_status']['indicator'] = []
        mbstatus['modbusproxy_status']['indicator'].append({"name":"MON "+indicator[mon_status], "status":str(mon_status)})
        mbstatus['modbusproxy_status']['indicator'].append({"name":"LAN "+indicator[lan_status], "status":str(lan_status)})
        mbstatus['modbusproxy_status']['indicator'].append({"name":"USB "+indicator[usb_status], "status":str(usb_status)})
        mbstatus['modbusproxy_status']['info'] = []
        mbstatus['modbusproxy_status']['info'].append({"name":"WLAN IP address", "value":lanip})
        localtime = time.asctime( time.localtime(time.time()) )
        mbstatus['modbusproxy_status']['info'].append({"name":"TIME", "value":localtime})

        mbstatus['device_status'] = []
        devstatus = { "name":"DC5888-3", "address":"1", "status":"3",
                "location":"iMX233-OLinuXino-MAXI", "channel_data":[] }
        for type in [ 'TI', 'AI', 'DI' ]:
            chstatus = {"typenum":"1", "typename":str(type), "data":[] }
            for key in sorted(datasnapshot.data.keys()):
                m = re.match(r"(?P<type>..)(?P<reg>\d+)", key)
                if (m != None):
                    if (m.groupdict()['type'] != type):
                        continue
                    addrstatus = {}
                    addrstatus['address'] = m.groupdict()['reg']
                    if (type == 'TI'):
                        addrstatus['value'] = datasnapshot.read(key)['value'][0]
                        if (addrstatus['value'] == 'N/A'):
                            addrstatus['value'] = ''
                        elif (addrstatus['value'] == 'ERR'):
                            addrstatus['status'] = 2
                        else:
                            addrstatus['status'] = 0
                    elif (type == 'AI'):
                        #addrstatus['value'] = "%0.1f" % (datasnapshot.read(key)['value'][0] * 5 / 4096)
                        addrstatus['value'] = datasnapshot.read(key)['value'][0]
                    elif (type == 'DI' or type == 'DO'):
                        byte = datasnapshot.read(key)['value'][0]
                        for bit in range(1, 17, 1):
                            addrstatus['bit'] = bit
                            addrstatus['value'] = 0
                            if (byte & (1 << (bit - 1))):
                                addrstatus['value'] = 1
                            if (bit < 16):   # add last bit outside loop
                                chstatus['data'].append(addrstatus.copy())
                    else:
                        addrstatus['value'] = datasnapshot.read(key)['value'][0]
                    chstatus['data'].append(addrstatus)
            devstatus['channel_data'].append(chstatus)
        mbstatus['device_status'].append(devstatus)

        mbstatus['debug'] = str(datasnapshot)

        return json.dumps(mbstatus, indent=4)
