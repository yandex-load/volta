""" Android phone worker
"""
import logging
import time
import queue as q
import pkg_resources
import pandas as pd
import numpy as np
import datetime

from volta.common.interfaces import Phone
from volta.common.util import execute, Drain, popen
from volta.common.resource import manager as resource


logger = logging.getLogger(__name__)


class AndroidPhone(Phone):
    """
        adb help:
            #   (-r: replace existing application)
            #   (-d: allow version code downgrade)
            #   (-t: allow test packages)

    """
    def __init__(self, config):
        Phone.__init__(self, config)
        self.logcat_stdout_reader = None
        self.logcat_stderr_reader = None
        # mandatory options
        self.source = config.get('source', '00dc3419957ba583')
        self.unplug_type = config.get('unplug_type', 'manual')
        # lightning app configuration
        self.lightning_apk_path = config.get('lightning', pkg_resources.resource_filename('volta.Phones', 'binary/lightning-new3.apk'))
        self.lightning_apk_class = config.get('lightning_class', 'net.yandex.overload.lightning')
        self.lightning_apk_fname = None
        # test app configuration
        self.test_apps = config.get('test_apps', [])
        self.test_class = config.get('test_class', '')
        self.test_package = config.get('test_package', '')
        self.test_runner = config.get('test_runner', '')

    def prepare(self):
        """
        pipeline:
            install lightning
            install apks
            clean log
        """

        # install lightning
        self.lightning_apk_fname = resource.get_opener(self.lightning_apk_path).get_filename
        logger.info('Installing lightning apk...')
        execute("adb -s {device_id} install -r -d -t {apk}".format(device_id=self.source, apk=self.lightning_apk_fname))

        # install apks
        for apk in self.test_apps:
            apk_fname = resource.get_opener(apk).get_filename
            execute("adb -s {device_id} install -r -d -t {apk}".format(device_id=self.source, apk=apk_fname))

        # clean logcat
        execute("adb -s {device_id} logcat -c".format(device_id=self.source))

        # unplug device or start logcat
        if self.unplug_type == 'manual':
            logger.info('Detach the phone %s from USB and press enter to continue...', self.source)
            # TODO make API and remove this
            raw_input()


    def start(self, phone_q):
        """
        pipeline:
            if uplug_type is manual:
                remind user to start flashlight app
            if unplug_type is auto:
                start async logcat reader
                start lightning flashes
        """
        self.phone_q = phone_q

        if self.unplug_type == 'manual':
            logger.info("It's time to start flashlight app!")
            return

        if self.unplug_type == 'auto':
            self.__start_async_logcat()
            # start flashes app
            execute(
                "adb -s {device_id} shell am start -n {package}/{runner}.MainActivity".format(
                    device_id=self.source,
                    package=self.lightning_apk_class,
                    runner=self.lightning_apk_class
                )
            )
            return

    def __start_async_logcat(self):
        """
        Start logcat read in subprocess and make threads to read its stdout/stderr to queues

        """
        cmd = "adb -s {device_id} logcat".format(device_id=self.source)
        logger.debug("Execute : %s", cmd)
        self.logcat_process = popen(cmd)

        self.logcat_reader_stdout = LogcatReader(self.logcat_process.stdout)
        self.drain_logcat_stdout = Drain(self.logcat_reader_stdout, self.phone_q)
        self.drain_logcat_stdout.start()

        self.phone_q_err=q.Queue()
        self.logcat_reader_stderr = LogcatReader(self.logcat_process.stderr)
        self.drain_logcat_stderr = Drain(self.logcat_reader_stderr, self.phone_q_err)
        self.drain_logcat_stderr.start()

    def run_test(self):
        """
        run apk or return if test is manual
        """

        if self.unplug_type == 'manual':
            return

        if self.unplug_type == 'auto':
            execute(
                "adb shell am instrument -w -e class {test_class} {test_package}/{test_runner}".format(
                    test_class=self.test_class,
                    test_package=self.test_package,
                    test_runner=self.test_runner
                )
            )
            return

    def end(self):
        """
        pipeline:
            if uplug_type is manual:
                ask user to plug device in
                get logcat dump from device
            if unplug_type is auto:
                stop async logcat process, readers and queues
        """

        if self.unplug_type == 'manual':
            logger.warning("Plug the phone in and press `enter` to continue...")
            # TODO make API and remove this
            raw_input()

            _, stdout, stderr = execute(
                "adb -s {device_id} logcat -d".format(device_id=self.source), catch_out=True
            )
            logger.debug('Recieved %d logcat data', len(stdout))
            self.phone_q.put(
                string_to_df(stdout)
            )
            return

        if self.unplug_type == 'auto':
            self.logcat_reader_stdout.close()
            self.logcat_reader_stderr.close()
            self.logcat_process.kill()
            self.drain_logcat_stdout.close()
            self.drain_logcat_stderr.close()
            return


def string_to_df(chunk):
    results = []
    df = None
    for line in chunk.split('\n'):
        if line:
            # skip logcat headers
            if line.startswith("---------"):
                continue
            try:
                # TODO regexp should be here, just like in eventshandler
                # input date format: 12-31 19:03:52.460  3795  4110 W GCM     : Mismatched messenger
                ts = datetime.datetime.strptime(line[:18], '%m-%d %H:%M:%S.%f').replace(
                    year=datetime.datetime.now().year
                )
                # unix timestamp in microseconds
                sys_uts = int(
                    (ts-datetime.datetime(1970,1,1)).total_seconds() * 10 ** 6
                )
                message = line[33:]
            except:
                logger.error('logcat parsing exception', exc_info=True)
                pass
            else:
                results.append([sys_uts, message])
    if results:
        df = pd.DataFrame(results, columns=['sys_uts', 'message'], dtype=np.int64)
        #df.set_index('sys_uts', inplace=True)
    return df


class LogcatReader(object):
    """
    Read chunks from source
    """

    def __init__(self, source, cache_size=1024):
        self.closed = False
        self.cache_size = cache_size # read from pipe blocks waiting for equal block if cache size is large
        self.source = source
        self.buffer = ""

    def _read_chunk(self):
        data = self.source.read(self.cache_size)
        if data:
            parts = data.rsplit('\n', 1)
            if len(parts) > 1:
                ready_chunk = self.buffer + parts[0] + '\n'
                self.buffer = parts[1]
                return string_to_df(ready_chunk)
            else:
                self.buffer += parts[0]
        else:
            self.buffer += self.source.readline()
        return None

    def __iter__(self):
        while not self.closed:
            yield self._read_chunk()
        yield self._read_chunk()

    def close(self):
        self.closed = True

