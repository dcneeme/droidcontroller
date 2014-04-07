# to be imported to access modbus registers as analogue io 
# 03.04.2014 neeme
# 04.04.2014 
# 06.04.2014 seguential register read for optimized reading


''' mb.read(mba, reg, count = 1, type = 'h'):  # modbus read example 
    
    mb.write(mba, reg, type = 'h', **kwargs):  # modbus write example 
        :param 'mba': Modbus device address
        :param 'reg': Modbus register address
        :param 'type': Modbus register type, h = holding, c = coil
        :param kwargs['count']: Modbus registers count for multiple register write
        :param kwargs['value']: Modbus register value to write
        :param kwargs['values']: Modbus registers values array to write
''' 



from sqlgeneral import * # SQLgeneral  
s=SQLgeneral() 

class Dchannels(SQLgeneral): # handles aichannels and aochannels tables
    ''' Access to io by modbus binary register bits (and also via services?)
        SQLgeneral will open shared Modbus client.
        Able to sync input and output channels and accept changes to service members by their sta_reg code
    '''
    
    def __init__(self, in_sql = 'dichannels.sql', out_sql = 'dochannels.sql', readperiod = 1, sendperiod = 30): # sends immediately on change too!
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
        #self.conn = sqlite3.connect(':memory:')
        self.sqlread(self.in_sql) # read dichannels
        self.sqlread(self.out_sql) # read dochannels if exist
        
        
        
    def read_di_grp(self,mba,regadd,count): # using self,in_sql as the table to store in.
        ''' Read sequential register group and store raw into table self.in_sql. Inside transaction! '''
        cur=conn.cursor()
        msg='reading data for dichannels group from mba '+str(mba)+' regadd '+str(regadd)+' count '+str(count)
        print(msg)
        if count>0 and mba<>0:
            result = mb.read(mba, regadd, count=count, type='h') # client.read_holding_registers(address=regadd, count=1, unit=mba)
        else:
            print('invalid parameters for read_ai_grp()!',mba,regadd,count)
            return 2
            
        if result != None:
            try:
                for i in range(count): # tuple to table rows. tuple len is twice count!
                    # bitwise processing now - only bits not words can be saved!
                    Cmd="select bit,value from "+self.in_sql+" where mba='"+str(mba)+"' and regadd='"+str(regadd+i)+"' group by bit" # handle repeated bits on one go
                    cur.execute(Cmd)
                    for srow in cur: # for every mba list the bits in used&to be updated
                        bit=0
                        ovalue=0
                        chg=0 #  bit change flag
                        #mba and regadd are known
                        if srow[0] != '':
                            bit=int(srow[0]) # bit 0..15
                        if srow[1] != '':
                            ovalue=int(float(srow[1])) # bit 0..15
                        value=(result[i]&2**bit)/2**bit # bit value 0 or 1 only
                        #print 'decoded value for bit',bit,value,'was',ovalue

                        # check if outputs must be written
                        if value != ovalue: # change detected, update dichannels value, chg-flag  - saaks ka maski alusel!!!
                            chg=3 # 2-bit change flag, bit 0 to send and bit 1 to process, to be reset separately
                            msg='DIchannel '+str(mba)+'.'+str(regadd)+' bit '+str(bit)+' change! was '+str(ovalue)+', became '+str(round(value)) # temporary
                            print(msg)
                            #syslog(msg)
                            # dichannels table update with new bit values and change flags. no status change here. no update if not changed!
                            Cmd="UPDATE "+self.in_sql+" set value='"+str(round(value))+"', chg='"+str(chg)+"', ts_chg='"+str(self.ts)+"' where mba='"+str(mba)+"' and regadd='"+str(regadd)+"' and bit='"+str(bit)+"'" # uus bit value ja chg lipp, 2 BITTI!
                        else: # ts_chg used as ts_read now! change detection does not need that  timestamp!
                            chg=0
                        Cmd="UPDATE "+self.in_sql+" set ts_chg='"+str(self.ts)+"', chg='"+str(chg)+"' where mba='"+str(mba)+"' and regadd='"+str(regadd)+"' and bit='"+str(bit)+"'" # old value unchanged, use ts_CHG AS TS!
                        #print Cmd # debug
                        conn.execute(Cmd) # write
                    
                return 0
            except:
                traceback.print_exc()
                return 1
        else:
            print('di processing failure')
            msg='ai grp data reading FAILED!'
            print(msg)
            return 1
            
            
    def sync_di(self): # binary input readings to sqlite, to be executed regularly.
        #global MBerr
        mba=0 
        val_reg=''
        mcount=0
        block=0 # vigade arv
        self.ts = time.time()
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
        
        # -- DI CONF BITS
        # 1 - value 1 = warningu (values can be 0 or 1 only)
        # 2 - value 1 = critical, 
        # 4 - value inversion 
        # 8 - value to status inversion
        # 16 - immediate notification on value change (whole multivalue service will be (re)reported)
        # 32 - this channel is actually a writable coil output, not a bit from the register (takes value 0000 or FF00 as value to be written, function code 05 instead of 06!)
        #     when reading coil, the output will be in the lowest bit, so 0 is correct as bit value

        try:
            Cmd="BEGIN IMMEDIATE TRANSACTION" # hoiab kinni kuni mb suhtlus kestab? teised seda ei kasuta samal ajal nagunii. iga tabel omaette.
            conn.execute(Cmd)
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
                    #print('di group mba '+str(bmba)+' start ',bfirst) # debug
                else: # not the first
                    if mba == bmba and regadd == blast+1: # sequential group still growing
                        blast = regadd
                        bcount=bcount+1
                        #print('di group end shifted to',blast) # debug
                    else: # a new group started, make a query for previous 
                        #print('di group end detected at regadd',blast,'bcount',bcount) # debugb
                        #print('going to read di registers from',bmba,bfirst,'to',blast,'regcount',bcount) # debug
                        self.read_di_grp(bmba,bfirst,bcount) # reads and updates table with previous data
                        bfirst = regadd # new grp starts immediately
                        blast = regadd
                        bcount=1
                        bmba=mba
                        #print('di group mba '+str(bmba)+' start ',bfirst) # debug
                        
            if bfirst != 0: # last group yet unread
                #print('di group end detected at regadd',blast) # debugb
                #print('going to read di registers from',bmba,bfirst,'to',blast,'regcount',bcount) # debug
                self.read_di_grp(bmba,bfirst,bcount) # reads and updates table
            
            #  bit values updated for all dichannels
            
            conn.commit()  # dichannel-bits transaction end

            return 0

        except: # Exception,err:  # python3 ei taha seda viimast
            msg='there was a problem with dichannels data reading or processing! '+str(sys.exc_info()[1])
            #syslog(msg)
            print(msg)
            traceback.print_exc()
            time.sleep(1)
            return 1

    # sync_di() end. FRESHENED DICHANNELS TABLE VALUES AND CGH BITS (0 TO SEND, 1 TO PROCESS)




    def make_dichannels(self): # send di svc with changed member or (lapsed sendperiod  AND updated less than 5 s ago (still fresh). ts_chg used as update ts)
        # mask == 1: send changed, mask == 3: send all
        mba=0 # local here
        val_reg=''
        desc=''
        comment=''
        mcount=0
        ts_created=self.ts # timestamp
        #sumstatus=0 # summary status for a service, based on service member statuses
        chg=0 # status change flag with 2 bits in use!
        value=0
        ts_last=0 # last time the service member has been reported to the server
        cur=conn.cursor()
        try:
            Cmd="BEGIN IMMEDIATE TRANSACTION" # transaction, dichannels
            conn.execute(Cmd) # dichannels
    
            # dichannels(mba,regadd,bit,val_reg,member,cfg,block,value,status,ts_chg,chg,desc,comment,ts_msg,type integer)
            Cmd="select val_reg,max((chg+0) & 1),min(ts_msg+0) from dichannels where ((chg+0 & 1) and ((cfg+0) & 16)) or ("+str(self.ts)+">ts_msg+"+str(self.sendperiod)+") group by val_reg"
            # take into account cfg! not all changes are to be reported immediately! cfg is also for application needs, not only monitoring!
            cur.execute(Cmd)

            for row in cur: # services to be processed. either just changed or to be resent
                
                #lisa='' # string of space-separated values
                val_reg=''
                sta_reg=''
                sumstatus=0 # at first

                val_reg=row[0] # service name
                chg=int(row[1]) # change bitflag here, 0 or 1
                ts_last=int(row[2]) # last reporting time
                if chg == 1: # message due to bichannel state change
                    msg='DI service to be reported due to change: '+val_reg
                    print(msg)
                
                udp.send(self.make_dichannel_svc(val_reg)) # sends this service tuple away via udp.send()
                
            conn.commit() # dichannels transaction end

        except:
            traceback.print_exc()
            #syslog('err: '+repr(err))
            msg='there was a problem with make_dichannels()! '+str(sys.exc_info()[1])
            print(msg)
            #syslog(msg)

    #make_dichannels() lopp




    def make_dichannel_svc(self,val_reg): # one service. find status and send away.
        ''' Find service status and return tuple of sta_reg,status, val_reg,value to be sent away. 
            Execute by make_dichannels() to get transaction
           '''
        # no transaction started here because we are in transaction (started make_dichannels())
        lisa='' # value string
        sumstatus=0 # status calc
        cur=conn.cursor()
        Cmd="select * from dichannels where val_reg='"+val_reg+"' order by member asc" # data for one service ###########
        cur.execute(Cmd)
        for srow in cur: # ridu tuleb nii palju kui selle teenuse liikmeid, pole oluline milliste mba ja readd vahele jaotatud
            #print 'row in cursor3a',srow # temporary debug
            mba=0 # local here
            regadd=0
            bit=0 #
            member=0
            cfg=0
            chg=0
            ostatus=0 # previous value
            ovalue=0 # previous or averaged value
            ots=0 # previous update timestamp
            avg=0 # averaging strength, has effect starting from 2
            # 0      1   2     3      4      5     6     7     8    9     10   11   12      13     14
            #(mba,regadd,bit,val_reg,member,cfg,block,value,status,ts_chg,chg,desc,comment,ts_msg,type integer) # dichannels
            if srow[0] != '':
                mba=int(srow[0])
            if srow[1] != '':
                regadd=int(srow[1]) # must be int! can be missing
            if srow[2] != '':
                bit=int(srow[2])
            val_reg=srow[3] #  string
            if srow[4] != '':
                member=int(srow[4])
            if srow[5] != '':
                cfg=int(srow[5]) # configuration byte
            # block?? to prevent sending service with errors. to be added!
            if srow[7] != '':
                value=int(float(srow[7])) # new value
            if srow[8] != '':
                ostatus=int(float(srow[8])) # old status
            if srow[9] != '':
                ots=eval(srow[9]) # value ts timestamp
            if srow[10] != '':
                chg=eval(srow[10]) # change flag 0..3
            
            #print 'make_dichannel_svc():',val_reg,'member',member,'value before status proc',value,', lisa',lisa  # temporary debug

            if lisa != "": # not the first member any nmore
                lisa=lisa+" "

            # status and inversions according to configuration byte
            status=0 # initially for each member
            if (cfg&4): # value2value inversion
                value=(1^value) # possible member values 0 voi 1
            lisa=lisa+str(value) # adding possibly inverted member value to multivalue string

            if (cfg&8): # value2status inversion
                value=(1^value) # member value not needed any more

            if (cfg&1): # status warning if value 1
                status=value #
            if (cfg&2): # status critical if value 1
                status=2*value

            if status>sumstatus: # summary status is defined by the biggest member sstatus
                sumstatus=status # suurem jaab kehtima

            print 'make_channel_svc():',val_reg,'member',member,'value after status proc',value,', status',status,', sumstatus',sumstatus,', lisa',lisa  # debug


            #dichannels table update with new chg ja status values. no changes for values! chg bit 0 off! set ts_msg!
            Cmd="UPDATE "+self.in_sql+" set ts_msg='"+str(self.ts)+"', chg='"+str(chg&2)+"' where val_reg='"+str(val_reg)+"'" # koik liikmed korraga sama ts_msg
            conn.execute(Cmd)
        
        sta_reg=val_reg[:-1]+"S" # service status register name
        if sta_reg == val_reg: # only status will be sent then!
            val_reg=''
            lisa=''

        return sta_reg,sumstatus,val_reg,lisa  # returns tuple to send. to be send to udp.send([])

            
            
    def sync_do(self): # synchronizes DO bits (output channels) with data in dochannels table, using actual values checking via output records in dichannels table
        print('write_dochannels start') # debug
        # find out which do channels need to be changed based on dichannels and dochannels value differencies
        # and use write_register() write modbus registers (not coils) to get the desired result (all do channels must be also defined as di channels in dichannels table!)
        respcode=0
        mba=0 # lokaalne siin
        omba=0 # previous value
        val_reg=''
        desc=''
        value=0
        word=0 # 16 bit register value
        #comment=''
        mcount=0
        #Cmd1=''
        #Cmd3=''
        #Cmd4=''
        ts_created=self.ts # selle loeme teenuse ajamargiks
        cur=conn.cursor()
        
        try:
            Cmd="BEGIN IMMEDIATE TRANSACTION" # conn3, kogu selle teenustegrupiga (aichannels) tegelemine on transaction - read only, no need...
            conn.execute(Cmd)
            
            # 0      1   2    3        4      5    6      7
            #mba,regadd,bit,bootvalue,value,rule,desc,comment

            # write coils first
            Cmd="select dochannels.mba,dochannels.regadd,dochannels.value from dochannels left join dichannels on dochannels.mba = dichannels.mba AND dochannels.regadd = dichannels.regadd AND dochannels.bit = dichannels.bit where dochannels.value != dichannels.value and (dichannels.cfg & 32) group by dochannels.mba,dochannels.regadd " # coils only here, 100..115
            # the command above retrieves mba, regadd and value for coils where bit values do not match in dichannels and dochannels 
            #print "Cmd=",Cmd
            cur.execute(Cmd)

            for row in cur: # got mba, regadd and value for coils that need to be updated / written
                regadd=0
                mba=0

                if row[0] != '':
                    mba=int(row[0]) # must be a number
                if row[1] != '':
                    regadd=int(row[1]) # must be a number
                if row[1] != '':
                    value=int(row[2]) # 0 or 1 to be written
                print('going to write as a coil register mba,regadd,value',mba,regadd,value) # temporary

                respcode=mb.write_register(reg=regadd, value=value, mba=mba)
                
        except:
            print('problem with dochannel grp select!')
            traceback.print_exc()
            sys.stdout.flush()

        # end coil writing


        # write do register(s?) now. take values from dichannels and replace the bits found in dochannels. missing bits are zeroes.
        # take powerup values and replace the bit values in dochannels to get the new do word
        # only write the new word if the bits in dochannel are not equal to the corresponding bits in dichannels
        Cmd="select dochannels.mba,dochannels.regadd,dochannels.bit,dochannels.value,dichannels.value from dochannels left join dichannels on dochannels.mba = dichannels.mba AND dochannels.regadd = dichannels.regadd AND dochannels.bit = dichannels.bit where round(dochannels.value) != round(dichannels.value) and not(dichannels.cfg & 32) group by dochannels.mba,dochannels.regadd,dochannels.bit"  # find changes only
        # without round() 1 != 1.0 !
        #Cmd="select dochannels.mba,dochannels.regadd,dochannels.bit,dochannels.value,dichannels.value from dochannels left join dichannels on dochannels.mba = dichannels.mba AND dochannels.regadd = dichannels.regadd AND dochannels.bit = dichannels.bit group by dochannels.mba,dochannels.regadd,dochannels.bit" # mba,reg,bit,dovalue, divalue changed or not
        # the command above retrieves mba, regadd that need to be written as 16 bit register
        # this solution should work for multiple modbus addresses and different registers. first cmd is for write on change only, the second is for debugging, always write!
        #print(Cmd)
        try:
            cur.execute(Cmd)
            mba_array=[]
            mba_dict={} # close to json nested format [mba[reg[bit,ddo,di]]]
            reg_dict={}
            bit_dict={}
            for row in cur: # got sorted by mba,regadd,bit values for bits that need to be updated / written
                tmp_array=[]
                #print('got something from dochannels-dichannels left join') # debug 
                regadd=0
                mba=0
                bit=0
                di_value=0
                do_value=0
                #syslog('change in output needed for mba,regadd,bit '+str(int(float(row[0])))+", "+str(int(float(row[1])))+", "+str(int(float(row[2])))+' from value '+str(int(float(row[4])))+' to '+str(int(float(row[3]))))
                try:
                    mba=int(float(row[0])) # must be number
                    regadd=int(float(row[1])) # must be a number. 0..255
                    bit=(int(float(row[2]))) # bit 0..15
                    tmp_array.append(int(float(row[3])))  # do_value=int(row[3]) # 0 or 1 to be written
                    tmp_array.append(int(float(row[4]))) # di_value=int(row[4]) # 0 or 1 to be written
                    bit_dict.update({bit : tmp_array}) # regadd:[bit,do,di] dict member
                    reg_dict.update({regadd : bit_dict})
                except:
                    msg='failure in creating tmp_array '+repr(tmp_array)+' '+str(sys.exc_info()[1])
                    print(msg)
                    #syslog(msg)
                    traceback.print_exc()
                    
                mba_dict.update({mba : reg_dict})
                print('reg_dict',reg_dict,'mba_dict',mba_dict) # debug
                
                # jargmine on jama?
                if mba != omba:  #  and omba != 0: # next mba, write register using omba now!
                    mba_array.append(mba) # mba values in array
                    omba=mba
                #####
                
            # dictionaries ready, let's process
            for mba in mba_dict.keys(): # this key is string!
                print('finding outputs for mba,regadd',mba,regadd)
                for regadd in reg_dict.keys(): # chk all output registers defined in dochannels table
                    
                    #word=client.read_holding_registers(address=regadd, count=1, unit=mba).registers[0] # find the current output word to inject the bitwise changes
                    word=mb.read(self, mba, reg, count = 1, type = 'h')[0]
                    print('value of the output',mba,regadd,'before change',format("%04x" % word)) # debug
                    
                    for bit in bit_dict.keys():
                        print('do di bit,[do,di]',bit,bit_dict[bit]) # debug
                        word2=bit_replace(word,bit,bit_dict[bit][0]) # changed the necessary bit. can't reuse / change word directly!
                        word=word2
                        #syslog('modified by bit '+str(bit)+' value '+str(bit_dict[bit][0])+' word '+format("%04x" % word)) # debug
                    #print('going to write a register mba,regadd,with modified word - ',mba,regadd,format("%04x" % word)) # temporary

                    respcode=mb.write(mba, regadd, type = 'h', value=word)
                    if respcode == 0:
                        msg='output written - mba,regadd,value '+str(mba)+' '+str(regadd)+' '+format("%04x" % word)
                    else:
                        msg='FAILED writing register '+str(mba)+'.'+str(regadd)+' '+str(sys.exc_info()[1])

                    #syslog(msg)
                    print(msg)

                
                omba=mba # to detect mba change. values in array mba_array
                    
        except:
            msg='problem with dichannel grp select in write_do_channels! '+str(sys.exc_info()[1])
            print(msg)
            #syslog(msg)
            traceback.print_exc() # debug
            sys.stdout.flush()
            time.sleep(1)
            return 1

        conn.commit() # transaction end, perhaps not even needed - 2 reads, no writes...
        msg='do sync done'
        print(msg) # debug
        #syslog(msg) # debug
        return 0
        # write_dochannels() end. 
        
        
    def doall(self): # do this regularly, blocks for the time of socket timeout!
        ''' Does everything on time if executed regularly '''
        self.ts = time.time()
        if self.ts - self.ts_read>self.readperiod:
            self.ts_read = self.ts
            self.sync_di() # 
            self.sync_do() # writes output registers to be changed via modbus, based on feedback on di bits
            self.make_dichannels() # compile services and send away on change or based on ts_last regular basis
            
        return 0
