import gzip
import logging
import sqlite3

logger = logging.getLogger(__name__)


def ids_file_to_sqlite(fname):
    """
    reads usb_ids.gz file and returns python dict

    Args:
        fname: usb_ids.gz

    Returns:
        sqlite3 db filename
    """

    out_fname = 'usb_list.db'
    conn = sqlite3.connect(out_fname)
    conn.text_factory = str
    c = conn.cursor()

    # Create table
    c.execute('''CREATE TABLE devices
                             (manufacturer_id, manufacturer_name, id, name)''')
    with gzip.open(fname, 'r') as ids_f:
        for line in ids_f.readlines():
            # exclude comments
            if line.startswith('#'):
                continue
            data = line.strip('\n').split('\t')
            if len(data) == 1:
                man_id = data[0].split(' ')[0]
                man_name = ' '.join(data[0].split(' ')[1:])
            # insert devices w/
            elif len(data) > 1:
                if not man_id:
                    continue
                dev_id = data[1].split(' ')[0]
                dev_name = ' '.join(data[1].split(' ')[1:])
                c.execute('INSERT INTO devices VALUES (?,?,?,?)', (man_id, man_name, dev_id, dev_name))
    # Save (commit) the changes
    conn.commit()
    # We can also close the connection if we are done with it.
    # Just be sure any changes have been committed or they will be lost.
    conn.close()

    return out_fname


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Reads USB ids file and returns sqlite3 db name w/ contents.')
    parser.add_argument(
        '-f', '--file',
        default="usb.ids.gz",
        help='USB devices filename, gzipped')
    args = parser.parse_args()
    logging.basicConfig(
        level="DEBUG",
        format='%(asctime)s [%(levelname)s] [USB list parser] %(filename)s:%(lineno)d %(message)s'
    )
    logger.info("USB devices list parser started.")
    print ids_file_to_sqlite(args.file)
    logger.info("USb devices list parser done.")


if __name__ == "__main__":
    main()
