import logging


logger = logging.getLogger(__name__)  # pylint: disable=C0103


class Report(object):
    def __init__(self, config):
        pass

    def configure(self):
        pass

    def flush(self):
        pass

    def post_process(self):
        pass