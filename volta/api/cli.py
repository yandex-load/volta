import logging
import yaml
import time
import os
import shutil

from netort.logging_and_signals import init_logging, set_sig_handler
from volta.core.core import Core


logger = logging.getLogger(__name__)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='volta console worker')
    parser.add_argument('-d', '--debug', '-v', '--verbose', dest='verbose', action='store_true', default=False)
    parser.add_argument('-t', '--trace', dest='trace', action='store_true', default=False)
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true', default=False)
    parser.add_argument('-l', '--log', dest='log', default='volta.log')
    parser.add_argument('-c', '--config', dest='config')
    parser.add_argument(
        '-p',
        '--patch-cfg',
        action='append',
        help='Patch config with yaml snippet (similar to -o, but has full compatibility to\
        and the exact scheme of yaml format config)',
        dest='patches',
        default=[]
    )
    args = parser.parse_args()

    if not args.config:
        raise RuntimeError('Empty config')

    init_logging(args.log, args.verbose, args.quiet)
    raw_config = []
    with open(args.config, 'r') as cfg_stream:
        try:
            raw_config = [yaml.safe_load(cfg_stream)]
        except yaml.YAMLError:
            logger.debug('Config file format not yaml or json...', exc_info=True)
            raise RuntimeError('Unknown config file format. Malformed?')

    if args.trace:
        import statprof
        statprof.start()

    patched_config = raw_config+parse_and_check_patches(args.patches)
    perform_test(patched_config, args.log)

    if args.trace:
        statprof.stop()
        statprof.display()


def parse_and_check_patches(patches):
    parsed = [yaml.load(p) for p in patches]
    for patch in parsed:
        if not isinstance(patch, dict):
            raise RuntimeError('Config patch "{}" should be a dict'.format(patch))
    return parsed


def perform_test(configs, log):
    core = Core(configs)
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
        core.end_test()
    finally:
        core.post_process()
        try:
            shutil.move(log, os.path.join(core.data_session.artifacts_dir, log))
        except Exception:
            logger.warn('Failed to move logfile %s to artifacts dir', log)
            logger.debug('Failed to move logfile %s to artifacts dir', log, exc_info=True)


if __name__ == '__main__':
    set_sig_handler()
    main()
