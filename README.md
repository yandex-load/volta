Yandex Volta is a framework for mobile performance and energy efficiency analysis.

[Telegram](https://t.me/joinchat/AAAAAAvBER7vU-672v1jbw) chat

![Volta](images/volta_small.jpg)

**Table of Contents**

   * [Links](#links)
   * [What do you need](#what-do-you-need)
   * [Usage](#usage)
   * [Architecture](#architecture)
   * [Volta components](#volta-components)
   * [Using Volta](#using-volta)
      * [Command-line entry-point volta](#command-line-entry-point-volta)
      * [Core as module](#core-as-module)
      * [Data Providers](#data-providers)
         * [VoltaBox module](#voltabox-module)
         * [Phone module](#phone-module)
            * [Phone module - Android](#phone-module---android)
            * [Phone module - iPhone](#phone-module---iphone)
      * [Data Mappers](#data-mappers)
         * [Events module - Router](#events-module---router)
      * [Data Listeners](#data-listeners)
         * [Sync module - SyncFinder](#sync-module---syncfinder)
            * [Report module - FileListener](#report-module---filelistener)
            * [Uploader module - DataUploader](#uploader-module---datauploader)
      * [API](#api)
         * [HTTP API](#http-api)
   * [Questions](#questions)


# Links
A [mobile performance testing](https://www.youtube.com/watch?v=zcTG2PzXD3s) talk by Alexey Lavrenuke (in Russian).
An [article](https://habrahabr.ru/company/yandex/blog/311046/) about the device (in Russian).


# What do you need
* **A Volta Box**. Volta Box is an arduino-based current meter and power source for your mobile device. We will provide schematics after a while. Contact us if you want to get explanation right away.
* An **instrumented** mobile device. You need to extract a battery from your mobile device and connect **Volta Box** instead.
* If you want to control your device with **adb** while running your tests, you also need a current-limiting USB cable. Currently, we use FET to make those (google "FET current limiter").


# Usage
Install with ```pip install volta```, connect your device, run ```volta```.


# Architecture
![Architecture scheme](/docs/architecture.png)
[yEd scheme](/docs/architecture.graphml)


# Volta components
There are different types of Volta modules

[Core](volta/core/core.py) - core module, configures test life cycle and test pipeline.
Creates, configures and controls other modules.

**Data Providers**
* [VoltaBox](volta/providers/boxes/) - module for different types of Volta Boxes.
* [Phone](volta/providers/phones/) - module for different types of phones. Android and iPhone supported.

**Data Mappers**
* [Events](volta/mappers/events/) - phone logs parser module.

**Data Listeners**
* [Sync](volta/listeners/sync/) - cross-corellation sync module, syncs volta logs to phone logs.
* [Uploader](volta/listeners/uploader/) - data uploader module (e.g. to Overload).
* [Report](volta/listeners/report/) - file write module.


# Using Volta

## Command-line entry-point `volta`
Use command-line entry-point `volta` with .yaml config
> `volta -c config.yaml`

Sample yaml config for cli-wrapper:
```yaml
volta:
  enabled: true
  type: '500hz'
  source: '/dev/cu.wchusbserial1420'
phone:
  enabled: true
  type: 'android'
  source: '01e345da733a4764'
sync:
  enabled: true
  search_interval: 30
```
This config creates a test with **VoltaBox500Hz** at **/dev/cu.wchusbserial1420** and android phone id **01e345da733a4764**, then starts to collect and process data from VoltaBox and the phone.

To stop the test, press **Ctrl+C** or send **SIGTERM** signal to the process.


## Core as module
Also, if you want to control test execution or integrate Volta into your CI, you can use Core as python library.
Core validates config and reads parts with `enabled`: `True` option only.

Sample usage:
```python
from volta.core.core import Core

config = {
    'volta': {
        'enabled': True,
        'source': '/dev/cu.wchusbserial1420',
        'type': 'binary'
    },
    'phone': {
        'enabled': True,
        'source': '01e345da733a4764',
        'type': 'android',
    },
   'sync': {
       'enabled': True,
       'search_interval': 30
    },
    'uploader':{
        'enabled': True,
        'task': 'LOAD-272'
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

## Data Providers
### VoltaBox module


If you want more flexibility using Volta components, you can use provided Volta modules (or write you own) as python classes.

Available configuration options:
* **source** (mandatory) - path to volta box device
* **sample_rate** - volta box sample rate, depends on software and which type of volta box you use. Default differs for each type of VoltaBox
* **chop_ratio** - chop ratio for incoming data, describes the way how pandas.DataFrames w/ data will be created. Default 1
* **baud_rate** - baud rate for VoltaBox. Default differs for each VoltaBox class.
* **grab_timeout** - timeout for data read from VoltaBox. Default 1

Sample usage:
```python
from volta.providers.boxes.box_binary import VoltaBoxBinary
from volta.core.validator import VoltaConfig
import queue
import time
import logging

config_dict = {
    'volta': {
        'source': '/dev/cu.wchusbserial1420',
        'type': 'binary'
    }
}
config = VoltaConfig(config_dict)
volta_box = VoltaBoxBinary(config) # VoltaBox class
q = queue.Queue()  # queue for results
volta_box.start_test(q)  # start acquiring data
time.sleep(5)  # do something (start autotests, do manual testing ...)
volta_box.end_test()  # stop acquiring data

# you can read pandas.DataFrames from results queue,
# data format: `['uts', 'value']`. Microseconds from test start and electrical currents value.
print(q.get_nowait())
```


### Phone module


We have modules for Android and iPhone. If you want to use some other type of device (e.g. Windows Phone), you can write your own phone module.

#### Phone module - Android


Works with android phones. Reads/parses system logs (`adb logcat`), starts lightning app for synchronization, installs/starts/runs tests on device.

Available configuration options:
* **source** (mandatory) - android device id
* **lightning** - path to lightning application (used for synchronization)
* **lightning_class** - lightning application class (how to run the app)
* **test_apps** - list of apps that will be installed to device for test
    * may be an url, e.g. 'http://myhost.tld/path/to/file'
    * may be a path to file, e.g. '/home/users/netort/path/to/file.apk'
* **test_class** - app class for run_test() stage
* **test_package** - app package for run_test() stage
* **test_runner** - app runner for run_test() stage

Sample usage:
```python
from volta.providers.phones.android import AndroidPhone
from volta.core.validator import VoltaConfig
import queue
import time
import logging

config_dict = {
    'phone': {
        'source': '01e345da733a4764',
        'type': 'android',
        'test_apps': [
            'http://hostname.tld/path/to/first/apk1.apk',
            'http://hostname.tld/path/to/second/apk2.apk',,
        ],
        'test_class': 'ru.yandex.test.highload.Tests',
        'test_package': 'ru.yandex.mobile.test',
        'test_runner': 'android.support.test.runner.AndroidJUnitRunner'
    }
}
config = VoltaConfig(config_dict)

phone = AndroidPhone(config)  # create Phone class
q = queue.Queue()  # create python queue for results
phone.prepare()  # prepare phone for test - clean logs, install test apps and install volta's `lightning` app for synchronization
phone.start(q)  # start acquiring log messages
phone.run_test()  # run test app, specified in config
time.sleep(5)  # do something ...
phone.end()  # stop acquiring log messages

# you can read pandas.DataFrames from results queue,
# data format: `['sys_uts', 'message']`. Microseconds from first event in phone log and message.
print(q.get_nowait())
```

#### Phone module - iPhone


Works with iPhone. Reads/parses system logs (`cfgutil`). To use this module install [Apple Configurator 2](https://itunes.apple.com/us/app/apple-configurator-2/id1037126344?mt=12) and use Mac.

To install apps on iPhone and control them you need to use `Apple's Instruments`.

Everithing else is the same as for AndroidPhone class.

Available configuration options:
* **source** (mandatory) - Apple device ECID. Run `/Applications/Apple\ Configurator\ 2.app/Contents/MacOS/cfgutil list` for getting ECID.
* **util** - path to Apple Configurator 2. Default: `/Applications/Apple\ Configurator\ 2.app/Contents/MacOS/`

Sample usage:
```python
from volta.phones.iphone import iPhone
from volta.core.validator import VoltaConfig

import queue
import time
import logging

config_dict = {
    'phone': {
        'source': '0x6382910F98C26',
        'type': 'iphone',
    }
}
config = VoltaConfig(config_dict)
phone = iPhone(config)  # create Phone class
q = queue.Queue()  # create python queue for results
phone.prepare()  # prepare for test
phone.start(q)  # start phone log data acquiring
phone.end()  # stop phone log data acquiring
```

## Data Mappers

### Events module - Router

Once you get data from one of your phone modules, parse it with **EventsRouter**. It reads phone's results queue, parses messages, groups them by different types and sends them to listeners.

Also, applications can write any information you want into phone's system log to use later for debugging/better synchronization or mark some special events.


Available configuration options: None


Special messages format:
```
[volta] %nanotime% %type% %tag% %message%
```


Special message format sample:
```
[volta] 12345678 fragment TagFragment start
```


Currently we have those types of special messages supported by **EventsRouter**:
* **sync** - synchronization message, Sync module uses it for cross-correlation
* **event** - event message, you can write any information you need by your application on phone and send it to system log
* **fragment** - fragment message, used to mark fragments of events in your test
* **metric** - just a metric with float value instead of message.


Everything else (e.g. default phone system log messages) is grouped to **unknown** message type.


Sample usage:
```python
from volta.providers.phones.android import AndroidPhone
from volta.mappers.events.router import EventsRouter
from volta.listeners.report.report import FileListener
from volta.core.validator import VoltaConfig

import queue
import time
import uuid

test_id = uuid.uuid4()  # some test id

config_dict = {
    'phone': {
        'source': '01e345da733a4764',
        'type': 'android',
    },
}
config = VoltaConfig(config_dict)
phone = AndroidPhone(config)  # create Phone instance
phone_q = queue.Queue()  # create python queue for results
phone.start(phone_q)  # start acquiring phone log messages

event_types = ['event', 'sync', 'fragment', 'metric', 'unknown'] # define event types
event_listeners = {key:[] for key in event_types} # create dict w/ empty list for each event type

event_fnames = {
    key:"{data}_{id}.data".format(
        data=key,
        id=test_id
    ) for key in event_types
}  # file name for each event type

# setup FileListener for each event type (at this sample we write each event type to its own file)
for type, fname in event_fnames.items():
    listener_config = {'fname': fname}
    f = FileListener(listener_config)
    event_listeners[type].append(f)

events_router = EventsRouter(phone_q, event_listeners)
events_router.start()  # start phone log messages processing and routing

time.sleep(10)
phone.end()  # stop acquiring phone log messages
time.sleep(5)
events_router.close()  # stop phone log messages processing and rouring

# in the end you will have files w/ events for each event type in current working directory
```



## Data Listeners
### Sync module - SyncFinder
Module for time synchronization. Calculates synchronization offsets for volta current measurements and phone's system log.
Uses fast Fourier transform convolution.


Available configuration options:
* **search_interval** -  sync search interval, in seconds from start. Default 30
* **sample_rate** - volta samplerate. Default 500


Sample usage:
```python
from volta.providers.boxes.box500hz import VoltaBox500Hz
from volta.providers.phones.android import AndroidPhone
from volta.mappers.events.router import EventsRouter
from volta.listeners.sync.sync import SyncFinder
from volta.common.util import Tee
from volta.core.validator import VoltaConfig


# setup Volta and start
config_dict = {
    'volta': {
        'source': '/dev/cu.wchusbserial1420',
        'type': '500hz'
    },
    'phone': {
        'source': '01e345da733a4764',
        'type': 'android',
    'sync': {
        'search_interval': 30
    },
}
config = VoltaConfig(config_dict)
volta_box = VoltaBox500Hz(config)  # create VoltaBox class
volta_q = queue.Queue()  # create python queue for volta results
volta_listeners = []  # create electrical current listeners list

# setup Phone and start
phone = AndroidPhone(config)  # create Phone class
phone_q = queue.Queue()  # create python queue for results

# setup EventsRouter
event_types = ['event', 'sync', 'fragment', 'metric', 'unknown']  # define event types
event_listeners = {key:[] for key in event_types}  # create dict w/ empty list for each event type
events_router = EventsRouter(phone_q, event_listeners)

# at the moment we have electrical currents queue and phone queue
sync_finder = SyncFinder(config)  # create SyncFinder class

# subscribe our SyncFinder to electrical current and sync events
volta_listeners.append(sync_finder)
event_listeners['sync'].append(sync_finder)

# now process electrical currents to listeners
# Tee drains the queue and send data to listeners
process_volta_data = Tee(
    volta_q,
    volta_listeners,
    'currents'
)

volta_box.start_test(volta_q)  # start volta_box data acquiring
process_volta_data.start()  # start volta_box data processing
phone.start(phone_q)  # start acquiring phone log messages
events_router.start()  # start phone logs processing and routing

# do some work... or maybe phone.run_test()
time.sleep(15)

volta_box.end_test()  # stop volta_box data acquiring
process_volta_data.close()  # stop volta_box data processing
phone.end()  # stop acquiring phone log messages
events_router.close()  # stop phone logs processing and routing

offsets = sync_finder.find_sync_points()
print(offsets)
# output format:
# sys_uts_offset is the phone's system uts to volta's uts offset
# log_uts_offset is the phone's logs custom events nanotime to volta's uts offset
# {'sys_uts_offset': -1005000, 'sync_sample': 0, 'log_uts_offset': 0}
```

#### Report module - FileListener
Saves data to a file.


Available configuration options:
* **fname** (mandatory) - Path to file.


Sample usage:
```python
from volta.providers.boxes.box500hz import VoltaBox500Hz
from volta.listeners.report.report import FileListener
from volta.common.util import Tee
from volta.core.validator import VoltaConfig
import queue
import time
import logging

config_dict = {
    'volta': {
        'source': '/dev/cu.wchusbserial1420',
        'type': '500hz'
    }
}
config = VoltaConfig(config_dict)
volta_box = VoltaBox500Hz(config)  # VoltaBox class
volta_q = queue.Queue()  # queue for results
volta_listeners = []  # empty list for listeners

# create FileListeners and subscribe it to volta
report_config = {'fname': 'current_output_filename'}
file_listener = FileListener(report_config)
volta_listeners.append(file_listener)

volta_data_process = Tee(volta_q, volta_listeners, 'currents')  # start volta data processing

volta_box.start_test(volta_q)  # start test and pass results queue
volta_data_process.start()
time.sleep(15) # do something (start autotests, do manual testing ...). I passed 5 seconds sleep as a placeholder.
volta_box.end_test()  # end test execution
volta_data_process.close()
```

#### Uploader module - DataUploader
Upload data. Currently supports only clickhouse TSV upload.


Available configuration options:
* **address** (mandatory) - Path to destination.
* **task** (mandatory) - You can specify task id manually.
* **test_id** - You can specify test id manually, otherwise it will be automatically generated (using uuid)

Sample yaml config section for uploader:
```yaml
uploader:
  enabled: true,
  address: 'https://lunapark.test.yandex-team.ru/api/volta'
  task: 'LOAD-272'
```


Sample usage:
```python
from volta.providers.boxes.box500hz import VoltaBox500Hz
from volta.listeners.uploader.uploader import DataUploader
from volta.common.util import Tee
from volta.core.validator import VoltaConfig
import queue
import time
import logging

config_dict = {
    'volta': {
        'source': '/dev/cu.wchusbserial1420',
        'type': '500hz'
    },
    'uploader': {
        'task': LOAD-272
    }
}
config = VoltaConfig(config_dict)
volta_box = VoltaBox500Hz(config)  # VoltaBox class
volta_q = queue.Queue()  # queue for results
volta_listeners = []  # emptry list for listeners

# create DataUploader and subscribe it to volta_box
uploader = DataUploader(config)
volta_listeners.append(uploader)

volta_data_process = Tee(volta_q, volta_listeners, 'currents')  # start volta data processing

volta_box.start_test(volta_q)  # start test and pass results queue
volta_data_process.start()
time.sleep(15) # do something (start autotests, do manual testing ...). I passed 5 seconds sleep as a placeholder.
volta_box.end_test()  # end test execution
volta_data_process.close()
```

## API
### HTTP API (concurrent tests, improved statuses)
Allows to start and stop test via HTTP interface.

Entry point: `volta-api`


Simply put config into a POST body.

Start test sample:
```bash
curl 'http://localhost:9998/api/v1/start/' --data 'config={"volta":{"source":"/dev/cu.wchusbserial1420","type":"500hz","enabled":True}, "uploader": {"enabled": True, "task":"LOAD-272"},"phone":{"source":"1f434a75","type":"android","enabled":True}}' -v
```

Stop test sample:
```bash
curl 'http://localhost:9998/api/v1/stop?session=20170801180806_0000000000'
```

Check test status:
```bash
curl 'http://localhost:9998/api/v1/status?session=20170801180806_0000000000'
```


### simple and mini HTTP API (no concurrent tests allowed)
Allows to start and stop test via HTTP interface.

Entry point: `volta-http`


Simply put config into a POST body.


Start test sample:
```bash
curl 'http://localhost:9998/api/v1/start/' --data 'config={"volta":{"source":"/dev/cu.wchusbserial1420","type":"500hz","enabled":True}}' -v
```

Stop test sample:
```bash
curl 'http://localhost:9998/api/v1/stop/' -XPOST -v
```



# Questions
Any questions to Alexey Lavrenuke <direvius@yandex-team.ru> OR [Telegram](https://t.me/joinchat/AAAAAAvBER7vU-672v1jbw) chat.

