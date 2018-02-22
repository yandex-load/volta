class VoltaBox(object):
    """ Volta box interface - parent class for volta boxes """
    def __init__(self, config):
        """
        Args:
            config (VoltaConfig): module configuration data
        """
        self.config = config

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
    def __init__(self, config):
        """ Configure phone module """
        self.config = config

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

    def __init__(self, config):
        self.config = config

    def put(self, data, type_):
        """ Process data """
        raise NotImplementedError("Abstract method needs to be overridden")

    def close(self):
        """ Close listeners """
        raise NotImplementedError("Abstract method needs to be overridden")

    def get_info(self):
        raise NotImplementedError("Abstract method needs to be overridden")
