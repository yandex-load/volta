""" Android phone worker, OS version below 5

"""
import logging
import re
import queue as q
import time
import pkg_resources

from volta.common.interfaces import Phone
from volta.common.util import LogReader

from netort.data_processing import Drain
from netort.process import execute, popen
from netort.resource import manager as resource

logger = logging.getLogger(__name__)

event_regexp = r"""
    ^(?P<date>\S+)
    \s+
    (?P<time>\S+)
    \s+
    \S+
    \s+
    \S+
    \s+
    \S+
    \s+
    (?P<message>.*)
    $
    """


class AndroidOldPhone(Phone):
    """ Android Old phone worker class - work w/ phone, read phone logs, run test apps and store data

    Attributes:
        source (string): path to data source, phone id (adb devices)
        unplug_type (string): type of test execution
            `auto`: disable battery charge (by software) or use special USB cord limiting charge over USB
            `manual`: disable phone from USB by your own hands during test exection and click your test
        lightning_apk_path (string, optional): path to lightning app
            may be url, e.g. 'http://myhost.tld/path/to/file'
            may be path to file, e.g. '/home/users/netort/path/to/file.apk'
        lightning_apk_class (string, optional): lightning class
        test_apps (list, optional): list of apps to be installed to device for test
        test_class (string, optional): app class to be started during test execution
        test_package (string, optional): app package to be started during test execution
        test_runner (string, optional): app runner to be started during test execution

    Todo:
        unplug_type manual - remove raw_input()
    """

    def __init__(self, config):
        """
        Args:
            config (VoltaConfig): module configuration data
        """
        Phone.__init__(self, config)
        self.logcat_stdout_reader = None
        self.logcat_stderr_reader = None
        # mandatory options
        self.source = config.get_option('phone', 'source')
        #self.unplug_type = config.get('unplug_type', 'auto')
        # lightning app configuration
        self.lightning_apk_path = config.get_option(
            'phone', 'lightning', pkg_resources.resource_filename(
                'volta.providers.phones', 'binary/lightning-new3.apk'
            )
        )
        self.lightning_apk_class = config.get_option('phone', 'lightning_class')
        self.lightning_apk_fname = None
        # test app configuration
        self.test_apps = config.get_option('phone', 'test_apps')
        self.test_class = config.get_option('phone', 'test_class')
        self.test_package = config.get_option('phone', 'test_package')
        self.test_runner = config.get_option('phone', 'test_runner')
        self.cleanup_apps = config.get_option('phone', 'cleanup_apps')
        self.regexp = config.get_option('phone', 'event_regexp', event_regexp)
        try:
            self.compiled_regexp = re.compile(self.regexp, re.VERBOSE | re.IGNORECASE)
        except:
            logger.debug('Unable to parse specified regexp', exc_info=True)
            raise RuntimeError("Unable to parse specified regexp")
        self.test_performer = None


    def prepare(self):
        """ Phone preparements stage: install apps etc

        pipeline:
            install lightning
            install apks
            clean log
        """
        # apps cleanup
        for apk in self.cleanup_apps:
            execute("adb -s {device_id} uninstall {app}".format(device_id=self.source, app=apk))

        # install lightning
        self.lightning_apk_fname = resource.get_opener(self.lightning_apk_path).get_filename
        logger.info('Installing lightning apk...')
        execute("adb -s {device_id} install -r -d -t {apk}".format(device_id=self.source, apk=self.lightning_apk_fname))

        # install apks
        for apk in self.test_apps:
            apk_fname = resource.get_opener(apk).get_filename
            execute("adb -s {device_id} install -r -d -t {apk}".format(device_id=self.source, apk=apk_fname))

        # clean logcat
        execute("adb -s {device_id} logcat -c".format(device_id=self.source))

        # unplug device or start logcat
        #if self.unplug_type == 'manual':
        #    logger.info('Detach the phone %s from USB and press enter to continue...', self.source)
        #    # TODO make API and remove this
        #    raw_input()


    def start(self, results):
        """ Grab stage: starts log reader, make sync w/ flashlight

        pipeline:
            if uplug_type is manual:
                remind user to start flashlight app
            if unplug_type is auto:
                start async logcat reader
                start lightning flashes

        Args:
            results (queue-like object): Phone should put there dataframes, format: ['sys_uts', 'message']
        """
        self.phone_q = results

        #if self.unplug_type == 'manual':
        #    logger.info("It's time to start flashlight app!")
        #    return

        #if self.unplug_type == 'auto':
        self.__start_async_logcat()
        # start flashes app
        execute(
            "adb -s {device_id} shell am start -n {package}/{runner}.MainActivity".format(
                device_id=self.source,
                package=self.lightning_apk_class,
                runner=self.lightning_apk_class
            )
        )
        logger.info('Waiting 15 seconds till flashlight app end its work...')
        time.sleep(15)
        return

    def __start_async_logcat(self):
        """ Start logcat read in subprocess and make threads to read its stdout/stderr to queues """
        cmd = "adb -s {device_id} logcat -v time".format(device_id=self.source)
        logger.debug("Execute : %s", cmd)
        self.logcat_process = popen(cmd)

        self.logcat_reader_stdout = LogReader(self.logcat_process.stdout, self.compiled_regexp)
        self.drain_logcat_stdout = Drain(self.logcat_reader_stdout, self.phone_q)
        self.drain_logcat_stdout.start()

        self.phone_q_err=q.Queue()
        self.logcat_reader_stderr = LogReader(self.logcat_process.stderr, self.compiled_regexp)
        self.drain_logcat_stderr = Drain(self.logcat_reader_stderr, self.phone_q_err)
        self.drain_logcat_stderr.start()

    def run_test(self):
        """ App stage: run app/phone tests """
        if self.test_package:
            command = "adb -s {device_id} shell am instrument -w -e class {test_class} {test_package}/{test_runner}".format(
                test_class=self.test_class,
                device_id=self.source,
                test_package=self.test_package,
                test_runner=self.test_runner
            )
        else:
            logger.info('Infinite loop for volta because there are no tests specified, waiting for SIGINT')
            command = 'while [ 1 ]; do sleep 1; done'
        self.test_performer = PhoneTestPerformer(command)
        self.test_performer.start()
        return

    def end(self):
        """ Stop test and grabbers """
        if self.test_performer:
            self.test_performer.close()
        self.logcat_reader_stdout.close()
        self.logcat_reader_stderr.close()
        self.logcat_process.kill()
        self.drain_logcat_stdout.close()
        self.drain_logcat_stderr.close()

        # apps cleanup
        for apk in self.cleanup_apps:
            execute("adb -s {device_id} uninstall {app}".format(device_id=self.source, app=apk))
        return

    def get_info(self):
        data = {}
        if self.drain_logcat_stdout:
            data['grabber_alive'] = self.drain_logcat_stdout.isAlive()
        if self.phone_q:
            data['grabber_queue_size'] = self.phone_q.qsize()
        if self.test_performer:
            data['test_performer_alive'] = self.test_performer.isAlive()
        return data

