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
import os

from volta.analysis.sync import sync, torch_status

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


logger = logging.getLogger(__name__)


env = {
    "front": "https://lunapark.yandex-team.ru",
    "backend": "https://lunapark.yandex-team.ru",
    # "front": "https://lunapark.test.yandex-team.ru",
    # "backend": "https://lunapark.test.yandex-team.ru"
}


def create_work_dirs():
    work_dirs = {
        'plots' : 'plots',
        'logs' : 'logs',
        'events': 'events',
    }
    for key, dirname in work_dirs.iteritems():
        try:
            os.stat(dirname)
        except:
            logging.debug('Directory %s not found, trying to create it', dirname)
            os.mkdir(dirname)
    return


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
        print "I/O error({0}): {1} > {2}".format(exc.errno, exc.strerror, csv_file)
        # print ("I/O error:" % exc) -- crash if no "log" folder found
    return


def CreateJob(test_id, job_config):
    """
    creates job in lunapark, uploading metadata

    Args:
        test_id: volta test id, str
        task: lunapark task id, str
        meta: meta json
    Returns:

    """
    try:
        # FIXME params w/ refactoring here!
        url = "{url}{path}".format(url=env['front'], path="/mobile/create_job.json")
        data = {}
        logger.debug('job_config: %s', job_config)
        if job_config:
            for key in job_config:
                try:
                    data[str(key)] = job_config[key].encode('utf-8')
                except AttributeError:
                    logger.warning('Unable to decode value while create lunapark job: %s', key)
        data['test_id'] = test_id
        if not data.get('task', None):
            data['task'] = 'LOAD-272' # default task id
        lunapark_req = requests.post(url, data=data, verify=False)
        logger.debug('Lunapark create job status: %s', lunapark_req.status_code)
        logger.debug('Data: %s', data)
        answ = lunapark_req.json()
        logger.debug(answ)
        job_url = "{url}{path}{jobno}".format(url=env['front'], path="/mobile/", jobno=answ['jobno'])
        try:
            with open('jobno.log', 'w') as jobno:
                jobno.write(job_url)
        except:
            logger.warning('Unable to dump jobno', exc_info=True)
    except Exception as exc:
        logger.error('Lunapark create job exception: %s', exc, exc_info=True)
        return None
    return job_url




class CurrentsWorker(object):
    def __init__(self, args, sync, date, test_id):
        self.filename = args.get('filename')
        self.sync = sync
        self.date = date
        self.test_id = test_id
        self.output_file = 'logs/current_{test_id}.data'.format(test_id=test_id)
        self.backend = ("{url}{path}".format(url=env['backend'], path="/api/volta"), "volta.current")
        self.samplerate = args.get('samplerate')
        self.slope = args.get('slope')
        self.offset = args.get('offset')
        self.binary = args.get('binary')

    def FormatCurrent(self):
        """
        lists of currents data

        Returns:
            list of values w/ lists inside, format: [today, test_id, ts, message]
        """
        logger.info('Started formatting currents')
        reader = FileReader(self.filename, self.slope, self.offset)
        if self.binary:
            df = reader.binary_to_df()
        else:
            df = reader.plaintext_to_df()
        start = datetime.datetime.utcfromtimestamp(self.sync)
        index_freq = "{value}{units}".format(
            value = int(10 ** 6 / self.samplerate),
            units = "us"
        )
        logger.debug('Index freq: %s', index_freq)
        index = pd.date_range(start, periods=len(df), freq=index_freq)
        series = pd.Series(df.values, index=index)
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
            r = requests.post(url, data=data, verify=False)
            logger.debug('Upload current to clickhouse status: %s. Message: %s', r.status_code, r.text, exc_info=True)
            r.raise_for_status()
            return


class EventsWorker(object):
    def __init__(self, fname, sync_point, date, test_id, fragment_start, fragment_stop):
        self.filename = fname
        self.date = date
        self.sync = sync_point
        self.test_id = test_id
        self.fragment_start = fragment_start
        self.fragment_stop = fragment_stop
        self.fragments = []
        self.output_file = 'logs/events_{test_id}.data'.format(test_id=test_id)
        self.fragments_output_file = 'logs/fragments_{test_id}.data'.format(test_id=test_id)
        self.backend = ("{url}{path}".format(url=env['backend'], path="/api/volta"), "volta.logs")
        self.custom_ts = None

    def setCustomTimestamp(self, ts):
        self.custom_ts = ts

    def FormatEvents(self):
        """
        lists of events data

        Returns:
            list of values w/ lists inside, format: [today, test_id, ts, message]
        """
        logger.info('Started formatting events')
        values = []
        self.fragments = []
        if self.fragment_start and self.fragment_stop:
            fr_start = re.compile(self.fragment_start, re.X)
            fr_stop = re.compile(self.fragment_stop, re.X)
        for data in find_event_messages(self.filename):
            date, ts, tag, message, event = data
            if message.startswith('[volta]') and self.custom_ts is not None:
                m = re.match(r"\[volta\]\s+(?P<event_ts>\S+)\s+(?P<custom_message>flash_ON.*?)", message)
                if m:
                    custom_data = m.groupdict()
                    event_custom_ts = int(custom_data['event_ts'])/10**9.
                    logger.debug('Event custom ts: %s', event_custom_ts)
                    event_ts = self.sync + (float(event_custom_ts) - float(self.custom_ts))
                    logger.debug('Event synced ts: %s', event_ts)
            else:
                # Android doesn't log `year` to logcat by default
                ts_prepare = datetime.datetime.strptime(
                    "{year}-{date} {time}".format(
                        year=datetime.datetime.now().year,
                        date=date,
                        time=ts
                    ),
                    "%Y-%m-%d %H:%M:%S.%f"
                )
            ts = int(((ts_prepare - datetime.datetime(1970,1,1)).total_seconds()) * 10000 )
            if self.fragment_start and self.fragment_stop:
                match_start = fr_start.match(event)
                if match_start:
                    name = match_start.group('name').strip()
                    if name:
                        self.fragments.append([name, ts])
                        values.append([self.date, self.test_id, ts, name, "fragment_start"])
                match_stop = fr_stop.match(event)
                if match_stop:
                    name = match_stop.group('name').strip()
                    if name and self.fragments[-1][0]==name:
                        self.fragments[-1].append(ts)
                        values.append([self.date, self.test_id, ts, name, "fragment_end"])
            values.append([self.date, self.test_id, ts, "{tag} {message}".format(tag=tag, message=message), "log_event"])
        return values

    def upload(self):
        with open(self.output_file, 'r') as outfile:
            data = outfile.read()
            url = "{url}{query}".format(
                url="{backend_url}/?query=".format(backend_url=self.backend[0]),
                query="INSERT INTO {backend_table} FORMAT CSV".format(backend_table=self.backend[1])
            )
            headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
            r = requests.post(url, data=data, headers=headers, verify=False)
            logger.debug('Upload current to clickhouse status: %s. Message: %s', r.status_code, r.text, exc_info=True)
            r.raise_for_status()
            return


class FileReader(object):
    def __init__(self, fname, slope, offset):
        self.filename = fname
        self.slope = slope
        self.offset = offset

    def binary_to_df(self):
        df = pd.DataFrame(
            np.fromfile(
                self.filename,
                dtype=np.uint16
            ).astype(np.float32) * self.slope + self.offset
        )
        return df[0][256:]

    def plaintext_to_df(self):
        df = pd.read_csv(
            self.filename,
            names=['curr']
        ) * self.slope + self.offset
        return df.curr


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
        '-d', '--debug',
        help='enable debug logging',
        action='store_true')
    parser.add_argument(
        '-w', '--binary',
        help='enable binary input log format',
        action='store_true')
    parser.add_argument(
        '-c', '--custom',
        help='enable custom events format',
        action='store_true',
        default=False)
    parser.add_argument(
        '-t', '--task',
        help='lunapark task id',
        default=None)
    parser.add_argument(
        '-u', '--fragment-start',
        help='fragment start regular expression - ^.*TestRunner:\sstarted:\s(?P<name>.*)$',
        default=None)
    parser.add_argument(
        '-v', '--fragment-stop',
        help='fragment stop regular expression - ^.*TestRunner:\sfinished:\s(?P<name>.*)$',
        default=None)
    args = vars(parser.parse_args())
    main(args)


def find_event_messages(log):
    RE = re.compile(r"""^(?P<Time>(?P<Time_dm>\S+)\s+(?P<Time_time>\S+)\s+(?P<Time_tag>(\S+?)\s*\(\s*\d+\)):\s+(?P<Time_msg>.*))$|^(?P<Threadtime>(?P<Threadtime_dm>\S+)\s+(?P<Threadtime_time>\S+)\s+(?P<Threadtime_tag>(.+?))\:\s+(?P<Threadtime_msg>.*))$""", re.X)
    with open(log,'r') as eventlog:
        for event in eventlog.readlines():
            match = RE.match(event)
            if match:
                #date, ts, tag, message = match.groups(0)
                #yield (date, ts, tag, message)

                #logger.debug(event)
                #logger.debug(match)
                if match.group('Time'):
                    date = match.group('Time_dm')
                    ts = match.group('Time_time')
                    tag = match.group('Time_tag')
                    message = match.group('Time_msg')
                    yield (date, ts, tag, message, event)
                elif match.group('Threadtime'):
                    date = match.group('Threadtime_dm')
                    ts = match.group('Threadtime_time')
                    tag = match.group('Threadtime_tag')
                    message = match.group('Threadtime_msg')
                    yield (date, ts, tag, message, event)


def main(args):
    logging.basicConfig(
        level="DEBUG" if args.get('debug') else "INFO",
        format='%(asctime)s [%(levelname)s] [uploader] %(filename)s:%(lineno)d %(message)s'
    )
    logger.debug('Args: %s', args)
    logger.info('Uploader started.')

    create_work_dirs()
    test_id = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")
    date = datetime.datetime.now().strftime("%Y-%m-%d")

    # FIXME please refactor option/job_config configuration below
    job_config = args.get('job_config', None)
    if args.get('task', None):
        if not job_config:
            job_config = {}
        job_config['task'] = args.get('task')

    if not args.get('filename'):
        raise ValueError('Unable to run without electrical current measurements file. `-f option`')

    # events log specified, so we trying to find sync point
    if args.get('events'):
        # find sync sample in electrical currents log
        reader = FileReader(args.get('filename'), args.get('slope'), args.get('offset'))
        # volta binary format, uint16
        if args.get('binary'):
            df = reader.binary_to_df()
            logger.debug('Read dataframe: \n%s', df)
        # volta plaintext [old-style 500Hz compatibility]
        else:
            df = reader.plaintext_to_df()
            logger.debug('Read dataframe: \n%s', df)

        # sync
        sync_sample = sync(
            df,
            args.get('events'),
            sps=args.get('samplerate'),
            first=args.get('samplerate')*20,
        )

        # find first flashlight message in events log
        syncflash = None
        for data in find_event_messages(args.get('events')):
            dt, ts, tag, message, event = data
            if "newStatus=2" in message:
                syncflash = datetime.datetime.strptime(
                    "{year}-{date} {time}".format(
                        year=datetime.datetime.now().year,
                        date=dt,
                        time=ts
                   ),
                    "%Y-%m-%d %H:%M:%S.%f"
                )
                break

        if not syncflash:
            raise ValueError('Unable to find appropriate flashlight messages in android log to synchronize')

        syncflash_unix = (syncflash - datetime.datetime(1970,1,1)).total_seconds()
        sync_point = syncflash_unix - float(sync_sample)/args.get('samplerate')
        logger.info('sync_point found: %s', sync_point)

    # no events log specified, so we take timestamp.now() as syncpoint
    else:
        sync_point = (datetime.datetime.now() - datetime.datetime(1970, 1, 1)).total_seconds()
        logger.info('sync_point is datetime.now(): %s', sync_point)

    # create lunapark job
    jobid = CreateJob(test_id, job_config)

    # reformat and upload currents
    current_worker = CurrentsWorker(args, sync_point, date, test_id)
    current_data = current_worker.FormatCurrent()
    WriteListToCSV(current_worker.output_file, current_data)
    current_worker.upload()

    # make and upload events
    if args.get('events'):
        events_worker = EventsWorker(args.get('events'), sync_point, date, test_id, args.get('fragment_start'), args.get('fragment_stop'))

        # find custom first sync flashlight
        if args.get('custom'):
            for data in find_event_messages(args.get('events')):
                dt, ts, tag, message, event = data
                if message.startswith('[volta]'):
                    m = re.match(r"\[volta\]\s+(?P<custom_ts>\S+)\s+(?P<custom_message>flash_ON.*?)", message)
                    if m:
                        custom_data = m.groupdict()
                        events_worker.setCustomTimestamp(custom_data['custom_ts'])
                        logger.debug('custom data: %s', custom_data)
                        break

        events_data = events_worker.FormatEvents()
        WriteListToCSV(events_worker.output_file, events_data)
        if events_worker.fragments:
            WriteListToCSV(events_worker.fragments_output_file, events_worker.fragments)
        events_worker.upload()

    logger.info('Lunapark url: %s', jobid)
    return jobid


if __name__ == "__main__":
    run()

