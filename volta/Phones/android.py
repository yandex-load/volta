""" Android phone worker
"""
import logging
import time
import queue
import pkg_resources
import numpy as np
import pandas as pd
import subprocess
import datetime
from volta.common.interfaces import Phone
from volta.common.util import execute, Drain, popen
from volta.common.resource import manager as resource
from volta.Boxes.box_binary import VoltaBoxBinary


logger = logging.getLogger(__name__)


class AndroidPhone(Phone):
    def __init__(self, config):
        Phone.__init__(self, config)
        self.source = config.get('source', '00dc3419957ba583')
        self.lightning_apk_path = config.get('lightning', pkg_resources.resource_filename('volta.Phones', 'binary/lightning.apk'))
        self.lightning_apk_class = config.get('lightning_class', 'net.yandex.overload.lightning')
        self.lightning_apk_fname = None
        self.unplug_type = config.get('unplug_type', 'manual')

        self.test_apks = config.get('test_apks', '').split()
        self.test_class = config.get('test_class', '')
        self.test_package = config.get('test_package', '')
        self.test_runner = config.get('test_runner', '')

        self.logcat_stdout_reader = None
        self.logcat_stderr_reader = None

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
        # adb install
        #   (-r: replace existing application)
        #   (-d: allow version code downgrade)
        #   (-t: allow test packages)
        execute("adb -s {device_id} install -r -d -t {apk}".format(device_id=self.source, apk=self.lightning_apk_fname))

        # install apks
        for apk in self.test_apks:
            apk_fname = resource.get_opener(apk).get_filename
            execute("adb -s {device_id} install -r -d -t {apk}".format(device_id=self.source, apk=apk_fname))

        # clean logcat
        execute("adb -s {device_id} logcat -c".format(device_id=self.source))

        # unplug device or start logcat
        if self.unplug_type == 'manual':
            logger.info('Detach the phone %s from USB and press enter to continue...', self.source)
            raw_input()


    def start(self, phone_q):
        """
        pipeline:
            if unplug_type is auto:
                start adb logcat
                start reader threads
            start lightning flashes
        """
        self.phone_q = phone_q
        if self.unplug_type == 'manual':
            logger.info("It's time to start flashlight app!")
            return
        else:
            cmd = "adb -s {device_id} logcat".format(device_id=self.source)
            logger.info("Execute : %s", cmd)
            self.logcat_process = popen(cmd)

            self.logcat_reader_stdout = LogcatReader(self.logcat_process.stdout)
            self.drain_logcat_stdout = Drain(self.logcat_reader_stdout, self.phone_q)
            self.drain_logcat_stdout.start()

            self.phone_q_err=queue.Queue()
            self.logcat_reader_stderr = LogcatReader(self.logcat_process.stderr)
            self.drain_logcat_stderr = Drain(self.logcat_reader_stderr, self.phone_q_err)
            self.drain_logcat_stderr.start()

        # start flashes app
        execute(
            "adb -s {device_id} shell am start -n {package}/{runner}.MainActivity".format(
                device_id=self.source,
                package=self.lightning_apk_class,
                runner=self.lightning_apk_class
            )
        )

    def run_test(self):
        """
        run apk
        """

        if self.unplug_type == 'manual':
            return

        execute(
            "adb shell am instrument -w -e class {test_class} {test_package}/{test_runner}".format(
                test_class=self.test_class,
                test_package=self.test_package,
                test_runner=self.test_runner
            )
        )

    def end(self):
        """
        plug device
        get logs from device
        """

        # plug device in if manual test
        if self.unplug_type == 'manual':
            logger.warning("Plug the phone in and press `enter` to continue...")
            raw_input()

            _, stdout, stderr = execute(
                "adb -s {device_id} logcat -d".format(device_id=self.source), catch_out=True
            )
            logger.debug('Recieved %d logcat data', len(stdout))
            self.phone_q.put(string_to_df(stdout))
        elif self.unplug_type == 'auto':
            self.logcat_reader_stdout.close()
            self.logcat_reader_stderr.close()
            self.logcat_process.kill()
            self.drain_logcat_stdout.close()
            self.drain_logcat_stderr.close()


def string_to_df(chunk):
    results = []
    for line in chunk.split('\n'):
        if line.startswith('----'):
            continue
        data = line.split(' ')
        if len(data) > 2:
            month_day, time = data[0], data[1]
            if month_day != '' or time != '':
                ts = "{year}-{month_day} {time}".format(
                    year=datetime.datetime.now().year,
                    month_day=month_day,
                    time=time
                )
            else:
                ts = None
            message = " ".join(data[2:])
            results.append([ts, message])
    if results:
        df = pd.DataFrame(results, columns=['ts', 'message'])
    else:
        df = None
    return df


class LogcatReader(object):
    """
    Read chunks from source
    """

    def __init__(self, source, cache_size=1024):
        self.closed = False
        self.cache_size = cache_size
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



# ==================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--debug', dest='debug', action='store_true', default=False)
    args = parser.parse_args()
    logging.basicConfig(
        level="DEBUG" if args.debug else "INFO",
        format='%(asctime)s [%(levelname)s] [Volta Phone Android] %(filename)s:%(lineno)d %(message)s')
    logger.info("Volta Phone Anroid")
    cfg_volta = {
        'source': '/dev/cu.wchusbserial1410'
    }
    cfg_phone = {
        'source': '00dc3419957ba583',
        'test_apks': 'http://highload-metrica.s3.mds.yandex.net/test-be19404d-de02-4c05-92f1-e2cb3873609f.apk '
                'http://highload-metrica.s3.mds.yandex.net/app-e19ab4f6-f56e-4a72-a702-61e1527b1da7.apk',
        'test_package': 'ru.yandex.mobile.metrica.test',
        'test_class': 'ru.yandex.metrica.test.highload.LittleTests',
        'test_runner': 'android.support.test.runner.AndroidJUnitRunner'
    }
    volta = VoltaBoxBinary(cfg_volta)
    phone = AndroidPhone(cfg_phone)
    logger.debug('volta args: %s', volta.__dict__)
    logger.debug('phone args: %s', phone.__dict__)
    grabber_q = queue.Queue()
    phone_q = queue.Queue()
    phone.prepare()
    logger.info('prepare finished!')
    volta.start_test(grabber_q)
    phone.start(phone_q)
    time.sleep(15)
    logger.info('finishing test')
    phone.end()
    logger.info('test finished')

if __name__ == "__main__":
    main()