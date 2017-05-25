Yandex Volta is a framework for mobile performance and energy efficiency analysis.


# Links
A [mobile performance testing](https://www.youtube.com/watch?v=zcTG2PzXD3s) talk by Alexey Lavrenuke (in Russian).
An [article](https://habrahabr.ru/company/yandex/blog/311046/) about the device (in Russian).


# What do you need
* **A Volta Box**. Volta Box is an arduino-based current meter and power source for your mobile device. We will provide schematics after a while. Contact us if you want to get explanation right now.
* An **instrumented** mobile device. You need to extract a battery from your mobile device and connect **Volta Box** instead.
* If you want to control your device with **adb** while running your tests, you also need a current-limiting USB cable. Currently, we use FET to make those (google "FET current limiter").


# Usage:  
Install with ```pip install volta```, connect your device, run ```volta```.


# Architecture:
![Architecture scheme](/docs/architecture.png)
[yEd scheme](/docs/architecture.graphml)


# Volta components
There are different types of Volta modules

**Core** - module that configures test life cycle and test pipeline, creates, configures and controls other modules.

Data Providers:
* **VoltaBox** - module for different types of Volta Boxes.
* **Phone** - module for different types of phones. Android and iPhone supported.
* **Events** - phone logs parser module.

Data Listeners:
* **Sync** - cross-corellation sync module, syncs volta logs to phone logs.
* **Uploader** - data uploader module (e.g. to Overload).
* **Report** - file write module.


# Using Volta


## Command-line entry-point `volta`
Use command-line entry-point `volta` with .yaml config
`volta -c config.yaml`

Sample yaml config for cli-wrapper:
```yaml
volta:
  type: '500hz'
  source: '/dev/cu.wchusbserial1420'
phone:
  type: 'android'
  unplug_type: 'auto'
  source: '01e345da733a4764'
sync:
  search_interval: 30
```
This config creates a test with **VoltaBox500Hz** at **/dev/cu.wchusbserial1420** and android phone id **01e345da733a4764**, then starts to collect and process data from VoltaBox and the phone.

If you want to stop the test, press **Ctrl+C** or send **SIGTERM** signal to the process.


## Core as python module
Also, if you want to control test execution or integrate Volta into your CI, you can use Core as python library.

Sample usage:
```python
from volta.core.core import Core

config = {
    'volta': {
        'source': '/dev/cu.wchusbserial1420',
        'type': '500hz'
    },
    'phone': {
        'source': '01e345da733a4764',
        'type': 'android',
        'unplug_type': 'auto'
    },
   'sync': {
       'search_interval': 30
    }
}

core = Core(config)
try:
    core.configure()
    core.start_test()
except KeyboardInterrupt:
    core.end_test()
finally:
    core.post_process()
```

## VoltaBox class


If you want more flexibility using of Volta components, you can use provided Volta modules (or write you own) as python classes.

Sample usage:
```python
from volta.boxes.box500hz import VoltaBox500Hz
import queue
import time
import logging

config = {
  'source': '/dev/cu.wchusbserial1420'
}
volta = VoltaBox500Hz(config) # create VoltaBox class
q = queue.Queue() # create python queue for results
volta.start_test(q) # start test and pass results queue
time.sleep(5) # do something (start autotests, do manual testing ...). I passed 5 seconds sleep as a placeholder.
volta.end_test() # end test execution

# and you can read pandas.DataFrames from results queue,
# data format: `['uts', 'value']`. Microseconds from test start and electrical currents value.
print(q.get_nowait())
```

## Phone class


We have modules for Android and iPhone. If you want to use your own phone (e.g. Windows Phone), you can write your own phone module.

### Phone class - Android


Works with android phones. Reads/parses system logs (`adb logcat`), starts lightning app for synchronization, installs/starts/runs tests on device.

Sample usage:
```python
from volta.phones.android import AndroidPhone
import queue
import time
import logging

config = {
  'source': '01e345da733a4764',  # android device id
  'unplug_type': 'auto',         # test type
  'test_apps': [
    'http://hostname.tld/path/to/first/apk1.apk',
    'http://hostname.tld/path/to/second/apk2.apk',,
  ],
  'test_package': 'ru.yandex.mobile.test',
  'test_class': 'ru.yandex.test.highload.Tests',
  'test_runner': 'android.support.test.runner.AndroidJUnitRunner'
}

phone = AndroidPhone(config) # create Phone class
q = queue.Queue() # create python queue for results
phone.prepare() # prepare phone to test - clean logs, install test apps and install volta's `lightning` app for synchronization
phone.start(q) # start test and pass results queue
phone.run_test() # run test app, specified in config
time.sleep(5) # do something ...
phone.end() # end test execution

# and you can read pandas.DataFrames from results queue,
# data format: `['sys_uts', 'message']`. Microseconds from first event in phone log and message.
print(q.get_nowait())
```

### Phone class - iPhone


Works with iPhone. Reads/parses system logs (`cfgutil`). If you want to use this module, you should install [Apple Configurator 2](https://itunes.apple.com/us/app/apple-configurator-2/id1037126344?mt=12) and use Mac.

To install apps on iPhone and control them you need to use `Apple's Instruments`.

Everithing else is the same as for AndroidPhone class.

Sample usage:
```python
from volta.phones.iphone import iPhone
import queue
import time
import logging

config = {
  'source': '0x6382910F98C26',
}
phone = iPhone(config) # create Phone class
q = queue.Queue() # queue for results
phone.prepare()
phone.start(q)
phone.end()
```

## EventsRouter class


Once you get data from one of your phone modules, parse it with **EventsRouter**. It reads phone's results queue, parses messages, groups them by different types and sends them to  listeners.

Also, applications can write to phone's system log any information you want to use later for debugging/better synchronization or mark some special events.


Special messages format:
```
%app%: [volta] %nanotime% %type% %tag% %message%
```


Special message format sample:
```
lightning: [volta] 12345678 fragment TagFragment start
```


Currently we have those types of special messages supported by **EventsRouter**:
* **sync** - synchronization message, Sync module uses it for cross-correlation
* **event** - event message, you can write any information you need by your application on phone and send it to system log
* **fragment**
* **metric**


Everything else (e.g. default phone system log messages) is grouped to **unknown** message type.

Sample usage:
```python
from volta.phones.android import AndroidPhone
from volta.events.router import EventsRouter
from volta.report.report import FileListener
import queue
import time
import uuid

phone_config = {'source': '01e345da733a4764'} # phone id
phone = AndroidPhone(phone_config) # Phone class
phone_q = queue.Queue() # queue for results
phone.start(phone_q) # start phone log reader

test_id = uuid.uuid4() # some test id
event_types = ['event', 'sync', 'fragment', 'metric', 'unknown'] # define event types
event_listeners = {key:[] for key in event_types} # create dict w/ empty list for each event type

event_fnames = {
    key:"{data}_{id}.data".format(
        data=key,
        id=test_id
    ) for key in event_types
} # file name for each event type

# setup FileListener for each event type (at this sample we write each event type to its own file)
for type, fname in event_fnames.items():
    listener_config = {'fname': fname}
    f = FileListener(listener_config)
    event_listeners[type].append(f)

# start events router
events_router = EventsRouter(phone_q, event_listeners)
events_router.start()

time.sleep(10)
phone.end()
time.sleep(5)
events_router.close()

# in the end you will have files w/ events for each event type in current working directory
```



# Questions
Any questions to Alexey Lavrenuke <direvius@yandex-team.ru>.

