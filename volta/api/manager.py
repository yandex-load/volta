"""
Module that manages webserver and volta
"""
import os
import signal
import multiprocessing
import logging
import logging.handlers
import traceback
import json
import time
import yaml

from volta.api import common
from volta.api import worker
from volta.api import webserver


logger = logging.getLogger(__name__)


class TestRunner(object):
    """
    Manages the test process and its working directory.
    """

    def __init__(
            self, cfg, manager_queue, session_id, test_config):
        """
        Sets up working directory and test queue
        Starts test process
        """

        work_dir = os.path.join(cfg['tests_dir'], session_id)
        load_ini_path = os.path.join(work_dir, 'config.ini')
        # Create load.ini
        logger.info("Saving test config to %s", load_ini_path)
        try:
            with open(load_ini_path, 'w') as test_config_file:
                test_config_file.write(test_config)
        except:
            logger.info('Failed to write config file to %s', load_ini_path, exc_info=True)

        # Create test queue
        self.test_queue = multiprocessing.Queue()
        parsed_config = yaml.load(test_config)
        # Start test process
        try:
            self.test_process = multiprocessing.Process(
                target=worker.run,
                args=(
                    self.test_queue, manager_queue, work_dir, parsed_config, session_id
                )
            )
            self.test_process.start()
        except:
            logger.info('Failed to start test_process', exc_info=True)

    def is_alive(self):
        """Check that the test process didn't exit """
        return self.test_process.exitcode is None

    def get_exitcode(self):
        """Return test exitcode"""
        return self.test_process.exitcode

    def join(self):
        """Joins the test process"""
        logger.info("Waiting for test exit...")
        return self.test_process.join()

    def stop(self):
        """Interrupts the test process"""
        if self.is_alive():
            sig = signal.SIGINT
            os.kill(self.test_process.pid, sig)

    def __del__(self):
        self.stop()


class Manager(object):
    """
    Implements the message processing logic
    """

    def __init__(self, cfg):
        """Sets up initial state of Manager"""

        self.cfg = cfg

        self.manager_queue = multiprocessing.Queue()
        self.webserver_queue = multiprocessing.Queue()
        allow_multiple = True

        self.webserver_process = multiprocessing.Process(
            target=webserver.main,
            args=(
                self.webserver_queue, self.manager_queue, cfg['tests_dir'],
                allow_multiple, cfg['tornado_debug']
            )
        )
        self.webserver_process.daemon = True
        self.webserver_process.start()

        self.running_sessions = {}
        self.session_ids = []

        self._reset_session()

    def _reset_session(self, id=None):
        """
        Resets session state variables
        Should be called only when test is not running
        """
        if not id:
            return
        logger.info("Resetting current session variables")
        if id in self.session_ids:
            self.session_ids.remove(id)
        self.running_sessions[id] = {}

    def _handle_cmd_stop(self, msg):
        """Check running session and kill test"""
        self.running_sessions[msg['session']].stop()

    def _handle_cmd_new_session(self, msg):
        """Start new session"""
        if 'session' not in msg or 'config' not in msg:
            # Internal protocol error
            logger.critical(
                "Not enough data to start new session: "
                "both config and test should be present:%s\n", json.dumps(msg))
            return
        try:
            self.running_sessions[msg['session']] = TestRunner(
                cfg=self.cfg,
                manager_queue=self.manager_queue,
                session_id=msg['session'],
                test_config=msg['config']
            )
        except KeyboardInterrupt:
            pass
        except Exception as ex:
            self.webserver_queue.put({
                'session': msg['session'],
                'status': 'failed',
                'reason': 'Failed to start test:\n' + traceback.format_exc(ex)
            })
        else:
            self.session_ids.append(msg['session'])

    def _handle_cmd(self, msg):
        """Process command from webserver"""

        if 'session' not in msg:
            logger.error("Bad command: session id not specified")
            return

        cmd = msg['cmd']

        if cmd == 'stop':
            self._handle_cmd_stop(msg)
        elif cmd == 'run':
            self._handle_cmd_new_session(msg)
        else:
            logger.critical("Unknown command: %s", cmd)

    def _handle_test_exit(self):
        """
        Empty manager queue.
        Report if test died unexpectedly.
        Reset session.
        """
        logging.info("Test exit, sleeping 1 s and handling remaining messages")
        time.sleep(1)
        while True:
            try:
                msg = self.manager_queue.get(block=False)
            except multiprocessing.queues.Empty:
                break
            self._handle_msg(msg)
        #if self.last_test_status == 'running'\
        #        or not self.test_runner\
        #        or self.test_runner.get_exitcode() != 0:
        #    # Report unexpected death
        #    self.webserver_queue.put({
        #        'session': self.session_id,
        #        'status': 'failed',
        #        'reason': "Test died unexpectedly. Last reported "
        #        "status: % s, worker exitcode: % s" % (
        #            self.last_test_status,
        #            self.test_runner.get_exitcode() if self.test_runner else None)
        #    })
        # In any case, reset the session
            self._reset_session(msg['session'])

    def _handle_webserver_exit(self):
        """Stop tank and raise RuntimeError"""
        logger.error("Webserver died unexpectedly.")
        if len(self.running_sessions) >= 1:
            [session.stop() for session in self.running_sessions]
            [session.join() for session in self.running_sessions]
        raise RuntimeError("Unexpected webserver exit")

    def run(self):
        """
        Manager event loop.
        Process message from self.manager_queue
        Check that test is alive.
        Check that webserver is alive.
        """

        while True:
            #if self.session_ids is not None and not self.test_runner.is_alive():
            #    self._handle_test_exit()
            if not self.webserver_process.is_alive():
                self._handle_webserver_exit()
            try:
                msg = self.manager_queue.get(
                    block=True, timeout=self.cfg['message_check_interval'])
            except multiprocessing.queues.Empty:
                continue
            self._handle_msg(msg)

    def _handle_msg(self, msg):
        """Handle message from manager queue"""
        logger.info("Recieved message:\n%s", json.dumps(msg))
        if 'cmd' in msg:
            # Recieved command from server
            self._handle_cmd(msg)
        elif 'status' in msg:
            # This is a status message from tank
            self._handle_test_status(msg)
        else:
            logger.error("Strange message (not a command and not a status) ")

    def _handle_test_status(self, msg):
        """
        Wait for test exit if it stopped.
        Remember new status and notify webserver.
        """
        new_status = msg['status']

        if new_status in ['success', 'failed']:
            self.running_sessions[msg['session']].join()
            self._reset_session(msg['session'])

        self.webserver_queue.put(msg)


def run_server(options):
    """Runs the whole api server """

    # Configure
    # TODO: un-hardcode cfg
    cfg = {
        'message_check_interval': 1.0,
        'tests_dir': options.work_dir + '/tests',
        'tornado_debug': options.debug
    }

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    if options.log_file is None:
        handler = logging.StreamHandler()
    else:
        handler = logging.handlers.RotatingFileHandler(
            options.log_file, maxBytes=1000000, backupCount=16)

    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s %(message)s"))
    root_logger.addHandler(handler)

    logger = logging.getLogger(__name__)
    try:
        logger.info("Starting server")
        Manager(cfg).run()
    except KeyboardInterrupt:
        logger.info("Interrupted, terminating")
    except Exception:
        logger.exception("Unhandled exception in manager.run_server:")
    except:
        logger.error("Caught something strange in manager.run_server")


def parse_options():
    '''parse command line options'''
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debug",
        action='store_true',
        help='Debug mode of torando',
        dest='debug',
        default=False)
    parser.add_argument(
        "--work-dir",
        help='Working directory (for tests, etc).',
        default='.',
        dest='work_dir')
    parser.add_argument(
        "--log",
        help='Log file',
        default='api.log',
        dest='log_file')
    return parser.parse_args()


def signal_handler(sig, frame):
    """ required for everything to be released safely on SIGTERM and SIGINT"""
    raise KeyboardInterrupt()


def main():
    import logging
    logging.basicConfig(
        level=logging.DEBUG, format="%(asctime)s %(levelname)s: %(message)s")
    options = parse_options()
    try:
        run_server(options)
    except:
        logging.exception("Uncaught exception:")


if __name__ == '__main__':
    main()

