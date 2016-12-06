# -*- coding: utf-8 -*-

import os
import datetime
import requests
import csv
import pandas as pd
import logging
import numpy as np
import argparse

from pkg_resources import resource_filename


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
    df = pd.DataFrame(
        np.fromfile(
            fname,
            dtype=np.uint16
        ).astype(np.float32) * (3300 / 2**12)
    )
    #df = pd.read_csv(fname, delimiter=' ', names="ts curr".split())
    start = datetime.datetime.utcfromtimestamp(volta_start)
    logging.info('start: %s', start)
    index = pd.date_range(start, periods=len(df), freq='L')
    series = pd.Series(df[0].values, index=index)
    values = []
    for key, value in series.iteritems():
        dt = key.strftime("%Y-%m-%d %H:%M:%S.%f")
        ts = int((datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M:%S.%f") - datetime.datetime(1970,1,1)).total_seconds() * 10000 )
        values.append([date, test_id, ts, value])
    return values

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
        logging.info('Lunapark create job status: %s. \n Answer: %s', lunapark_req.status_code, lunapark_req.text)
        answ = lunapark_req.json()
        logging.info('https://lunapark.yandex-team.ru/mobile/%s', answ['jobno'])
        job_url = 'https://lunapark.yandex-team.ru/mobile/{jobno}'.format(jobno=answ['jobno'])
    except Exception as exc:
        logging.error('Lunapark create job exception: %s', exc, exc_info=True)
        return None
    return job_url

def main():
    logging.basicConfig(
        level="DEBUG",
        format='%(asctime)s [%(levelname)s] [uploader logging] %(filename)s:%(lineno)d %(message)s'
    )
    parser = argparse.ArgumentParser(
        description='upload data to lunapark.')
    parser.add_argument(
        '-f', '--filename',
        help='path to binary file w/ volta output')
    args = parser.parse_args()
    test_id = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    volta_start = (datetime.datetime.now() - datetime.datetime(1970, 1, 1)).total_seconds()
    current_data = FormatCurrent(args.filename, volta_start, date, test_id)
    task = 'LOAD-272'
    jobid = CreateJob(test_id, task)
    output_current = 'current_'+test_id+".data"
    WriteListToCSV(output_current, current_data)

    with open(output_current, 'r') as outfile:
        data = outfile.read()
        url = "{url}{query}".format(
            url="http://volta-backend-test.haze.yandex.net:8123/?query=",
            query="INSERT INTO volta.current FORMAT CSV"
        )
        r = requests.post(url, data=data)
        logging.info('Upload current to clickhouse status: %s. \n Answer: %s', r.status_code, r.text)
        logging.info('URL: %s', jobid)
        return jobid

if __name__ == "__main__":
    main()
