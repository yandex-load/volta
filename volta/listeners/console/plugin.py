import logging

from volta.common.interfaces import DataListener

logger = logging.getLogger(__name__)


class ConsoleListener(DataListener):
    """
    Prints stats to console every second
    """

    def __init__(self, config):
        """
        Args:
            config: config to listeners, config.fname should store a name of file
        """
        super(ConsoleListener, self).__init__(config)
        self.closed = None
        self.output_fmt = {
            'currents': ['uts', 'value'],
            'sync': ['sys_uts', 'log_uts', 'app', 'tag', 'message'],
            'event': ['sys_uts', 'log_uts', 'app', 'tag', 'message'],
            'metric': ['sys_uts', 'log_uts', 'app', 'tag', 'value'],
            'fragment': ['sys_uts', 'log_uts', 'app', 'tag', 'message'],
            'unknown': ['sys_uts', 'message']
        }

    def get_info(self):
        """ mock """
        pass

    def put(self, df, type_):
        """ Process data

        Args:
            df (pandas.DataFrame): dfs w/ data contents,
                differs for each data type.
                Should be processed differently from each other
            type_ (string): dataframe type
        """
        if not self.closed:
            logger.info("Data type: %s", type_)
            logger.info("\n%s\n", df.describe())

    def close(self):
        self.closed = True
