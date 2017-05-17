import logging
import sys
import signal
import yaml
import time
from optparse import OptionParser

from volta.core.core import Core


logger = logging.getLogger(__name__)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='volta console worker')
    parser.add_argument('--debug', dest='debug', action='store_true', default=False)
    parser.add_argument('--config', dest='config')
    args = parser.parse_args()

    logging.basicConfig(
        level="DEBUG" if args.debug else "INFO",
        format='%(asctime)s [%(levelname)s] [Volta Core] %(filename)s:%(lineno)d %(message)s')
    logger.info("Volta Core init")

    with open(args.config, 'r') as cfg:
        cfg_data = cfg.read()
    cfg_dict = yaml.safe_load(cfg_data)
    core = Core(cfg_dict)
    try:
        core.configure()
        core.start_test()
        time.sleep(20)
        core.end_test()
    except KeyboardInterrupt:
        core.end_test()
    except:
        logger.error('Uncaught exception in core\n', exc_info=True)
    finally:
        core.post_process()


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
