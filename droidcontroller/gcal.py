import os, traceback, sqlite3, time, datetime, subprocess
## the full day events must be done in hours in order to end properly and not to mess up the following as well!!!
## the event created this way will be shown as full day in calendar, but with time 00:00 and now tick in full day field.

import requests # for sync usage mode
import dateutil.parser

import logging
log = logging.getLogger(__name__)

try:
    import tornado # for async usage mode
    import tornado.ioloop # for async usage mode
    import tornado.httpclient # for async usage mode

    from functools import partial
    from concurrent.futures import ThreadPoolExecutor
    EXECUTOR = ThreadPoolExecutor(max_workers=1) # re remark below for self.gcal_scheduler
except:
    log.warning('tornado and concurrent not imported, do not use async mode!')
    time.sleep(2)


''' Class and methods to read events from monitoring server handling access to google calendar.
    Usage in sync mode:
    from droidcontroller.gcal.py import *
    cal=Gcal('00101200006')
    cal.sync()
    cal.check('S') # returns value for S (1 if just 'S' in event summary, 22 if 'S=22' in summary)

    Usage in async mode:
    from droidcontroller.gcal.py import *
    cal=Gcal('00101200006')
    cal.async() # sends request, now with executor

    cal.check('S') # returns value for S (1 if just 'S' in event summary, 22 if 'S=22' in summary)


    FIXME - cooling/warming delay should be taken into account in heating control, to shift setpoint!

    use this in iomain init:

    self.gcal_scheduler = tornado.ioloop.PeriodicCallback(self.gcal.run, 30000, io_loop = self.loop) # every 30 minutes (3 for tst) # using future
    self.gcal_scheduler.start()

'''

class Gcal(object):
    ''' Class containing methods to read events from monitoring server handing access to google calendar '''

    def __init__(self, host_id, days=3, table='calendar', auth='base64here'): 
        ''' Calendar data from gcal, processed to simpler wo overlaps by itvilla.ee    '''
        self.host_id = host_id
        self.days = days
        self.conn = sqlite3.connect(':memory:')
        self.cur = self.conn.cursor()
        self.table = table
        self.auth = auth  # Basic base64

        self.sqlread()
        log.info('gcal instance created')


    def sqlread(self): # drops table and reads from file <table>.sql that must exist
        ''' restore table from sql dump. basically the same as in sqlgeneral.py  but also makes calendar if missing '''
        sql = ''
        filename = self.table+'.sql' # the file to read from
        try:
            if os.path.getsize(filename) > 50:
                msg = 'found '+filename
                sql = open(filename).read()
            else:
                msg = filename+' corrupt or empty!'
                log.info(msg)
                time.sleep(1)
                return self.makecalendar() # dumps also

        except:
            msg = filename+' missing!'
            log.warning(msg)
            return self.makecalendar() # dumps the new table also

        Cmd = 'drop table if exists '+self.table
        try:
            self.conn.execute(Cmd) # drop the table if it exists
            self.conn.commit()
            self.conn.executescript(sql) # read the existing table into database
            self.conn.commit()
            msg = 'successfully recreated table '+self.table+' based on '+filename
            log.info(msg)
            return 0

        except:
            msg = filename+' corrupt: '+str(sys.exc_info()[1])
            log.warning(msg)
            traceback.print_exc()
            time.sleep(1)
            return 1


    def makecalendar(self):
        '''recreates without a need for sql file '''
        # some problem with reading. what if corrupt?
        log.warning('deleting and creating a new calendar table '+self.table)
        Cmd = 'drop table if exists '+self.table
        try:
            self.conn.execute(Cmd) # drop the table if it exists
            Cmd = "CREATE TABLE "+self.table+"(title,timestamp,value);"
            self.conn.execute(Cmd)
            Cmd = "CREATE INDEX title_ts_calendar on '"+self.table+"'(title,timestamp);"
            self.conn.execute(Cmd)
            self.conn.commit()
            log.info('created new calendar table '+self.table)
            self.dump() # to create the missing sql file
            return 0

        except:
            log.error('calendar table '+self.table+' creation FAILED!')
            traceback.print_exc()
            time.sleep(1)
            return 1

    def dump(self): # dump sql table to file
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


    def calprint(self):
        ''' reads and returns the whole content of the calendar table '''
        output = []
        Cmd ="SELECT * from "+self.table
        self.cur.execute(Cmd)
        self.conn.commit()
        for row in self.cur:
            print(row, time.asctime(time.localtime(int(row[1]))))
            #output.append(row)
        #return output


    def send_async(self, cal_id=''): # query to SUPPORTHOST, returning all events. cal_id may be different from host_id (several cals)...
        ''' the request will be in a separate thread! '''
        # example:   http://www.itvilla.ee/cgi-bin/gcal.cgi?mac=000101000001&days=10
        if not 'str' in str(type(cal_id)) or len(cal_id) == 0:
            cal_id = self.host_id
            log.warning('replaced cal_id with host_id '+self.host_id)

        req = 'http://www.itvilla.ee/cgi-bin/gcal.cgi?mac='+cal_id+'&days='+str(self.days)+'&format=json'
        headers = {'Authorization': 'Basic '+self.auth} #
        msg = 'starting gcal async query '+req
        log.info(msg) # debug
        # in this method wait until response or timeout
        try:
            res = requests.get(req, headers = headers)
            #self.process_response(res.content) ##
            return res.content
        except:
            msg = 'gcal query '+req+' failed!'
            log.warning(msg)
            traceback.print_exc()
            #return 1 # kui ei saa gcal yhendust, siis lopetab ja vana ei havita!


    def sync(self, cal_id='', auth=''): # query to SUPPORTHOST, returning all events. cal_id may be different from host_id (several cals)...
        ''' the request will be in a separate thread! '''
        # example:   http://www.itvilla.ee/cgi-bin/gcal.cgi?mac=000101000001&days=10
        if not 'str' in str(type(cal_id)) or len(cal_id) == 0:
            cal_id = self.host_id
            log.warning('replaced cal_id with host_id '+self.host_id)

        req = 'http://www.itvilla.ee/cgi-bin/gcal.cgi?mac='+cal_id+'&days='+str(self.days)+'&format=json'
        headers = {'Authorization': 'Basic '+self.auth}
        msg = 'starting gcal sync query '+req
        log.info(msg) # debug
        # in this method wait until response or timeout
        try:
            res = requests.get(req, headers = headers)
            self.process_response(res.content) ##
            return 0

        except:
            msg = 'gcal query '+req+' failed!'
            log.warning(msg)
            traceback.print_exc()
            return 1 # kui ei saa gcal yhendust, siis lopetab ja vana ei havita!


    def async(self, reply_cb):
        ''' use with concurrent.futures  '''
        EXECUTOR.submit(self.send_async).add_done_callback(lambda future: tornado.ioloop.IOLoop.instance().add_callback(partial(self.callback, future)))
        #eraldi threadis read_sync, mis ootab vastust.


    def callback(self, future):
        result = future.result()
        self.async_reply(result)

    def async_reply(self, result):
        print("    gcal result: " + str(result))
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
                titles = []
                for i in range(len(events)):
                    titles.append(events[i]['title'])
                titles = list(set(titles))
        except:
            msg = 'getting calendar events failed for host_id '+self.host_id
            log.warning(msg)
            traceback.print_exc() # debug
            return 1 # kui ei saa normaalseid syndmusi, siis ka lopetab

        #print(repr(events)) # debug
        Cmd = "BEGIN IMMEDIATE TRANSACTION"
        try:
            self.conn.execute(Cmd)
            Cmd = "delete from "+self.table+" where timestamp+0 < "+str(int(time.time()))+"-180000"  # over 48h of age to be deleted
            self.conn.execute(Cmd)
            for i in range(len(titles)):
                Cmd = "delete from "+self.table+" where title='"+titles[i]+"'"
                # deleting selectively using title enables adding rows from various sources! incl energy prices
                log.info(Cmd)
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


    def check(self, title, timeshift=0): # set a new setpoint if found in table calendar (sharing database connection with setup)
        ''' Returns the current or future (if timeshift >0) value for the event in the local calendar event buffer table '''
        tsnow = int(time.time())
        value = '' # local string value
        if title == '':
            return None

        Cmd = "BEGIN IMMEDIATE TRANSACTION"
        try:
            self.conn.execute(Cmd)
            Cmd = "select value,timestamp from "+self.table+" where title='"+title+"' and timestamp+0<"+str(tsnow+timeshift)+" order by timestamp asc" # find the last passed event value
            self.cur.execute(Cmd)
            for row in self.cur:
                value = row[0] # overwrite with the last value before now
                ts = row[1]
                #log.debug('cal tsnow '+str(tsnow)+', ts '+str(ts)+', value '+str(value)) # debug.  viimane value jaab iga title jaoks kehtima
            self.conn.commit()
            #if self.msgbus:
            #    self.msgbus.publish(val_reg, {'values': values, 'status': sumstatus})
            return str(value) # last one for given title becomes effective. can be empty string too, then use default value for setpoint related to title
            # miks str? value huvitab ju alati... kuigi - mine tea!
        except:
            traceback.print_exc()
            return None


    def check_above(self, title, level):
        ''' Returns True if cal value is above the comparision level '''
        value = int(self.check(title))
        if value > level:
            return True
        else:
            return False


    def check_below(self, title, level):
        ''' Returns True if cal value is above the comparision level '''
        value = int(self.check(title))
        if value < level:
            return True
        else:
            return False


    def get_min(self, title='el_energy_EE', ts_max=0): # ts_until 0 means until the values for title end
        ''' select ts,min(value) from changes where mac='el_energy_EE' and ts+0 < tsmax and ts+0>tsnow '''
        found = 0
        tsnow = time.time()
        if ts_max == 0:
            Cmd="select timestamp,min(value) from "+self.table+" where title='"+title+"' and timestamp+0 > "+str(tsnow)
        else:
            Cmd="select timestamp,min(value) from "+self.table+" where title='"+title+"' and timestamp+0 < "+str(ts_max)+" and timestamp+0 > "+str(tsnow)
        #log.info(Cmd)
        self.cur.execute(Cmd)
        self.conn.commit()
        for row in self.cur:
            #log.info(str(repr(row)))
            ts = int(row[0])
            value = int(row[1])
            found = 1

        if found == 1:
            return ts, value # timestamp for minvalue, minvalue
        else:
            log.warning('INVALID parameters or NO EVENTS found for '+title)
            return None


    def next_time2sec(self, hour, minute=0):
        ''' convert the next occurence of localtime hour,min into sec '''
        # time.asctime(time.localtime(int(row[1]))))
        tsnow = int(time.time())
        d = time.localtime(tsnow) # y, m, d, h, min, sec, wd, yd, isdst
        if d[3] >= hour and d[4] > minute: # tomorrow
            ts24 = tsnow + 24 * 3600 # VAJA LIITA 24H JA VAADATA MIS KUUPAEV (DAY) TULEB!
            d = time.localtime(ts24) # y, m, d, h, min, sec ... for tomorrow
        t = datetime.datetime(d[0], d[1], d[2], hour, minute) # replace hour, min
        sec = time.mktime(t.timetuple()) # get the seconds
        print('next ts for hour, min ', hour, minute, 'at', t)
        return sec


    def set_untilmin(self, title_set, title_ref='el_energy_EE', maxhour=5, maxminute=0):
        ''' sets event from now until now+len '''
        ts_max = self.next_time2sec(maxhour, maxminute)
        ts_until = self.get_min(title='el_energy_EE', ts_max=ts_max)[0] # ts of minvalue only needed here
        if ts_until == None: # minimum or ref value not found
            log.error('minimum or ref value for calendar pulse setting NOT found')
            return None

        tsnow = int(time.time())
        Cmd = "BEGIN IMMEDIATE TRANSACTION"
        try:
            self.conn.execute(Cmd)
            Cmd="delete from "+self.table+" where title='"+title_set+"'" # all remove old records for this title_set
            self.conn.execute(Cmd)
            Cmd = "insert into "+self.table+"(title,timestamp, value) values('"+title_set+"','"+str(tsnow)+"','1')"
            #log.debug(Cmd) # debug
            self.conn.execute(Cmd) # pulse start
            Cmd = "insert into calendar(title,timestamp, value) values('"+title_set+"','"+str(ts_until)+"','0')"
            #log.debug(Cmd) # debug
            self.conn.execute(Cmd) # pulse end
            self.conn.commit()
            self.dump() # to file
            msg = 'calendar table '+self.table+' updated and dumped with pulse from now until '+str(ts_until)
            log.info(msg)
            d = time.localtime(ts_until) # d contains y, m, d, h, min, sec, ..
            t = time.asctime(d)
            return t # str
        except:
            msg = 'adding pulse to calendar table '+self.table+' FAILED!'
            log.warning(msg)
            traceback.print_exc() # debug
            return None # kui insert ei onnestu, siis ka delete ei toimu


    def set_top(self, title_set, title_ref='el_energy_EE', tophours=6): # 6h is 25% of 24h # ei tohi kustutada viimast eventi?
        ''' set values 1 if the hours are in the top price selection. use before midnight. '''
        midnight = self.next_time2sec(0, minute=0) # next midnight, prices known 24h ahead from that
        threshold = None
        Cmd = "BEGIN IMMEDIATE TRANSACTION"
        try:
            self.conn.execute(Cmd)
            Cmd = "select value,timestamp from "+self.table+" where title='"+title_ref+"' and timestamp+0>"+str(midnight)+" order by value desc limit "+str(tophours)
            self.cur.execute(Cmd) # GET THE TOP VALUES in descending order, the last one will be the threshold
            for row in self.cur:
                threshold = int(row[0]) # the lowest value that will be included into the top selection

            if threshold != None:
                Cmd = "select value,timestamp from "+self.table+" where title='"+title_ref+"' and timestamp+100>"+str(midnight)+" order by timestamp asc"
                self.cur.execute(Cmd) # get all next day value sorted by time
                intop = 0
                for row in self.cur:
                    value = int(row[0])
                    ts = int(row[1])
                    if value >= threshold and intop == 0:
                        Cmd = "insert into calendar(title_set,timestamp, value) values('"+title_set+"','"+str(ts)+"','1')"
                        intop = 1
                    elif value < threshold and intop == 1:
                        Cmd = "insert into calendar(title_set,timestamp, value) values('"+title_set+"','"+str(ts)+"','0')"
                        intop = 0
                    self.comm.execute(Cmd)
                self.conn.commit()
                return 0
            else:
                log.warning('Failed to find threshold value for top hours')
                return 1
        except:
            log.error('FAILED to set top for '+title_set)
            traceback.print_exc()
            return 2
        

    def delete(self, title):
        ''' remove all records with title '''
        Cmd = "BEGIN IMMEDIATE TRANSACTION"
        try:
            self.conn.execute(Cmd)
            Cmd="delete from "+self.table+" where title='"+title+"'" # all remove old records for this title_set
            self.conn.execute(Cmd)
            self.conn.commit()
            self.dump() # to file
            msg = 'records with title '+title+' deleted from the calendar table '+self.table
            log.info(msg)
            return 0
        except:
            msg = 'deleting records from '+self.table+' FAILED!'
            log.warning(msg)
            traceback.print_exc() # debug
            return 1 # kui insert ei onnestu, siis ka delete ei toimu
