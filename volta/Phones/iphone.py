""" iPhone phone worker
"""
import logging
import time
import queue
import pandas as pd
import datetime
from volta.common.interfaces import Phone
from volta.common.util import Drain, popen
from volta.Boxes.box_binary import VoltaBoxBinary


logger = logging.getLogger(__name__)


class iPhone(Phone):
    def __init__(self, config):
        Phone.__init__(self, config)
        self.log_stdout_reader = None
        self.log_stderr_reader = None
        self.path_to_util = "/Applications/Apple\ Configurator\ 2.app/Contents/MacOS/"
        # mandatory options
        self.source = config.get('source', '0x6382910F98C26')
        self.unplug_type = config.get('unplug_type', 'auto')

    def prepare(self):
        return

    def start(self, phone_q):
        """
        pipeline:
            start async logcat reader
        """
        self.phone_q = phone_q
        self.__start_async_log()

    def run_test(self):
        return

    def end(self):
        """
        pipeline:
            stop async logcat process, readers and queues
        """

        self.log_reader_stdout.close()
        self.log_reader_stderr.close()
        self.log_process.kill()
        self.drain_log_stdout.close()
        self.drain_log_stderr.close()

    def __start_async_log(self):
        """
        Start logcat read in subprocess and make threads to read its stdout/stderr to queues

        """
        cmd = "{path}cfgutil -e {device_id} syslog".format(
            path=self.path_to_util,
            device_id=self.source
        )
        logger.debug("Execute : %s", cmd)
        self.log_process = popen(cmd)

        self.log_reader_stdout = LogReader(self.log_process.stdout)
        self.drain_log_stdout = Drain(self.log_reader_stdout, self.phone_q)
        self.drain_log_stdout.start()

        self.phone_q_err=queue.Queue()
        self.log_reader_stderr = LogReader(self.log_process.stderr)
        self.drain_log_stderr = Drain(self.log_reader_stderr, self.phone_q_err)
        self.drain_log_stderr.start()


def string_to_df(chunk):
    results = []
    df = None
    for line in chunk.split('\n'):
        try:
            # input format:
            # Apr 13 14:17:18 Benders-iPhone kernel(AppleBiometricSensor)[0] <Debug>: exit
            ts = datetime.datetime.strptime(
                line[:15], '%b %d %H:%M:%S'
            ).replace(
                year=datetime.datetime.now().year
            )
            message = line[15:]
        except:
            pass
        else:
            results.append([ts, message])
    if results:
        df = pd.DataFrame(results, columns=['ts', 'message'])
    return df


class LogReader(object):
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




# ==================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description='')
    parser.add_argument('--debug', dest='debug', action='store_true', default=False)
    args = parser.parse_args()
    logging.basicConfig(
        level="DEBUG" if args.debug else "INFO",
        format='%(asctime)s [%(levelname)s] [Volta Phone iPhone] %(filename)s:%(lineno)d %(message)s')
    logger.info("Volta Phone iPhone")
    cfg_volta = {
        'source': '/dev/cu.wchusbserial1410',
    }
    cfg_phone = {
        'source': '0x6382910F98C26',
        'type': 'iphone',
        'unplug_type': 'auto',
    }
    volta = VoltaBoxBinary(cfg_volta)
    phone = iPhone(cfg_phone)
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
