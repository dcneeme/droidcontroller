# lighting control listening services from msgbus and publishing new services to mgsbus

from droidcontroller.util_n import UN # for val2int()
from droidcontroller.statekeeper import StateKeeper

import traceback, logging, time
log = logging.getLogger(__name__)

###############
class Lamp(object): # one instance per floor loop. no d or ac needed, just msgbus!
    def __init__(self, d, msgbus=None, in_svc={'K1W':[(1,1), (2,1)], 'KAW':[(1,3)], 'DKS':[(1,19)], 'DAS':[(1,6)], 'LAS':[(1,5)]}, 
            out_svc=['DOV',1], name = 'undefined', timeout = None, out = 0): # timeout in s
        #K1W like a switch, KAW like a pir, DAS like dim all, LAS like light all
        ''' 
        Virtual lamp that controls the actual io output channel, via level or dimmer pulse or (TBD) dali command.
        Input svc may present level or transition (define the change direction). 
        In order to mix manual and automated control, the levels should not be generally followed directly. 
        It is better to use transitions, to avoid conficts between inputs channels and enable multi-input control. 
        
        Presence sensors may be used to swith on or off (via timeout) if such services are defined.
        
        There may be several input services with similar or different properties. Define as list of lists.
        in_svc = {svc:[(member,mtype), ], } # mtype 1 invbyup, 2 invbydn, 3 invbyboth, 
                                               5 upbyup, 6 upbydn, 7 upbyboth
                                               9 followhi, 10 followlo, 11 followboth
       
        out_svc = svc, member. level!
                                               
    
        TESTING
        python
        from droidcontroller.msgbus import *; from droidcontroller.lamp import *
        msgbus=MsgBus(); lamp=Lamp(msgbus)
        lamp.inproc('KAW',[1]); lamp.get_state()
        '''
        self.name = name
        self.d = d # dchannels instance
        self.in_svc = in_svc # dict of lists
        self.out_svc = out_svc # one svc only
        self.invars = {} # keep the input states in memory
        self.msgbus = msgbus
        if msgbus:
            self.msgbus = msgbus
            for svc in self.in_svc:
                print('subscribing to '+svc)
                self.msgbus.subscribe('in_'+self.name+'_'+svc, svc, 'lights', self.listen_proc) # several members per svvc may have values & types
                currvalues = []
                for i in range(len(self.in_svc[svc])):
                    print(i, svc)
                    currvalues.append(None) # until replaced by values (from msgbus)
                self.invars.update({svc: currvalues})
            if len(self.in_svc) != len(self.invars):
                log.error('in_svc and invars len do not match for lamp '+self.name+'! invars: '+str(self.invars))
        else:
            low.warning('no msgbus in use...')
            
        self.darktime = False # presence sensors to activate ligths disabled
        self.out = out # lamp state on program start. None for no change!
        print('instance '+self.name+' created, in_svc '+str(self.in_svc)+', invars '+str(self.invars))

    def get_state(self):
        ''' Returns current output state 0 or 1 (latter is active). '''
        return self.out
    
    def listen_proc(self, token, subject, message):
        ''' Returns the value of received service member '''
        log.info('received from msgbus for '+self.name+':'+subject+', '+str(message))
        values = message['values'] # member index starting from 0
        self.inproc(subject, values)
      
      
        
    def inproc(self, svc, values):
        ''' Processes the lamp inputs service received 
            from msgbus token floorset, subject TBW, message {'values': [210, 168, 250, 210], 'status': 0} 
            if status == 1 then activate, otherwise inverse
        ''' 
        out = None # peaks lugema tegelikku! msgbus kaudu kuula ka seda!
        #print('svc,values',svc, values, type(svc), type(values)) ##
        if not isinstance(svc, str):
            log.error('invalid svc '+str(svc))
            return None
        if not isinstance(values, list): # 'list' in str(type(values)):
            log.error('invalid values '+str(values))
            return None
           
        print('processing svc '+svc+' values '+str(values))
        currvalues = self.invars[svc] # list
        for im in range(len(self.invars[svc])): # im = input member
            mtype = self.in_svc[svc][im][1]
            log.info(str(im)+' mtype '+str(mtype)+' values[im] '+str(values[im])+' currvalues[im] '+str(currvalues[im]))
            if values[im] != currvalues[im]:
                currvalues[im] = values[im]
                log.info('new value for svc '+svc+', im '+str(im)+', currvalues '+str(currvalues[im]))
                #processing according to the mtype    
                ## manual switches, bits 0..1
                if mtype == 1:
                    if values[im] == 1:
                        out = (self.out ^ 1)
                elif mtype == 2:
                    if values[im] == 0:
                        out = (self.out ^ 1)
                elif mtype == 3:
                    out = (self.out ^ 1)
                ## pir sensors, bitvalue 4 to flag
                if self.darktime == 1: # presence signals to activate light enabled (disactivate always operational it timeout)
                    if mtype == 5:
                        if values[im] == 1:
                            out = 1
                    elif mtype == 6:
                        if values[im] == 0:
                            out = 1
                    elif mtype == 7:
                        out = 1
                
            ## level control without change, bitvalue 8 to flag
            if mtype == 9:
                if values[im] == 1:
                    out = 1
            elif mtype == 10:
                if values[im] == 0:
                    out = 0
            elif mtype == 11:
                out = values[im]
            
            ## darktime sensor
            if mtype == 17:
                if values[im] == 1:
                    self.darktime = 1
            elif mtype == 18:
                if values[im] == 0:
                    self.darktime = 0
            if mtype == 19: # dark time depends on di level
                self.darktime = values[im]
                
            self.invars.update({svc: currvalues}) #remember the new valuelist
            
        if out != None:
            if out != self.out:
                log.info('lamp out change to '+str(out)+', to svc '+str(self.out_svc[0])+'.'+str(self.out_svc[1]))
                d.set_domember(out_svc[0], out_svc[1], out) # svc, member, value
                self.out = out
            #if self.msgbus:
            #    self.msgbus.publish(self.out_svc[0], {'values': [self.out], 'status': 0}) # 
            # liikme kaupa msgbus kaudu paha tegutseda...
            
        return out    
            
            
