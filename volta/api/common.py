"""
Commands from HTTP Server (from manager_queue):
    Run the test:
        {
        'session': '1a2b4f3c'
        'cmd':'run',
        'test': --- only when creating new session
        'config': --- only when creating new  session
        }
    Stop the test
        {
        'session': '1a2b4f3c'
        'cmd':'stop'
        }


Status reported by test (from manager_queue):
    {
     'session': '1a2b4f3c'
     'test': 'DEATHSTAR-10-12345'
     'status': 'running'|'success'|'failure'
     'current_stage': --- current stage (from test_stage_order)
     'failures': --- [ {'stage': stage-at-which-failed,'reason': reason of failure },
                       {'stage':stage-of-next-failure,'reason':...},
                       ... ]
     }
=====

Status reported to HTTP Server (into webserver_queue):
    {
    'session': '1a2b4f3c'
    'test': 'DEATHSTAR-10-12345'
    'status': 'running'|'success'|'failed' (from tank or from  manager)
               running: the tank is running
               success: tank has exited and no failures occured
               failed: tank has exited and there were failures

    'stage': --- optional, from tank only.
                 This is the last stage that was executed.
    'reason' : --- optional (from manager)
    'failures': --- optional, from tank only
    }
"""

TEST_STAGE_ORDER = ['configure', 'start_test', 'end_test', 'post_process']
TEST_STAGE_ORDER_AND_DEPS = [('configure', set()), ('start_test', 'configure'),
                             ('end_test', 'start_test'), ('post_process', 'end_test')]
TEST_STAGE_DEPS = {stage: dep for stage, dep in TEST_STAGE_ORDER_AND_DEPS}
