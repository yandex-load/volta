import json

from volta.common.interfaces import DataListener


class FileListener(DataListener):
    """
    Saves data to file

    Attributes:
        fname (string): path to file
        init_header (bool): write header to file
        output_separator (string): line-separator for output data
        file_output_fmt (dict): list of columns to store for each data type
    """

    def __init__(self, config):
        """
        Args:
            config (dict): config to listeners, config.fname should store a name of file
        """
        super(FileListener, self).__init__(config)
        self.fname = open(config.get('fname'), 'w')
        self.closed = None
        self.output_separator = '\t'
        self.init_header = True
        self.file_output_fmt = {
            'currents': ['uts', 'value'],
            'sync': ['sys_uts', 'log_uts', 'app', 'tag', 'message'],
            'event': ['sys_uts', 'log_uts', 'app', 'tag', 'message'],
            'metric': ['sys_uts', 'log_uts', 'app', 'tag', 'value'],
            'fragment': ['sys_uts', 'log_uts', 'app', 'tag', 'message'],
            'unknown': ['sys_uts', 'message']
        }


    def put(self, df, type):
        """ Process data

        Args:
            data (pandas.DataFrame): dfs w/ data contents,
                differs for each data type.
                Should be processed differently from each other
            type (string): dataframe type
        """
        if not self.closed:
            if self.init_header:
                types = df.dtypes.apply(lambda x: x.name).to_dict()
                header = json.dumps({'type': type, 'names': self.file_output_fmt.get(type), 'dtypes': types})
                self.fname.write(header)
                self.fname.write('\n')
                self.init_header = False
            data = df.to_csv(
                sep=self.output_separator,
                header=False,
                index=False,
                columns=self.file_output_fmt.get(type, [])
            )
            self.fname.write((data))
            self.fname.flush()

    def close(self):
        self.closed = True
        if self.fname:
            self.fname.close()


