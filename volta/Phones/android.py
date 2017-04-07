""" Android phone
"""
import logging
import signal
import os
import time
import queue
from volta.common.interfaces import Phone
from volta.common.util import popen, Drain, execute
from volta.common.resource import manager as resource
from volta.Boxes.box_binary import VoltaBoxBinary


logger = logging.getLogger(__name__)


lightning_apk_fullname = "net.yandex.overload.lightning"


class AndroidPhone(Phone):
    def __init__(self, config, volta):
        Phone.__init__(self, config, volta)
        self.volta = volta
        self.source = config.get('source', '00dc3419957ba583')
        self.lightning_apk_path = config.get('lightning', 'binary/lightning.apk')
        self.lightning_apk_fname = None
        self.apks = config.get('apks', '').split()
        self.unplug_type = config.get('unplug', 'manual')
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
        for apk in self.apks:
            apk_fname = resource.get_opener(apk).get_filename
            execute("adb -s {device_id} install -r -d -t {apk}".format(device_id=self.source, apk=apk_fname))

        # clean logcat
        execute("adb -s {device_id} logcat -c".format(device_id=self.source))

        # unplug device
        if self.unplug_type:
            if self.unplug_type == 'manual':
                logger.info('Detach the phone %s from USB and press enter to continue...', self.source)
                raw_input()
            elif self.unplug_type == 'auto':
                pass

    def start(self):
        """
        pipeline:
            start lightning flashes
        """

        # start flashes app
        execute(
            "adb -s {device_id} shell am start "
            "-n {package}/{runner}.MainActivity".format(
                device_id=self.source,
                package=lightning_apk_fullname,
                runner=lightning_apk_fullname
            )
        )

    def run_test(self):
        """
        run apk
        """

        logger.info('Perform test')
        execute(
            "adb shell am instrument -w -e class {test_class} {test_package}/{test_runner}".format(
                test_class=self.test_class,
                test_package=self.test_package,
                test_runner=self.test_runner
            )
        )

    def end(self):
        """
        volta.stop
        plug device
        get logs from device
        """

        # volta.stop
        self.volta.end_test()

        # device
        if self.unplug_type:
            pass

        _, stdout, stderr = execute(
            "adb -s {device_id} logcat -d".format(device_id=self.source), catch_out=True
        )
        logger.debug('Recieved %d logcat data', len(stdout))
        return stdout





# ==================================================

def main():
    logging.basicConfig(
        level="INFO",
        format='%(asctime)s [%(levelname)s] [Volta Phone Android] %(filename)s:%(lineno)d %(message)s')
    logger.info("Volta Phone Anroid ")
    cfg_volta = {
        'source': '/dev/cu.wchusbserial1410'
    }
    cfg_phone = {
        'source': '00dc3419957ba583',
        'apks': 'http://highload-metrica.s3.mds.yandex.net/test-be19404d-de02-4c05-92f1-e2cb3873609f.apk '
                'http://highload-metrica.s3.mds.yandex.net/app-e19ab4f6-f56e-4a72-a702-61e1527b1da7.apk',
        'test_package': 'ru.yandex.mobile.metrica.test',
        'test_class': 'ru.yandex.metrica.test.highload.LittleTests',
        'test_runner': 'android.support.test.runner.AndroidJUnitRunner'
    }
    volta = VoltaBoxBinary(cfg_volta)
    phone = AndroidPhone(cfg_phone, volta)
    logger.debug('volta args: %s', volta.__dict__)
    logger.debug('phone args: %s', phone.__dict__)
    grabber_q = queue.Queue()
    phone.prepare()
    volta.start_test(grabber_q)
    phone.start()
    time.sleep(15)
    logger.info('finishing test')
    phone.end()
    logger.info('test finished')

if __name__ == "__main__":
    main()