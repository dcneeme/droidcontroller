import os, traceback, sqlite3, time
from droidcontroller.sqlgeneral import * # SQLgeneral  
s=SQLgeneral()

''' Class and methods to read events from monitoring server handing access to google calendar '''

class Gcal:
    ''' Class containing methods to read events from monitoring server handing access to google calendar '''

    def __init__(self, host_id, days=3):
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
            #log.warning(msg)
            traceback.print_exc()
            print(msg)
            return 1 # kui ei saa gcal yhendust, siis lopetab ja vana ei havita!

        try:
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
            print(msg)
            #log.warning(msg)
            traceback.print_exc() # debug
            return 1 # kui insert ei onnestu, siis ka delete ei toimu
            
            
    def check(self, title): # set a new setpoint if found in table calendar (sharing database connection with setup)
        ''' Returns the current value for the event with title from the local event buffer '''
        ts = time.time()
        value='' # local string value
        if title == '':
            return None
        
        Cmd = "BEGIN IMMEDIATE TRANSACTION"
        try:
            conn.execute(Cmd)
            Cmd="select value from calendar where title='"+title+"' and timestamp+0<"+str(ts)+" order by timestamp asc" # find the last passed event value
            self.cur.execute(Cmd)
            for row in self.cur:
                value=row[0] # overwrite with the last value before now
                #print(Cmd,', value',value) # debug. voib olla mitu rida, viimane value jaab iga title jaoks kehtima
            conn.commit()
            return value # last one for given title becomes effective. can be empty string too, then use default value for setpoint related to title
        except:
            traceback.print_exc()
            return None