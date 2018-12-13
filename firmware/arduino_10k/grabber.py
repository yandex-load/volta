
import serial
import sys
import json
import argparse
import progressbar
import logging

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(
        description='Calculate sync point for android log and electrical current measurements.')
    parser.add_argument(
        '-i', '--device',
        default="/dev/cu.wchusbserial1410",
        help='Arduino port')
    parser.add_argument(
        '-s', '--seconds',
        default=60,
        help='number of seconds to collect')
    parser.add_argument(
        '-o', '--output',
        default="output.bin",
        help='file to store the results')
    parser.add_argument(
        '-d', '--debug',
        help='enable debug logging',
        action='store_true')
    args = parser.parse_args()
    logging.basicConfig(
        level="DEBUG" if args.debug else "INFO",
        format='%(asctime)s [%(levelname)s] [VOLTA GRAB] %(filename)s:%(lineno)d %(message)s')
    logger.info("Volta data grabber.")
    with serial.Serial(args.device, 230400, timeout=1) as ser:
        logger.info("Waiting for synchronization line...")
        while ser.readline() != "VOLTAHELLO\n":
            pass
        params = json.loads(ser.readline())
        sps = params["sps"]
        logger.info("Synchronization successful. Sample rate: %d", sps)

        logger.info(
            "Collecting %d seconds of data (%d samples) to '%s'." % (
                args.seconds, args.seconds * sps, args.output))
        while ser.readline() != "DATASTART\n":
            pass
        with open(args.output, "wb") as out:
            with progressbar.ProgressBar(max_value=args.seconds) as bar:
                for i in range(args.seconds):
                    bar.update(i)
                    out.write(ser.read(sps * 2))

if __name__ == '__main__':
    main()
