Yandex Volta is a framework for mobile performance and energy efficiency analysis.

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
         * [Events module - Router](#events-module---router)
      * [Data Listeners](#data-listeners)
         * [Sync module - SyncFinder](#sync-module---syncfinder)
            * [Report module - FileListener](#report-module---filelistener)
            * [Uploader module - DataUploader](#uploader-module---datauploader)
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

[Core](volta/core/) - core module, configures test life cycle and test pipeline.
Creates, configures and controls other modules.

**Data Providers**
* [VoltaBox](volta/boxes/) - module for different types of Volta Boxes.
* [Phone](volta/phones/) - module for different types of phones. Android and iPhone supported.
* [Events](volta/events/) - phone logs parser module.

**Data Listeners**
* [Sync](volta/sync/) - cross-corellation sync module, syncs volta logs to phone logs.
* [Uploader](volta/uploader/) - data uploader module (e.g. to Overload).
* [Report](volta/report/) - file write module.


# Using Volta

## Command-line entry-point `volta`
Use command-line entry-point `volta` with .yaml config
> `volta -c config.yaml`

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

To stop the test, press **Ctrl+C** or send **SIGTERM** signal to the process.


## Core as module
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
from volta.boxes.box500hz import VoltaBox500Hz
import queue
import time
import logging

config = {'source': '/dev/cu.wchusbserial1420'}
volta = VoltaBox500Hz(config) # VoltaBox class
q = queue.Queue() # queue for results
volta.start_test(q) # start test and pass results queue
time.sleep(5) # do something (start autotests, do manual testing ...). I passed 5 seconds sleep as a placeholder.
volta.end_test() # end test execution

# and you can read pandas.DataFrames from results queue,
# data format: `['uts', 'value']`. Microseconds from test start and electrical currents value.
print(q.get_nowait())
```

### Phone module


We have modules for Android and iPhone. If you want to use some other type of device (e.g. Windows Phone), you can write your own phone module.

#### Phone module - Android


Works with android phones. Reads/parses system logs (`adb logcat`), starts lightning app for synchronization, installs/starts/runs tests on device.

Available configuration options:
* **source** (mandatory) - android device id
* **unplug_type** - type of test execution, describes the way you do the tests on your phone
    * `auto`: disable battery charge (by software) or use special USB cord limiting charge over USB
    * `manual`: disable phone from USB with your bare hands during test exection and click your test
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
from volta.phones.android import AndroidPhone
import queue
import time
import logging

config = {
  'source': '01e345da733a4764',
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

#### Phone module - iPhone


Works with iPhone. Reads/parses system logs (`cfgutil`). To use this module install [Apple Configurator 2](https://itunes.apple.com/us/app/apple-configurator-2/id1037126344?mt=12) and use Mac.

To install apps on iPhone and control them you need to use `Apple's Instruments`.

Everithing else is the same as for AndroidPhone class.

Available configuration options:
* **source** (mandatory) - Apple device id
* **util** - path to Apple Configurator 2. Default: `/Applications/Apple\ Configurator\ 2.app/Contents/MacOS/`

Sample usage:
```python
from volta.phones.iphone import iPhone
import queue
import time
import logging

config = {'source': '0x6382910F98C26'}
phone = iPhone(config) # create Phone class
q = queue.Queue() # queue for results
phone.prepare()
phone.start(q)
phone.end()
```

### Events module - Router

Once you get data from one of your phone modules, parse it with **EventsRouter**. It reads phone's results queue, parses messages, groups them by different types and sends them to listeners.

Also, applications can write any information you want into phone's system log to use later for debugging/better synchronization or mark some special events.


Available configuration options: None


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
* **fragment** - fragment message, used to mark fragments of events in your test
* **metric** - just a metric with float value instead of message.


Everything else (e.g. default phone system log messages) is grouped to **unknown** message type.


Sample usage:
```python
from volta.phones.android import AndroidPhone
from volta.events.router import EventsRouter
from volta.report.report import FileListener
import queue
import time
import uuid

test_id = uuid.uuid4() # some test id

phone_config = {'source': '01e345da733a4764'} # phone id
phone = AndroidPhone(phone_config) # Phone class
phone_q = queue.Queue() # queue for results
phone.start(phone_q) # start phone log reader

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



## Data Listeners
### Sync module - SyncFinder
Module for time synchronization. Calculates synchronization offsets for volta current measurements and phone's system log.
Uses fast Fourier transform convolution.


Available configuration options:
* **search_interval** -  sync search interval, in seconds from start. Default 30
* **sample_rate** - volta samplerate. Default 500


Sample usage:
```python
from volta.boxes.box500hz import VoltaBox500Hz
from volta.phones.android import AndroidPhone
from volta.events.router import EventsRouter
from volta.sync.sync import SyncFinder
from volta.common.util import Tee

# setup Volta and start
volta_config = {'source': '/dev/cu.wchusbserial1420'} # volta box device
volta = VoltaBox500Hz(volta_config) # VoltaBox class
volta_q = queue.Queue() # queue for volta results
volta_listeners = [] # init electrical current listeners

# setup Phone and start
phone_config = {'source': '01e345da733a4764'} # phone id
phone = AndroidPhone(phone_config) # Phone class
phone_q = queue.Queue() # queue for results

# setup EventsRouter
event_types = ['event', 'sync', 'fragment', 'metric', 'unknown'] # define event types
event_listeners = {key:[] for key in event_types} # create dict w/ empty list for each event type
events_router = EventsRouter(phone_q, event_listeners)

# at the moment we have electrical currents queue and phone queue
sync_config = {'search_interval': 30, 'sample_rate': volta.sample_rate}
sync_finder = SyncFinder(sync_config)

# subscribe our SyncFinder to electrical current and sync events
volta_listeners.append(sync_finder)
event_listeners['sync'].append(sync_finder)

# now process electrical currents to listeners
# Tee is a thread: drains the queue and send data to listeners
process_volta_data = Tee(
    volta_q,
    volta_listeners,
    'currents'
)

volta.start_test(volta_q) # start volta data grabber
process_volta_data.start() # start volta data processing
phone.start(phone_q) # start phone log reader
events_router.start() # start events processing
# do some work... or maybe phone.run_test()
time.sleep(15)

# end the test
volta.end_test()
process_volta_data.close()
phone.end()
events_router.close()

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
from volta.boxes.box500hz import VoltaBox500Hz
from volta.report.report import FileListener
from volta.common.util import Tee
import queue
import time
import logging

config = {'source': '/dev/cu.wchusbserial1420'}
volta = VoltaBox500Hz(config) # VoltaBox class
volta_q = queue.Queue() # queue for results
volta_listeners = [] # emptry list for listeners

# create FileListeners and subscribe it to volta
report_config = {'fname': 'current_output_filename'}
file_listener = FileListener(report_config)
volta_listeners.append(file_listener)

volta_data_process = Tee(volta_q, volta_listeners, 'currents') # start volta data processing

volta.start_test(volta_q) # start test and pass results queue
volta_data_process.start()
time.sleep(15) # do something (start autotests, do manual testing ...). I passed 5 seconds sleep as a placeholder.
volta.end_test() # end test execution
volta_data_process.close()
```

#### Uploader module - DataUploader
Upload data. Currently supports only clickhouse TSV upload.


Available configuration options:
* **address** (mandatory) - Path to destination.
* **test_id** - You can specify test id manually, otherwise it will be automatically generated (using uuid)

Sample usage:
```python
from volta.boxes.box500hz import VoltaBox500Hz
from volta.uploader.uploader import DataUploader
from volta.common.util import Tee
import queue
import time
import logging

config = {'source': '/dev/cu.wchusbserial1420'}
volta = VoltaBox500Hz(config) # VoltaBox class
volta_q = queue.Queue() # queue for results
volta_listeners = [] # emptry list for listeners

# create DataUploader and subscribe it to volta
uploader_config = {'address': 'https://path/to/clickhouse/api/volta'}
uploader = DataUploader(uploader_config)
volta_listeners.append(uploader)

volta_data_process = Tee(volta_q, volta_listeners, 'currents') # start volta data processing

volta.start_test(volta_q) # start test and pass results queue
volta_data_process.start()
time.sleep(15) # do something (start autotests, do manual testing ...). I passed 5 seconds sleep as a placeholder.
volta.end_test() # end test execution
volta_data_process.close()
```


# Questions
Any questions to Alexey Lavrenuke <direvius@yandex-team.ru>.

