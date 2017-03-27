class VoltaBox(object):
    """ Volta box interface
    Parent class for all volta boxes
    """

    def __init__(self, core):
        self.core = core
        self.samplerate = None
        self.device = None
        self.output_file = None
        self.test_duration = None

    def configure(self, config=None):
        """     configure volta box, set baud rate and samplerate      """
        pass

    def grab(self):
        """     Grab stage      """
        raise NotImplementedError("Abstract method needs to be overridden")

