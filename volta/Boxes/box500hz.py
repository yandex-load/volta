""" 500Hz box
"""
import serial
import logging
import progressbar
from volta.common.interfaces import VoltaBox

logger = logging.getLogger(__name__)


class VoltaBox500Hz(VoltaBox):
    def __init__(self, core):
        VoltaBox.__init__(self, core)

    def configure(self, config=None):
        self.samplerate = 500
        self.baud_rate = 115200
        self.grab_timeout = 1

    def grab(self):
        with serial.Serial(self.device, self.baud_rate, timeout=self.grab_timeout) as ser:
            logger.info(
                "Collecting %d seconds of data (%d samples) to '%s'." % (
                    self.test_duration, self.test_duration * self.samplerate, self.output_file))
            logger.debug('first 500 values will be skipped')
            for n in range(500):
                ser.readline()
            logger.debug('Opening output file and starting grab')
            with open(self.output_file, "wb") as out:
                with progressbar.ProgressBar(max_value=self.test_duration) as bar:
                    for i in range(self.test_duration):
                        if not self.stopped:
                            bar.update(i)
                            for _ in range(self.samplerate):
                                data = ser.readline().strip('\n')
                                self.filter(data)
                                out.write(data)
                                out.write('\n')
                        else:
                            logger.info('Stopped via signal on %s second', i)
                            out.flush()
                            logger.info('Done graceful shutdown')
                            raise KeyboardInterrupt()

    def filter(self, data):
        try:
            float(data)
        except:
            logger.warning('Trash data grabbed. Skipping and filling w/ zeroes. Data: %s. ', data)
            data = "0.0"
        finally:
            return data



# ================================
def main():
    logging.basicConfig(
        level="DEBUG",
        format='%(asctime)s [%(levelname)s] [Volta 500hz] %(filename)s:%(lineno)d %(message)s')
    logger.info("Volta 500 hz box ")
    test = ()
    worker = VoltaBox500Hz(test)
    worker.configure()
    worker.output_file = "output.bin"
    worker.device = "/dev/cu.wchusbserial1420"
    worker.test_duration = 15
    logger.info('worker args: %s', worker)
    worker.grab()
    logger.info('done')

if __name__ == "__main__":
    main()