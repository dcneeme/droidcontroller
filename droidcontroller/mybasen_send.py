''' Send data into mybasen server.
    Needs the data to be arranged in arrays of self.values2basen, 
    configured in dictionary self.channels2basen like {0:['TempSauna','double',10]} # name, type, divisor
    where key is the self.values2basen index
'''

import sys, traceback, time
import tornado.httpclient
import json

import logging
log = logging.getLogger(__name__)


class MyBasenSend(object):
    ''' Sends away the messages, combining different key:value pairs and adding host id and time (time not yet).
        Listens for response, non-blocking, relies on tornado IOLoop.
    '''

    def __init__(self, aid = '', uid = b'', passwd = b'', path= 'tutorial/testing'):
        ''' Sender to mybase '''
        self.url = 'https://mybasen.pilot.basen.com/_ua/'+aid+'/v0.1/data'
        self.uid = uid # binary!
        self.passwd = passwd # binary!
        self.path = path
        self.ts = int(time.time())
        self.ts_send = 0

    def set_channels(self, in_dict):
        ''' channel configuration as dictionary {id:[name,type,coeff]} '''
        self.channels2basen = in_dict
        log.info(str(self.channels2basen))


    def mybasen_rows(self, values2basen):
        ''' Create data rows for mybasen '''
        rows = []
        for key in values2basen: # some channels may be without value in the beginning. add time?
            # show chan, type, value
            if values2basen[key] != None:
                if self.channels2basen[key][2] != None:
                    value = values2basen[key] / self.channels2basen[key][2]
                else:
                    value = int(values2basen[key])
                #log.info('4basen '+str(channels2basen[key][0:2])+' '+str(value))
                row = "{"
                row += "\"channel\":\"" + str(self.channels2basen[key][0]) + "\","
                row += "\"" + str(self.channels2basen[key][1]) + "\":" + str(value) # + ","
                #row += "\"comment\":\"" + str(self.comment) + "\","
                #row += "\"unit\":\"" + str(self.unit) + "\""
                row += "}"
                log.debug(row)
                rows.append(row)
        return rows


    def domessage(self, rows):
        ''' Create json message for the given subpath and uid+password '''
        # [{"dstore":{"path":"tutorial/testing/unit1","rows":[{"channels":[{"channel":"temp","double":23.3},{"channel":"weather","string":"Balmy"}]}]}}] # naide
        # [{"dstore":{"path":"tutorial/testing/sauna","rows":[{"channels":[{"channel":"TempSauna","double":0.1},{"channel":"TempBath","double":0.2}]}]}}] # tekib ok
        self.ts = int(time.time())
        self.ts_send = self.ts
        
        msg = '[{\"dstore\":{\"path\":'
        msg += '\"' + self.path + '\",'
        msg += '\"rows\":[{"channels":['
        for row in rows:
            msg += row
            msg += ","
        msg = msg.rstrip(",")
        msg += ']}]}}]'  # close
        log.debug('msg: '+str(msg))
        return msg


    def basen_send(self, values2basen):
        ''' the whole sending process with ioloop timer '''
        log.info('sending at '+str(self.ts)+' values '+str(values2basen))
        if len(values2basen) > 0: # initially empty
            rows = self.mybasen_rows(values2basen)
            self.mybasen_send(self.domessage(rows))


    def mybasen_send(self, message):
        ''' Actually sending '''
        headers = { "Content-Type": "application/json; charset=utf-8" }
        log.debug('sending PUT request, body '+str(message))
        tornado.httpclient.AsyncHTTPClient().fetch(self.url, self._async_handle_request, method='PUT', headers=headers,
            body=message, auth_username=self.uid, auth_password=self.passwd, auth_mode="basic")


    def _async_handle_request(self, response):
        ''' event of https put response '''
        #log.info('response received')
        self.ts = int(time.time())
        delay = self.ts - self.ts_send
        if response.error:
            log.error('response error: %s', str(response.error))
        else:
            log.info('response (delay '+str(delay)+' s): %s', response.body)

