import unittest
import sys

from counter2power import Counter2Power

def pulsesperkwh():
    return 1000

def onepulsews():
    return 1000 * 3600 / pulsesperkwh()

class PowerMeter():
    def __init__(self):
        self.lastpower = 0
        self.pulses = 0
        self.lasttime = None
        self.accupu = 0

    def getpulses(self, t, p):
        if self.lasttime == None:
            self.lasttime = t
            self.lastpower = p
            return self.pulses
        dt = t - self.lasttime
        ap = (self.lastpower + p) / 2
        self.lasttime = t
        self.lastpower = p
        self.accupu += dt * ap
        self.pulses += int(self.accupu / onepulsews())
        self.accupu = self.accupu % onepulsews()
        return self.pulses

class Test(unittest.TestCase):
    def test_power(self):
        pm = PowerMeter()
        cnt = 0
        c2p = Count2Power(svc_name = 'test', svc_member = 99, mininc = 10, maxinc = 100, minvalue = 0, maxvalue = None)
        for ts in range(3600):
            cnt = pm.getpulses(ts, 2000)
            data = c2p.calc(ts, cnt)
            sys.stderr.write(str(ts) + "," + str(cnt) + "," + str(data[0]) + "," + str(data[1]) + "," + str(data[2]) + "," + str(data[3]) + "\n")
#            print(data)
#        sys.stderr.write(str(cnt) + " pulses\n")

if __name__ == '__main__':
    unittest.main()

