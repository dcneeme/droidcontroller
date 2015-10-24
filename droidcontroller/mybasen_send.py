''' Send to mybasen '''


class MyBasenSend(object):
    ''' Sends away the messages, combining different key:value pairs and adding host id and time. Listens for incoming commands and setup data.
    Several UDPchannel instances can be used in parallel, to talk with different servers.

    Used by sqlgeneral.py

    '''

    def __init__(aid = 'itvilla', uid = b'itvilla', passwd = b'MxPZcbkjdFF5uEF9', path= 'tutorial/testing/test_async', \
            url = 'https://mybasen.pilot.basen.com/_ua/'+self.aid+'/v0.1/data'

        self.aid = aid
        self.uid = uid # binary!
        self.passwd = passwd # binary!
        self.path = path
        self.url = url

    def mybasen_rows(self):
        ''' Create datta rows for mybasen '''
        global values2basen, channels2basen
        self.rows = []
        for key in values2basen: # some channels may be without value in the beginning. add time?
            # show chan, type, value
            if channels2basen[key][2] != None:
                value = values2basen[key] / channels2basen[key][2]
            else:
                value = int(values2basen[key])
            #log.info('4basen '+str(channels2basen[key][0:2])+' '+str(value))
            row = "{"
            row += "\"channel\":\"" + str(channels2basen[key][0]) + "\","
            row += "\"" + str(channels2basen[key][1]) + "\":" + str(value) # + ","
            #row += "\"comment\":\"" + str(self.comment) + "\","
            #row += "\"unit\":\"" + str(self.unit) + "\""
            row += "}"
            log.info(row)
            self.rows.append(row)

    def createhttpheaders(self):
        '''create basic auth headers'''
        #authstr = 'aXR2aWxsYTpNeFBaY2JramRGRjV1RUY5' # in base64  FIXME
            #"Basic %s" % (
            #base64.b64encode("%s:%s" % (
            #        self.uid, self.passwd)),)
        self.httpheaders = {
            "Content-Type": "application/json"
            #,
            #"Authorization": "Basic " + authstr
            }
        log.info('headers: '+str(self.httpheaders))


    def domessage(self):
        ''' Create json message for the given subpath and uid+password '''
        # [{"dstore":{"path":"tutorial/testing/unit1","rows":[{"channels":[{"channel":"temp","double":23.3},{"channel":"weather","string":"Balmy"}]}]}}] # naide
        # [{"dstore":{"path":"tutorial/testing/sauna","rows":[{"channels":[{"channel":"TempSauna","double":0.1},{"channel":"TempBath","double":0.2}]}]}}] # tekib ok
        msg = '[{\"dstore\":{\"path\":'
        msg += '\"' + self.path + '\",'
        msg += '\"rows\":[{"channels":['
        for row in self.rows:
            msg += row
            msg += ","
        msg = msg.rstrip(",")
        msg += ']}]}}]'  # close
        log.debug('msg: '+str(msg))
        return msg

    def mybasen_send(self, message):
        '''Send the message over https POST'''
        self.createhttpheaders()
        try:
            #r = requests.post(self.url, data=message, headers=self.httpheaders) # NOT SUPPORTED!
            #r = requests.put(self.url, data=message, headers=self.httpheaders) # returns status code
            tornado.httpclient.AsyncHTTPClient().fetch(self.__class__.self.url + user, self._async_handle_request) # asunc
            #log.info('response: '+str(r.content))
        except:
            logging.error("https connection to mybasen failed")
            traceback.print_exc()
            return False

        #if r != 200:
        #    logging.error("https connection response not ok "+str(r))
        #    return False
        return True


    def _async_handle_request(self, response):
        ''' Handle non-blocking Nagios data reader response '''
        log.info('_async_handle_request(%s)', str(response))
        if response.error:
            log.error('_async_handle_request(): Nagios data read error: %s', str(response.error))
            self._data_callback(None)
            return
        try:
            userdata = json.loads(response.body.decode(encoding='UTF-8')).get('user_data', None)
            self._data_callback(userdata)
        except:
            raise SessionException('invalid nagios response')
            self._data_callback(None)


    def basen_send(self):
        ''' the whole sending process with ioloop timer '''
        global values2basen
        if len(values2basen) > 0: # initially empty
            self.mybasen_rows()
            self.mybasen_send(self.domessage())
