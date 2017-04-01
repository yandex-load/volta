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

Any questions to Alexey Lavrenuke <direvius@yandex-team.ru>.
