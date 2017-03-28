class VoltaBox(object):
    """ Volta box interface
    Parent class for volta boxes
    """
    def __init__(self, config):
        """ parse config stage """
        pass

    def start_test(self):
        """ Grab stage """
        raise NotImplementedError("Abstract method needs to be overridden")

    def end_test(self):
        """ end test """
        raise NotImplementedError("Abstract method needs to be overridden")

    def add_sink(self, queue):
        """ add listener """
        raise NotImplementedError("Abstract method needs to be overridden")
