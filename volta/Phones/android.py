""" Android phone worker
"""
import logging
import time
import queue
import pkg_resources
import numpy as np
import pandas as pd
from volta.common.interfaces import Phone
from volta.common.util import execute
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

        # unplug device
        if self.unplug_type == 'manual':
            logger.info('Detach the phone %s from USB and press enter to continue...', self.source)
            raw_input()

    def start(self):
        """
        pipeline:
            start lightning flashes
        """

        if self.unplug_type == 'manual':
            logger.info("It's time to start flashlight app!")
            return

        # start flashes app
        execute(
            "adb -s {device_id} shell am start "
            "-n {package}/{runner}.MainActivity".format(
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

        q = queue.Queue()
        for data in LogcatReader(stdout):
            q.put(data)
        logger.info('Logcat qsize: %s',  q.qsize())
        logger.info('Logcat sample: %s',  q.get_nowait())
        return q


def string_to_np(data):
    start_time = time.time()
    chunk = np.fromstring(data, sep='\t')
    logger.debug("Chunk decode time: %.2fms", (time.time() - start_time) * 1000)
    return chunk


class LogcatReader(object):
    def __init__(self, data):
        self.data = data.split('\n')
        logger.debug('Logcat data: %s', self.data)

    def __iter__(self):
        # TODO: read bulk and return chunks step-by-step
        for chunk in self.data:
            yield string_to_np(chunk)


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
    phone.prepare()
    logger.info('prepare finished!')
    volta.start_test(grabber_q)
    phone.start()
    time.sleep(15)
    logger.info('finishing test')
    phone.end()
    logger.info('test finished')

if __name__ == "__main__":
    main()