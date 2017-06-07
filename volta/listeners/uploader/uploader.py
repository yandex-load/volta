import logging
import requests
import datetime
import uuid
import pwd
import os

from urlparse import urlparse
from volta.common.interfaces import DataListener

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


logger = logging.getLogger(__name__)


class DataUploader(DataListener):
    """ Uploads data to Clickhouse
    have non-interface private method __upload_meta() for meta information upload
    """
    def __init__(self, config):
        super(DataUploader, self).__init__(config)
        self.addr = config.get('address', 'https://lunapark.test.yandex-team.ru/api/volta')
        self.hostname = urlparse(self.addr).scheme+'://'+urlparse(self.addr).netloc
        self.test_id = config.get('test_id', "{date}_{uuid}".format(
            date=datetime.datetime.now().strftime("%Y-%m-%d"),
            uuid=uuid.uuid4().hex
        ))
        self.task = config.get('task')
        self.key_date = datetime.datetime.now().strftime("%Y-%m-%d")
        self.data_types_to_tables = {
            'currents': 'volta.currents',
            'sync': 'volta.syncs',
            'event': 'volta.events',
            'metric': 'volta.metrics',
            'fragment': 'volta.fragments',
            'unknown': 'volta.logentries'
        }
        self.clickhouse_output_fmt = {
            'currents': ['key_date', 'test_id', 'uts', 'value'],
            'sync': ['key_date', 'test_id', 'sys_uts', 'log_uts', 'app', 'tag', 'message'],
            'event': ['key_date', 'test_id', 'sys_uts', 'log_uts', 'app', 'tag', 'message'],
            'metric': ['key_date', 'test_id', 'sys_uts', 'log_uts', 'app', 'tag', 'value'],
            'fragment': ['key_date', 'test_id', 'sys_uts', 'log_uts', 'app', 'tag', 'message'],
            'unknown': ['key_date', 'test_id', 'sys_uts', 'message']
        }
        try:
            self.operator = config.get('operator', pwd.getpwuid(os.geteuid())[0])
        except:
            self.operator = 'alien'

    def put(self, data, type):
        """ Process data

        Args:
            data (pandas.DataFrame): dfs w/ data contents,
                differs for each data type.
                Should be processed differently from each other
            type (string): dataframe type
        """
        if type in self.data_types_to_tables:
            data.loc[:, ('key_date')] = self.key_date
            data.loc[:, ('test_id')] = self.test_id
            data = data.to_csv(
                sep='\t',
                header=False,
                index=False,
                columns=self.clickhouse_output_fmt.get(type, [])
            )
            url = "{addr}/?query={query}".format(
                addr=self.addr,
                query="INSERT INTO {table} FORMAT TSV".format(table=self.data_types_to_tables[type])
            )
            r = requests.post(url, data=data, verify=False)

            if r.status_code != 200:
                logger.warning('Request w/ status code not 200. Error message:\n%s', r.text)
            r.raise_for_status()
        else:
            logger.warning('Unknown data type for DataUplaoder: %s', exc_info=True)
            return

    def create_job(self, data):
        url = "{url}{path}".format(url=self.hostname, path="/mobile/create_job.json")
        req = requests.post(url, data=data, verify=False)
        logger.debug('Lunapark create job status: %s', req.status_code)
        logger.debug('Req data: %s\nAnsw data: %s', data, req.json())
        req.raise_for_status()
        logger.info('Lunapark test id: %s', req.json()['jobno'])
        return

    def update_job(self, data):
        url = "{url}{path}".format(url=self.hostname, path="/mobile/update_job.json")
        req = requests.post(url, data=data, verify=False)
        logger.debug('Lunapark create job status: %s', req.status_code)
        logger.debug('Req data: %s\nAnsw data: %s', data, req.json())
        req.raise_for_status()
        return


    def close(self):
        pass