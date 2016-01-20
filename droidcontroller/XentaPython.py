import requests
import hashlib
import json
from html.parser import HTMLParser

#Login information
uid = "root"
pw = "root"

#Configuration
siteUrl = 'http://194.126.110.15'
sfile = '/www/index/Slogin.html'

#SLS cloud connection
#Following data should be obtained from http://slsui.azurewebsites.net/
SLS_deviceID = '1hf5vuAlRhBP4jcIg8Izd2bi%2buoncUoORDwqY3fvS6k%3d'
SLS_DataConnectionString = ''

#Initialization
temp = ''
string = ''

#FUNCTION AND CLASS DEFINITINOS
#Optimization request to SLS server
#Class for json
class OptResponse(object):
    def __init__(self, j):
        self.__dict__ = json.loads(j)

#HTML Parser for Xenta interface
class HTMLDataParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)        
        self.data = []

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            if ('type', 'text') in attrs:
                d = ['','']
                for attr_name, attr_value in attrs:
                    if attr_name == 'name':
                        #print('Name: ' + attr_value)
                        d[0] = attr_value
                    if attr_name == 'value':
                        #print('Value: ' + attr_value)
                        d[1] = attr_value
                self.data.append(d)

#Data sending to Xenta controller
def SendData(Url, Cookies, ParsedData):
    #Data extraction (array to string)
    datastring = ''    
    for variable,value in ParsedData:
            datastring += variable + '=' + value + '&'
    datastring += 'Submit=Submit'
    
    r_post = requests.post(Url, cookies = Cookies, data = datastring)
    return
        
#Optimization request from SLS server (refer to documentation on http://slsui.azurewebsites.net/documentation/HeatingAPI.pdf)
def SLSOptimizationRequest(StartValue, MinValue, MaxValue, MinPower, MaxPower, deviceID, OutsideTemperature = [0], StartUpCost = 0, ShutDownCost = 0):
    optimization_json = {"MinTemperature": MinValue, "MaxTemperature": MaxValue, "StartTemperature": MaxPower, "MaxHeaterCoolerPower": MaxPower, "MinHeaterCoolerPower": MinPower, "StartUpCost": StartUpCost ,"ShutDownCost": ShutDownCost, "OutsideTemperature":0, "DeviceID":deviceID}
    r_optimization = requests.post('http://slsoptimizationservice.cloudapp.net/json/reply/OptimizeHeaterCooler', json = optimization_json)
    PowerSchedule = OptResponse(r_optimization.text)
    if(r_optimization.status_code != 200):
        raise NameError('Optimization schedule request SLS server failed!')
    
    #Conversion to format [title, timestamp, value]
    Power_json = []
    for t in range(0, len(PowerSchedule.power)-1):
        Power_json.append({"Title": "Power", "timestamp": PowerSchedule.timeStamps[t][6:-2], "value": PowerSchedule.power[t]})
    return Power_json;

#Data sending to SLS server (for machine learning) (refer to documentation on http://slsui.azurewebsites.net/documentation/HeatingAPI.pdf)
def SLSSendData(ValueInside, ValueOutside, Power, deviceID, ConnectionString):
    data_json = {"ID": deviceID, "IT": ValueInside , "OT": ValueOutside, "P": Power}
    authorization_header = {'Authorization' : ConnectionString}
    r_data = requests.post('https://slsdataservice.servicebus.windows.net/slssensordata/messages', json = data_json, headers = authorization_header)
    if(r_data.status_code != 201):
        raise NameError('Data sending to SLS server failed!')
    return

#MD5 ENCRYPTION (Reverse engineered JavaScript)
#Get data for MD5 encryption
m = hashlib.md5()
r_md5 = requests.get(siteUrl + '/sys/GetLoginData.js')
js_script = r_md5.content.decode("utf-8")
#Parsing
start_index = js_script.index('arrData')
end_index = js_script.index('];return')
md5Data = js_script[start_index+9:end_index].replace('"','').split(',')
#Creation of md5 hashes for cookie
string = sfile+"?UID=" + uid
for j in range(0, len(md5Data)-1):
    n = md5Data[j].find('=')
    if(n != -1):
        md5Data[j] = md5Data[j][n:]
    temp += md5Data[j]
temp = uid+pw+sfile+md5Data[4]
m.update(temp.encode('utf-8'))
temp = m.hexdigest()
string = string + ",MAC=" + temp + ",NV=" + md5Data[4]

#GET COOKIE
r_cookie = requests.get(siteUrl + string)

#MAIN CODE HERE!
#Example: Get data from Xenta interface
r_data = requests.get(siteUrl + '/www/info/WebTest/HTML+pages/Html+Variable+Page+Write.html', cookies = r_cookie.cookies)
html_data = r_data.content.decode('utf-8')
#   Parse html
parser = HTMLDataParser()
parser.feed(html_data)

#Example: Data sending to Xenta interface
inputdata = SendData(siteUrl + '/sys/ssi', r_cookie.cookies, parser.data)

#Example: Send data to SLS server
SLSSendData('10', '10', '1', SLS_deviceID, SLS_DataConnectionString)

#Example: Optimization Request from SLS server
powerJSON = SLSOptimizationRequest('40', '30', '50', '0.0018', '0.0018', SLS_deviceID)
