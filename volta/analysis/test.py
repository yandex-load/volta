# -*- coding: utf-8 -*-

import datetime
import csv
import requests
import pandas as pd
import logging
import numpy as np
import argparse
import json
import re
import sys

from volta.analysis.sync import sync, torch_status

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


logger = logging.getLogger(__name__)

class EventsWorker(object):
    def __init__(self, fname, date, test_id):
        self.filename = fname
        self.date = date
        self.test_id = test_id
        self.output_file = 'events_{test_id}.data'.format(test_id=test_id)
        self.backend = ('http://volta-backend-test.haze.yandex.net:8123', 'volta.logs')

    def FormatEvents(self):
        """
        lists of events data

        Returns:
            list of values w/ lists inside, format: [today, test_id, ts, message]
        """
        logger.info('Started formatting events')
        with open(self.filename) as eventlog:
            values = []
            # 12-14 13:32:31.239  3679  3679 I CameraService: onTorchStatusChangedLocked: Torch status changed for cameraId=0, newStatus=1
            # 12-14 13:32:31.239  3679  3679 I CameraService: onTorchStatusChangedLocked: Torch status changed for cameraId=0, newStatus=1
            RE = re.compile(r"""
                ^
                (\S+) # date
                \s+
                (\S+) # timestamp
                \s+
                \S+ # pid
                \s+
                \S+ # ppid
                \s+
                \S # priority level
                \s+
                (\S+) # tag
                \s+
                (.*?) # message
                $
            """, re.X)
            for event in eventlog.readlines():
                m = RE.match(event)
                if m:
                    date, ts, tag, message = m.groups()
                    if message.startswith('[tesla]'):
                        ts = datetime.datetime.fromtimestamp(float(message.split(" ")[1]))
                        message = " ".join(message.split(" ")[2:])
                    else:
                        # Android doesn't log `year` to logcat by default
                        ts_prepare = datetime.datetime.strptime(
                            "{year}-{date} {time}".format(
                                year=datetime.datetime.now().year,
                                date=event.split()[0],
                                time=event.split()[1]
                            ),
                            "%Y-%m-%d %H:%M:%S.%f"
                        )
                        ts = int(((ts_prepare - datetime.datetime(1970,1,1)).total_seconds()) * 10000 )
                    values.append([self.date, self.test_id, ts, message])
            return values

    def upload(self):
        with open(self.output_file, 'r') as outfile:
            data = outfile.read()
            url = "{url}{query}".format(
                url="{backend_url}/?query=".format(backend_url=self.backend[0]),
                query="INSERT INTO {backend_table} FORMAT CSV".format(backend_table=self.backend[1])
            )
            headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
            r = requests.post(url, data=data, headers=headers)
            logger.debug('Upload current to clickhouse status: %s. Message: %s', r.status_code, r.text, exc_info=True)
            r.raise_for_status()
            return



def ttest(args):
    test_id = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")
    date = datetime.datetime.now().strftime("%Y-%m-%d")
            
    events_worker = EventsWorker(args.get('events'), date, test_id)
    events_data = events_worker.FormatEvents()
    #WriteListToCSV(events_worker.output_file, events_data)
    #events_worker.upload()


def main():
    parser = argparse.ArgumentParser(
        description='upload data to lunapark.')
    parser.add_argument(
        '-f', '--filename',
        help='path to binary file w/ volta output')
    parser.add_argument(
        '-e', '--events',
        help='path to events logcat file')
    parser.add_argument(
        '-s', '--samplerate',
        help='samplerate',
        type=int,
        default=10000
    )
    parser.add_argument(
        '-k', '--slope',
        help='slope, electrical current metric multiplier, `k` in linear y=kx+b function',
        type=float,
        default=float(5000/2**12)
    )
    parser.add_argument(
        '-b', '--offset',
        help='y-offset, electrical current metric addend, `b` in linear y=kx+b function',
        type=float,
        default=0
    )
    parser.add_argument(
        '-m', '--meta',
        help='meta json',
        default=None
    )
    parser.add_argument(
        '-d', '--debug',
        help='enable debug logging',
        action='store_true')
    args = vars(parser.parse_args())
    ttest(args)

if __name__ == "__main__":
    main()
