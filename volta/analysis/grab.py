from __future__ import print_function
import serial
import json
import argparse
import progressbar
import logging
import time


logger = logging.getLogger(__name__)


class Grabber(object):
    def __init__(self):
        self.samplerate = 10000
        self.baud_rate = 230400

    def detect_volta_format(self, args):
        """
        this method doesn't work because of some bug in pyserial - port stucks after close() method
        """
        with serial.Serial(args.get('device'), timeout=1) as ser:
            logger.info('baudrate set: %s', 230400)
            ser.baudrate = 230400
            for _ in range(10):
                data = ser.read(25)
                if data:
                    data_list = data.split('\n')
                    logger.info('data: %s', data_list)
                    for chunk in data_list:
                        if chunk == "VOLTAHELLO":
                            logger.info('Volta format detected: binary')
                            self.baud_rate = 230400
                            self.fmt = 'binary'
                            ser.close()
                            return
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            logger.info('baudrate set: %s', 115200)
            ser.baudrate = 115200
            for _ in range(10):
                data = ser.read(25)
                if data:
                    data_list = data.split('\n')
                    logger.info('data: %s', data_list)
                    try:
                        float(data_list[0])
                    except ValueError:
                        ser.reset_input_buffer()
                        ser.reset_output_buffer()
                        ser.close()
                        raise RuntimeError('unknown volta format: %s', data_list)
                    else:
                        logger.info('Volta format detected: text')
                        self.baud_rate = 115200
                        self.fmt = 'text'
                        self.samplerate = 500
                        ser.close()
                        return

    def grab_binary(self, args):
        with serial.Serial(args.get('device'), self.baud_rate, timeout=1) as ser:
            logger.info("Waiting for synchronization line...")
            while ser.readline() != "VOLTAHELLO\n":
                pass
            params = json.loads(ser.readline())
            self.samplerate = params["sps"]
            logger.info("Synchronization successful. Sample rate: %d", self.samplerate)

            logger.info(
                "Collecting %d seconds of data (%d samples) to '%s'." % (
                    args.get('seconds'), args.get('seconds') * self.samplerate, args.get('output')))
            while ser.readline() != "DATASTART\n":
                pass
            with open(args.get('output'), "wb") as out:
                with progressbar.ProgressBar(max_value=args['seconds']) as bar:
                    for i in range(args.get('seconds')):
                        bar.update(i)
                        out.write(ser.read(self.samplerate * 2))

    def grab_text(self, args):
        with serial.Serial(args.get('device'), self.baud_rate, timeout=1) as ser:
            logger.info(
                "Collecting %d seconds of data (%d samples) to '%s'." % (
                    args.get('seconds'), args.get('seconds') * self.samplerate, args.get('output')))
            logger.debug('first 500 values will be skipped')
            for n in range(500):
                ser.readline()
            logger.debug('Opening output file and starting grab')
            with open(args.get('output'), "wb") as out:
                with progressbar.ProgressBar(max_value=args['seconds']) as bar:
                    for i in range(args.get('seconds')):
                        bar.update(i)
                        for _ in range(self.samplerate):
                            out.write(ser.readline())


def run():
    parser = argparse.ArgumentParser(description='Grab data from measurement device.')
    parser.add_argument(
        '-i', '--device',
        default="/dev/cu.wchusbserial1410",
        help='Arduino device serial port')
    parser.add_argument(
        '-s', '--seconds',
        default=60,
        type=int,
        help='number of seconds to collect')
    parser.add_argument(
        '-o', '--output',
        default="output.bin",
        help='file to store the results')
    parser.add_argument(
        '-b', '--binary',
        action='store_true',
        default=False,
        help='volta output format detection')
    parser.add_argument(
        '-d', '--debug',
        help='enable debug logging',
        action='store_true')
    args = vars(parser.parse_args())
    main(args)

def main(args):
    logging.basicConfig(
        level="DEBUG" if args.get('debug') else "INFO",
        format='%(asctime)s [%(levelname)s] [grabber] %(filename)s:%(lineno)d %(message)s')
    logger.info("Volta data grabber.")
    grabber = Grabber()
    # grabber.detect_volta_format(args)
    if args.get('binary'):
        grabber.baud_rate = 230400
        grabber.grab_binary(args)
    else:
        grabber.baud_rate = 115200
        grabber.samplerate = 500
        grabber.grab_text(args)
    return grabber


if __name__ == '__main__':
    run()
