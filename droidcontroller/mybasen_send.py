''' Send to mybasen '''
import sys, traceback
import tornado.httpclient
import json

import logging
log = logging.getLogger(__name__)


class MyBasenSend(object):
    ''' Sends away the messages, combining different key:value pairs and adding host id and time. Listens for incoming commands and setup data.
    Several UDPchannel instances can be used in parallel, to talk with different servers.

    Used by sqlgeneral.py

    '''

    def __init__(self, aid = 'itvilla', uid = b'itvilla', passwd = b'MxPZcbkjdFF5uEF9', path= 'tutorial/testing/test_async'):
        ''' Sender to mybase '''    
        self.url = 'https://mybasen.pilot.basen.com/_ua/'+aid+'/v0.1/data'
        self.uid = uid # binary!
        self.passwd = passwd # binary!
        self.path = path
        

    def set_channels(self, in_dict):
        ''' channel configuration as dictionary {id:[name,type,coeff]} ''' 
        self.channels2basen = in_dict
        log.info(str(self.channels2basen))
        
    
    def mybasen_rows(self, values2basen):
        ''' Create datta rows for mybasen '''
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
            log.info(row)
            rows.append(row)
        return rows
            

    def domessage(self, rows):
        ''' Create json message for the given subpath and uid+password '''
        # [{"dstore":{"path":"tutorial/testing/unit1","rows":[{"channels":[{"channel":"temp","double":23.3},{"channel":"weather","string":"Balmy"}]}]}}] # naide
        # [{"dstore":{"path":"tutorial/testing/sauna","rows":[{"channels":[{"channel":"TempSauna","double":0.1},{"channel":"TempBath","double":0.2}]}]}}] # tekib ok
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


   # def mybasen_send(self, message):
        '''Send the message over https POST'''
        #self.createhttpheaders()
        #try:
            #r = requests.post(self.url, data=message, headers=self.httpheaders) # NOT SUPPORTED!
            #r = requests.put(self.url, data=message, headers=self.httpheaders) # returns status code
        #    tornado.httpclient.AsyncHTTPClient().fetch(self.__class__.self.url + user, self._async_handle_request) # asunc
            #log.info('response: '+str(r.content))
       # except:
        #    logging.error("https connection to mybasen failed")
        #    traceback.print_exc()
         #   return False

        #if r != 200:
        #    logging.error("https connection response not ok "+str(r))
        #    return False
       # return True


    def basen_send(self, values2basen):
        ''' the whole sending process with ioloop timer '''
        log.info('sending values '+str(values2basen))
        if len(values2basen) > 0: # initially empty
            rows = self.mybasen_rows(values2basen)
            self.mybasen_send(self.domessage(rows))

            
    def mybasen_send(self, message):
        headers = { "Content-Type": "application/json; charset=utf-8" }
        log.info('sending request')
        tornado.httpclient.AsyncHTTPClient().fetch(self.url, self._async_handle_request, method='PUT', headers=headers, 
            body=message, auth_username=self.uid, auth_password=self.passwd, auth_mode="basic")
        log.info('request sent')
 
 
    def _async_handle_request(self, response):
        log.info('response received')
        if response.error:
            log.error('response error: %s', str(response.error))
        else:
            log.info('response: %s', response.body)
        
 