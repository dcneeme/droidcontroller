import os, traceback, sqlite3, time
from droidcontroller.sqlgeneral import * # SQLgeneral
s=SQLgeneral()

import logging
log = logging.getLogger(__name__)

''' Class and methods to read events from monitoring server handling access to google calendar.
    Usage:
    from droidcontroller.gcal.py import *
    cal=Gcal('00101200006')
    cal.sync()
    cal.check('S')
      the last one returns value for S (1 if just 'S' in event summary, 22 if 'S=22' in summary)
'''

class Gcal:
    ''' Class containing methods to read events from monitoring server handing access to google calendar '''

    def __init__(self, host_id, days=3): # add sync_interval?
        self.host_id = host_id
        self.days = days
        s.sqlread('calendar')
        self.cur=conn.cursor()

    def sync(self): # query to SUPPORTHOST, returning all events
        ''' Updates the local event buffer for days ahead. Should happen in background according to some interval... '''
        # example:   http://www.itvilla.ee/cgi-bin/gcal.cgi?mac=000101000001&days=10
        req = 'http://www.itvilla.ee/cgi-bin/gcal.cgi?mac='+self.host_id+'&days='+str(self.days)+'&format=json'
        headers={'Authorization': 'Basic YmFyaXg6Y29udHJvbGxlcg=='} # Base64$="YmFyaXg6Y29udHJvbGxlcg==" ' barix:controller
        msg='starting gcal query '+req
        print(msg) # debug
        try:
            response = requests.get(req, headers = headers)
        except:
            msg='gcal query '+req+' failed!'
            log.warning(msg)
            traceback.print_exc()
            print(msg)
            return 1 # kui ei saa gcal yhendust, siis lopetab ja vana ei havita!

        try:
            print('response.content', response.content)
            if '[]' in str(response.content):
                log.warning('invalid content for calendar, keeping the existing calendar table')
                s.print_table('calendar')
                return 2
            else:
                events = eval(response.content) # string to list
            
        except:
            msg='getting calendar events failed for host_id '+self.host_id
            print(msg)
            #log.warning(msg)
            traceback.print_exc() # debug
            return 1 # kui ei saa normaalseid syndmusi, siis ka lopetab

        #print(repr(events)) # debug
        Cmd = "BEGIN IMMEDIATE TRANSACTION"
        try:
            conn.execute(Cmd)
            Cmd="delete from calendar"
            conn.execute(Cmd)
            for event in events:
                #print('event',event) # debug
                columns=str(list(event.keys())).replace('[','(').replace(']',')')
                values=str(list(event.values())).replace('[','(').replace(']',')')
                Cmd = "insert into calendar"+columns+" values"+values
                #print(Cmd) # debug
                conn.execute(Cmd)
            conn.commit()
            msg='calendar table updated'
            print(msg)
            #log.warning(msg)
            return 0
        except:
            msg='delete + insert to calendar table failed!'
            log.warning(msg)
            traceback.print_exc() # debug
            return 1 # kui insert ei onnestu, siis ka delete ei toimu


    def check(self, title): # set a new setpoint if found in table calendar (sharing database connection with setup)
        ''' Returns the current value for the event with title from the local event buffer '''
        tsnow = int(time.time())
        value='' # local string value
        if title == '':
            return None

        Cmd = "BEGIN IMMEDIATE TRANSACTION"
        try:
            conn.execute(Cmd)
            Cmd="select value,timestamp from calendar where title='"+title+"' and timestamp+0<"+str(tsnow)+" order by timestamp asc" # find the last passed event value
            self.cur.execute(Cmd)
            for row in self.cur:
                value = row[0] # overwrite with the last value before now
                ts = row[1]
                log.debug('cal tsnow '+str(tsnow)+', ts '+str(ts)+', value '+str(value)) # debug.  viimane value jaab iga title jaoks kehtima
            conn.commit()
            return str(value) # last one for given title becomes effective. can be empty string too, then use default value for setpoint related to title
        except:
            traceback.print_exc()
            return None