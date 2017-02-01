import os.path as op

import time
from adb import adb_commands
from adb import sign_m2crypto

signer = sign_m2crypto.M2CryptoSigner(op.expanduser('~/.android/adbkey'))
device = adb_commands.AdbCommands.ConnectDevice(rsa_keys=[signer])
print device.Push("config.json", "/sdcard/config.json")
print device.Shell(
    "am broadcast -a com.yandex.mobile.tools.perfmon.START_TEST"
    " -p com.yandex.mobile.tools.perfmon "
    "-e PACKAGE_NAME com.yandex.mobile.tools.highloadsample -e LOOP 10")
