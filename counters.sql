-- counters as modbus registers, several (2,3 or 4) registers can be combined to increase the counter size
-- member is the order of the values in multivalue messages. x1,x2 and y1,y2 define the linear conversion from raw to value
-- power calculation based on increment is possible in adition to cumulative readings. behavior depends on config

-- CONFIG BIT MEANINGS
-- # 1 - below outlo warning, 4 - above outhi warning
-- # 2 - below outlo critical, 8 - above outhi critical
-- # NB! 3 - below outlo ei saada, 12 - above outhi do not send /  UNKNOWN

-- 16 - power flag
-- 32 - regular reset  
-- 64 - resettable 0=montly, 1=daily
-- 128 RESERV (resettable hourly??)

-- counters are normally located in 2 registers 
 
PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;

CREATE TABLE counters(mba,regadd,val_reg,member,cfg,x1,x2,y1,y2,outlo,outhi,avg,block,raw,value,status,ts,desc,comment,wcount INTEGER);

INSERT INTO "counters" VALUES('9','412','EZV','1','0','0','800','0','1000','','','','','','110','','','vent seadme en tarve KWh','800 pulse/kWh',2); -- 3f energia impulsid AJUTISELT kinni, mingi viga list index...

 -- wcount -2 is for barionet, lsw msw order weird. normally 2 for msw, lsw. can be 1 or 4 as well.

-- power to be counted based on raw reading increment and time between the readings.
-- P1W is sending W for electricity and gas consumption. cannot be negative or more than 15 / 30 kW
-- INSERT INTO "counters" VALUES('1','410','P1W','1','16','0','500','0','3600000','0','20000','2','','','','','','el voimus, 500 imp=3600 kWs','max 15kW 25A kaitsmete korral?',-2);
-- INSERT INTO "counters" VALUES('1','412','P1W','2','16','0','100','0','33732000','0','30000','2','','','','','','gaasi voimsus kv alusel, 100 imp=33732000 Ws','max 30kW?',-2);

CREATE UNIQUE INDEX co_regmember on 'counters'(val_reg,member);
COMMIT;

