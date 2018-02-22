import logging
import signal
import yaml
import time
import sys

from volta.core.core import Core


logger = logging.getLogger(__name__)


class SingleLevelFilter(logging.Filter):
    """Exclude or approve one msg type at a time.    """

    def __init__(self, passlevel, reject):
        logging.Filter.__init__(self)
        self.passlevel = passlevel
        self.reject = reject

    def filter(self, record):
        if self.reject:
            return record.levelno != self.passlevel
        else:
            return record.levelno == self.passlevel


def init_logging(log_filename, verbose, quiet):
    """ Set up logging, as it is very important for console tool """
    logger = logging.getLogger('')
    logger.setLevel(logging.DEBUG)

    # create file handler which logs even debug messages
    if log_filename:
        file_handler = logging.FileHandler(log_filename)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d\t%(message)s"
            ))
        logger.addHandler(file_handler)

    # create console handler with a higher log level
    console_handler = logging.StreamHandler(sys.stdout)
    stderr_hdl = logging.StreamHandler(sys.stderr)

    fmt_verbose = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d\t%(message)s"
    )
    fmt_regular = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")

    if verbose:
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(fmt_verbose)
        stderr_hdl.setFormatter(fmt_verbose)
    elif quiet:
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(fmt_regular)
        stderr_hdl.setFormatter(fmt_regular)
    else:
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(fmt_regular)
        stderr_hdl.setFormatter(fmt_regular)

    f_err = SingleLevelFilter(logging.ERROR, True)
    f_warn = SingleLevelFilter(logging.WARNING, True)
    f_crit = SingleLevelFilter(logging.CRITICAL, True)
    console_handler.addFilter(f_err)
    console_handler.addFilter(f_warn)
    console_handler.addFilter(f_crit)
    logger.addHandler(console_handler)

    f_info = SingleLevelFilter(logging.INFO, True)
    f_debug = SingleLevelFilter(logging.DEBUG, True)
    stderr_hdl.addFilter(f_info)
    stderr_hdl.addFilter(f_debug)
    logger.addHandler(stderr_hdl)


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
        except Exception:
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


# ============= signals handler =========
def signal_handler(sig, frame):
    """ required for non-tty python runs to interrupt """
    logger.warning("Got signal %s, going to stop", sig)
    raise KeyboardInterrupt()


def ignore_handler(sig, frame):
    logger.warning("Got signal %s, ignoring", sig)


def set_sig_handler():
    uncatchable = ['SIG_DFL', 'SIGSTOP', 'SIGKILL']
    ignore = ['SIGCHLD', 'SIGCLD']
    all_sig = [s for s in dir(signal) if s.startswith("SIG")]
    for sig_name in ignore:
        try:
            sig_num = getattr(signal, sig_name)
            signal.signal(sig_num, ignore_handler)
        except Exception:
            pass
    for sig_name in [s for s in all_sig if s not in (uncatchable + ignore)]:
        try:
            sig_num = getattr(signal, sig_name)
            signal.signal(sig_num, signal_handler)
        except Exception as ex:
            logger.error("Can't set handler for %s, %s", sig_name, ex)

# ============================================


if __name__ == '__main__':
    set_sig_handler()
    main()
