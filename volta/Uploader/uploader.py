import logging
import requests
import datetime

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


# system time is index everywhere
clickhouse_output_fmt = {
    'currents': ['key_date', 'test_id', 'uts', 'value'],
    'sync': ['key_date', 'test_id', 'sys_uts', 'log_uts', 'app', 'tag', 'message'],
    'event': ['key_date', 'test_id', 'sys_uts', 'log_uts', 'app', 'tag', 'message'],
    'metric': ['key_date', 'test_id', 'sys_uts', 'log_uts', 'app', 'tag', 'value'],
    'fragment': ['key_date', 'test_id', 'sys_uts', 'log_uts', 'app', 'tag', 'message'],
    'unknown': ['key_date', 'test_id', 'sys_uts', 'message']
}


logger = logging.getLogger(__name__)


class DataUploader(object):
    def __init__(self, config, id):
        self.addr = config.get('address', 'https://lunapark.test.yandex-team.ru/api/volta')
        self.test_id = id
        self.data_types_to_tables = {
            'currents': 'volta.currents',
            'sync': 'volta.syncs',
            'event': 'volta.events',
            'metric': 'volta.metrics',
            'fragment': 'volta.fragments',
            'unknown': 'volta.logentries'
        }
        self.key_date = datetime.datetime.now().strftime("%Y-%m-%d")

    def put(self, data, type):
        if type in self.data_types_to_tables:
            data.loc[:, ('key_date')] = self.key_date
            data.loc[:, ('test_id')] = self.test_id
            data = data.to_csv(sep='\t', header=False, index=False, columns=clickhouse_output_fmt.get(type, []))
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

    def close(self):
        pass