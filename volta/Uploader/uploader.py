import logging
import requests
import datetime
import uuid

from volta.common.interfaces import DataListener

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


logger = logging.getLogger(__name__)


class DataUploader(DataListener):
    """
    Uploads data to clickhouse
    have non-interface private method __upload_meta() for meta information upload
    """
    def __init__(self, config):
        super(DataUploader, self).__init__(config)
        self.addr = config.get('address', 'https://lunapark.test.yandex-team.ru/api/volta')
        self.test_id = config.get('test_id', "{uuid}".format(uuid=uuid.uuid4().hex))
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

    def put(self, data, type):
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

    def __upload_meta(self, data):
        # TODO
        pass

    def close(self):
        pass