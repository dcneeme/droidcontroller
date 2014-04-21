# to be imported to access modbus registers as counters
# 04.04.2014 OOP
# 05.04.2014 OOP
# 06.04.2014 counter grousp with sequential regadd range, optimized read done
# 15.04.2014 added ask_counters()
# 19.05.2014 counters.sql ts tohib muuta ainult siis, kui raw muutus! niisama lugemine ei muuda ts!!!
#            siis saab voimsust arvestada aja alusel ka yhe impulsilise kasvu alusel, kui piisavalt tihti lugeda!


from sqlgeneral import * # SQLgeneral  / vaja ka time,mb, conn jne
s=SQLgeneral() # init sisse?
from counter2power import *  # Counter2Power() handles power calculation based on pulse count increments
import time

class Cchannels(SQLgeneral): # handles counters registers and tables
    ''' Access to io by modbus analogue register addresses (and also via services?).
        Modbus client must be opened before.
        Able to sync input and output channels and accept changes to service members by their sta_reg code
    '''

    def __init__(self, in_sql = 'counters.sql', readperiod = 10, sendperiod = 30):
        self.setReadPeriod(readperiod)
        self.setSendPeriod(sendperiod)
        self.in_sql = in_sql.split('.')[0]
        self.s = SQLgeneral()
        self.cp=[] # possible counter2value calculation instances
        self.Initialize()


    def setReadPeriod(self, invar):
        ''' Set the refresh period, executes sync if time from last read was earlier than period ago '''
        self.readperiod = invar


    def setSendPeriod(self, invar):
        ''' Set the refresh period, executes sync if time from last read was earlier than period ago '''
        self.sendperiod = invar


    def sqlread(self, table):
        self.s.sqlread(table) # read dichannels


    def Initialize(self): # before using this create s=SQLgeneral()
        ''' initialize delta t variables, create tables and modbus connection '''
        self.ts = round(time.time(),1)
        self.ts_read = self.ts # time of last read
        self.ts_send = self.ts -10 # time of last reporting
        self.sqlread(self.in_sql) # read counters table
        self.ask_counters() # ask server about the last known values of the counter related services


    def ask_counters(self): # use on init, send ? to server
        ''' Queries last counter service values from the server '''
        Cmd="select val_reg from "+self.in_sql+" group by val_reg" # process and report by services
        #print "Cmd=",Cmd
        cur=conn.cursor()
        cur.execute(Cmd) # getting services to be read and reported
        for row in cur: # possibly multivalue service members
            val_reg=row[0]
            udp.udpsend(val_reg+':?\n') # wo status to uniscada server
        conn.commit()
        return 0


    def restore_counter(self,register): # one at the time
        ''' decode values from server for set_counter(). some values are counted, but some may be setup values! '''
        #FIXME!
        return 0


    def set_counter(self, value = 0, **kwargs): # mba,regadd,val_reg,member   # one counter to be set. check wcount from counters table
        ''' sets ONE counter value, any wordlen (number of registers,must be defined in counters.sql) '''
        #val_reg=''  # arguments to use a subset of them
        #member=0
        #mba=0
        #regadd=0
        #wcount=0
        value=(int(value)&0xFFFFFFFF) # to make sure the value to write is 32 bit integer
        cur=conn.cursor()
        try:
            mba=kwargs['mba']
            regadd=kwargs['regadd']
            Cmd="select val_reg,member,mba,regadd,wcount,x2,y2 from counters where mba='"+str(mba)+"' and regadd='"+str(regadd)+"' and mbi="+str(mbi)
            #print(Cmd) # debug
        except:
            try:
                kwargs.get('val_reg','C1V')
                kwargs.get('member',1)

            except:
                print('invalid parameters for set_counter()')
                return 2

        try:
            cur.execute(Cmd)
            for srow in cur:
                val_reg=srow[0]
                member=int(srow[1]) # replaces if missing
                mba=int(srow[2]) # replaces if missing
                regadd=int(srow[3])
                wcount=int(srow[4])
                # x2 y2 for autoscale (5,6)

            if wcount == 2: # normal counter
                mb[mbi].write(mba,regadd,count=2, values=[value&4294901760,value&65535]) #
                return 0
            else:
                if wcount == -2: # barionet counter, MSW must be written first
                    mb[mbi].write(mba,address=regadd, count=2,values=[value&65535, value&4294901760])
                    return 0
                else:
                    print('unsupported counter configuration!',mba,regadd,wcount)
                    return 1
        except:  # set failed
            msg='failed restoring counter register '+str(mba)+'.'+str(regadd)
            #syslog(msg)
            print(msg)
            traceback.print_exc()
            return 1




    def read_counter_grp(self,mba,regadd,count,wcount,mbi=0): # using self,in_sql as the table to store in.
        ''' Reads sequential register group, process numbers according to counter size and store raw into table self.in_sql. Inside transaction!
            Compares the now value from mobdbus register with old value in the table. If changed, ts is set to the modbus readout time self.ts.
        '''
        step=abs(wcount)
        cur=conn.cursor()
        oraw=0
        if step == 0:
            print('illegal wcount',wcount,'in read_counter_grp()')
            return 2

        msg='reading data for counter group from mba '+str(mba)+', regadd '+str(regadd)+', count '+str(count)+', wcount '+str(wcount)+', mbi '+str(mbi)
        #print(msg) # debug
        if count>0 and mba<>0 and wcount<>0:
            result = mb[mbi].read(mba, regadd, count=count, type='h') # client.read_holding_registers(address=regadd, count=1, unit=mba)
            msg=msg+', result: '+str(result)
            print(msg) # debug
        else:
            print('invalid parameters for read_counter_grp()!',mba,regadd,count,wcount,mbi)
            return 2

        if result != None:
            try:
                for i in range(count/step): # counter processing loop. tuple to table rows. tuple len is twice count!
                    tcpdata=0
                    if wcount == 2:
                        tcpdata = 65536*result[step*i]+result[step*i+1]
                        #print('normal counter',str(i),'result',tcpdata) # debug
                    elif wcount == -2:
                        tcpdata = 65536*result[step*i+1]+result[step*i]  # wrong word order for counters in barionet!
                        #print('barionet counter',str(i),'result',tcpdata) # debug
                    else: # something else
                        print('unsupported counter word size',wcount)
                        return 1

                    Cmd="select raw from "+self.in_sql+" where mbi="+str(mbi)+" and mba='"+str(mba)+"' and regadd='"+str(regadd+i*step)+"' group by mbi,mba,regadd"
                    # get the old value to compare with new. can be multiple rows, group to single
                    cur.execute(Cmd)
                    for row in cur:
                        oraw=int(row[0]) if row[0] !='' else 0
                    if tcpdata != oraw:
                        Cmd="UPDATE "+self.in_sql+" set raw='"+str(tcpdata)+"', ts='"+str(self.ts)+"' where mba='"+str(mba)+"' and regadd='"+str(regadd+i*step)+"'" # koigile korraga
                        #print('i',i,Cmd) # debug
                        conn.execute(Cmd)
                return 0
            except:
                traceback.print_exc()
                return 1
        else:
            msg='counter data processing FAILED for mbi,mba,regadd,count '+str(mbi)+', '+str(mba)+', '+str(regadd)+', '+str(count)
            print(msg)
            return 1



    def read_counters(self): # read all defined counters, usually 32 bit / 2 registers.
        ''' Must read the counter registers by sequential regadd blocks if possible (if regadd increment == wcount.
            Also converts the raw data (incl member rows wo mba) into services and sends away to UDPchannel.
            '''
        respcode=0
        mba=0
        val_reg=''
        sta_reg=''
        status=0
        value=0
        lisa=''
        desc=''
        comment=''
        #mcount=0
        Cmd1=''
        self.ts = round(time.time(),2)
        ts_created=self.ts # selle loeme teenuse ajamargiks
        cur=conn.cursor()
        cur3=conn.cursor()
        bmba=0 # mba for sequential register address block
        bfirst=0 # sequential register block start
        blast=0
        wcount=0
        bwcount=0
        bcount=0
        tcpdata=0
        sent=0

        try:
            Cmd="BEGIN IMMEDIATE TRANSACTION" # conn3
            conn.execute(Cmd)
            Cmd="select mba,regadd,wcount,mbi from "+self.in_sql+" where mba<>'' and regadd<>'' group by mbi,mba,regadd" # tsykkel lugemiseks, tuleks regadd kasvavasse jrk grupeerida
            cur.execute(Cmd) # selle paringu alusel raw update, hiljem teha value arvutused iga teenuseliikme jaoks eraldi
            for row in cur: # these groups can be interrupted into pieces to be queried!
                mba=int(row[0]) if int(row[0]) != '' else 0
                regadd=int(row[1]) if int(row[0]) != '' else 0
                wcount=int(row[2])  if int(row[0]) != '' else 0 # wordcount for the whole group
                mbi=int(row[3]) if int(row[0]) != '' else 0 # modbus connection indexed
                #print 'found counter mbi,mba,regadd,wcount',mbi,mba,regadd,wcount # debug
                if bfirst == 0:
                    bfirst = regadd
                    blast = regadd
                    bwcount = wcount # wcount can change with next group
                    bcount=abs(wcount) # word count is the count
                    bmba=mba
                    bmbi=mbi
                    #print('counter group mba '+str(bmba)+' start ',bfirst) # debug
                else: # not the first
                    if mbi == bmbi and mba == bmba and regadd == blast+abs(wcount): # sequential group still growing
                        blast = regadd
                        bcount=bcount+abs(wcount) # increment by word size
                        #print('counter group end shifted to',blast) # debug
                    else: # a new group started, make a query for previous
                        #print('counter group end detected at regadd',blast,'bcount',bcount) # debugb
                        #print('going to read counter registers from',bmba,bfirst,'to',blast,'regcount',bcount) # debug
                        self.read_counter_grp(bmba,bfirst,bcount,bwcount,bmbi) # reads and updates table with previous data
                        bfirst = regadd # new grp starts immediately
                        blast = regadd
                        #bwcount = wcount # does not change inside group
                        bcount=abs(wcount) # new read piece started
                        bwcount=wcount
                        bmba=mba
                        bmbi=mbi
                        #print('counter group mba '+str(bmba)+' start ',bfirst) # debug

            if bfirst != 0: # last group yet unread
                #print('counter group end detected at regadd',blast) # debug
                #print('going to read counter registers from',bmba,bfirst,'to',blast,'regcount',bcount) # debug
                self.read_counter_grp(bmba,bfirst,bcount,bwcount,bmbi) # reads and updates table

            # raw sync done.



            # now process raw -> value and find status BY SERVICES. service loop begins.
            #power calcultions happens below too, for each service , not for each counter!

            Cmd="select val_reg from "+self.in_sql+" group by val_reg" # process and report by services
            #print "Cmd=",Cmd
            cur.execute(Cmd) # getting services to be read and reported
            cpi=-1 # counter2power instance index, increase only if with cfg weight 64 true
            for row in cur: # possibly multivalue service members
                lisa='' # string to put space-separated values in
                val_reg=''
                sta_reg=''
                status=0 #
                value=0
                val_reg=row[0] # service value register name
                sta_reg=val_reg[:-1]+"S" # status register name
                #print 'reading counter values for val_reg',val_reg,'with',mcount,'members' # temporary
                Cmd3="select * from "+self.in_sql+" where val_reg='"+val_reg+"' order by member asc" # chk all members, also virtual!
                #print Cmd3 # debug
                cur3.execute(Cmd3)

                for srow in cur3: # members for one counter svc
                    #print srow # debug
                    mba=0 # local here
                    regadd=0
                    member=0
                    cfg=0
                    x1=0
                    x2=0
                    y1=0
                    y2=0
                    outlo=0
                    outhi=0
                    ostatus=0 # eelmine
                    #tvalue=0 # test
                    raw=0 # unconverted reading
                    #oraw=0 # previous unconverted reading
                    ovalue=0 # previous converted value
                    value=0 # latest (converted) value
                    ots=0
                    avg=0 # averaging strength, effective from 2
                    desc='' # description for UI
                    comment='' # comment internal
                    result=[]

                    # 0       1     2     3     4   5  6  7  8  9    10     11  12    13   14   15    16  17   18
                    #mba,regadd,val_reg,member,cfg,x1,x2,y1,y2,outlo,outhi,avg,block,raw,value,status,ts,desc,comment  # counters
                    mba=int(srow[0]) if srow[0] != '' else 0 # modbus address
                    regadd=int(srow[1]) if srow[1] != '' else 0 # must be int! can be missing
                    val_reg=srow[2] # string
                    member=int(srow[3]) if srow[3] != '' else 0
                    cfg=int(srow[4]) if srow[4] != '' else 0 # config byte
                    x1=int(srow[5]) if srow[5] != '' else 0
                    x2=int(srow[6]) if srow[6] != ''  else 0
                    y1=int(srow[7]) if srow[7] != '' else 0
                    y2=int(srow[8]) if srow[8] != '' else 0
                    outlo=int(srow[9]) if srow[9] != '' else 0
                    outhi=int(srow[10]) if srow[10] != '' else 0
                    avg=int(srow[11]) if srow[11] != '' else 0 #  averaging strength, effective from 2
                    #if srow[12] != '': # block
                    #  block=int(srow[12]) # block / error count
                    # updated before raw reading
                    raw=int(srow[13]) if srow[13] != '' else 0
                    # previous converted value
                    ovalue=eval(srow[14]) if srow[14] != '' else 0 # not updated above!
                    ostatus=int(srow[15]) if srow[15] != '' else 0
                    ots=eval(srow[16]) if srow[16] != '' else self.ts
                    #desc=srow[17]
                    #comment=srow[18]
                    #wcount=srow[19] # word count
                    #print('got from '+self.in_sql+' raw,ovalue',raw,ovalue) # debug

                    if lisa != '':
                        lisa=lisa+" "

                    # CONFIG BYTE BIT MEANINGS
                    # 1 - below outlo warning,
                    # 2 - below outlo critical,
                    # NB! 3 - not to be sent  if value below outlo
                    # 4 - above outhi warning
                    # 8 - above outhi critical

                    # 16 - to be zeroed regularly, see next bits for when NOT IN USE! done by server
                    # 32  - midnight if 1, month change if 0   NOT IN USE
                    # 64 - power to be counted based on count increase and time period between counts
                    # 128 - OFF-state not used in lolimit, OFF is equal to in-range??

                    if x1 != x2 and y1 != y2: # seems like normal input data
                        value=(raw-x1)*(y2-y1)/(x2-x1)
                        value=int(y1+value) # integer values to be reported only
                    else:
                        print("read_counters val_reg",val_reg,"member",member,"ai2scale PARAMETERS INVALID:",x1,x2,'->',y1,y2,'conversion not used!')
                        # jaab selline value nagu oli


                    if avg>1 and abs(value-ovalue)<value/2:  # averaging the readings. big jumps (more than 50% change) are not averaged.
                        value=int(((avg-1)*ovalue+value)/avg) # averaging with the previous value, works like RC low pass filter
                        #print('counter avg on, value became ',value) # debug

                   # print('end processing counter',val_reg,'member',member,'raw',raw,' value',value,' ovalue',ovalue,', avg',avg) # debug


                    #POWER?
                    if (cfg&64): # power, increment to be calculated! divide increment to time from the last reading to get the power
                        cpi=cpi+1 # counter2power index
                        try:
                            if self.cp[cpi]:
                                pass # instance already exists
                        except:
                            self.cp.append(Counter2Power(val_reg,member,off_tout = 120)) # another Count2Power instance. 120S  = 30W threshold if 1WS per pulse
                            print('Counter2Power() instance cp['+str(cpi)+'] created')
                        res=self.cp[cpi].calc(ots, value, ts_now = self.ts) # power calculation based on counter increase
                        value=res[0]
                        print('got result from cp['+str(cpi)+']: '+str(res))  # debug
                    else: # normal counter
                        if value == 0 and ovalue >0: # possible pic reset. perhaps value <= 100?
                            msg='restoring lost content for counter '+str(mba)+'.'+str(regadd)+':2 to become '+str(ovalue)+' again instead of '+str(value)
                            #syslog(msg)
                            print(msg)
                            value=ovalue # +value # restoring based on ovalue and new count
                            self.set_counter(value,mba,regadd)


                    Cmd="update "+self.in_sql+" set value='"+str(value)+"' where val_reg='"+val_reg+"' and member='"+str(member)+"'"
                    conn.execute(Cmd) # new value set in sql table


                    # STATUS SET. check limits and set statuses based on that
                    # returning to normal with hysteresis, take previous value into account
                    status=0 # initially for each member
                    if value>outhi: # yle ylemise piiri
                        if (cfg&4) and status == 0: # warning if above the limit
                            status=1
                        if (cfg&8) and status<2: # critical if  above the limit
                            status=2
                        if (cfg&12) == 12: # unknown if  above the limit
                            status=3
                    else: # return to normal with hysteresis
                        if value<outhi-0.05*(outhi-outlo):
                            status=0 # normal again

                    if value<outlo: # below lo limit
                        if (cfg&1) and status == 0: # warning if below lo limit
                            status=1
                        if (cfg&2) and status<2: # warning  if below lo limit
                            status=2
                        if (cfg&3) == 3: # unknown  if below lo limit
                            status=3
                    else: # return
                        if value>outlo+0.05*(outhi-outlo):
                            status=0 # normal again

                    #print('status for counter svc',val_reg,status,'due to cfg',cfg,'and value',value,'while limits are',outlo,outhi) # debug

                    #if value<ovalue and ovalue < 4294967040: # this will restore the count increase during comm break



                    lisa=lisa+str(value) # members together into one string


                # sending service to buffer
                if self.ts - self.ts_send>self.sendperiod:
                    sent=1
                    sendtuple=[sta_reg,status,val_reg,lisa]
                    #print('counter svc - going to report',sendtuple)  # debug
                    udp.send(sendtuple) # to uniscada instance
            if sent == 1:
                self.ts_send = self.ts
            sent = 0
            conn.commit() # counters transaction end
            return 0

        except: # end reading counters
            msg='problem with counters read or processing: '+str(sys.exc_info()[1])
            print(msg)
            #syslog(msg)
            traceback.print_exc()
            sys.stdout.flush()
            time.sleep(1)
            return 1

    #read_counters end #############




    def doall(self): # do this regularly, executes only if time is is right
        ''' Reads and possibly reports counters on time if executed regularly '''
        self.ts = round(time.time(),1)
        if self.ts - self.ts_read>self.readperiod:
            self.ts_read = self.ts
            self.read_counters() # also includes ts_sent test and reporting

        return 0
