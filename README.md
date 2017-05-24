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

# Using Volta software as a python library:
There are different types of Volta modules
* Core - module that configures test life cycle and test pipeline, creates, configures and controls other modules.
* VoltaBox - module for different types of Volta Boxes.
* Phone - module for different types of phones. Android and iPhone supported.
* Events - phone logs parser module.
* Sync - cross-corellation sync module, syncs volta logs to phone logs.
* Uploader - data uploader module (e.g. to Overload).
* Report - file write module.


# Using Volta
## Command-line entry-point `volta`
You can configure you test using command-line entry-point `volta`, configuring test w/ .yaml config
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
This config creates test with `VoltaBox500Hz` at `/dev/cu.wchusbserial1420` and android phone id `01e345da733a4764`, starts to collect and process data from VoltaBox and Phone. 
If you want to stop the test, press `Ctrl+C` or send `SIGTERM` to process. 

## Core as python module
Also, if you want to control test execution or integrate Volta with your CI, you can you Core as python library.

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
If you want more flexible use of Volta components, you can use different Volta modules (or write you own) as python modules aswell.

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

## Phone class - Android
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
# создать очередь, в которую будут складываться результаты работы
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

## Phone class - iPhone
Works with iPhone. Reads/parses system logs (`cfgutil`). If you want to use this module, you should install [Apple Configurator 2](https://itunes.apple.com/us/app/apple-configurator-2/id1037126344?mt=12) and use Mac.
If you want to install apps on iPhone and control them you nede to use `Apple's Instruments`.
Everithing else is like android class.

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

# Questions
Any questions to Alexey Lavrenuke <direvius@yandex-team.ru>.

