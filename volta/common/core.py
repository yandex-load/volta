import logging
import queue as q
import time
import signal
import datetime

from volta import Boxes
from volta import Phones
from volta.common.eventshandler import EventsParser
from volta.common.interfaces import DataListener
from volta.Sync.sync import SyncFinder


logger = logging.getLogger(__name__)


def signal_handler(sig, frame):
    """ required for non-tty python runs to interrupt """
    logger.warning("Got signal %s, going to stop", sig)
    raise KeyboardInterrupt()


def ignore_handler(sig, frame):
    logger.warning("Got signal %s, ignoring", sig)


# TODO: move this to (non-existent atm) console worker
def set_sig_handler():
    uncatchable = ['SIG_DFL', 'SIGSTOP', 'SIGKILL']
    ignore = ['SIGCHLD', 'SIGCLD']
    all_sig = [s for s in dir(signal) if s.startswith("SIG")]
    for sig_name in ignore:
        try:
            sig_num = getattr(signal, sig_name)
            signal.signal(sig_num, ignore_handler)
        except Exception:
            pass
    for sig_name in [s for s in all_sig if s not in (uncatchable + ignore)]:
        try:
            sig_num = getattr(signal, sig_name)
            signal.signal(sig_num, signal_handler)
        except Exception as ex:
            logger.error("Can't set handler for %s, %s", sig_name, ex)


class Factory(object):
    def __init__(self):
        """ find VoltaBox and Phone """
        self.voltas = {
            '500hz': Boxes.VoltaBox500Hz,
            'binary': Boxes.VoltaBoxBinary,

        }
        self.phones = {
            'android': Phones.AndroidPhone,
            'iphone': Phones.iPhone,
        }

    def detect_volta(self, config):
        type = config.get('type', None).lower()
        if type in self.voltas:
            logger.debug('Volta type detected: %s', type)
            return self.voltas[type](config)

    def detect_phone(self, config):
        type = config.get('type', None).lower()
        if type in self.phones:
            logger.debug('Phone type detected: %s', type)
            return self.phones[type](config)


class Core(object):
    """ Core
    Core class, test performer """
    def __init__(self, config):
        """ parse config, @type:dict """
        self.config = config
        self.listeners = []
        self.factory = Factory()
        self.grabber_q = q.Queue()
        self.phone_q = q.Queue()
        self.test_id = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")
        self.sync = None

    def configure(self):
        """
        1) VoltaFactory - VOLTA-87
        2) PhoneFactory - VOLTA-120 / VOLTA-131
        3) EventLogParser - VOLTA-129
        # TODO
        4) Sync - VOLTA-133
        5) Uploader -
        """
        self.volta = self.factory.detect_volta(self.config.get('volta', {}))
        self.phone = self.factory.detect_phone(self.config.get('phone', {}))
        self.phone.prepare()

    def start_test(self):
        logger.info('Starting test...')
        self.volta.start_test(self.grabber_q)
        self.phone.start(self.phone_q)

        logger.info('Starting test apps and waiting for finish...')
        self.phone.run_test()

    def end_test(self):
        logger.info('Finishing test...')
        self.volta.end_test()
        self.phone.end()

    def post_process(self):
        logger.info('Post process...')
        self.events_q = q.Queue()
        self.sync_q = q.Queue()

        events_parser = EventsParser(self.phone_q, self.events_q, self.sync_q)
        events_parser.run()

        # TODO make util.Tee and pass separate queue to sync and uploader
        self.sync = SyncFinder(
            self.config.get('sync', {}),
            self.sync_q,
            self.grabber_q,
            self.volta.sample_rate
        )

        sync_data = self.sync.find_sync_points()

        logger.info('Finished!')



class FileListener(DataListener):
    """
    Default listener - saves data to file
    """

    def __init__(self, fname):
        DataListener.__init__(self, fname)
        self.fname = open(fname, 'w')

    def add_data(self, data):
        self.fname.write((data))
        self.fname.write('\n')
        self.fname.flush()

    def close(self):
        """ close open files """
        if self.fname:
            self.fname.close()




# ==================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--debug', dest='debug', action='store_true', default=False)
    args = parser.parse_args()

    logging.basicConfig(
        level="DEBUG" if args.debug else "INFO",
        format='%(asctime)s [%(levelname)s] [Volta Core] %(filename)s:%(lineno)d %(message)s')
    logger.info("Volta Core init")
    sample_cfg = {
        'work_dir': './logs/',
        'volta': {
            'type': '500hz',
            'source': '/dev/cu.wchusbserial1420',
        },
        'phone': {
            # android
            'type': 'android',
            'unplug_type': 'auto',
            #'source': '00dc3419957ba583', # old
            'source': '01e345da733a4764', # new
            'test_apps': 'http://highload-metrica.s3.mds.yandex.net/test-be19404d-de02-4c05-92f1-e2cb3873609f.apk '
                         'http://highload-metrica.s3.mds.yandex.net/app-e19ab4f6-f56e-4a72-a702-61e1527b1da7.apk',
            'test_package': 'ru.yandex.mobile.metrica.test',
            'test_class': 'ru.yandex.metrica.test.highload.LittleTests',
            'test_runner': 'android.support.test.runner.AndroidJUnitRunner'

            # iphone
            # 'type': 'iphone',
            # 'source': '0x6382910F98C26', # iphone 6
        },
        'sync': {
            'search_interval': 30
        }
    }

    core = Core(sample_cfg)
    try:
        core.configure()
        core.start_test()
        time.sleep(10)
        core.end_test()
        core.post_process()
    except KeyboardInterrupt:
        core.end_test()


if __name__ == "__main__":
    set_sig_handler()
    main()
