""" Android phone
"""
import logging
import signal
import os
import time
import queue
from volta.common.interfaces import Phone
from volta.common.util import popen, Drain
from volta.common.resource import manager as resource
from volta.Boxes.box_binary import VoltaBoxBinary


logger = logging.getLogger(__name__)


class AndroidPhone(Phone):
    def __init__(self, config, volta):
        Phone.__init__(self, config)
        self.volta = volta
        self.source = config.get('source', '00dc3419957ba583')
        self.lightning_apk_path = config.get('lightning', 'binary/lightning.apk')
        self.adb_cmd = "adb -s {dev} logcat".format(dev=self.source)

    def prepare(self):
        """
        pipeline:
            install ligtning
            install apks
            clean log
        """
        # test
        self.lightning_apk_fname = resource.get_opener(self.lightning_apk_path).get_filename
        logger.info('Lightning: %s', self.lightning_apk_fname)

    def start(self):
        """
        pipeline:
            unplug device
            volta.start
            start lightning flashes
        """
        pass

    def run_test(self):
        """
        run apk
        """
        pass

    def end(self):
        """
        volta.stop
        plug device
        get logs from device
        """
        pass





# ==================================================

def main():
    logging.basicConfig(
        level="DEBUG",
        format='%(asctime)s [%(levelname)s] [Volta 500hz] %(filename)s:%(lineno)d %(message)s')
    logger.info("Volta Phone Anroid ")
    cfg_volta = {
    }
    cfg_phone = {
        'source': '00dc3419957ba583'
    }
    volta = VoltaBoxBinary(cfg_volta)
    worker = AndroidPhone(cfg_phone, volta)
    logger.info('worker args: %s', worker.__dict__)
    worker.start_test()
    time.sleep(10)
    logger.info('test finishing...')
    worker.end_test()
    logger.info('test finished')

if __name__ == "__main__":
    main()