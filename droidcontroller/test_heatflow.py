# test heatflow.py

from heatflow import *
fr = FlowRate()
he = HeatExchange(0.05)

fr.output(0,0)
time.sleep(2)

fr.output(0,1)
time.sleep(2)

fr.output(1,0)
time.sleep(2)

fr.output(1,1)
time.sleep(2)

fr.output(1,0)
time.sleep(2)

hf = fr.output(1,1)
print('hf l/s', hf)
he.setflowrate(hf)

he.output(0,40,30)
time.sleep(2)

he.output(1,40,30)
time.sleep(2)

he.output(1,40,30)
time.sleep(2)

he.output(1,40,30)
