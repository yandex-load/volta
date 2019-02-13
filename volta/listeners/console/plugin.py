import logging

from volta.common.interfaces import DataListener

logger = logging.getLogger(__name__)


class ConsoleListener(DataListener):
    """
    Prints stats to console every second
    """

    def __init__(self, config, core):
        """
        Args:
            config: config to listeners, config.fname should store a name of file
        """
        super(ConsoleListener, self).__init__(config, core)
        self.closed = None
        self.output_fmt = {
            'currents': ['ts', 'value'],
            'sync': ['sys_uts', 'log_uts', 'app', 'tag', 'message'],
            'event': ['sys_uts', 'log_uts', 'app', 'tag', 'message'],
            'metric': ['sys_uts', 'log_uts', 'app', 'tag', 'value'],
            'fragment': ['sys_uts', 'log_uts', 'app', 'tag', 'message'],
            'unknown': ['sys_uts', 'message']
        }
        self.core.data_session.manager.subscribe(self.put, {'type': 'metrics', 'name': 'current'})

    def get_info(self):
        """ mock """
        pass

    def put(self, df):
        """ Process data

        Args:
            df (pandas.DataFrame): dfs w/ data contents,
                differs for each data type.
                Should be processed differently from each other
        """
        if not self.closed:
            logger.info("\n%s\n", df.describe())

    def close(self):
        self.closed = True
