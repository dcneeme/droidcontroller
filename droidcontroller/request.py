import requests

import logging
log = logging.getLogger(__name__)

''' Usage example:
>>> from droidcontroller.request import *
>>> r = Request(part1='http://streetlight.tartu.ee/cgi-bin/lightctrl?')
>>> r.dorequest('lux=10')
response.content b'ok'
0
'''

class Request:
    ''' Class containing methods to query any generic web server, no or expected response '''

    def __init__(self, part1, headers={}): # add sync_interval?
        self.part1 = part1 # kuni cgi kysimargini
        self.headers = headers
        
    def dorequest(self, part2, expected='ok'): # part2 alates kysimargist
        ''' Sends query, returns response '''
        #headers={'Authorization': 'Basic YmFyaXg6Y29udHJvbGxlcg=='} # Base64$="YmFyaXg6Y29udHJvbGxlcg==" ' barix:controller
        req = self.part1+part2
        try:
            response = requests.get(req, headers = self.headers)
        except:
            msg='request query '+req+' failed!'
            log.warning(msg)
            traceback.print_exc()
            return 1 # kui ei saa gcal yhendust, siis lopetab ja vana ei havita!

        try:
            #print('response.content', response.content)
            if expected in str(response.content):
                return 0
            else:
                return 2
                #events = eval(response.content) # string to list
            
        except:
            msg='FAILED request '+req
            log.warning(msg)
            traceback.print_exc() # debug
            return 1 # kui ei saa normaalseid syndmusi, siis ka lopetab

        