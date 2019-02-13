from netort.resource import manager as resource


class VoltaBox(object):
    """ Volta box interface - parent class for volta boxes """
    def __init__(self, config, core):
        """
        Args:
            self.config (VoltaConfig): module configuration data

        Attributes:
            self.source (string): path to data source, should be able to be opened by resource manager
                may be url, e.g. 'http://myhost.tld/path/to/file'
                may be device, e.g. '/dev/cu.wchusbserial1420'
                may be path to file, e.g. '/home/users/netort/path/to/file.data'
            self.chop_ratio (int): chop ratio for incoming data, 1 means 1 second (500 for sample_rate 500)
            self.grab_timeout (int): timeout for grabber
            self.sample_rate (int): volta box sample rate - depends on software and which type of volta box you use
            self.baud_rate (int): baud rate for device if device specified in source
        """
        self.core = core
        self.config = config
        self.pipeline = None
        self.grabber_q = None
        self.process_currents = None
        self.reader = None

        self.source = config.get_option('volta', 'source')
        self.chop_ratio = config.get_option('volta', 'chop_ratio')
        self.grab_timeout = config.get_option('volta', 'grab_timeout')
        self.slope = config.get_option('volta', 'slope')
        self.offset = config.get_option('volta', 'offset')
        self.precision = config.get_option('volta', 'precision')
        self.power_voltage = config.get_option('volta', 'power_voltage')
        self.sample_swap = config.get_option('volta', 'sample_swap', False)

        # initialize data source
        try:
            self.source_opener = resource.get_opener(self.source)
        except Exception:
            raise RuntimeError('Device %s not found. Please check VoltaBox USB connection', self.source)

    def start_test(self, results):
        """ Grab stage - starts grabber thread and puts data to results queue

        Args:
            results (queue-like object): VoltaBox should put there dataframes, format: ['uts', 'value']
        """
        raise NotImplementedError("Abstract method needs to be overridden")

    def end_test(self):
        """ end test """
        raise NotImplementedError("Abstract method needs to be overridden")

    def get_info(self):
        raise NotImplementedError("Abstract method needs to be overridden")


class Phone(object):
    """ Phone interface - parent class for phones """
    def __init__(self, config, core):
        """ Configure phone module """
        self.config = config
        self.core = core

    def prepare(self):
        """ Phone preparements stage: install apps etc """
        raise NotImplementedError("Abstract method needs to be overridden")

    def start(self, results):
        """ Grab stage: starts async log readers, run flashlight app """
        raise NotImplementedError("Abstract method needs to be overridden")

    def run_test(self):
        """ App stage: run app/phone tests """
        raise NotImplementedError("Abstract method needs to be overridden")

    def end(self):
        """ Stop test and grabbers """
        raise NotImplementedError("Abstract method needs to be overridden")

    def get_info(self):
        raise NotImplementedError("Abstract method needs to be overridden")


class DataListener(object):
    """ Listener interface

    Args:
        config (VoltaConfig): module configuration information, differs for each type of listener
    """

    def __init__(self, config, core):
        self.config = config
        self.core = core

    def put(self, incoming_df):
        """ Process data """
        raise NotImplementedError("Abstract method needs to be overridden")

    def close(self):
        """ Close listeners """
        raise NotImplementedError("Abstract method needs to be overridden")

    def get_info(self):
        raise NotImplementedError("Abstract method needs to be overridden")
