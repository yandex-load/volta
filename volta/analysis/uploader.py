# -*- coding: utf-8 -*-

import datetime
import csv
import requests
import pandas as pd
import logging
import numpy as np
import argparse

from sync import sync, torch_status

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

def CreateJob(test_id, task='LOAD-272'):
    """
    creates job in lunapark, uploading metadata

    Args:
        test_id: volta test id, str
        task: lunapark task id, str

    Returns:

    """
    try:
        url = "https://lunapark.yandex-team.ru/mobile/create_job.json"
        data = {
            'task': task,
            'test_id': test_id
        }
        lunapark_req = requests.post(url, data=data, verify=False)
        logging.debug('Lunapark create job status: %s', lunapark_req.status_code)
        answ = lunapark_req.json()
        job_url = 'https://lunapark.yandex-team.ru/mobile/{jobno}'.format(jobno=answ['jobno'])
    except Exception as exc:
        logging.error('Lunapark create job exception: %s', exc, exc_info=True)
        return None
    return job_url




class CurrentsWorker(object):
    def __init__(self, fname, sync, date, test_id):
        self.filename = fname
        self.sync = sync
        self.date = date
        self.test_id = test_id
        self.output_file = 'current_{test_id}.data'.format(test_id=test_id)
        self.backend = ('http://volta-backend-test.haze.yandex.net:8123', 'volta.current')

    def FormatCurrent(self):
        """
        lists of currents data

        Returns:
            list of values w/ lists inside, format: [today, test_id, ts, message]
        """
        logging.info('Started formatting currents')
        df = pd.DataFrame(
            np.fromfile(
                self.filename,
                dtype=np.uint16
            ).astype(np.float32) * (3300 / 2**12)
        )
        start = datetime.datetime.utcfromtimestamp(self.sync)
        index = pd.date_range(start, periods=len(df), freq='L')
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
            logging.debug('Upload current to clickhouse status: %s. Message: %s', r.status_code, r.text, exc_info=True)
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
        logging.info('Started formatting events')
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
                        year=datetime.datetime.now().strftime("%Y"),
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
            r = requests.post(url, data=data)
            logging.debug('Upload current to clickhouse status: %s. Message: %s', r.status_code, r.text, exc_info=True)
            r.raise_for_status()
            return


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
        default=10000
    )
    parser.add_argument(
        '-d', '--debug',
        help='enable debug logging',
        action='store_true')
    args = parser.parse_args()
    logging.basicConfig(
        level="DEBUG" if args.debug else "INFO",
        format='%(asctime)s [%(levelname)s] [UPLOADER] %(filename)s:%(lineno)d %(message)s'
    )
    logger.info('Uploader started.')
    test_id = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    if not args.filename:
        raise ValueError('Unable to run without electrical current measurements file. `-f option`')
    if args.events:
        df = pd.DataFrame(np.fromfile(args.filename, dtype=np.uint16).astype(np.float32) * (3300 / 2**12))
        sync_sample = sync(
            df,
            args.events,
            sps=args.samplerate,
            first=300000,
            trailing_zeros=1000,
        )
        message = None
        with open(args.events) as eventlog:
            for line in eventlog.readlines():
                if "newStatus=2" in line:
                    message = line
                    break

        if message:
            syncflash = datetime.datetime.strptime(
                ' '.join(message.split(' ')[:2]), "%m-%d %H:%M:%S.%f"
            ).replace(year=datetime.datetime.stpftime("%Y"))
            syncflash_unix = (syncflash - datetime.datetime(1970,1,1)).total_seconds()
        else:
            raise Exception('Unable to find appropriate flashlight messages in android log to synchronize')
        sync_point = syncflash_unix - sync_sample/args.samplerate
        logger.info('sync_point found: %s', sync_point)
    else:
        sync_point = (datetime.datetime.now() - datetime.datetime(1970, 1, 1)).total_seconds()
        logger.info('sync_point is datetime.now(): %s', sync_point)

    jobid = CreateJob(test_id, 'LOAD-272')

    # make and upload currents
    current_worker = CurrentsWorker(args.filename, sync_point, date, test_id)
    current_data = current_worker.FormatCurrent()
    WriteListToCSV(current_worker.output_file, current_data)
    current_worker.upload()

    # make and upload events
    if args.events:
        events_worker = EventsWorker(args.events, date, test_id)
        events_data = events_worker.FormatEvents()
        WriteListToCSV(events_worker.output_file, events_data)
        events_worker.upload()

    logging.info('Lunapark url: %s', jobid)


if __name__ == "__main__":
    main()
