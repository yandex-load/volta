# -*- coding: utf-8 -*-

import datetime
import csv
import requests
import pandas as pd
import logging
import numpy as np
import argparse
import json
import sys

from volta.analysis.sync import sync, torch_status

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


logger = logging.getLogger(__name__)


def WriteListToCSV(csv_file, data_list):
    """
    Write contents of python list to CSV file row-by-row
    FIXME : python csv standart library unable to use unicode. Burn this logic, please!

    Args:
        csv_file: output csv filename
        data_list: python list w/ contents

    Returns:
        None
    """
    try:
        with open(csv_file, 'w') as csvfile:
            writer = csv.writer(csvfile, dialect='excel', quoting=csv.QUOTE_NONNUMERIC)
            for data in data_list:
                writer.writerow(data)
    except IOError as exc:
        print ("I/O error:" % exc)
    return

def CreateJob(test_id, meta, task='LOAD-272'):
    """
    creates job in lunapark, uploading metadata

    Args:
        test_id: volta test id, str
        task: lunapark task id, str
        meta: meta json
    Returns:

    """
    try:
        url = "https://lunapark.yandex-team.ru/mobile/create_job.json"
        if not meta:
            data = {
                'task': task,
                'test_id': test_id
            }
        else:
            data = {
                'task': task,
                'test_id': test_id,
                'device_id': meta['device_id'],
                'device_name': meta['device_name'],
                'device_os': meta['android_version'],
                'ver': meta['android_api_version'],
                'dsc': 'DeviceID: {device_id}. Device name: {device_name}. Device OS: {device_os}. Device API: {device_api}'.format(
                    device_id=meta['device_id'],
                    device_name=meta['device_name'],
                    device_os=meta['android_version'],
                    device_api=meta['android_api_version']
                ),
                'name': 'DeviceID: {device_id}. Device name: {device_name}. Device OS: {device_os}. Device API: {device_api}'.format(
                    device_id=meta['device_id'],
                    device_name=meta['device_name'],
                    device_os=meta['android_version'],
                    device_api=meta['android_api_version']
                )
            }
        lunapark_req = requests.post(url, data=data, verify=False)
        logger.debug('Lunapark create job status: %s', lunapark_req.status_code)
        answ = lunapark_req.json()
        job_url = 'https://lunapark.yandex-team.ru/mobile/{jobno}'.format(jobno=answ['jobno'])
    except Exception as exc:
        logger.error('Lunapark create job exception: %s', exc, exc_info=True)
        return None
    return job_url




class CurrentsWorker(object):
    def __init__(self, fname, sync, date, test_id, samplerate):
        self.filename = fname
        self.sync = sync
        self.date = date
        self.test_id = test_id
        self.output_file = 'current_{test_id}.data'.format(test_id=test_id)
        self.backend = ('http://volta-backend-test.haze.yandex.net:8123', 'volta.current')
        self.samplerate = int(samplerate)

    def FormatCurrent(self):
        """
        lists of currents data

        Returns:
            list of values w/ lists inside, format: [today, test_id, ts, message]
        """
        logger.info('Started formatting currents')
        df = pd.DataFrame(
            np.fromfile(
                self.filename,
                dtype=np.uint16
            ).astype(np.float32) * (float(5000) / 2**12)
        )
        start = datetime.datetime.utcfromtimestamp(self.sync)
        index_freq = "{value}{units}".format(
            value = int(1/float(self.samplerate) * 10 ** 6),
            units = "us"
        )
        index = pd.date_range(start, periods=len(df), freq=index_freq)
        series = pd.Series(df[0].values, index=index)
        values = []
        for key, value in series.iteritems():
            dt = key.strftime("%Y-%m-%d %H:%M:%S.%f")
            ts = int((datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S.%f") - datetime.datetime(1970,1,1)).total_seconds() * 10000 )
            values.append([self.date, self.test_id, ts, value])
        return values

    def upload(self):
        with open(self.output_file, 'r') as outfile:
            data = outfile.read()
            url = "{url}{query}".format(
                url="{backend_url}/?query=".format(backend_url=self.backend[0]),
                query="INSERT INTO {backend_table} FORMAT CSV".format(backend_table=self.backend[1])
            )
            r = requests.post(url, data=data)
            logger.debug('Upload current to clickhouse status: %s. Message: %s', r.status_code, r.text, exc_info=True)
            r.raise_for_status()
            return


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
            for event in eventlog.readlines():
                # filter trash
                if event.startswith("----"):
                    continue
                message = ' '.join(event.split()[5:])
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

def run():
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
        default=10000
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
    main(args)


def main(args):
    logging.basicConfig(
        level="DEBUG" if args.get('debug') else "INFO",
        format='%(asctime)s [%(levelname)s] [uploader] %(filename)s:%(lineno)d %(message)s'
    )
    logger.info('Uploader started.')
    test_id = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    if not args.get('filename'):
        raise ValueError('Unable to run without electrical current measurements file. `-f option`')
    if args.get('events'):
        df = pd.DataFrame(np.fromfile(args.get('filename'), dtype=np.uint16).astype(np.float32) * (float(5000) / 2**12))
        sync_sample = sync(
            df[0],
            args.get('events'),
            sps=int(args.get('samplerate')),
            first=int(args.get('samplerate')*15),
            trailing_zeros=1000,
        )
        message = None
        with open(args.get('events')) as eventlog:
            for line in eventlog.readlines():
                if "newStatus=2" in line:
                    message = line
                    break

        if message:
            syncflash = datetime.datetime.strptime(
                ' '.join(message.split(' ')[:2]), "%m-%d %H:%M:%S.%f"
            ).replace(year=datetime.datetime.now().year)
            syncflash_unix = (syncflash - datetime.datetime(1970,1,1)).total_seconds()
        else:
            raise Exception('Unable to find appropriate flashlight messages in android log to synchronize')
        sync_point = syncflash_unix - float(sync_sample)/int(args.get('samplerate'))
        logger.info('sync_point found: %s', sync_point)
    else:
        sync_point = (datetime.datetime.now() - datetime.datetime(1970, 1, 1)).total_seconds()
        logger.info('sync_point is datetime.now(): %s', sync_point)

    if args.get('meta'):
        with open(args.get('meta'), 'r') as jsn_fname:
            data = jsn_fname.read()
            meta = json.loads(data)
    else:
        meta = None
    jobid = CreateJob(test_id, meta, 'LOAD-272')

    # make and upload currents
    current_worker = CurrentsWorker(args.get('filename'), sync_point, date, test_id, args.get('samplerate'))
    current_data = current_worker.FormatCurrent()
    WriteListToCSV(current_worker.output_file, current_data)
    current_worker.upload()

    # make and upload events
    if args.get('events'):
        events_worker = EventsWorker(args.get('events'), date, test_id)
        events_data = events_worker.FormatEvents()
        WriteListToCSV(events_worker.output_file, events_data)
        events_worker.upload()

    logger.info('Lunapark url: %s', jobid)
    return jobid


if __name__ == "__main__":
    run()
