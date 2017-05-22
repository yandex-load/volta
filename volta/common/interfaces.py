class VoltaBox(object):
    """
    Volta box interface
    Parent class for volta boxes
    """
    def __init__(self, config):
        """
        Creates and configures hardware box

        Parameters
        ----------
            config : dict
                module configuration
        """
        pass

    def start_test(self, results):
        """
        Grab stage

        Parameters
        ----------
            results : queue-like object, should be able to answer to put()/get_nowait()/get()
                queue for results, VoltaBox should put there dataframes w/ columns: ['uts', 'value']
        """
        raise NotImplementedError("Abstract method needs to be overridden")

    def end_test(self):
        """ end test """
        raise NotImplementedError("Abstract method needs to be overridden")


class Phone(object):
    """
    Phone interface
    Parent class for phones
    """
    def __init__(self, config):
        """
        Creates and configures phone

        Parameters
        ----------
            config : dict
                module configuration
        """
        pass

    def prepare(self):
        """
        Phone preparements:
            install apps, unplug device """
        raise NotImplementedError("Abstract method needs to be overridden")

    def start(self, results):
        """
        Grab stage: starts log reader, make sync w/ flashlight

        Parameters
        ----------
            results : queue-like object, should be able to answer to put()/get_nowait()/get()
                queue for results, Phone should put there dataframes w/ columns: ['sys_uts', 'message']
        """
        raise NotImplementedError("Abstract method needs to be overridden")

    def run_test(self):
        """
        App stage: run app/phone tests
        """
        raise NotImplementedError("Abstract method needs to be overridden")

    def end(self):
        """
        Stop grab stage
        """
        raise NotImplementedError("Abstract method needs to be overridden")


class DataListener(object):
    """
    Listener interface
    """

    def __init__(self, config):
        """
        Configures data listeners

        Parameters
        ----------
            config : dict
                module configuration information, differs for each type of listener
        """
        pass

    def put(self, data, type):
        """
        Process data

        Parameters
        ----------
            data : pandas.DataFrame
                dataframes w/ data contents, differs for each data type. Should be processed differently from each other
            type : basestring
                dataframe type
        """
        raise NotImplementedError("Abstract method needs to be overridden")

    def close(self):
        """
        Close listeners
        """
        raise NotImplementedError("Abstract method needs to be overridden")
