import logging
import queue
import time
import signal

from volta import Boxes
from volta import Phones


logger = logging.getLogger(__name__)



def signal_handler(sig, frame):
    """ required for non-tty python runs to interrupt """
    logger.warning("Got signal %s, going to stop", sig)
    raise KeyboardInterrupt()

def ignore_handler(sig, frame):
    logger.warning("Got signal %s, ignoring", sig)

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
        """ find VoltaBox """
        self.voltas = {
            '500hz': Boxes.VoltaBox500Hz,
            'binary': Boxes.VoltaBoxBinary,

        }
        self.phones = {
            'android': Phones.AndroidPhone,
            'iphone': None
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
        self.grabber_q = None

    def configure(self):
        """
        1) VoltaFactory
        2) PhoneFactory
        3) EventLogParser
        4) MetricsExtractor
        5) Sync
        6) Uploader
        """
        factory = Factory()
        self.volta = factory.detect_volta(self.config.get('volta', None))
        self.phone = factory.detect_phone(self.config.get('phone', None))
        self.grabber_q = queue.Queue()
        self.phone_q = queue.Queue()
        self.phone.prepare()

    def start_test(self):
        logger.info('Starting test...')
        self.volta.start_test(self.grabber_q)
        self.phone.start(self.phone_q)

        logger.info('Starting test apps and waiting for finish...')
        # TODO remove this -> phone.run_test() should be here instead of sleeps
        time.sleep(self.config['meta'].get('duration', 60))

    def end_test(self):
        logger.info('Finishing test...')
        self.volta.end_test()
        self.phone.end()

    def post_process(self):
        logger.info('Post process...')

        logger.debug('Phone qsize: %s', self.phone.phone_q.qsize())
        try:
            logger.debug('Phone smaple:\n%s', self.phone.phone_q.get_nowait())
        except queue.Empty:
            pass
        
        logger.info('Finished!')




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
        'volta': {
            'type': '500hz',
            'source': '/dev/cu.wchusbserial1410',
        },
        'phone': {
            'type': 'android',
            #'unplug_type': 'manual',
            'unplug_type': 'auto',
            'source': '00dc3419957ba583',
        },
        'uploader': {
        },
        'meta': {
            'duration': 15
        }
    }
    try:
        core = Core(sample_cfg)
        core.configure()
        core.start_test()
        core.end_test()
        core.post_process()

    except KeyboardInterrupt:
        raise RuntimeError('stopped')


if __name__ == "__main__":
    set_sig_handler()
    main()