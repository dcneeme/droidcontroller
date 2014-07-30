# to be imported to access modbus registers as counters
# combines previous achannels.py and cchannels.py into one universal acchannel.py. add cfg bit for counter?
# 28 may 2014.... handle negative values
# 27.06.2014 make_svc() handles change and age detection together with value (incl power) calc. svc stalled if a member is older than 10xself.readperiod
''' For testing:
    from main_energy_starman import *
    comm_doall()  # read mb 
    ac.make_svc('A2W','A2S') # ai values limits, status, returns ['A2S', 0, 'A2W', '6720 6480 6420 10000 15000']
'''

from droidcontroller.sqlgeneral import * # SQLgeneral  / vaja ka time,mb, conn jne
s=SQLgeneral() # init sisse?
from droidcontroller.counter2power import *  # Counter2Power() handles power calculation based on pulse count increments

import time

class ACchannels(SQLgeneral): # handles aichannels and counters, modbus registers and sqlite tables
    ''' Access to io by modbus analogue register addresses (and also via services?). Modbus client must be opened before.
        Able to sync input and output channels and accept changes to service members by their sta_reg code.
        Channel configuration is defined in sql tables. Required table format:
        
    '''

    def __init__(self, in_sql = 'aicochannels.sql', out_sql = 'aochannels.sql', readperiod = 1, sendperiod = 30):
        self.setReadPeriod(readperiod) 
        self.setSendPeriod(sendperiod)
        self.in_sql = in_sql.split('.')[0]
        self.out_sql = out_sql.split('.')[0]
        #self.s = SQLgeneral()
        self.cp=[] # possible counter2value calculation instances
        self.Initialize()


    def setReadPeriod(self, invar):
        ''' Set the refresh period, executes sync if time from last read was earlier than period ago.
            values considered as stalled after 10x self.readperiod
        '''
        self.readperiod = invar  # values considered as stalled after 10x self.readperiod


    def setSendPeriod(self, invar):
        ''' Set the refresh period, executes sync if time from last read was earlier than period ago '''
        self.sendperiod = invar


    def sqlread(self, table):
        s.sqlread(table) # read dichannels


    def Initialize(self): # before using this create s=SQLgeneral()
        ''' initialize delta t variables, create tables and modbus connection '''
        self.ts = round(time.time(),1)
        self.ts_read = self.ts # time of last read
        self.ts_send = self.ts-10 # allow counters restoring
        self.sqlread(self.in_sql) # read counters table
        self.sqlread(self.out_sql) # read aochannels if exist
        self.ask_counters() # ask server about the last known values of all counter related services (1024 in cfg)


    def ask_counters(self): # use on init, send ? to server
        ''' Queries last counter service values from the server '''
        Cmd="select val_reg,max(cfg) from "+self.in_sql+" where (cfg+0 & 1024) group by val_reg" # counters only, to be asked and restored
        #print "Cmd=",Cmd
        cur=conn.cursor()
        cur.execute(Cmd) # getting services to be read and reported
        for row in cur: # possibly multivalue service members
            val_reg=row[0]
            #cfg=int(row[1]) if row[1] != '' else 0
            udp.udpsend(val_reg+':?\n') # ask last value from uniscada server if counter
        conn.commit()
        return 0


    def parse_udp(self,data_dict): # search for setup or set counter values
        ''' Setup change for variables in sql or value preset for modbus cpountyer channels '''
        cur=conn.cursor()
        setup_changed = 0 # flag general setup change, data to be dumped into sql file
        msg=''
        mval=''
        res=0
        member=0
        if data_dict == {} or data_dict == '' or data_dict == None:
            print('ac: nothing to parse in',data_dict)
            return 0
        print('acchannels: parsing key:value data ',data_dict) # debug
        for key in data_dict: # process per key:value
            valmembers=data_dict[key].split(' ') # convert value to member list
            print('number of members for',key,len(valmembers),valmembers) # debug
            for valmember in range(len(valmembers)): # 0...N-1
                Cmd="select mba,regadd,val_reg,member,value,regtype,wcount,mbi,x2,y2 from "+self.in_sql+" where val_reg='"+key+"' and member='"+str(valmember+1)+"'"
                #print(Cmd) # debug
                cur.execute(Cmd)
                conn.commit()
                for row in cur: # single member
                    print('srow:',row) # debug
                    sqlvalue=int(row[4]) if row[4] != '' else 0 # eval(row[4]) if row[4] != '' else 0 # 
                    value=eval(valmembers[valmember])
                    regtype=row[5] # 'h' 'i' 's!' 
                    
                    if sqlvalue != value and ((regtype == 'h' and value == 0 or value > sqlvalue) \
                            or (regtype == 's!')): 
                        # replace actual counters only if bigger than existing or zero, no limits for setup type 's!' 
                        member=valmember+1
                        
                        print('going to replace '+key+' member '+str(member)+' existing value '+str(sqlvalue)+' with '+str(value)) # debug
                        # faster to use physical data instead of svc. also clear counter2power buffer if cp[] exsists!
                        
                        if regtype == 's!': # setup row, external modif allowed (!)
                            if (row[0] == '' and row[1] == ''): # mba, regadd
                                if self.set_aivalue(str(key),member,value) == 0: # set setup value in sql table
                                    msg='setup changed for key '+key+', member '+str(member)+' to value '+str(value)
                                    setup_changed=1
                                    print(msg)
                                    udp.syslog(msg)
                                else:
                                    msg='svc member setting problem for key '+key+', member '+str(member)+' to value '+str(value)
                                    print(msg)
                                    udp.syslog(msg)
                                    res+=1
                            else:
                                msg='acchannels.udp_parse: setup value cannot have mba,regadd defined!'
                                print(msg)
                                udp.syslog(msg)
                                res+=1
                        elif regtype == 'h': # holding register, probably counter
                            if (eval(row[0]) > 0 and eval(row[1]) >= 0): # mba,regadd probably valid
                                mba=eval(row[0]) if row[0] != '' else 0
                                regadd=eval(row[1]) if row[1] != '' else None
                                wcount=int(row[6]) if row[6] != '' else 1
                                mbi=int(row[7]) if row[7] != '' else None
                                x2=eval(row[8]) if row[8] != '' else 0
                                y2=eval(row[9]) if row[9] != '' else 0
                                
                                #if self.set_counter(val_reg=key, member=member,value=value, wcount=wcount) == 0: # faster to use physical data instead of svc
                                if self.set_counter(mbi=mbi, mba=mba, regadd=regadd, value=value, wcount=wcount, x2=x2, y2=y2) == 0: # set counter
                                    #set_counter also cleared counter2power buffer if cp[] exsisted!
                                    msg='counter set for key '+key+', member '+str(member)+' to value '+str(value)
                                    print(msg)
                                    #udp.syslog(msg)
                                else:
                                    msg='member value setting problem for key '+key+', member '+str(member)+' to value '+str(value)
                                    print(msg)
                                    #udp.syslog(msg)
                                    res+=1
                            else:
                                msg='acchannels.udp_parse: holding register must have mba,regadd defined!'
                                print(msg)
                                #udp.syslog(msg)
                                res+=1
                    else: # skip
                        print('parse_udp: member value write for key '+key+' SKIPPED due to sqlvalue,value,regtype',sqlvalue,value,regtype)
                
            if setup_changed == 1:
                print('going to dump table',self.in_sql)
                try:
                    s.dump_table(self.in_sql)
                    sendstring=self.make_svc(key,key[:-1]+'S')
                    print('going to report back sendstring',sendstring)
                    udp.send(sendstring)
                except:
                    print('FAILED to dump table',self.in_sql)
                    traceback.print_exc() # debug
        #if res == 0:
            #self.read_all() # reread the changed channels to avoid repeated restore - no need
            
        return res # kui setup_changed ==1, siis todo = varlist! aga kui samal ajal veel miski ootel?
        

    def set_counter(self, value = 0, **kwargs): # value, mba,regadd,mbi,val_reg,member   # one counter to be set. check wcount from counters table
        ''' Sets consecutive holding registers, wordlen 1 or 2 or -2 (must be defined in sql table in use). 
            Usable for cumulative counter counting initialization, not for analogue output (use set_output for this).
            Must also clear counter2power instance buffer dictionary if cp[] instance exsists, to avoid unwanted spike in power calculation result!
        '''
        #val_reg=''  # arguments to use a subset of them
        #member=0
        #mba=0
        #mbi=0
        #regadd=0
        #wcount=0
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
                val_reg=kwargs.get('val_reg')
                member=kwargs.get('member')
                if val_reg == '' or member == 0:
                    print('set_counter: invalid parameters val_reg,member',val_reg,member)
                    return 1
            except:
                print('invalid parameters for set_counter()',kwargs)
                return 2

            Cmd="select mbi,mba,regadd,wcount,x2,y2 from "+self.in_sql+" where val_reg='"+val_reg+"' and member='"+str(member)+"'"
            #print('set_counter: ',Cmd) # debug
            cur.execute(Cmd) # what about commit()? FIXME
            conn.commit()
            for row in cur:
                print('row:',row) # debug
                mbi=row[0]
                mba=int(row[1]) if row[1] != '' else 0
                regadd=int(row[2]) if row[2] != '' else 0
                wcount=int(row[3]) if row[3] != '' else 0
                x2=int(row[4]) if row[4] != '' else 0
                y2=int(row[5]) if row[5] != '' else 0
                    
        #print('set_counter: mbi,mba,regadd,wcount,x2,y2',mbi,mba,regadd,wcount,x2,y2) # debug
        if x2 != 0 and y2 != 0: #convert
            value=round(1.0*value*x2/y2) # assuming x1=x2=0, only counter registers to be written this way...
        else:
            print('set_counter: invalid scaling x2,y2',x2,y2)
            return 1
        
        value=(int(value)&0xFFFFFFFF) # to make sure the value to write is 32 bit integer    
        try:
            if wcount == 2: # normal counter, type h
                #res=mb[mbi].write(mba, regadd, values=[(value&0xFFFF0000)>>16,(value&0xFFFF)]) # works if multiple register write supported
                res=mb[mbi].write(mba, regadd, value=(value&0xFFFF0000)>>16) # single registe write
                time.sleep(0.1)
                res+=mb[mbi].write(mba, regadd+1, value=(value&0xFFFF)) # single registe write
                
            elif wcount == -2:
                #res=mb[mbi].write(mba, regadd, values=[(value&0xFFFF), (value&0xFFFF0000)>>16]) # works if multiple register write supported
                res=mb[mbi].write(mba, regadd, value=(value&0xFFFF)) # single registe write
                time.sleep(0.1)
                res+=mb[mbi].write(mba, regadd+1, value=(value&0xFFFF0000)>>16) # single registe write
                
            elif wcount == 1:
                res=mb[mbi].write(mba, regadd, value=(value&0xFFFF)) # single register write
                
            else:
                print('set_counter: unsupported word count! mba,regadd,wcount',mba,regadd,wcount)
                res=1
                
            if res == 0:
                print('set_counter: write success to mba,regadd',mba,regadd)
                
                #check if there are counter2power instances (cp[]) related to that register, intialize them
                Cmd="select mbi,mba,regadd,val_reg,member from "+self.in_sql+" where (cfg+0 & 192) order by val_reg,member" # counter2power bits 64+128
                cur.execute(Cmd) # what about commit()? FIXME
                conn.commit()
                j=-1
                for row in cur: # start from 0 with indexing
                    j+=1
                    #print('cp init prep select row (j,mbi,mba,regadd):',j,row) # debug
                    try:
                        if self.cp and mbi == int(row[0]) and mba == int(row[1]) and regadd == int(row[2]): # cp[j] must be initialized
                            print('initializing counter2power instance cp['+str(j)+'] due to counter setting')
                            self.cp[j].init() # cp[] may not exist on start, but init is then not needed either...
                    except:    
                        print('FAILED initializing counter2power instance cp['+str(j)+'], tried due to counter setting')
                        traceback.print_exc() # debug
                # end power init
            else:
                print('set_counter: write FAILED to mba,regadd',mba,regadd)
            return res
                
        except:  # set failed
            msg='failed set_counter mbi.mba.regadd'+str(mbi)+'.'+str(mba)+'.'+str(regadd)
            #udp.syslog(msg)
            print(msg)
            traceback.print_exc()
            return 1
        # no need for commit, this method is used in transaction



    def read_grp(self,mba,regadd,count,wcount,mbi=0): # update raw in self.in_sql with data from modbus registers
        ''' Reads sequential register group, process numbers according to counter size and store raw into table self.in_sql. Inside transaction!
            Compares the raw value from mobdbus register with old value in the table. If changed, ts is set to the modbus readout time self.ts.

            Add here counter state recovery if suddenly zeroed
            #    if value == 0 and ovalue >0: # possible pic reset. perhaps value <= 100?
            #        msg='restoring lost content for counter '+str(mba)+'.'+str(regadd)+':2 to become '+str(ovalue)+' again instead of '+str(value)
            #        #syslog(msg)
            #        print(msg)
            #        self.set_counter(value=ovalue, mba=mba, regadd=regadd, mbi=mbi, wcount=wcount, x2=x2, y2=y2) # does not contain commit()!
            #this above should be fixed. value is already saved, put it there!
            FIMXME:  do not attempt to access counters that are not defined in devices.sql! this should be an easy way to add/remove devices.
        '''
        self.ts = round(time.time(),2) # refresh timestamp for raw, common for grp members
        step=int(abs(wcount))
        cur=conn.cursor()
        oraw=0
        if step == 0:
            print('illegal wcount',wcount,'in read_grp()')
            return 2

        msg=' from mba '+str(mba)+'.'+str(regadd)+', cnt '+str(count)+', wc '+str(wcount)+', mbi '+str(mbi)
        if count>0 and mba != 0 and wcount != 0:
            try:
                if mb[mbi]:
                    result = mb[mbi].read(mba, regadd, count=count, type='h') # client.read_holding_registers(address=regadd, count=1, unit=mba)
                    msg=msg+', raw: '+str(result)
                    print(msg) # debug
            except:
                print('read_grp: mb['+str(mbi)+'] missing, device with mba '+str(mba)+' not defined in devices.sql?')
                return 2
        else:
            print('invalid parameters for read_counter_grp()!',mba,regadd,count,wcount,mbi)
            return 2

        if result != None: # got something from modbus register
            try:
                for i in range(int(count/step)): # ai-co processing loop. tuple to table rows. tuple len is twice count! int for py3 needed
                    tcpdata=0
                    #print('aico_grp debug: i',i,'step',step,'results',result[step*i],result[step*i+1]) # debug
                    if wcount == 2:
                        tcpdata = (result[step*i]<<16)+result[step*i+1]
                        #print('normal counter',str(i),'result',tcpdata) # debug
                    elif wcount == -2:
                        tcpdata = (result[step*i+1]<<16)+result[step*i]  # swapped word order, as in barionet
                        #print('swapped words counter',str(i),'result',tcpdata) # debug
                    elif wcount == 1:
                        tcpdata = result[i]
                    else: # something else, lengths other than 1 2 -2 not yet supported!
                        print('unsupported counter word size',wcount)
                        return 1

                    #Cmd="select raw from "+self.in_sql+" where mbi="+str(mbi)+" and mba='"+str(mba)+"' and regadd='"+str(regadd+i*step)+"' group by mbi,mba,regadd"
                    Cmd="select raw,max(cfg) from "+self.in_sql+" where mbi="+str(mbi)+" and mba='"+str(mba)+"' and regadd='"+str(regadd+i*step)+"' group by mbi,mba,regadd" 
                    # get the old value to compare with new. can be multiple rows, group to single row. if counter and zero, ask_counters()
                    cur.execute(Cmd)
                    for row in cur:
                        oraw=int(row[0]) if row[0] !='' else -1
                        cfg=int(row[1]) if row[1] != '' else 0
                    #if tcpdata != oraw or oraw == -1: # update only if change needed or empty so far - NO! value CAN stay the same, but age is needed!
                    Cmd="UPDATE "+self.in_sql+" set raw='"+str(tcpdata)+"', ts='"+str(self.ts)+ \
                        "' where mba='"+str(mba)+"' and regadd='"+str(regadd+i*step)+"' and mbi="+str(mbi) # koigile korraga selle mbi, mba, regadd jaoks
                    #print('counters i',i,Cmd) # debug
                    conn.execute(Cmd)
                time.sleep(0.05) # ainult seriali puhul? ##########  FIXME
                return 0
            except:
                traceback.print_exc()
                return 1
        else:
            msg='aicochannels grp read FAILED for mbi,mba,regadd,count '+str(mbi)+', '+str(mba)+', '+str(regadd)+', '+str(count)
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
        #self.ts = round(time.time(),2) # not needed here
        #ts_created=self.ts # not needed here
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
            Cmd="BEGIN IMMEDIATE TRANSACTION" # combines several read/writes into one transaction
            # read mbi,mba,regadd,wcount from table to define groups
            # read modbus registers in groups and write raw into table
            # read svc from table to calculate and update value
            # 
            
            conn.execute(Cmd)
            Cmd="select mba,regadd,wcount,mbi from "+self.in_sql+" where mba != '' and regadd != '' group by mbi,mba,regadd" # tsykkel lugemiseks, tuleks regadd kasvavasse jrk grupeerida
            cur.execute(Cmd) # selle paringu alusel raw update, hiljem teha value arvutused iga teenuseliikme jaoks eraldi
            for row in cur: # these groups can be interrupted into pieces to be queried!
                mba=int(row[0]) if int(row[0]) != '' else 0
                regadd=int(row[1]) if int(row[1]) != '' else 0
                wcount=int(row[2]) if int(row[2]) != '' else 0 # wordcount for the whole group!!
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
                        self.read_grp(bmba,bfirst,bcount,bwcount,bmbi) # reads and updates table with previous data #####################  READ MB  ######
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
                self.read_grp(bmba,bfirst,bcount,bwcount,bmbi) # reads and updates table with previous data #####################  READ MB  ######

            # raw sync (from modbus to sql) done.



            # now process raw -> value and find statuses using make_svc() for each service. 
            #power calculations happen in make_svc too!

            Cmd="select val_reg from "+self.in_sql+" group by val_reg" # find ervices
            #print "Cmd=",Cmd
            #cur.execute(Cmd) # getting services to be read and reported
            #cpi=-1 # counter2power instance index, increase only if with cfg weight 64 true
            for row in cur: # SERVICES LOOP
                #val_reg=''
                #sta_reg=''
                #status=0 #
                #value=0
                val_reg=row[0] # service value register name
                sta_reg=val_reg[:-1]+"S" # status register name
                
                
                self.make_svc(val_reg,sta_reg) # sets status and notifies id status chg in any member
                                
            conn.commit() # also for make_svc()
            sys.stdout.write('A')
            return 0

        except: # end reading counters
            msg='problem with acchannels.read_all(): '+str(sys.exc_info()[1])
            print(msg)
            #udp.syslog(msg)
            traceback.print_exc()
            sys.stdout.flush()
            time.sleep(1)
            return 1

    #read_all end #############



    def sync_ao(self): # synchronizes AI registers with data in aochannels table
        #print('write_aochannels start') # debug
        # and use write_register() write modbus registers  to get the desired result (all ao channels must be also defined in aichannels table!)
        respcode=0
        mbi=0
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

            Cmd="select "+self.out_sql+".mba,"+self.out_sql+".regadd,"+self.out_sql+".value,"+self.out_sql+".mbi from "+self.out_sql+" left join "+self.in_sql+" \
                on "+self.out_sql+".mba = "+self.in_sql+".mba AND "+self.out_sql+".mbi = "+self.in_sql+".mbi AND "+self.out_sql+".regadd = "+self.in_sql+".regadd \
                where "+self.out_sql+".value != "+self.in_sql+".value" # 
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
                msg='sync_ao: going to write value '+str(value)+' to register mba.regadd '+str(mba)+'.'+str(regadd) 
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
                try:
                    if mb[mbi]:
                        respcode=respcode+mb[mbi].write(mba=mba, reg=regadd,value=value) 
                
                except:
                    print('device mbi,mba',mbi,mba,'not defined in devices.sql')
                    return 2
            
            conn.commit()  #  transaction end - why?
            return 0
        except:
            msg='problem with acchannel.sync_ao!'
            print(msg)
            #udp.syslog(msg)
            traceback.print_exc()
            sys.stdout.flush()
            return 1
        # sync_ao() end. FRESHENED DICHANNELS TABLE VALUES AND CGH BITS (0 TO SEND, 1 TO PROCESS)

    
    
    def get_aivalue(self,svc,member): # returns raw,value,lo,hi,status values based on service name and member number
        # but status is for a service, not for member!!!??
        #(mba,regadd,val_reg,member,cfg,x1,x2,y1,y2,outlo,outhi,avg,block,raw,value,status,ts,desc,comment,type integer)
        cur=conn.cursor()
        Cmd="BEGIN IMMEDIATE TRANSACTION" # conn3, et ei saaks muutuda lugemise ajal
        conn.execute(Cmd)
        Cmd="select value,outlo,outhi,status from "+self.in_sql+" where val_reg='"+svc+"' and member='"+str(member)+"'"
        #print(Cmd) # debug
        cur.execute(Cmd)
        raw=0
        value=None
        outlo=0
        outhi=0
        status=0
        found=0    
        for row in cur: # should be one row only
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
        
        conn.commit()
        #print('get_aivalue ',svc,member,'value,outlo,outhi,status',value,outlo,outhi,status) # debug
        return value,outlo,outhi,status


    def set_aivalue(self,svc,member,value): # sets variables like setpoints or limits to be reported within services, based on service name and member number
        ''' Setting member value using sqlgeneral set_aivalue. adding sql table below for that '''
        return s.set_membervalue(svc,member,value,self.in_sql)
        

    def set_aovalue(self, value, mba, reg): # sets variables to control, based on physical addresses
        ''' Write value to follow by read_all() and sync_ao() using mba and regadd'''
        #(mba,regadd,bootvalue,value,ts,rule,desc,comment)
        Cmd="BEGIN IMMEDIATE TRANSACTION" # conn
        conn.execute(Cmd)
        Cmd="update "+self.out_sql+" set value='"+str(value)+"' where regadd='"+str(reg)+"' and mba='"+str(mba)+"'"
        try:
            conn.execute(Cmd)
            conn.commit()
            return 0
        except:
            msg='set_aovalue failure: '+str(sys.exc_info()[1])
            print(msg)
            #udp.syslog(msg)
            return 1  # update failure


    def set_aosvc(self, svc, member, value): # to set a readable output channel by the service name and member using dichannels table
        ''' Set service member value bby service name and member number'''
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
                self.set_aovalue(value,mba,reg)
                conn.commit()
                return 0
            except:
                msg='set_aovalue failed for reg '+str(reg)+': '+str(sys.exc_info()[1])
                print(msg)
                #udp.syslog(msg)
                return 1
            
            
            
    def report_all(self, svc = ''): # send the aico service messages to the monitoring server (only if fresh enough, not older than 2xappdelay). all or just one svc.
        ''' Make all (defined self.in_sql) services reportable (with status chk) based on counters members and send it away to UDPchannel '''
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

                sendstring=self.make_svc(val_reg,sta_reg)
                if sendstring != None: # == 0: # successful svc insertion into buff2server
                    udp.send(sendstring) #may send to buffer double if make_svc found change. no dblk sending if ts is the same.
                    #print('regular report of svc',val_reg,sta_reg)
                else:
                    print('FAILED to report svc',val_reg,sta_reg)
                    return 1 #cancel


            conn.commit() # aicochannels svc_report transaction end
            return 0
            
        except:
            msg='PROBLEM with acchannels.report_all() for svc '+svc+' based on table '+self.in_sql+': '+str(sys.exc_info()[1])
            print(msg)
            #udp.syslog(msg)
            traceback.print_exc()
            sys.stdout.flush()
            time.sleep(0.5)
            return 1




    def make_svc(self, val_reg, sta_reg):  # ONE svc, both val_reg and sta_reg exist for ai and counters
        ''' Make a single service record WITH STATUS based on existing values and update the scaled value in sql table. '''
      
        status=0 # initially for whole service
        cur=conn.cursor()
        lisa=''
        #print('acchannels.make_svc: reading aico values for val_reg,sta_reg',val_reg,sta_reg) # debug

        Cmd="select mba,regadd,val_reg,member,cfg,x1,x2,y1,y2,outlo,outhi,avg,block,raw,value,status,ts,desc,regtype,grp,mbi,wcount from "+self.in_sql \
            +" where val_reg='"+val_reg+"' order by member asc" # avoid trouble with column order
        #print Cmd # ajutine
        cur.execute(Cmd) # another cursor to read the same table
        ts_now=time.time() # time now in sec
        
        for srow in cur: # go through service members
            #print(repr(srow)) # debug
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
            ostatus=0 # previous member status
            #tvalue=0 # test, vordlus
            oraw=0
            ovalue=0 # previous (possibly averaged) value
            ots=0 # eelmine ts value ja status ja raw oma
            avg=0 # keskmistamistegur, mojub alates 2
            result=None
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
            raw=int(srow[13]) if srow[13] != '' else None # 0
            ovalue=float(srow[14]) if srow[14] != '' else 0 # teenuseliikme endine vaartus
            ostatus=int(srow[15]) if srow[15] != '' else 0 # teenusekomponendi status - ei kasuta / votame kasutusele
            ots=eval(srow[16]) if srow[16] != '' else 0
            #desc=srow[17]
            #comment=srow[18]
            mbi=srow[20] # int
            wcount=int(srow[21]) if srow[21] != '' else 1  # word count
            chg=0 # member status change flag        
            
            print('val_reg,member,cfg,raw,ovalue,outlo,outhi',val_reg,member,cfg,raw,ovalue,outlo,outhi) # debug
            ################ sat
            
            if raw != None: # valid data for either energy or power value
                if ots < ts_now - 10*self.readperiod: # data stalled
                    print('make_svc() cancelled due to stalled member data for',val_reg,member,'ots,ts_now',ots,ts_now)
                    return None
                
                #POWER?
                if (cfg&64): # power, no sign, increment to be calculated! divide increment to time from the last reading to get the power
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
                
                
                if (cfg&128) > 0: # 
                    cpi=cpi+1 # counter2power index on /off jaoks
                    try:
                        if self.cp[cpi]:
                            pass # instance already exists
                    except:
                        self.cp.append(Counter2Power(val_reg,member,off_tout = block)) # another Count2Power instance. 10s tout = 360W threshold if 1000 imp per kWh
                        print('Counter2Power() instance cp['+str(cpi)+'] created for state svc '+val_reg+' member '+str(member)+', off_tout '+str(block))
                    res=self.cp[cpi].calc(ots, raw, ts_now = self.ts) # power calculation based on raw counter increase
                    raw=res[1] # on off = 0 1
                    #print('got result from cp['+str(cpi)+']: '+str(res))  # debug
                    if res[2] != 0: # on/off change
                        chg=1 # immediate notification needed due to state change
                
                # SCALING
                if (cfg&1024) == 0: # take sign into account, not counter ### SIGNED if not counter ##
                    if raw >= (2**(wcount*16-1)): # negative!
                        raw=raw-(2**(wcount*16))
                        #print('read_all: converted to negative value',raw,'wcount',wcount) # debug
                   
                if raw != None and x1 != x2 and y1 != y2: # seems like normal input data
                    value=(raw-x1)*(y2-y1)/(x2-x1)
                    value=int(round(y1+value)) # integer values to be reported only
                else:
                    print("read_counters val_reg",val_reg,"member",member,"raw",raw,"ai2scale PARAMETERS INVALID:",x1,x2,'->',y1,y2,'conversion not used!') # debug
                    value=None
                   
                if outhi == None or outlo == None:
                    print('no limit chk for',val_reg,'due to outlo, outhi',outlo,outhi) # debug
                    
                if value != None:
                    if avg>1 and abs(value-ovalue) < value/2:  # averaging the readings. big jumps (more than 50% change) are not averaged.
                        value=int(((avg-1)*ovalue+value)/avg) # averaging with the previous value, works like RC low pass filter
                        #print('counter avg on, value became ',value) # debug
                    
                    if (cfg&256) and abs(value-ovalue) > value/5.0: # change more than 20% detected, use num w comma!
                        print('value change of more than 20% detected in '+val_reg+'.'+str(member)+', need to notify') # debug
                        chg=1
                        

                    # counter2power and scaling done, status check begins ##########
                    mstatus=self.value2status(value,cfg,outlo,outhi,ostatus) # default hyst=5%
                    
                  
                    if mstatus != ostatus: # member status change detected
                        chg=1 # immediate notification within this method
                        print('member status chg (after possible inversion) to',mstatus) # debug
            
                Cmd="update "+self.in_sql+" set status='"+str(status)+"', value='"+str(value)+"' where val_reg='"+val_reg+"' and member='"+str(member)+"'"
                conn.execute(Cmd) # who commits? the calling method!!!
                    
                #############   
        
                
                
            else: # setup values with no raw
                value=ovalue # use the value in table without conversion or influence on status
                if mba > 0 and member > 0:
                    print('ERROR: raw None for svc',val_reg,member) # debug
                    return None
            
            if lisa != '': # not the first member
                lisa=lisa+' ' # separator between member values
            lisa=lisa+str(int(round(value))) # adding member values into one string
        
            if mstatus>status:
                    status=mstatus
        
        # service members done
        sendtuple=[sta_reg,status,val_reg,lisa] # sending service to buffer
        if not (cfg&512) and chg == 1: # immediate notification
            udp.send(sendtuple) # to uniscada instance 
            
        return sendtuple # for regular send or status check
        
            
    def value2status(self,value,cfg,outlo,outhi,ostatus=0,hyst=2):
        ''' Returns svc member status based on value and limits, taking cfg and previous status into account.
            If value to status inversion is in use (to define forbidden instead of allowed zones),
            normalize old status ostatus first and then invert mstatus in the end.
        '''
        # svc STATUS CHK. check the value limits and set the status, according to configuration byte cfg bits values
        # use hysteresis to return from non-zero status values
        
        # CONFIG BYTE BIT MEANINGS
        # 1 - below outlo warning,
        # 2 - below outlo critical,
            # NB! 3 - not to be sent  if value below outlo
        # 4 - above outhi warning
        # 8 - above outhi critical
            # NB! 3 - not to be sent  if value above outhi
        # 16 - - immediate notification on status change (USED FOR STATE FROM POWER)
        # 32  - limits to state inversion
        # 64 - power to be counted based on count increase and time period between counts
        # 128 -  state from power flag
        # 256 - notify on 10% value change (not only limit crossing that becomes activated by first 4 cfg bits)
        # 512 - do not report at all, for internal usage
        # 1024 - raw counter, no sign
            # counters are normally located in 2 registers, but also ai values can be 32 bits. 
            # negative wcount means swapped words (barionet, npe imod)
        
        mstatus=0 # initial service member status
        bitvalue=0 # remember the important bitvalue for nonzero internal status 
        #print('value,cfg,outlo,outhi',value,cfg,outlo,outhi) # debug
        
        if (cfg&32): # status inversion IN USE, normalize
            if ostatus>0:
                ostatus=0
            else:
                ostatus=1 # treating statuses 1 and 2 equally
        
        if outhi != None: # hi limit set
            if value>outhi: # above hi limit
                #print('value above outhi,cfg',cfg) # debug
                if (cfg&4)>0: # warning
                    mstatus=1
                if (cfg&8)>0: # critical
                    mstatus=2
                if (cfg&12) == 12: #  not to be sent
                    mstatus=3
                #print('mstatus due to value above outhi',mstatus) # debug
            else: # POSSIBLE return with hysteresis, even without existing outlo
                if value<outhi-(hyst/100.0)*outhi and (outlo == None or (outlo != None and value>outlo+(hyst/100.0)*outlo)):
                    mstatus=0 # below hyst limit
                    #print('mstatus due to return below outhi',mstatus) # debug
                else: # within dead zone or above
                    if mstatus == 0 and ostatus > 0:
                        mstatus=ostatus
                        #print('no change for old mstatus due to dead zone hi',mstatus) # debug
                    
        if outlo != None: # lo limit set
            if value<outlo: # below lo limit
                #print('value below outlo') # debug
                if (cfg&1): # warning
                    mstatus=1
                if (cfg&2): # critical
                    mstatus=2
                if (cfg&3) == 3: # not to be sent, unknown
                    mstatus=3
                #print('mstatus due to value below outlo',mstatus) # debug    
            else: # POSSIBLE return with hysteresis, even without existing outlo
                if value>outlo+(hyst/100.0)*outlo and (outhi == None or (outhi != None and value<outhi-(hyst/100.0)*outhi)):
                    mstatus=0 # below hyst limits
                    #print('mstatus due to return above outlo',mstatus) # debug
                else: # within dead zone or below
                    if mstatus == 0 and ostatus > 0:
                        mstatus=ostatus
                        #print('no change for old mstatus due to dead zone lo',mstatus) # debug
                    
        if (cfg&32): # possible status inversion for each member
            #print('status inversion enabled,cfg,mstatus before inv',cfg,mstatus) # debug
            if mstatus == 0: # within FORBIDDEN zone
                if (cfg&5):
                    mstatus = 1 # normal becomes warning
                elif(cfg&10):
                    mstatus = 2 # normal becomes critical, higher cfg bit  wins
            else: # outside forbidden zone
                mstatus = 0 # not normal becomes normal
        else:
            #print('no inversion used, unchanged mstatus',mstatus) # debug
            pass
        return mstatus
    
    def doall(self): # do this regularly, executes only if time is is right
        ''' Does everything that is regularly needed in this class on time if executed often enough.
            Do not report too after early, counters may get restored from server.
        '''
        res=0
        self.ts = round(time.time(),2)
        if self.ts - self.ts_read > self.readperiod:
            self.ts_read = self.ts
            try:
                res=self.read_all() # read all aico channels
            except:
                traceback.print_exc()
        if self.ts - self.ts_send > self.sendperiod:
            self.ts_send = self.ts
            try:
                res=res+self.report_all() # compile services and send away  / raporteerimine, harvem
            except:
                traceback.print_exc()
        return res
   