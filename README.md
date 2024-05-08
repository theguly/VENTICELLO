# VENTICELLO

(https://upload.wikimedia.org/wikipedia/it/6/6b/Bombolopiange.jpg)

inkbird has a very useful thermometer that can power a heating/cooling source when temperature goes above/beyond a configured limit, and also provide a cool mobile app.

unfortunately, it doesn't have APIs. we can of course reverse engineer the app protocol, but i had a couple of ESP board gathering dust and i have preferred to experiment

this project can be used to monitor, log through a webserver and (in the near future) power a heating/cooling device based on the measured temperature.

the ESP board will measure temperature using supported sensors, and send data using a wifi connection to a remote webserver that logs and present measurement.

in the near future (targeting max end of june) i'll add relais support and it will be possible to power a cooling/heating device to really control the temperature of the wort.

because of this super useful feature for homebrewing, and because we miss Bombolo, the project has been named VENTICELLO because `he controls the weather`.

notes:

- i know it shouldn't be micropython, lazyness sometimes sucks sometimes wins
- temp are set in C, if you prefer F you are on your own ¯\\\_(ツ)\_/¯
- works on my laptop, if it doesn't work on your open a ticket or send a PR

# USAGE

## esp8266

i have tested using the esp8266 nodemcu v3, you can find one anywhere from aliexpress to amazon. probably it can work on arduino, rpico and other board that supports micropython and has GPIO, let me know if you test with different boards.

1. install micropython on the board
1. mpremote mip install github:peterhinch/micropython-async/v3/primitives
1. mpremote mip install github:peterhinch/micropython-async/v3/threadsafe
1. mpremote cp measure.py /main.py
1. configure config.py
1. mpremote cp config.py /config.py

### config.py

config dict is pretty self explainatory, sensors requires more attention.

dict subkey is the name of the location, and have to reflect config.php from _www_. you can enable/disable a given sensor setting the _enable_ property.

the main.py script handles out of the box _DS18X20_ and _DHT22_ sensors, i have only tested one single _dht_ and i use two _ds_ sensors on the same pin. sensor type can be set using the _type_ property, and the connected pin is set on the _loc_ property.

_ds_ sensors have a unique id that allows to connect more than one using a single pin. that id is required by main script.

to get rom id, run following python code:

```from machine import Pin
from ds18x20 import DS18X20
from onewire import OneWire
z = DS18X20(OneWire(Pin(4)))
z.convert_temp()
z.scan()
```

i believe it can easily support any other sensor, given micropython has the library, and you configure _loc_ with the right path.

relais stanza can be optionally set to link sensors with external power sources. given a target temperature and an accepted delta, both set on any configured relay, main.py script will power up a heating or cooling system based on the measured temperature.

this can be very useful during the fermentation phase when you target a wort temperature of say 20C. when the temperature goes below the delta, the relay connected to the heating machine will be open and if the temperature becomes too high the relay connected to the cooling machine will be open.

I ~~have only tested~~will test SRD-05VDC-SL-C

### wiring

TODO

## web

1. copy the content of www to any webserver that supports php
1. create the database
1. create log table: `create table log (ts int NOT NULL, temperature varchar(255));`
1. create sensor measurement tables, change DBTABLE to follow config.py/php sensors: `create table DBTABLE (ts int NOT NULL, location varchar(30), temperature varchar(4));`
1. create log table, change DBTABLE to follow config.php: `create table {DBTABLE}_log (insert_time timestamp DEFAULT current_timestamp(), ts int NOT NULL, message varchar(255));`
1. write a config.php file starting from config.php.sample
1. place jpgraph (https://jpgraph.net/) in the \_jpgraph folder

to view logs, visit url https://www.xyz.com/temperature.php?show=

where show can be one of :

- d => show day
- w => show week (default)
- y => show year

and the optional l ask for a specific location, with a default of all

to send measurement:
https://www.xyz.com/temperature.php?time=_measure-time_&l=_sensor-location-in-configfile_&th=_measured-temperature_

### config.php

the web configuration is very similar to the python one, but it's way shorter. each define is commented, please keep in sync _LOCATIONS_ and the optional _TARGET_TEMP_ with _sensors_ on config.py

# TODO

- implement authentication
- add some pictures to README.md
- ticks on graph.php are not always the best
- measure.py adjust tosend log time after ntp
- get rid of the useless uasyncio
- rewrite python in C
