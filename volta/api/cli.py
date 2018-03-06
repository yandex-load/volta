import logging
import yaml
import time

from netort.logging_and_signals import init_logging, set_sig_handler
from volta.core.core import Core


logger = logging.getLogger(__name__)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='volta console worker')
    parser.add_argument('-d', '--debug', '-v', '--verbose', dest='verbose', action='store_true', default=False)
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true', default=False)
    parser.add_argument('-l', '--log', dest='log', default='volta.log')
    parser.add_argument('-c', '--config', dest='config')
    args = parser.parse_args()

    if not args.config:
        raise RuntimeError('Empty config')

    init_logging(args.log, args.verbose, args.quiet)
    cfg_dict = {}
    with open(args.config, 'r') as cfg_stream:
        try:
            cfg_dict = yaml.safe_load(cfg_stream)
        except yaml.YAMLError:
            logger.debug('Config file format not yaml or json...', exc_info=True)
            raise RuntimeError('Unknown config file format. Malformed?')

    core = Core(cfg_dict)

    try:
        core.configure()
        logger.info('Starting test... You can interrupt test w/ Ctrl+C or SIGTERM signal')
        core.start_test()

        while True:
            time.sleep(1)  # infinite loop until SIGTERM

    except KeyboardInterrupt:
        logger.info('Keyboard interrupt, trying graceful shutdown. Do not press interrupt again, '
                    'otherwise test might be broken')
        core.end_test()
    except Exception:
        logger.error('Uncaught exception in core\n', exc_info=True)
    finally:
        core.post_process()
        core.collect_file(args.log)


if __name__ == '__main__':
    set_sig_handler()
    main()
