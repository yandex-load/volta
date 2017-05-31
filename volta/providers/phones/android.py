""" Android phone worker
"""
import logging
import re
import queue as q
import pkg_resources

from volta.common.interfaces import Phone
from volta.common.util import execute, Drain, popen, chunk_to_df, LogReader
from volta.common.resource import manager as resource


logger = logging.getLogger(__name__)


android_logevent_re = re.compile(r"""
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
    """, re.VERBOSE | re.IGNORECASE
)


class AndroidPhone(Phone):
    """ Android phone worker class - work w/ phone, read phone logs, run test apps and store data

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
            config (dict): module configuration data
        """
        Phone.__init__(self, config)
        self.logcat_stdout_reader = None
        self.logcat_stderr_reader = None
        # mandatory options
        self.source = config.get('source', '00dc3419957ba583')
        self.unplug_type = config.get('unplug_type', 'auto')
        # lightning app configuration
        self.lightning_apk_path = config.get('lightning', pkg_resources.resource_filename(
            'volta.providers.phones', 'binary/lightning-new3.apk')
        )
        self.lightning_apk_class = config.get('lightning_class', 'net.yandex.overload.lightning')
        self.lightning_apk_fname = None
        # test app configuration
        self.test_apps = config.get('test_apps', [])
        self.test_class = config.get('test_class', '')
        self.test_package = config.get('test_package', '')
        self.test_runner = config.get('test_runner', '')

    def prepare(self):
        """ Phone preparements stage: install apps etc

        pipeline:
            install lightning
            install apks
            clean log
        """

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
        if self.unplug_type == 'manual':
            logger.info('Detach the phone %s from USB and press enter to continue...', self.source)
            # TODO make API and remove this
            raw_input()


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

        if self.unplug_type == 'manual':
            logger.info("It's time to start flashlight app!")
            return

        if self.unplug_type == 'auto':
            self.__start_async_logcat()
            # start flashes app
            execute(
                "adb -s {device_id} shell am start -n {package}/{runner}.MainActivity".format(
                    device_id=self.source,
                    package=self.lightning_apk_class,
                    runner=self.lightning_apk_class
                )
            )
            return

    def __start_async_logcat(self):
        """ Start logcat read in subprocess and make threads to read its stdout/stderr to queues """
        cmd = "adb -s {device_id} logcat".format(device_id=self.source)
        logger.debug("Execute : %s", cmd)
        self.logcat_process = popen(cmd)

        self.logcat_reader_stdout = LogReader(self.logcat_process.stdout, android_logevent_re)
        self.drain_logcat_stdout = Drain(self.logcat_reader_stdout, self.phone_q)
        self.drain_logcat_stdout.start()

        self.phone_q_err=q.Queue()
        self.logcat_reader_stderr = LogReader(self.logcat_process.stderr, android_logevent_re)
        self.drain_logcat_stderr = Drain(self.logcat_reader_stderr, self.phone_q_err)
        self.drain_logcat_stderr.start()

    def run_test(self):
        """ App stage: run app/phone tests,

        pipeline:
            if unplug_type is auto:
                run test
            if unplug_type is manual:
                skip
        """

        if self.unplug_type == 'manual':
            return

        if self.unplug_type == 'auto':
            execute(
                "adb shell am instrument -w -e class {test_class} {test_package}/{test_runner}".format(
                    test_class=self.test_class,
                    test_package=self.test_package,
                    test_runner=self.test_runner
                )
            )
            return

    def end(self):
        """ Stop test and grabbers

        pipeline:
            if uplug_type is manual:
                ask user to plug device in
                get logcat dump from device
            if unplug_type is auto:
                stop async logcat process, readers and queues
        """

        if self.unplug_type == 'manual':
            logger.warning("Plug the phone in and press `enter` to continue...")
            # TODO make API and remove this
            raw_input()

            _, stdout, stderr = execute(
                "adb -s {device_id} logcat -d".format(device_id=self.source), catch_out=True
            )
            logger.debug('Recieved %d logcat data', len(stdout))
            self.phone_q.put(
                chunk_to_df(stdout, android_logevent_re)
            )
            return

        if self.unplug_type == 'auto':
            self.logcat_reader_stdout.close()
            self.logcat_reader_stderr.close()
            self.logcat_process.kill()
            self.drain_logcat_stdout.close()
            self.drain_logcat_stderr.close()
            return

