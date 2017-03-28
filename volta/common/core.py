import logging

logger = logging.getLogger(__name__)


class Core(object):
    """ Core
    Core class, test performer """
    def __init__(self, config):
        """ parse config, @type:dict """
        self.config = config
        pass

    def configure(self):
        """
        1) VoltaBoxFactory
        2) PhoneFactory
        3) EventLogParser
        4) MetricsExtractor
        5) Sync
        6) Uploader
        """
        pass

    def start_test(self):
        pass

    def end_test(self):
        pass

    def post_process(self):
        pass


class VoltaBoxFactory(object):
    def __init__(self):
        """ find VoltaBox """
        pass


class PhoneFactory(object):
    def __init__(self):
        """ find Phone """
        pass