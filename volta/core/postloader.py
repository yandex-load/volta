import logging
import yaml
import pandas as pd


logger = logging.getLogger(__name__)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='volta console post-loader')
    parser.add_argument('--debug', dest='debug', action='store_true', default=False)
    parser.add_argument('-c', '--config', dest='config')
    args = parser.parse_args()

    logging.basicConfig(
        level="DEBUG" if args.debug else "INFO",
        format='%(asctime)s [%(levelname)s] [Volta Post-loader] %(filename)s:%(lineno)d %(message)s')

    if not args.config:
        raise RuntimeError('Empty config')
    with open(args.config, 'r') as cfg:
        cfg_data = cfg.read()
    try:
        cfg_dict = yaml.safe_load(cfg_data)
    except:
        logger.debug('Config file format not yaml or json...', exc_info=True)
        raise RuntimeError('Unknown config file format. Malformed?')

