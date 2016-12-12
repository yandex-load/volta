# -*- coding: utf-8 -*-

import tornado.web
import os
import datetime
import requests
import csv
import pandas as pd
import logging

from pkg_resources import resource_filename


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


def FormatEvents(events, today, test_id):
    """
    lists of events data

    Args:
        events: android log w/ events (flash on/off etc)
        today: today date, string
        test_id: volta test id, string

    Returns:
        list of values w/ lists inside, format: [today, test_id, ts, message]
    """
    logging.info('Started formatting events')
    with open(events) as eventlog:
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
            values.append([today, test_id, ts, message])
        return values


def FormatCurrent(fname, volta_start, date, test_id):
    """
    lists of currents data

    Args:
        fname: electrical current measurement csv file
        volta_start: start, counted by sync point w/ cross-correlation
        date: today date, string
        test_id: volta test id, string

    Returns:
        list of values w/ lists inside, format: [today, test_id, ts, message]
    """

    logging.info('Started formatting currents')

    df = pd.read_csv(fname, delimiter=' ', names="ts curr".split())
    start = datetime.datetime.utcfromtimestamp(volta_start)
    logging.info('Volta start: %s', start)
    index = pd.date_range(start, periods=len(df['curr']), freq='2ms')
    series = pd.Series(df['curr'].values, index=index)

    values = []
    for key, value in series.iteritems():
        dt = key.strftime("%Y-%m-%d %H:%M:%S.%f")
        ts = int((datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S.%f") - datetime.datetime(1970,1,1)).total_seconds() * 10000 )
        values.append([date, test_id, ts, value])
    return values


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
        logging.info('Lunapark create job status: %s. \n Answer: %s', lunapark_req.status_code, lunapark_req.text)
        answ = lunapark_req.json()
        logging.info('https://lunapark.yandex-team.ru/mobile/%s', answ['jobno'])
        job_url = 'https://lunapark.yandex-team.ru/mobile/{jobno}'.format(jobno=answ['jobno'])
    except Exception as exc:
        logging.error('Lunapark create job exception: %s', exc, exc_info=True)
        return None
    return job_url


class LogcatMerger(tornado.web.RequestHandler):
    def get(self):
        """
        Helper page for logcat merger w/ list of available events/logs

        Returns:
            template w/ list of logs/events
        """
        logs = os.listdir('logs')
        log_files = ['logs/{filename}'.format(filename=filename) for filename in logs if filename.endswith('log')]

        events = os.listdir('events')
        event_files = ['events/{filename}'.format(filename=filename) for filename in events if filename.endswith('log')]

        self.render(
            resource_filename(__name__, 'merger.html'),
            title="Log merger",
            logs=log_files,
            events=event_files
        )

    def post(self):
        """
        Sync android and electrical current measurements logs and upload data to lunapark

        Returns:
            url to test
        """
        year = datetime.datetime.now().strftime("%Y")
        test_id = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")
        date = datetime.datetime.now().strftime("%Y-%m-%d")
    
        log = self.get_body_argument('log')
        events = self.get_body_argument('events')
        samplerate = float(self.get_body_argument('samplerate'))
        task = self.get_body_argument('task')

        logging.info('Incoming log fname: %s', log)
        logging.info('Incoming events fname: %s', events)

        sync_point = sync(
            pd.read_csv(log, delimiter=' ', names="ts curr".split())["curr"],
            events,
            sps=samplerate,
            first=10000,
            trailing_zeros=1000,
        )
        logging.debug('Sync point: %s', sync_point)

        message = None
        with open(events) as eventlog:
            for line in eventlog.readlines():
                if "newStatus=2" in line:
                    message = line
                    break

        if message:
            syncflash = datetime.datetime.strptime(' '.join(message.split(' ')[:2]), "%m-%d %H:%M:%S.%f").replace(year=2016)
            syncflash_unix = (syncflash - datetime.datetime(1970,1,1)).total_seconds()
        else:
            self.write('Unable to find appropriate flashlight messages in android log to synchronize')
            return
        
        logging.debug('Syncflash_unix: %s', syncflash_unix)

        volta_start = syncflash_unix - sync_point/samplerate

        # format data to desired
        events_data = FormatEvents(events, date, test_id)
        current_data = FormatCurrent(log, volta_start, date, test_id)

        jobid = CreateJob(test_id, task)

        output_events = 'events/events_'+test_id+".data"
        WriteListToCSV(output_events, events_data)
        with open(output_events, 'r') as outfile:
            data = outfile.read()
            url = "{url}{query}".format(
                url="http://volta-backend-test.haze.yandex.net:8123/?query=",
                query="INSERT INTO volta.logs FORMAT CSV"
            )
            r = requests.post(url, data=data)
            logging.info('Upload events to clickhouse status: %s. \n Answer: %s', r.status_code, r.text)
    
        output_current = 'logs/current_'+test_id+".data"
        WriteListToCSV(output_current, current_data)
        with open(output_current, 'r') as outfile:
            data = outfile.read()
            url = "{url}{query}".format(
                url="http://volta-backend-test.haze.yandex.net:8123/?query=",
                query="INSERT INTO volta.current FORMAT CSV"
            )
            r = requests.post(url, data=data)
            logging.info('Upload current to clickhouse status: %s. \n Answer: %s', r.status_code, r.text)

        url_for_return = "<html>" \
                         "<meta http-equiv='refresh' content=\"0;{redir_url}\" />" \
                         "<p><a href='{id}'>redirect</a></p>" \
                         "</html>".format(id=jobid, redir_url=jobid)
        self.write(url_for_return)
