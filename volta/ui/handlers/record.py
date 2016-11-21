import tornado.web
import subprocess
import datetime
import logging
import os

from pkg_resources import resource_filename


class Recorder(tornado.web.RequestHandler):
    def get(self):
        """ Helper page allows to enter some args for file recording

        Returns:
            record template w/ list of available devices
        """
        devices = os.listdir('/dev')
        # any device endswith 'cu'
        # FIXME : find a better way to detect devices
        # FIXME : exclude bluetooth!
        # FIXME : enter total seconds, not total amount of samples
        arduino_devs = ['/dev/{device}'.format(device=device) for device in devices if device.startswith('cu')]
        self.render(
            resource_filename(__name__, 'record.html'),
            title="Recorder",
            devices=arduino_devs
        )

    def post(self):
        """ Records data from device

        Args:
            POST body argument 'samples'
            POST body argument 'device'
            POST body argument 'prefix'
        Returns:
            'ok' and logfilename
         """
        # FIXME: make a progressbar or some hack
        samples = self.get_body_argument('samples')
        device = self.get_body_argument('device')
        prefix = self.get_body_argument('prefix')

        cmd = "serial-reader -device=%s -samples=%s" % (device, samples)
        logfile = 'logs/%s%s.log' % (
                prefix,
                datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d_%H-%M-%S')
            )
        with open(logfile, "wb") as out:
            try:
                p = subprocess.Popen(
                    cmd,
                    stdout=out,
                    shell=True
                )
                p.communicate()
                p.wait()
            except Exception as exc:
                logging.error('Error trying to record samples', exc_info=True)
                return None
        self.write('Ok. Logfile: %s' % logfile)
