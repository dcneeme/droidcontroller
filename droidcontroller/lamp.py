# lighting control listening services from msgbus and publishing new services to mgsbus

from droidcontroller.util_n import UN # for val2int()
from droidcontroller.statekeeper import StateKeeper

import traceback, logging, time
log = logging.getLogger(__name__)

###############
class Lamp(object): # one instance per floor loop. no d or ac needed, just msgbus!
    def __init__(self, msgbus=None, in_svc={'K1W':[(1,1), (2,2)], 'KAW':[(1,3)]}, out_svc=['DOV',1], name = 'undefined', timeout = None, out = 0): # timeout in s
        ''' Virtual lamp that controls the actual io output channel, via level or dimmer pulse or (TBD) dali command.
            Input svc may present level or transition (define the change direction). 
            In order to mix manual and automated control, the levels should not be generally followed directly. 
            It is better to use transitions, to avoid conficts between inputs channels and enable multi-input control. 
            
            Presence sensors may be used to swith on or off (via timeout) if such services are defined.
            
            There may be several input services with similar or different properties. Define as list of lists.
            in_svc = [[svc,member,mtype],] # mtype 1 invbyup, 2 invbydn, 3 invbyboth, 5 forcehi, 6 forcelo, 7 follow
            out_svc = svc, member. level!
        
        TESTING
        python
        from droidcontroller.msgbus import *; from droidcontroller.lamp import *
        msgbus=MsgBus(); lamp=Lamp(msgbus)
        lamp.inproc('KAW',[1]); lamp.get_state()
        '''
        self.name = name
        self.in_svc = in_svc # dict of lists
        self.out_svc = out_svc # one svc only
        self.invars = {} # keep the input states in memory
        self.msgbus = msgbus
        if msgbus != None:
            self.msgbus = msgbus
            for svc in self.in_svc:
                print('subscribing to '+svc)
                self.msgbus.subscribe('in_'+self.name+'_'+svc, svc, 'lights', self.listen) # several members per svvc may have values & types
                currvalues = []
                for i in range(len(self.in_svc[svc])):
                    print(i, svc)
                    currvalues.append(None) # until replaced by values (from msgbus)
                self.invars.update({svc: currvalues})
                
        self.out = out
        print('instance '+self.name+' created, in_svc '+str(self.in_svc)+', invars '+str(self.invars))

    def get_state(self):
        ''' Returns current output state 0 or 1 (latter is active). '''
        return self.out
    
    def listen(self, token, subject, message):
        ''' Returns the value of received service member '''
        log.info('received from msgbus for '+self.name+':'+subject+', '+str(message))
        svc = message['subject'] # not to be returned, not important
        values = message['values'][self.in_svc[subject]] # extract one member value
        return svc, values
        
    def inproc(self, svc, values):
        ''' Processes the lamp inputs service received 
            from msgbus token floorset, subject TBW, message {'values': [210, 168, 250, 210], 'status': 0} 
            if status == 1 then activate, otherwise inverse
        ''' 
        out = None # peaks lugema tegelikku! msgbus kaudu kuula ka seda!
        print('svc,values',svc, values, type(svc), type(values)) ##
        if 'str' in str(type(svc)):
            pass
        else:
            log.error('invalid svc '+str(svc))
            return None
        if 'list' in str(type(values)):
            pass
        else:
            log.error('invalid values '+str(values))
            return None
        if len(values) != len(self.invars[svc]):
            log.error('values '+str(values)+' length does not match invars['+svc+'] '+str(self.invars[svc])+' lenght!')
            return None
            
        print('processing svc '+svc+' values '+str(values))
        currvalues = self.invars[svc] # list
        for im in range(len(self.invars[svc])): # im = input member
            if values[im] != currvalues[im]:
                mtype = self.in_svc[svc][im][1]
                currvalues[im] = values[im]
                print('new value for svc %s im %d: %d',svc,im,currvalues[im])
                #processing according to the mtype    
                if mtype == 1:
                    if values[im] == 1:
                        out = (self.out ^ 1)
                elif mtype == 2:
                    if values[im] == 0:
                        out = (self.out ^ 1)
                elif mtype == 3:
                    out = (self.out ^ 1)
                        


            self.invars.update({svc: currvalues}) #remember the new valuelist
            
        if out != None:
            if out != self.out:
                log.info('lamp out change to '+str(out))
            if self.msgbus != None:
                self.msgbus.publish(self.out_svc[0], {'values': [self.out], 'status': 0}) # statuse suhtes ei vota siin seisukohta, peaks ehk olema None?
        return out    
            
            
    
