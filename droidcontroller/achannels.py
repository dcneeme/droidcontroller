# to be imported to access modbus registers as analogue io 
# 03.04.2014 neeme
# 04.04.2014 it works, without periodical executuoin and without acces by svc reg 
# 06.04.2014 seguential register read for optimized reading, done


from sqlgeneral import * # SQLgeneral  / vaja ka time,mb, conn jne
s=SQLgeneral() # sql connection

class Achannels(SQLgeneral): # handles aichannels and aochannels tables
    ''' Access to io by modbus analogue register addresses (and also via services?). 
        Modbus client must be opened before.
        Able to sync input and output channels and accept changes to service members by their sta_reg code
    '''
    
    def __init__(self, in_sql = 'aichannels.sql', out_sql = 'aochannels.sql', readperiod = 10, sendperiod = 30):  # period for mb reading, renotify for udpsend
        self.setReadPeriod(readperiod)
        self.setSendPeriod(sendperiod)
        self.in_sql = in_sql.split('.')[0]
        self.out_sql = out_sql.split('.')[0]
        self.s = SQLgeneral()
        self.Initialize()


    def setReadPeriod(self, invar):
        ''' Set the refresh period, executes sync if time from last read was earlier than period ago '''
        self.readperiod = invar


    def setSendPeriod(self, invar):
        ''' Set the refresh period, executes sync if time from last read was earlier than period ago '''
        self.sendperiod = invar

        
    def sqlread(self,table):
        self.s.sqlread(table) # read dichannels
        
        
    def Initialize(self): # before using this create s=SQLgeneral()
        ''' initialize delta t variables, create tables and modbus connection '''
        self.ts = time.time()
        self.ts_read = self.ts # time of last read
        self.ts_send = self.ts -150 # time of last reporting
        self.sqlread(self.in_sql) # read aichannels
        self.sqlread(self.out_sql) # read aochannels if exist
        
        
    def read_ai_grp(self,mba,regadd,count): # using self,in_sql as the table to store in.
        ''' Read sequential register group and store raw into table self.in_sql. Inside transaction! '''
        msg='reading data for aichannels group from mba '+str(mba)+' regadd '+str(regadd)+' count '+str(count)
        print(msg)
        if count>0 and mba<>0:
            result = mb.read(mba, regadd, count=count, type='h') # client.read_holding_registers(address=regadd, count=1, unit=mba)
        else:
            print('invalid parameters for read_ai_grp()!',mba,regadd,count)
            return 2
            
        if result != None:
            try:
                for i in range(count): # tuple to table rows. tuple len is twice count!
                    Cmd="UPDATE "+self.in_sql+" set raw='"+str(result[i])+"', ts='"+str(self.ts)+"' where mba='"+str(mba)+"' and regadd='"+str(regadd+i)+"'" # koigile korraga
                    #print('i',i,Cmd) # debug
                    conn.execute(Cmd)
                return 0
            except:
                traceback.print_exc()
                return 1
        else:
            msg='ai grp data reading FAILED!'
            print(msg)
            return 1
            
            
    def sync_ai(self): # analogue input readings to sqlite, to be executed regularly.
        #global MBerr
        mba=0 
        val_reg=''
        mcount=0
        block=0 # vigade arv
        #self.ts = time.time()
        ts_created=self.ts # selle loeme teenuse ajamargiks
        value=0
        ovalue=0
        Cmd = ''
        Cmd3= ''
        cur = conn.cursor()
        cur3 = conn.cursor()
        bfirst=0
        blast=0
        bmba=0
        bcount=0
        
        try:
            Cmd="BEGIN IMMEDIATE TRANSACTION" # hoiab kinni kuni mb suhtlus kestab? teised seda ei kasuta samal ajal nagunii. iga tabel omaette.
            conn.execute(Cmd)
            #self.conn.execute(Cmd)
            Cmd="select mba,regadd from "+self.in_sql+" where mba<>'' and regadd<>'' group by mba,regadd" # tsykkel lugemiseks, tuleks regadd kasvavasse jrk grupeerida
            cur.execute(Cmd) # selle paringu alusel raw update, hiljem teha value arvutused iga teenuseliikme jaoks eraldi 
            for row in cur:
                mba=int(row[0])
                regadd=int(row[1])
                if bfirst == 0:
                    bfirst = regadd
                    blast = regadd
                    bcount=1
                    bmba=mba
                    #print('ai group mba '+str(bmba)+' start ',bfirst) # debug
                else: # not the first
                    if mba == bmba and regadd == blast+1: # sequential group still growing
                        blast = regadd
                        bcount=bcount+1
                        #print('ai group end shifted to',blast) # debug
                    else: # a new group started, make a query for previous 
                        #print('ai group end detected at regadd',blast,'bcount',bcount) # debugb
                        #print('going to read ai registers from',bmba,bfirst,'to',blast,'regcount',bcount) # debug
                        self.read_ai_grp(bmba,bfirst,bcount) # reads and updates table with previous data
                        bfirst = regadd # new grp starts immediately
                        blast = regadd
                        bcount=1
                        bmba=mba
                        #print('ai group mba '+str(bmba)+' start ',bfirst) # debug
                        
            if bfirst != 0: # last group yet unread
                #print('ai group end detected at regadd',blast) # debugb
                #print('going to read ai registers from',bmba,bfirst,'to',blast,'regcount',bcount) # debug
                self.read_ai_grp(bmba,bfirst,bcount) # reads and updates table
            
            #  raw updated for all aichannels
            
            # now process raw -> value, by services. x1 x2 y1 y may be different even if the same mba regadd in use. DO NOT calculate status here, happens separately.
            Cmd="select val_reg from "+self.in_sql+" where mba<>'' and regadd<>'' group by val_reg" # service list. other 
            cur.execute(Cmd) # selle paringu alusel raw update, hiljem teha value arvutused iga teenuseliikme jaoks eraldi 
            for row in cur: # services
                status=0 # esialgu, aga selle jaoks vaja iga teenuse jaoks oma tsykkel.
                val_reg=row[0] # teenuse nimi
                Cmd3="select * from "+self.in_sql+" where val_reg='"+val_reg+"' and mba<>'' and regadd<>'' order by member" # loeme yhe teenuse kogu info
                cur3.execute(Cmd3) # another cursor to read the same table
                for srow in cur3: # value from raw and also status
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
                    raw=0
                    ovalue=0 # previous (possibly averaged) value
                    ots=0 # eelmine ts value ja status ja raw oma
                    avg=0 # keskmistamistegur, mojub alates 2
                    desc=''
                    comment=''
                    # 0       1     2     3     4   5  6  7  8  9    10     11  12    13  14   15     16  17    18
                    #mba,regadd,val_reg,member,cfg,x1,x2,y1,y2,outlo,outhi,avg,block,raw,value,status,ts,desc,comment  # "+self.in_sql+"
                    if srow[0] != '':
                        mba=int(srow[0]) # must be int! will be -1 if empty (setpoints)
                    if srow[1] != '':
                        regadd=int(srow[1]) # must be int! will be -1 if empty
                    val_reg=srow[2] # see on string
                    if srow[3] != '':
                        member=int(srow[3])
                    if srow[4] != '':
                        cfg=int(srow[4]) # konfibait nii ind kui grp korraga, esita hex kujul hiljem
                    if srow[5] != '':
                        x1=int(srow[5])
                    if srow[6] != '':
                        x2=int(srow[6])
                    if srow[7] != '':
                        y1=int(srow[7])
                    if srow[8] != '':
                        y2=int(srow[8])
                    #if srow[9] != '':
                    #    outlo=int(srow[9])
                    #if srow[10] != '':
                    #    outhi=int(srow[10])
                    if srow[11] != '':
                        avg=int(srow[11])  #  averaging strength, values 0 and 1 do not average!
                    if srow[12] != '': # block - loendame siin vigu, kui kasvab yle 3? siis enam ei saada
                        block=int(srow[12])  #
                    if srow[13] != '': #
                        raw=int(srow[13])
                    if srow[14] != '':
                        ovalue=eval(srow[14]) # ovalue=int(srow[14])
                    #if srow[15] != '':
                    #    ostatus=int(srow[15])
                    if srow[16] != '':
                        ots=eval(srow[16])
                    #desc=srow[17]
                    #comment=srow[18]


                    #jargmise asemel vt pid interpolate
                    if x1 != x2 and y1 != y2: # konf normaalne
                        value=(raw-x1)*(y2-y1)/(x2-x1) # lineaarteisendus
                        value=y1+value
                        msg=val_reg
                        print 'raw',raw,', value',value, # debug
                        if avg>1 and abs(value-ovalue)<value/2: # keskmistame, hype ei ole suur
                        #if avg>1:  # lugemite keskmistamine vajalik, kusjures vaartuse voib ju ka komaga sailitada!
                            value=((avg-1)*ovalue+value)/avg # averaging
                            msg=msg+', averaged '+str(int(value))
                        else: # no averaging for big jumps
                            msg=msg+', nonavg value '+str(int(value))

                    else:
                        print("val_reg",val_reg,"member",member,"ai2scale PARAMETERS INVALID:",x1,x2,'->',y1,y2,'value not used!')
                        value=0
                        status=3 # not to be sent status=3! or send member as NaN?
                    
                    print(msg) # temporarely off SIIN YTLEB RAW LUGEMI AI jaoks
                    
            
                    #print 'status for AI val_reg, member',val_reg,member,status,'due to cfg',cfg,'and value',value,'while limits are',outlo,outhi # debug
                    #"+self.in_sql+"  update with new value and sdatus
                    Cmd="UPDATE "+self.in_sql+"  set status='"+str(status)+"', value='"+str(value)+"' where val_reg='"+val_reg+"' and member='"+str(member)+"'" # meelde
                    #print Cmd
                    conn.execute(Cmd)
                    
            
            conn.commit() 
            #self.conn.commit() # "+self.in_sql+"  transaction end
            return 0

        except:
            msg='PROBLEM with '+self.in_sql+' reading or processing: '+str(sys.exc_info()[1])
            print(msg)
            #syslog(msg)
            traceback.print_exc() 
            sys.stdout.flush()
            time.sleep(0.5)

            return 1
    

    def sync_ao(self): # synchronizes AI registers with data in aochannels table
        #print('write_aochannels start') # debug
        # and use write_register() write modbus registers  to get the desired result (all ao channels must be also defined in aichannels table!)
        respcode=0
        mba=0 
        omba=0 # previous value
        val_reg=''
        desc=''
        value=0
        word=0 # 16 bit register value
        #comment=''
        mcount=0
        cur = conn.cursor()
        cur3 = conn.cursor()
        ts_created=self.ts # selle loeme teenuse ajamargiks

        try:
            Cmd="BEGIN IMMEDIATE TRANSACTION" 
            conn.execute(Cmd)

            # 0      1   2    3        4      5    6      7
            #mba,regadd,bit,bootvalue,value,rule,desc,comment

            Cmd="select aochannels.mba,aochannels.regadd,aochannels.value from aochannels left join aichannels on aochannels.mba = aichannels.mba AND aochannels.regadd = aichannels.regadd where aochannels.value != aichannels.value" # 
            # the command above retrieves mba, regadd and value where values do not match in aichannels and aochannels 
            #print "Cmd=",Cmd
            cur.execute(Cmd)

            for row in cur: # got mba, regadd and value for registers that need to be updated / written
                regadd=0
                mba=0

                if row[0] != '':
                    mba=int(row[0]) # must be a number
                if row[1] != '':
                    regadd=int(row[1]) # must be a number
                if row[1] != '':
                    value=int(float(row[2])) # komaga nr voib olla, teha int!
                msg='write_aochannels: going to write value '+str(value)+' to register mba.regadd '+str(mba)+'.'+str(regadd) 
                print(msg) # debug
                #syslog(msg)

                #client.write_register(address=regadd, value=value, unit=mba)
                ''' write(self, mba, reg, type = 'h', **kwargs):
                :param 'mba': Modbus device address
                :param 'reg': Modbus register address
                :param 'type': Modbus register type, h = holding, c = coil
                :param kwargs['count']: Modbus registers count for multiple register write
                :param kwargs['value']: Modbus register value to write
                :param kwargs['values']: Modbus registers values array to write
                ''' 
                respcode=respcode+mb.write(mba=mba, reg=regadd,value=value) 
   
            conn.commit()  #  transaction end - why?
            return 0
        except:
            msg='problem with aochannel - aichannel sync!'
            print(msg)
            #syslog(msg)
            traceback.print_exc()
            sys.stdout.flush()
            return 1
        # write_aochannels() end. FRESHENED DICHANNELS TABLE VALUES AND CGH BITS (0 TO SEND, 1 TO PROCESS)

    
    
    def get_aivalue(self,svc,member): # returns raw,value,lo,hi,status values based on service name and member number
        #(mba,regadd,val_reg,member,cfg,x1,x2,y1,y2,outlo,outhi,avg,block,raw,value,status,ts,desc,comment,type integer)
        Cmd3="BEGIN IMMEDIATE TRANSACTION" # conn3, et ei saaks muutuda lugemise ajal
        conn3.execute(Cmd3)
        Cmd3="select value,outlo,outhi,status from "+self.in_sql+" where val_reg='"+svc+"' and member='"+str(member)+"'"
        #Cmd3="select raw,value,outlo,outhi,status,mba,regadd,val_reg,member from aichannels where val_reg='"+svc+"' and member='"+str(member)+"'" # debug. raw ei tule?
        #print(Cmd3) # debug
        cursor3.execute(Cmd3)
        raw=0
        value=None
        outlo=0
        outhi=0
        status=0
        found=0    
        for row in cursor3: # should be one row only
            #print(repr(row)) # debug
            found=1
            #raw=int(float(row[0])) if row[0] != '' and row[0] != None else 0
            value=int(float(row[0])) if row[0] != '' and row[0] != None else 0
            outlo=int(float(row[1])) if row[1] != '' and row[1] != None else 0
            outhi=int(float(row[2])) if row[2] != '' and row[2] != None else 0
            status=int(float(row[3])) if row[3] != '' and row[3] != None else 0
        if found == 0:
            msg='get_aivalue failure, no member '+str(member)+' for '+svc+' found!'
            print(msg)
            #syslog(msg)
        
        conn3.commit()
        #print('get_aivalue ',svc,member,'value,outlo,outhi,status',value,outlo,outhi,status) # debug
        return value,outlo,outhi,status


    def set_aivalue(self,svc,member,value): # sets variables like setpoints or limits to be reported within services, based on service name and member number
        #(mba,regadd,val_reg,member,cfg,x1,x2,y1,y2,outlo,outhi,avg,block,raw,value,status,ts,desc,comment,type integer)
        Cmd="BEGIN IMMEDIATE TRANSACTION" # conn3
        conn.execute(Cmd)
        Cmd="update aichannels set value='"+str(value)+"' where val_reg='"+svc+"' and member='"+str(member)+"'"
        #print(Cmd) # debug
        try:
            conn.execute(Cmd)
            conn.commit()
            return 0
        except:
            msg='set_aivalue failure: '+str(sys.exc_info()[1])
            print(msg)
            #syslog(msg)
            return 1  # update failure
        

    def set_aovalue(self, value,mba,reg): # sets variables to control, based on physical addresses
        #(mba,regadd,bootvalue,value,ts,rule,desc,comment)
        Cmd="BEGIN IMMEDIATE TRANSACTION" # conn3
        conn.execute(Cmd)
        Cmd="update aochannels set value='"+str(value)+"' where regadd='"+str(reg)+"' and mba='"+str(mba)+"'"
        try:
            conn.execute(Cmd)
            conn.commit()
            return 0
        except:
            msg='set_aovalue failure: '+str(sys.exc_info()[1])
            print(msg)
            #syslog(msg)
            return 1  # update failure


    def set_aosvc(self,svc,member,value): # to set a readable output channel by the service name and member using dichannels table
        #(mba,regadd,val_reg,member,cfg,x1,x2,y1,y2,outlo,outhi,avg,block,raw,value,status,ts,desc,comment,type integer) # ai
        Cmd="BEGIN IMMEDIATE TRANSACTION" 
        conn.execute(Cmd)
        Cmd="select mba,regadd from "+self.in_sql+" where val_reg='"+svc+"' and member='"+str(member)+"'"
        cur=conn.cursor()
        cur.execute(Cmd)
        mba=None
        reg=None
        for row in cur: # should be one row only
            try:
                mba=row[0]
                reg=row[1]
                set_aovalue(value,mba,reg)
                conn.commit()
                return 0
            except:
                msg='set_aovalue failed for reg '+str(reg)+': '+str(sys.exc_info()[1])
                print(msg)
                #syslog(msg)
                return 1
            
            
            
    def make_aichannels(self,svc = ''): # send the ai service messages to the monitoring server (only if fresh enough, not older than 2xappdelay). all or just one svc.
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

                if self.make_aichannel_svc(val_reg,sta_reg) == 0: # successful svc insertion into buff2server
                    pass
                    #print('tried to report svc',val_reg,sta_reg)
                else:
                    print('make_aichannel FAILED to report svc',val_reg,sta_reg)
                    return 1 #cancel


            conn.commit() # aichannels transaction end
            
        except:
            msg='PROBLEM with aichannels reporting '+str(sys.exc_info()[1])
            print(msg)
            #syslog(msg)
            traceback.print_exc()
            sys.stdout.flush()
            time.sleep(0.5)
            return 1




    def make_aichannel_svc(self,val_reg,sta_reg):  # 
        ''' make a single service record (with status chk) based on aichannel members and send it away to UDPchannel '''
        status=0 # initially
        cur=conn.cursor()
        lisa=''
        #print 'reading aichannels values for val_reg',val_reg,'with',mcount,'members' # ajutine

        Cmd="select * from "+self.in_sql+" where val_reg='"+val_reg+"'" # loeme yhe teenuse kogu info uuesti
        #print Cmd3 # ajutine
        cur.execute(Cmd) # another cursor to read the same table

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
            mts=0 # max ts, if too old, skip the service reporting
            avg=0 # keskmistamistegur, mojub alates 2
            #desc=''
            #comment=''
            # 0       1     2     3     4   5  6  7  8  9    10     11  12    13  14   15     16  17    18
            #mba,regadd,val_reg,member,cfg,x1,x2,y1,y2,outlo,outhi,avg,block,raw,value,status,ts,desc,comment  # aichannels
            if srow[0] != '':
                mba=int(srow[0]) # must be int! will be -1 if empty (setpoints)
            if srow[1] != '':
                regadd=int(srow[1]) # must be int! will be -1 if empty
            val_reg=srow[2] # see on string
            if srow[3] != '':
                member=int(srow[3])
            if srow[4] != '':
                cfg=int(srow[4]) # konfibait nii ind kui grp korraga, esita hex kujul hiljem
            if srow[5] != '':
                x1=int(srow[5])
            if srow[6] != '':
                x2=int(srow[6])
            if srow[7] != '':
                y1=int(srow[7])
            if srow[8] != '':
                y2=int(srow[8])
            if srow[9] != '':
                outlo=int(srow[9])
            if srow[10] != '':
                outhi=int(srow[10])
            if srow[11] != '':
                avg=int(srow[11])  #  averaging strength, values 0 and 1 do not average!
            #if srow[12] != '': # block - loendame siin vigu, kui kasvab yle 3? siis enam ei saada
                #block=int(srow[12])  #
            if srow[13] != '': #
                oraw=int(srow[13])
            if srow[14] != '':
                value=float(srow[14]) # teenuseliikme vaartus
            if srow[15] != '':
                ostatus=int(srow[15]) # teenusekomponendi status - ei kasuta
            if srow[16] != '':
                ots=eval(srow[16])
            #desc=srow[17]
            #comment=srow[18]

            
            ################ sat
            
    
            # ai svc STATUS CHK. check the value limits and set the status, according to configuration byte cfg bits values
            # use hysteresis to return from non-zero status values
            status=0 # initially for each member
            if value>outhi: # above hi limit
                if (cfg&4) and status == 0: # warning
                    status=1
                if (cfg&8) and status<2: # critical
                    status=2
                if (cfg&12) == 12: #  not to be sent
                    status=3
                    #block=block+1 # error count incr
            else: # return with hysteresis 5%
                if value>outlo and value<outhi-0.05*(outhi-outlo): # value must not be below lo limit in order for status to become normal
                    status=0 # back to normal
                   # block=0 # reset error counter

            if value<outlo: # below lo limit
                if (cfg&1) and status == 0: # warning
                    status=1
                if (cfg&2) and status<2: # critical
                    status=2
                if (cfg&3) == 3: # not to be sent, unknown
                    status=3
                    #block=block+1 # error count incr
            else: # back with hysteresis 5%
                if value<outhi and value>outlo+0.05*(outhi-outlo):
                    status=0 # back to normal
                    #block=0

    #############                
                            
            if mba<>'' and regadd<>'':
                if ots>mts:
                    mts=ots # latest member timestamp for the current service

            if lisa != '': # not the first member
                lisa=lisa+' ' # separator between member values
            lisa=lisa+str(value) # adding member values into one string

        # service done
        if self.ts-mts < 3*self.readperiod and status<3: # data fresh enough to be sent
            sendtuple=[sta_reg,status,val_reg,lisa] # sending service to buffer
            print('ai svc - going to report',sendtuple)  # debug
            udp.send(sendtuple) # to uniscada instance 

        else:
            msg='skipping ai data send (buff2server wr) due to stale aichannels data, reg '+val_reg+',mts '+str(mts)+', ts '+str(self.ts)
            #syslog(msg) # incl syslog
            print(msg)
            return 1

        return 0

        
        
    def doall(self): # do this regularly, executes only if time is is right
        ''' Does everything on time if executed regularly '''
        self.ts = time.time()
        if self.ts - self.ts_read > self.readperiod:
            self.ts_read = self.ts
            self.sync_ai() # 
            self.sync_ao() # writes output registers to be changed via modbus, based on feedback on di bits
            
        if self.ts - self.ts_send > self.sendperiod:
            self.ts_send = self.ts
            self.make_aichannels() # compile services and send away
            
        return 0
