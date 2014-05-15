# to be imported to access modbus registers as counters
# 04.04.2014 OOP
# 05.04.2014 OOP
# 06.04.2014 counter grousp with sequential regadd range, optimized read done
# 15.04.2014 added ask_counters()
# 19.05.2014 counters.sql ts tohib muuta ainult siis, kui raw muutus! niisama lugemine ei muuda ts!!!
#            siis saab voimsust arvestada aja alusel ka yhe impulsilise kasvu alusel, kui piisavalt tihti lugeda!
# 25.4.2014 power metering ok. need to add on/off svc

# use do_read_all() and report_all() for external use after importing. or doall()


from droidcontroller.sqlgeneral import * # SQLgeneral  / vaja ka time,mb, conn jne
s=SQLgeneral() # init sisse?
from droidcontroller.counter2power import *  # Counter2Power() handles power calculation based on pulse count increments

import time

class Cchannels(SQLgeneral): # handles counters registers and tables
    ''' Access to io by modbus analogue register addresses (and also via services?).
        Modbus client must be opened before.
        Able to sync input and output channels and accept changes to service members by their sta_reg code
    '''

    def __init__(self, in_sql = 'counters.sql', readperiod = 1, sendperiod = 30):
        self.setReadPeriod(readperiod)
        self.setSendPeriod(sendperiod)
        self.in_sql = in_sql.split('.')[0]
        #self.s = SQLgeneral()
        self.cp=[] # possible counter2value calculation instances
        self.Initialize()


    def setReadPeriod(self, invar):
        ''' Set the refresh period, executes sync if time from last read was earlier than period ago '''
        self.readperiod = invar


    def setSendPeriod(self, invar):
        ''' Set the refresh period, executes sync if time from last read was earlier than period ago '''
        self.sendperiod = invar


    def sqlread(self, table):
        s.sqlread(table) # read dichannels


    def Initialize(self): # before using this create s=SQLgeneral()
        ''' initialize delta t variables, create tables and modbus connection '''
        self.ts = round(time.time(),1)
        self.ts_read = self.ts # time of last read
        self.ts_send = self.ts -10 # time of last reporting
        self.sqlread(self.in_sql) # read counters table
        self.ask_counters() # ask server about the last known values of the counter related services


    def ask_counters(self): # use on init, send ? to server
        ''' Queries last counter service values from the server '''
        Cmd="select val_reg,max(cfg) from "+self.in_sql+" group by val_reg" # process and report by services
        #print "Cmd=",Cmd
        cur=conn.cursor()
        cur.execute(Cmd) # getting services to be read and reported
        for row in cur: # possibly multivalue service members
            val_reg=row[0]
            cfg=int(row[1]) if row[1] != '' else 0
            if cfg<64: # exclude the services that are not cumulative counters
                udp.udpsend(val_reg+':?\n') # ask last value from uniscada server if counter, not power related (cfg<64)
        conn.commit()
        return 0


    def restore_counter(self,register): # one at the time
        ''' decode values from server for set_counter(). some values are counted, but some may be setup values! '''
        #FIXME!
        return 0


    def set_counter(self, value = 0, **kwargs): # value, mba,regadd,mbi,val_reg,member   # one counter to be set. check wcount from counters table
        ''' sets ONE counter value, any wordlen (number of registers,must be defined in counters.sql) '''
        val_reg=''  # arguments to use a subset of them
        member=0
        mba=0
        mbi=0
        regadd=0
        wcount=0
        #value=value
        cur=conn.cursor()
        x2=0
        y2=0
        Cmd=''
        try: # is is mba or val_reg based addressing in use?
            mba=kwargs['mba']
            regadd=kwargs['regadd']
            mbi=kwargs['mbi']
            wcount=kwargs['wcount']
            x2=kwargs['x2']
            y2=kwargs['y2']
            # if this fails, svc_name and member must be given as parameters
        except:
            try:
                kwargs.get('val_reg')
                kwargs.get('member')
                Cmd="select mbi,mba,regadd,wcount,x2,y2 from "+self.in_sql+" where val_reg='"+val_reg+"' and member='"+str(member)+"'"
                print(Cmd) # debug
                cur.execute(Cmd) # what about commit()? FIXME
                for row in cur:
                    print(row) # debug
                    mbi=row[0]
                    mba=int(row[1]) if row[1] != '' else 0
                    regadd=int(row[2]) if row[2] != '' else 0
                    wcount=int(row[3]) if row[3] != '' else 0
                    x2==int(row[4]) if row[4] != '' else 0
                    y2==int(row[5]) if row[5] != '' else 0
                    
            except:
                print('invalid parameters for set_counter()',kwargs)
                return 2
        
        print('mbi,mba,regadd,wcount,x2,y2',mbi,mba,regadd,wcount,x2,y2) # debug
        if x2 != 0 and y2 != 0: #convert
            value=round(1.0*value*x2/y2)
        else:
            print('invalid scaling x2,y2',x2,y2)
        
        value=(int(value)&0xFFFFFFFF) # to make sure the value to write is 32 bit integer    
        try:
            if wcount == 2: # normal counter, type h
                mb[mbi].write(mba, regadd, values=[(value&0xFFFF0000)>>16,(value&0xFFFF)]) #
                return 0
            else:
                if wcount == -2: # barionet counter, MSW must be written first
                    mb[mbi].write(mba, regadd, values=[(value&0xFFFF), (value&0xFFFF0000)>>16])
                    return 0
                else:
                    print('unsupported counter configuration! mba,regadd,wcount',mba,regadd,wcount)
                    return 1
        except:  # set failed
            msg='failed restoring counter register '+str(mba)+'.'+str(regadd)
            #syslog(msg)
            print(msg)
            traceback.print_exc()
            return 1
        # no need for commit, this method is used in transaction



    def read_counter_grp(self,mba,regadd,count,wcount,mbi=0): # using self,in_sql as the table to store in.
        ''' Reads sequential register group, process numbers according to counter size and store raw into table self.in_sql. Inside transaction!
            Compares the now value from mobdbus register with old value in the table. If changed, ts is set to the modbus readout time self.ts.

            Add here counter state recovery if suddenly zeroed
            #    if value == 0 and ovalue >0: # possible pic reset. perhaps value <= 100?
            #        msg='restoring lost content for counter '+str(mba)+'.'+str(regadd)+':2 to become '+str(ovalue)+' again instead of '+str(value)
            #        #syslog(msg)
            #        print(msg)
            #        self.set_counter(value=ovalue, mba=mba, regadd=regadd, mbi=mbi, wcount=wcount, x2=x2, y2=y2) # does not contain commit()!
            #this above should be fixed. value is already saved, put it there!
            FIMXME:  do not attempt to access counters that are not defined in devices.sql! this should be an easy way to add/remove devices.
        '''
        step=int(abs(wcount))
        cur=conn.cursor()
        oraw=0
        if step == 0:
            print('illegal wcount',wcount,'in read_counter_grp()')
            return 2

        msg='reading data for counter group from mba '+str(mba)+', regadd '+str(regadd)+', count '+str(count)+', wcount '+str(wcount)+', mbi '+str(mbi)+', step '+str(step)
        if count>0 and mba != 0 and wcount != 0:
            try:
                if mb[mbi]:
                    result = mb[mbi].read(mba, regadd, count=count, type='h') # client.read_holding_registers(address=regadd, count=1, unit=mba)
                    msg=msg+', result: '+str(result)
                    #print(msg) # debug
            except:
                print('device mbi,mba',mbi,mba,'not defined in devices.sql')
                return 2
        else:
            print('invalid parameters for read_counter_grp()!',mba,regadd,count,wcount,mbi)
            return 2

        if result != None: # got something from modbus register
            try:
                for i in range(int(count/step)): # counter processing loop. tuple to table rows. tuple len is twice count! int for py3 needed
                    tcpdata=0
                    #print('counter_grp debug: i',i,'step',step,'results',result[step*i],result[step*i+1]) # debug
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
                        oraw=int(row[0]) if row[0] !='' else -1
                    if tcpdata != oraw or oraw == -1: # update only if change needed or empty so far
                        Cmd="UPDATE "+self.in_sql+" set raw='"+str(tcpdata)+"', ts='"+str(self.ts)+"' where mba='"+str(mba)+"' and regadd='"+str(regadd+i*step)+"'" # koigile korraga
                        #print('counters i',i,Cmd) # debug
                        conn.execute(Cmd)
                return 0
            except:
                traceback.print_exc()
                return 1
        else:
            msg='counter grp data processing FAILED for mbi,mba,regadd,count '+str(mbi)+', '+str(mba)+', '+str(regadd)+', '+str(count)
            print(msg)
            return 1



    def read_all(self): # read all defined modbus counters to sql, usually 32 bit / 2 registers.
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
            Cmd="select mba,regadd,wcount,mbi from "+self.in_sql+" where mba != '' and regadd != '' group by mbi,mba,regadd" # tsykkel lugemiseks, tuleks regadd kasvavasse jrk grupeerida
            cur.execute(Cmd) # selle paringu alusel raw update, hiljem teha value arvutused iga teenuseliikme jaoks eraldi
            for row in cur: # these groups can be interrupted into pieces to be queried!
                mba=int(row[0]) if int(row[0]) != '' else 0
                regadd=int(row[1]) if int(row[1]) != '' else 0
                wcount=int(row[2]) if int(row[2]) != '' else 0 # wordcount for the whole group
                mbi=int(row[3]) if int(row[3]) != '' else 0 # modbus connection indexed
                #print 'found counter mbi,mba,regadd,wcount',mbi,mba,regadd,wcount # debug
                if bfirst == 0:
                    bfirst = regadd
                    blast = regadd
                    bwcount = wcount # wcount can change with next group
                    bcount=int(abs(wcount)) # word count is the count
                    bmba=mba
                    bmbi=mbi
                    #print('counter group mba '+str(bmba)+' start ',bfirst) # debug
                else: # not the first
                    if mbi == bmbi and mba == bmba and regadd == blast+abs(wcount): # sequential group still growing
                        blast = regadd
                        bcount=bcount+int(abs(wcount)) # increment by word size
                        #print('counter group end shifted to',blast) # debug
                    else: # a new group started, make a query for previous
                        #print('counter group end detected at regadd',blast,'bcount',bcount, 'mbi',mbi,'bmbi',bmbi) # debugb
                        #print('going to read non-last counter group, registers from',bmba,bfirst,'to',blast,'regcount',bcount) # debug
                        self.read_counter_grp(bmba,bfirst,bcount,bwcount,bmbi) # reads and updates table with previous data #####################  READ MB  ######
                        bfirst = regadd # new grp starts immediately
                        blast = regadd
                        #bwcount = wcount # does not change inside group
                        bcount=int(abs(wcount)) # new read piece started
                        bwcount=wcount
                        bmba=mba
                        bmbi=mbi
                        #print('counter group mba '+str(bmba)+' start ',bfirst) # debug

            if bfirst != 0: # last group yet unread
                #print('counter group end detected at regadd',blast) # debug
                #print('going to read last counter group, registers from',bmba,bfirst,'to',blast,'regcount',bcount) # debug
                self.read_counter_grp(bmba,bfirst,bcount,bwcount,bmbi) # reads and updates table with previous data #####################  READ MB  ######

            # raw sync (from modbus to sql) done.



            # now process raw -> value and find status BY SERVICES. service loop begins.
            #power calcultions happens below too, for each service , not for each counter!

            Cmd="select val_reg from "+self.in_sql+" group by val_reg" # process and report by services
            #print "Cmd=",Cmd
            cur.execute(Cmd) # getting services to be read and reported
            cpi=-1 # counter2power instance index, increase only if with cfg weight 64 true
            for row in cur: # SERVICES LOOP
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
                chg=0 # service change flag based on member state or value change
                
                for srow in cur3: # members for one counter svc
                    #print srow # debug
                    mbi=0
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
                    block=int(srow[12]) if srow[12] != '' else 0  # threshold in s for OFF state
                    # updated before raw reading
                    raw=int(srow[13]) if srow[13] != '' else None
                    # previous converted value
                    ovalue=eval(srow[14]) if srow[14] != '' else 0 # not updated above!
                    ostatus=int(srow[15]) if srow[15] != '' else 0
                    ots=eval(srow[16]) if srow[16] != '' else self.ts
                    #desc=srow[17]
                    #comment=srow[18]
                    wcount=int(srow[19]) if srow[19] != '' else 0  # word count
                    mbi=srow[20] # int
                    #print('got from '+self.in_sql+' raw,ovalue',raw,ovalue) # debug

                    if lisa != '':
                        lisa=lisa+" "

                    # CONFIG BYTE BIT MEANINGS
                    # 1 - below outlo warning,
                    # 2 - below outlo critical,
                    # NB! 3 - not to be sent  if value below outlo
                    # 4 - above outhi warning
                    # 8 - above outhi critical

                    # 16 - - immediate notification on status change (USED FOR STATE FROM POWER)
                    # 32  - limits to state inversion
                    # 64 - power to be counted based on count increase and time period between counts
                    # 128 -  state from power flag
                    
                    if raw != None: # valid data for either energy or power value
                        #POWER?
                        if (cfg&64): # power, increment to be calculated! divide increment to time from the last reading to get the power
                            cpi=cpi+1 # counter2power index
                            try:
                                if self.cp[cpi]:
                                    pass # instance already exists
                            except:
                                self.cp.append(Counter2Power(val_reg,member,off_tout = block)) # another Count2Power instance. 100s  = 36W threshold if 1000 imp per kWh
                                print('Counter2Power() instance cp['+str(cpi)+'] created for pwr svc '+val_reg+' member '+str(member)+', off_tout '+str(block))
                            res=self.cp[cpi].calc(ots, raw, ts_now = self.ts) # power calculation based on raw counter increase
                            raw=res[0]
                            #print('got result[0] from cp['+str(cpi)+']: '+str(res))  # debug
                 
                        # on-off?
                        #if (cfg&128): # 
                        if (cfg&128) > 0: # 
                            cpi=cpi+1 # counter2power index on /off jaoks
                            try:
                                if self.cp[cpi]:
                                    pass # instance already exists
                            except:
                                self.cp.append(Counter2Power(val_reg,member,off_tout = block)) # another Count2Power instance. 10s tout = 360W threshold if 1000 imp per kWh
                                print('Counter2Power() instance cp['+str(cpi)+'] created for state svc '+val_reg+' member '+str(member)+', off_tout '+str(block))
                            res=self.cp[cpi].calc(ots, raw, ts_now = self.ts) # power calculation based on raw counter increase
                            raw=res[1]
                            #print('got result from cp['+str(cpi)+']: '+str(res))  # debug
                            if res[2] != 0: # on/off change
                                chg=1 # immediate notification needed due to state change
                        
                        
                        # SCALING
                        if raw != None and x1 != x2 and y1 != y2: # seems like normal input data
                            value=(raw-x1)*(y2-y1)/(x2-x1)
                            value=int(round(y1+value)) # integer values to be reported only
                        else:
                            #print("read_counters val_reg",val_reg,"member",member,"raw",raw,"ai2scale PARAMETERS INVALID:",x1,x2,'->',y1,y2,'conversion not used!') # debug
                            value=None
                            

                        if value != None:
                            if avg>1 and abs(value-ovalue) < value/2:  # averaging the readings. big jumps (more than 50% change) are not averaged.
                                value=int(((avg-1)*ovalue+value)/avg) # averaging with the previous value, works like RC low pass filter
                                #print('counter avg on, value became ',value) # debug
                            #print('counter svc,val_reg,member,ovalue,value,avg,abs(value-ovalue),cfg',val_reg,member,ovalue,value,avg,abs(value-ovalue),cfg) # debug
                            Cmd="update "+self.in_sql+" set value='"+str(value)+"' where val_reg='"+val_reg+"' and member='"+str(member)+"'"
                            #print(Cmd) # debug
                            conn.execute(Cmd) # new value set in sql table ONLY if there was a valid result
                            if (cfg&256) and abs(value-ovalue) > value/10.0: # change more than 20% detected, use num w comma!
                                print('value change of more than 10% detected in '+val_reg+'.'+str(member)+', need to notify') # debug
                                chg=1
                            
                        # print('end processing counter',val_reg,'member',member,'raw',raw,' value',value,' ovalue',ovalue,', avg',avg) # debug

                    else:
                        if mba > 0 and member > 0:
                            print('ERROR: raw None for svc',val_reg,member) # debug
                            return 1

                # END OF SERVICE PROCESSING
                if chg == 1: # no matter up or down
                    print('immediate counter/power/status notification due to svc '+val_reg+' status or value change!') # debug
                    self.make_counter_svc(val_reg,sta_reg) # immediate notification due to state or value change
                   
            sys.stdout.write('c')
            return 0

        except: # end reading counters
            msg='problem with counters read or processing: '+str(sys.exc_info()[1])
            print(msg)
            #syslog(msg)
            traceback.print_exc()
            sys.stdout.flush()
            time.sleep(1)
            return 1

    #read_all end #############



    def report_all(self, svc = ''): # send the ai service messages to the monitoring server (only if fresh enough, not older than 2xappdelay). all or just one svc.
        ''' make all counter services (with status chk) based on counters members and send it away to UDPchannel '''
        mba=0 
        val_reg=''
        desc=''
        cur=conn.cursor()
        ts_created=self.ts # selle loeme teenuse ajamargiks

        try:
            Cmd="BEGIN IMMEDIATE TRANSACTION" # conn3, kogu selle teenustegrupiga (aichannels) tegelemine on transaction
            conn.execute(Cmd)
            if svc == '':  # all services
                Cmd="select val_reg from "+self.in_sql+" group by val_reg"
            else: # just one
                Cmd="select val_reg from "+self.in_sql+" where val_reg='"+svc+"'"
            cur.execute(Cmd)

            for row in cur: # services
                val_reg=row[0] # teenuse nimi
                sta_reg=val_reg[:-1]+"S" # nimi ilma viimase symbolita ja S - statuse teenuse nimi, analoogsuuruste ja temp kohta

                if self.make_counter_svc(val_reg,sta_reg) == 0: # successful svc insertion into buff2server
                    pass
                    #print('tried to report svc',val_reg,sta_reg)
                else:
                    print('make_counters FAILED to report svc',val_reg,sta_reg)
                    return 1 #cancel


            conn.commit() # aichannels transaction end
            return 0
            
        except:
            msg='PROBLEM with counters reporting '+str(sys.exc_info()[1])
            print(msg)
            #syslog(msg)
            traceback.print_exc()
            sys.stdout.flush()
            time.sleep(0.5)
            return 1




    def make_counter_svc(self,val_reg,sta_reg):  # should be generic, suitable both for aichannels and counters
        ''' make a single service record WITH STATUS based on existing values of the counter members and send it away to UDPchannel '''
        #FIXME! we do not need to calc value here, that has to be made with aquiry of every new raw!

        status=0 # initially
        cur=conn.cursor()
        lisa=''
        #print 'reading counters values for val_reg',val_reg,'with',mcount,'members' # ajutine

        Cmd="select * from "+self.in_sql+" where val_reg='"+val_reg+"'" # loeme yhe teenuse kogu info uuesti
        #print Cmd3 # ajutine
        cur.execute(Cmd) # another cursor to read the same table

        mts=0  # max timestamp for svc members. if too old, skip messaging to server
        for srow in cur: # service members
            #print repr(srow) # debug
            mba=-1 #
            regadd=-1
            member=0
            cfg=0
            x1=0
            x2=0
            y1=0
            y2=0
            outlo=0
            outhi=0
            ostatus=0 # eelmine
            #tvalue=0 # test, vordlus
            oraw=0
            ovalue=0 # previous (possibly averaged) value
            ots=0 # eelmine ts value ja status ja raw oma
            avg=0 # keskmistamistegur, mojub alates 2
            #desc=''
            #comment=''
            # 0       1     2     3     4   5  6  7  8  9    10     11  12    13  14   15     16  17    18
            #mba,regadd,val_reg,member,cfg,x1,x2,y1,y2,outlo,outhi,avg,block,raw,value,status,ts,desc,comment  # aichannels
            mba=int(srow[0]) if srow[0] != '' else 0   # must be int! will be -1 if empty (setpoints)
            regadd=int(srow[1]) if srow[1] != '' else 0  # must be int! will be -1 if empty
            val_reg=srow[2] # see on string
            member=int(srow[3]) if srow[3] != '' else 0
            cfg=int(srow[4]) if srow[4] != '' else 0 # konfibait nii ind kui grp korraga, esita hex kujul hiljem
            x1=int(srow[5]) if srow[5] != '' else 0
            x2=int(srow[6]) if srow[6] != '' else 0
            y1=int(srow[7]) if srow[7] != '' else 0
            y2=int(srow[8]) if srow[8] != '' else 0
            outlo=int(srow[9]) if srow[9] != '' else None
            outhi=int(srow[10]) if srow[10] != '' else None
            avg=int(srow[11]) if srow[11] != '' else 0  #  averaging strength, values 0 and 1 do not average!
            #block=int(srow[12]) if srow[12] != '' else 0 # - loendame siin vigu, kui kasvab yle 3? siis enam ei saada
            oraw=int(srow[13]) if srow[13] != '' else 0
            value=float(srow[14]) if srow[14] != '' else 0 # teenuseliikme vaartus
            ostatus=int(srow[15]) if srow[15] != '' else 0 # teenusekomponendi status - ei kasuta
            ots=eval(srow[16]) if srow[16] != '' else 0
            #desc=srow[17]
            #comment=srow[18]
            wcount=int(srow[19]) if srow[19] != '' else 0  # word count
            mbi=srow[20] # int
                    
            
            ################ sat
            
    
            # svc STATUS CHK. check the value limits and set the status, according to configuration byte cfg bits values
            # use hysteresis to return from non-zero status values
            status=0 # initially for each member
            if outhi != None:
                if value>outhi: # above hi limit
                    if (cfg&4) and status == 0: # warning
                        status=1
                    if (cfg&8) and status<2: # critical
                        status=2
                    if (cfg&12) == 12: #  not to be sent
                        status=3
                        #block=block+1 # error count incr
                else: # return with hysteresis 5%
                    if outlo != None:
                        if value>outlo and value<outhi-0.05*(outhi-outlo): # value must not be below lo limit in order for status to become normal
                            status=0 # back to normal
                        else:
                            if value<outhi: # value must not be below lo limit in order for status to become normal
                                status=0 # back to normal
                            
            if outlo != None:
                if value<outlo: # below lo limit
                    if (cfg&1) and status == 0: # warning
                        status=1
                    if (cfg&2) and status<2: # critical
                        status=2
                    if (cfg&3) == 3: # not to be sent, unknown
                        status=3
                        #block=block+1 # error count incr
                else: # back with hysteresis 5%
                    if outhi != None:
                        if value<outhi and value>outlo+0.05*(outhi-outlo):
                            status=0 # back to normal
                    else:
                        if value>outlo:
                            status=0 # back to normal
                            
            # CONFIG BYTE BIT MEANINGS
            # 1 - below outlo warning,
            # 2 - below outlo critical,
            # NB! 3 - not to be sent  if value below outlo
            # 4 - above outhi warning
            # 8 - above outhi critical

            # 16 - - immediate notification on status change (USED FOR STATE FROM POWER)
            # 32  - limits to state inversion
            # 64 - power to be counted based on count increase and time period between counts
            # 128 -  state from power flag
        #############                
            #print 'make counter_svc mba ots mts',mba,ots,mts # debug
            if mba>0:
                if ots>mts:
                    mts=ots # latest member timestamp for the current service
                    
            if lisa != '': # not the first member
                lisa=lisa+' ' # separator between member values
            lisa=lisa+str(int(round(value))) # adding member values into one string

        if (cfg&32): # this must be done in service loop end, for the final status, not for each member!
            print('status inversion enabled for val_reg',val_reg,'initial status',status,',cfg',cfg) # debug
            if status == 0: 
                status = (cfg&3) # normal becomes warning or critical
            else:
                status = 0 # not normal becomes normal
            #print('status inversion enabled for val_reg',val_reg,'final status',status) # debug
          
        # service done
        sendtuple=[sta_reg,status,val_reg,lisa] # sending service to buffer
        if not (cfg&512): # bit weight 512 means not to be sent, internal services
            udp.send(sendtuple) # to uniscada instance 
            #print('cchannels sent',sendtuple) # debug
        #else:
            #print('skipped send due to cfg 512',sendtuple) # debug
        return 0
        
        
    def doall(self): # do this regularly, executes only if time is is right
        ''' Does everything on time if executed regularly '''
        res=0
        self.ts = round(time.time(),2)
        if self.ts - self.ts_read > self.readperiod:
            self.ts_read = self.ts
            res=self.read_all() # koikide loendite lugemine
            
        if self.ts - self.ts_send > self.sendperiod:
            self.ts_send = self.ts
            res=res+self.report_all() # compile services and send away  / raporteerimine, harvem
            
        return res
   