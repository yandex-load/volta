from volta.common.interfaces import DataListener


class FileListener(DataListener):
    """
    Saves data to file
    """

    def __init__(self, config):
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
        if not self.closed:
            if self.init_header:
                self.fname.write(str(self.file_output_fmt.get(type, [])))
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


