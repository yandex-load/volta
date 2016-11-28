import usb
import gzip
import logging

logger = logging.getLogger(__name__)


def ids_file_to_dict(fname):
    ids_dict = {}
    with gzip.open(fname, 'r') as ids_f:
        for line in ids_f.readlines():
            # exclude comments
            if line.startswith('#'):
                continue
            data = line.strip('\n').split('\t')
            # create manufacturers
            if len(data) == 1:
                man_id = data[0].split(' ')[0]
                man_name = data[0].split(' ')[1:]
                if man_id and man_id not in ids_dict:
                    ids_dict[man_id] = {}
                    ids_dict[man_id]['manufacturer_name'] = ' '.join(man_name)
                    ids_dict[man_id]['devices'] = {}
            # fill devices
            elif len(data) > 1:
                dev_id = data[1].split(' ')[0]
                dev_name = data[1].split(' ')[1:]
                ids_dict[man_id]['devices'][dev_id] = ' '.join(dev_name)
    return ids_dict


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Reads USB ids file and returns dict contents.')
    parser.add_argument(
        '-f', '--file',
        default="usb.ids.gz",
        help='USB devices filename, gzipped')
    args = parser.parse_args()
    logging.basicConfig(
        level="DEBUG",
        format='%(asctime)s [%(levelname)s] [USB list parser] %(filename)s:%(lineno)d %(message)s'
    )
    logger.info("USB list parser.")
    print ids_file_to_dict(args.file)


if __name__ == "__main__":
    main()
