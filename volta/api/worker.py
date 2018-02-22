"""
Test worker process for volta api
"""

import signal
import logging
import os
import os.path
import traceback
import json
import yaml
from volta.core.core import Core as VoltaCore

# Test stage order, internal protocol description, etc...
from volta.api import common


logger = logging.getLogger(__name__)


class InterruptTest(BaseException):
    """Raised by sigterm handler"""

    def __init__(self):
        super(InterruptTest, self).__init__()

class StopTest(BaseException):
    """Raised by sigterm handler"""

    def __init__(self):
        super(StopTest, self).__init__()


class VoltaWorker(object):
    """ Volta Worker class that runs Volta core """

    def __init__(self, tank_queue, manager_queue, working_dir, config, session_id):

        # Parameters from manager
        self.tank_queue = tank_queue
        self.manager_queue = manager_queue
        self.working_dir = working_dir
        self.session_id = session_id
        self.config = config

        # State variables
        self.stage = 'not started'
        self.failures = []
        self.retcode = None
        self.locked = False
        self.done_stages = set()
        self.core = VoltaCore(
            yaml.safe_load(self.config)
        )
        self.core.session_id = None
        self.core.status = None

    def __add_log_file(self, logger, loglevel, filename):
        """Adds FileHandler to logger; adds filename to artifacts"""
        self.core.add_artifact_file(filename)
        handler = logging.FileHandler(filename)
        handler.setLevel(loglevel)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s %(message)s"))
        logger.addHandler(handler)

    def __setup_logging(self):
        """
        Logging setup.
        Should be called only after the lock is acquired.
        """
        logger = logging.getLogger('')
        logger.setLevel(logging.DEBUG)

        self.__add_log_file(logger, logging.DEBUG, 'test.log')

    def report_status(self, status, stage_completed):
        """Report status to manager and dump status.json, if required"""
        msg = {
            'status': status,
            'session': self.session_id,
            'current_stage': self.stage,
            'stage_completed': stage_completed,
            'failures': self.failures,
            'retcode': self.retcode,
            'test_status': self.core.status,
        }
        self.manager_queue.put(msg)
        if self.locked:
            json.dump(
                msg,
                open('status.json', 'w'),
                indent=4)

    def process_failure(self, reason):
        """
        Act on failure of current test stage:
        - log it
        - add to failures list
        """
        logger.error("Failure in stage %s:\n%s", self.stage, reason)
        self.failures.append({'stage': self.stage, 'reason': reason})

    def _execute_stage(self, stage):
        """Really execute stage and set retcode"""
        new_retcode = {
            'configure': self.core.configure,
            'start_test': self.core.start_test
        }[stage]()
        if new_retcode is not None:
            self.retcode = new_retcode

    def _stop_stage(self):
        """Really execute stage and set retcode"""
        self.core.end_test()
        self.core.post_process()

    def next_stage(self, stage):
        """
        Report stage completion.
        Switch to the next test stage if allowed.
        Run it or skip it
        """
        self.stage = stage
        self.report_status('running', False)
        if stage == common.TEST_STAGE_ORDER[0] or common.TEST_STAGE_DEPS[stage] in self.done_stages:
            try:
                self._execute_stage(stage)
            except InterruptTest:
                self.retcode = self.retcode or 1
                self.process_failure("Interrupted")
                raise StopTest()
            except Exception as ex:
                self.retcode = self.retcode or 1
                logger.exception(
                    "Exception occured, trying to exit gracefully...")
                self.process_failure("Exception:" + traceback.format_exc(ex))
            else:
                self.done_stages.add(stage)
        else:
            self.process_failure("skipped")

        self.report_status('running', True)

    def perform_test(self):
        """Perform the test sequence via TankCore"""
        try:
            for stage in common.TEST_STAGE_ORDER[:-1]:
                self.next_stage(stage)
        except StopTest:
            self._stop_stage()
        else:
            self._stop_stage()
        self.stage = 'finished'
        self.report_status('failed' if self.failures else 'success', True)
        logger.info("Done performing test with code %s", self.retcode)


def signal_handler(signum, _):
    """ required for everything to be released safely on SIGTERM and SIGINT"""
    if signum == signal.SIGINT:
        raise InterruptTest()
    raise InterruptTest()


def run(test_queue, manager_queue, work_dir, config, session_id):
    """
    Target for test process.
    This is the only function from this module ever used by Manager.

    test_queue
        Read next break from here

    manager_queue
        Write tank status there

    """
    try:
        os.chdir(work_dir)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        VoltaWorker(
            test_queue, manager_queue, work_dir, config, session_id
            ).perform_test()
    except:
        logger.info('Failed to lauch VoltaWorker', exc_info=True)
