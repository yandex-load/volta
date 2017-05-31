import logging
import pandas as pd
import json
import yaml

from volta.listeners.uploader.uploader import DataUploader

logger = logging.getLogger(__name__)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='volta console post-loader')
    parser.add_argument('--debug', dest='debug', action='store_true', default=False)
    parser.add_argument('-l', '--logs', action='append', help='Log files list')
    parser.add_argument('-c', '--config', dest='config')
    args = parser.parse_args()

    logging.basicConfig(
        level="DEBUG" if args.debug else "INFO",
        format='%(asctime)s [%(levelname)s] [Volta Post-loader] %(filename)s:%(lineno)d %(message)s')

    config = {}
    if not args.config:
        # TODO switch to defaults
        config = {'uploader': {'address': 'https://lunapark.test.yandex-team.ru/api/volta'}}
    else:
        with open(args.config, 'r') as cfg_stream:
            try:
                config = yaml.load(cfg_stream)
            except:
                raise RuntimeError('Config file not in yaml or malformed')


    if not args.logs:
        raise RuntimeError('Empty log list')

    for log in args.logs:
        try:
            with open(log, 'r') as logname:
                meta = json.loads(logname.readline())
        except:
            raise RuntimeError('There is no json header in logfile or json malformed')
        else:
            df = pd.read_csv(log, sep='\t', skiprows=1, names=meta['names'], dtype=meta['dtypes'])

        logger.info('Uploading %s', log)
        uploader = DataUploader(config)
        logger.info('Meta type: %s', meta['type'])
        logger.info('New test_id created for this log: %s', uploader.test_id)
        uploader.put(df, meta['type'])
        logger.info('Done!')
