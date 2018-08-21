import os
import datetime
import uuid
import pwd
import sys


DYNAMIC_OPTIONS = {
    'pid': lambda: os.getpid(),
    'cmdline': lambda: ' '.join(sys.argv),
    'test_id': lambda: 'job_{uuid}'.format(uuid=uuid.uuid4()),
    'key_date': lambda: datetime.datetime.now().strftime("%Y-%m-%d"),
    'operator': lambda: pwd.getpwuid(os.geteuid())[0]
}