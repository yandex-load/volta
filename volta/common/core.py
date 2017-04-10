import logging
import queue
import time

from volta import Boxes
from volta import Phones


logger = logging.getLogger(__name__)


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
        self.volta = Factory.detect_volta(factory, self.config.get('volta', None))
        self.phone = Factory.detect_phone(factory, self.config.get('phone', None))
        self.grabber_q = queue.Queue()
        self.phone.prepare()

    def start_test(self):
        logger.info('Starting test...')
        self.volta.start_test(self.grabber_q)
        self.phone.start()

        logger.info('Starting test apps and waiting for finish...')
        # TODO remove this -> phone.run_test() should be here instead of sleeps
        time.sleep(self.config['meta'].get('duration', 60))

    def end_test(self):
        logger.info('Finishing test...')
        self.volta.end_test()
        self.phone.end()


    def post_process(self):
        logger.info('Post process...')

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
    core = Core(sample_cfg)
    core.configure()
    core.start_test()
    core.end_test()
    core.post_process()


if __name__ == "__main__":
    main()