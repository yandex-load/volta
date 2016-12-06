import tornado.web
import subprocess
import datetime
import logging
import os
import serial
import sys
import glob

import time

from pkg_resources import resource_filename



class Recorder(tornado.web.RequestHandler):
    def get(self):
        """ Helper page allows to enter some args for file recording

        Returns:
            record template w/ list of available devices
        """
        arduino_devs = []
        if sys.platform.startswith('win'):
            ports = ['COM%s' % (i + 1) for i in range(256)]
            for port in ports:
                try:
                    s = serial.Serial(port)
                    s.close()
                    arduino_devs.append(port)
                except (OSError, serial.SerialException):
                    pass
        elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin') or sys.platform.startswith('darwin'):
            ports = glob.glob('/dev/cu.[A-Za-z]*')
            # FIXME : maybe some intelligent logic here?
            for port in ports:
                if not 'Bluetooth' in port:
                    arduino_devs.append(port)
        else:
            raise EnvironmentError('Unsupported platform')
        # FIXME : enter total seconds, not total amount of samples
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

        self.render(
            resource_filename(__name__, 'result.html'),
            title="Results",
            data=None,
            message="Done. Logfile name: %s" % logfile
        )
