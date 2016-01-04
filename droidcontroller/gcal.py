import os, traceback, sqlite3, time, subprocess

import requests # for sync usage mode
import tornado # for async usage mode
import tornado.ioloop # for async usage mode
import tornado.httpclient # for async usage mode


from functools import partial
from concurrent.futures import ThreadPoolExecutor
EXECUTOR = ThreadPoolExecutor(max_workers=1)

import logging
log = logging.getLogger(__name__)

''' Class and methods to read events from monitoring server handling access to google calendar.
    Usage in sync mode:
    from droidcontroller.gcal.py import *
    cal=Gcal('00101200006')
    cal.sync()
    cal.check('S') # returns value for S (1 if just 'S' in event summary, 22 if 'S=22' in summary)

    Usage in async mode:
    from droidcontroller.gcal.py import *
    cal=Gcal('00101200006')
    cal.async() # sends request, response must be processed by _httpreply()
    
    cal.check('S') # returns value for S (1 if just 'S' in event summary, 22 if 'S=22' in summary)

    
    FIXME - cooling/warming delay should be taken into account in heating control, to shift setpoint
'''

class Gcal(object):
    ''' Class containing methods to read events from monitoring server handing access to google calendar '''

    def __init__(self, host_id, days=3, table='calendar', user='barix', password='controller'):
        ''' Calendar data from gcal, processed to simpler wo overlaps by itvilla.ee '''
        self.host_id = host_id
        self.user = user
        self.password = password
        #self.url = 
        self.days = days
        self.conn = sqlite3.connect(':memory:')
        self.cur = self.conn.cursor()
        self.table = table
        if self.sqlread(self.table) == 0: # dump read ok
            log.info('reusing existing calendar file')
        else: # create new table
            Cmd = 'drop table if exists '+self.table
            self.conn.execute(Cmd) # drop the table if it exists
            Cmd = "CREATE TABLE calendar(title,timestamp,value);"
            self.conn.execute(Cmd)
            Cmd = "CREATE INDEX ts_calendar on 'calendar'(timestamp);"
            self.conn.execute(Cmd)
            self.conn.commit()
            log.info('created new calendar table')
        log.info('gcal instance for cal/host_id '+self.host_id+' created')


    def sqlread(self, table): # drops table and reads from file <table>.sql that must exist
        ''' restore buffer from dump. basically the same as in sqlgeneral.py '''
        sql = ''
        filename=table+'.sql' # the file to read from
        try:
            if os.path.getsize(filename) > 50:
                msg = 'found '+filename
                sql = open(filename).read()
            else:
                msg = filename+' corrupt or empty!'
                log.info(msg)
                time.sleep(1)
                return 1
        except:
            msg = filename+' missing!'
            log.warning(msg)
            time.sleep(1)
            return 1

        Cmd = 'drop table if exists '+table
        try:
            self.conn.execute(Cmd) # drop the table if it exists
            self.conn.commit()
            self.conn.executescript(sql) # read the existing table into database
            self.conn.commit()
            msg = 'successfully recreated table '+table
            log.info(msg)
            return 0

        except:
            msg = filename+' corrupt: '+str(sys.exc_info()[1])
            log.warning(msg)
            traceback.print_exc()
            time.sleep(1)
            return 1

    def sync(self, cal_id=None): # query to SUPPORTHOST, returning all events. cal_id may be different from host_id (several cals)...
        ''' Updates the local event buffer for days ahead. Dumps the result into sql file.
            Blocks until response! Use async() with tornado ioloop if you can. ''' 
        # example:   http://www.itvilla.ee/cgi-bin/gcal.cgi?mac=000101000001&days=10
        if not cal_id:
            cal_id = self.host_id
        req = 'http://www.itvilla.ee/cgi-bin/gcal.cgi?mac='+cal_id+'&days='+str(self.days)+'&format=json'
        headers = {'Authorization': 'Basic YmFyaXg6Y29udHJvbGxlcg=='} # Base64$="YmFyaXg6Y29udHJvbGxlcg==" ' barix:controller
        msg = 'starting gcal sync query '+req
        log.info(msg) # debug
        # in this method wait until response or timeout
        try:
            res = requests.get(req, headers = headers)
            #self.process_response(res.content) ##
            return res           
        except:
            msg = 'gcal query '+req+' failed!'
            log.warning(msg)
            traceback.print_exc()
            #return 1 # kui ei saa gcal yhendust, siis lopetab ja vana ei havita!

    def async(self, cal_id=None):
        ''' Non-blocking request to calendar server '''
        self.url = 'http://www.itvilla.ee/cgi-bin/gcal.cgi?mac='+self.host_id+'&days='+str(self.days)+'&format=json'
        headers = { "Content-Type": "application/json; charset=utf-8" }
        try:
            log.info("starting gcal async query: "+self.url) ##
            tornado.httpclient.AsyncHTTPClient().fetch(self.url, self._httpreply, method='GET', headers=headers,  body=None,
                auth_mode="basic", auth_username=self.user, auth_password=self.password) # response to httpreply when it comes, without blocking
                # vaikimisi request_timeout=20, connect_timeout=20
        except:
            loq.error('async request '+self.url+' FAILED!')
            traceback.print_exc()
            
    def _httpreply(self, response):
        ''' For async usage '''
        # tcpdump -A -vvv port 80 # debugging
        if response.error:
            log.error("HTTP ERROR: %s", str(response.error))
        else:
            #log.info("HTTP RESPONSE: %s", response.body)
            self.process_response(response.body)
            
    def read_async(self, reply_cb):
        ''' use with concurrent.futures  ''' 
        log.info("  gcal_send_request..")
        EXECUTOR.submit(self.sync).add_done_callback(lambda future: tornado.ioloop.IOLoop.instance().add_callback(partial(self.callback, future)))
        #eraldi threadis read_sync, mis ootab vastust. 
        
    def callback(self, future):
        result = future.result()
        self.async_reply(result)

    def async_reply(self, result):
        print("    mbus result: " + str(result))
        #self.parse(result)
        self.process_response(result)
       
    def process_response(self, response):
        ''' Calendar content into sql table, use inside sync() or independently for async mode '''
        try:
            if '[]' in str(response):
                log.info('no content from calendar, keeping the existing calendar table')
                return 2
            else:
                log.info('got calendar content: '+ str(response))
                events = eval(response) # string to list

        except:
            msg = 'getting calendar events failed for host_id '+self.host_id
            log.warning(msg)
            traceback.print_exc() # debug
            return 1 # kui ei saa normaalseid syndmusi, siis ka lopetab

        #print(repr(events)) # debug
        Cmd = "BEGIN IMMEDIATE TRANSACTION"
        try:
            self.conn.execute(Cmd)
            Cmd = "delete from "+self.table
            self.conn.execute(Cmd)
            for event in events:
                #print('event',event) # debug
                columns = str(list(event.keys())).replace('[','(').replace(']',')')
                values = str(list(event.values())).replace('[','(').replace(']',')')
                Cmd = "insert into calendar"+columns+" values"+values
                log.debug(Cmd) # debug
                self.conn.execute(Cmd)
            self.conn.commit()
            self.dump() # to file
            msg = 'calendar table '+self.table+' updated and dumped'
            log.info(msg)
            return 0
        except:
            msg = 'delete + insert to calendar table '+self.table+' FAILED!'
            log.warning(msg)
            traceback.print_exc() # debug
            return 1 # kui insert ei onnestu, siis ka delete ei toimu


    def dump(self): # sql table to file
        ''' Writes the table into a SQL-file to keep the existing scheduling data '''
        try:
            with open(self.table+'.sql', 'w') as f:
                for line in self.conn.iterdump(): # see dumbib koik kokku!
                    if self.table in line: # needed for one table only! without that dumps all!
                        f.write('%s\n' % line)
            subprocess.call('sync')
            time.sleep(0.1)
            log.info(self.table+' dump into '+self.table+'.sql done')
            return 0
        except:
            msg = 'FAILURE dumping '+self.table+'!'
            log.warning(msg)
            traceback.print_exc()
            time.sleep(1)
            return 1


    def check(self, title): # set a new setpoint if found in table calendar (sharing database connection with setup)
        ''' Returns the current value for the event with title from the local event buffer '''
        tsnow = int(time.time())
        value = '' # local string value
        if title == '':
            return None

        Cmd = "BEGIN IMMEDIATE TRANSACTION"
        try:
            self.conn.execute(Cmd)
            Cmd = "select value,timestamp from calendar where title='"+title+"' and timestamp+0<"+str(tsnow)+" order by timestamp asc" # find the last passed event value
            self.cur.execute(Cmd)
            for row in self.cur:
                value = row[0] # overwrite with the last value before now
                ts = row[1]
                log.debug('cal tsnow '+str(tsnow)+', ts '+str(ts)+', value '+str(value)) # debug.  viimane value jaab iga title jaoks kehtima
            self.conn.commit()
            #if self.msgbus:
            #    self.msgbus.publish(val_reg, {'values': values, 'status': sumstatus})
            return str(value) # last one for given title becomes effective. can be empty string too, then use default value for setpoint related to title

        except:
            traceback.print_exc()
            return None
                