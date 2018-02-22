import tornado.web
import tornado.ioloop
import logging
import json
import datetime
import os
import multiprocessing
import errno

DEFAULT_HEARTBEAT_TIMEOUT = 600


logger = logging.getLogger(__name__)


class APIHandler(tornado.web.RequestHandler):  # pylint: disable=R0904
    """
    Parent class for API handlers
    """

    def initialize(self, server):  # pylint: disable=W0221
        """
        sessions
            dict: session_id->session_status
        """
        # pylint: disable=W0201
        server.read_status_updates()
        self.srv = server

    def reply_json(self, status_code, reply):
        """
        Reply with a json and a specified code
        """
        if status_code != 418:
            self.set_status(status_code)
        else:
            self.set_status(status_code, 'I\'m a teapot!')
        self.set_header('Content-Type', 'application/json')
        reply_str = json.dumps(reply, indent=4)
        self.finish(reply_str)

    def reply_reason(self, code, reason):
        return self.reply_json(code, {'reason': reason})

    def write_error(self, status_code, **kwargs):
        if self.settings.get("debug"):
            tornado.web.RequestHandler(self, status_code, **kwargs)
            return

        self.set_header('Content-Type', 'application/json')
        if 'exc_info' in kwargs and status_code >= 400 and status_code < 500:
            self.reply_json(status_code, {'reason': str(kwargs['exc_info'][1])})
        else:
            self.reply_json(status_code, {'reason': self._reason})


class RunHandler(APIHandler):
    def post(self):
        offered_test_id = self.get_argument(
            "test_id", datetime.datetime.now().strftime('%Y%m%d%H%M%S'))
        if len(self.srv.running_sessions) >= 1 and not self.srv.allow_multiple:
            self.reply_reason(
                500, 'There are active tests running: {test_id}'.format(test_id=self.srv.running_sessions)
            )
            return

        try:
            cfg_data = self.request.body
            # cfg_data = self.get_body_argument("config")
        except:
            self.reply_reason(
                500, "Config MUST be specified"
            )
            logger.warning('Failed to get config', exc_info=True)
            return
        logger.debug('Received config: %s. Starting test', cfg_data)
        try:
            session_id = self.srv.create_session_dir(offered_test_id)
        except RuntimeError as err:
            self.reply_reason(500, str(err))
            return
        # Remember that such session exists
        self.srv.set_session_status(
            session_id, {'status': 'starting'}
        )
        self.srv.cmd({
            'session': session_id,
            'cmd': 'run',
            'config': cfg_data
        })
        self.srv.running_sessions[session_id] = session_id
        self.reply_json(200, {"session": session_id})
        return


class StopHandler(APIHandler):  # pylint: disable=R0904
    """
    Handles GET /stop
    """

    def get(self):
        session_id = self.get_argument("session")

        try:
            self.srv.status(session_id)
        except KeyError:
            self.reply_reason(404, 'No session with this ID.')
            return
        if session_id in self.srv.running_sessions.keys():
            self.srv.cmd({'cmd': 'stop', 'session': session_id})
            self.reply_reason(200, 'Will try to stop test process.')
            return
        else:
            self.reply_reason(409, 'This session is already stopped.')
            return


class StatusHandler(APIHandler):  # pylint: disable=R0904
    """
    Handle GET /status?
    """

    def get(self):
        session_id = self.get_argument("session", default=None)
        if session_id:
            try:
                status = self.srv.status(session_id)
            except KeyError:
                self.reply_reason(404, 'No session with this ID.')
                return
            self.reply_json(200, status)
        else:
            self.reply_json(200, self.srv.all_sessions)


class ApiServer(object):
    """ API server class"""

    def __init__(self, in_queue, out_queue, working_dir, allow_multiple=True, debug=False):
        self._in_queue = in_queue
        self._out_queue = out_queue
        self._working_dir = working_dir
        self._sessions = {}
        self._running_sessions = {}
        self._hb_deadline = None
        self._hb_timeout = DEFAULT_HEARTBEAT_TIMEOUT
        self.allow_multiple = allow_multiple

        handler_params = dict(server=self)
        handlers = [
            (r"/api/v1/run", RunHandler, handler_params),
            (r"/api/v1/stop", StopHandler, handler_params),
            (r"/api/v1/status", StatusHandler, handler_params)
        ]

        self.app = tornado.web.Application(
            handlers,
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            debug=debug
        )

    def read_status_updates(self):
        """Read status messages from manager"""
        try:
            while True:
                message = self._in_queue.get_nowait()
                session_id = message.get('session')
                del message['session']
                self.set_session_status(session_id, message)
        except multiprocessing.queues.Empty:
            pass

    def check(self):
        """Read status messages from manager and check heartbeat"""
        self.read_status_updates()

        #if self._running_id and self._hb_deadline is not None and time.time() > self._hb_deadline:
        #    self.cmd({
        #        'cmd': 'run',
        #        'session': self._running_id,
        #        'break': 'finished'
        #    })
        #    self.cmd({'cmd': 'stop', 'session': self._running_id})

    def set_session_status(self, session_id, new_status):
        """Remember session status and change running_id"""

        if new_status['status'] in ['success', 'failed']:
            if self._running_sessions.get(session_id, None):
                del self._running_sessions[session_id]
        else:
            self._running_sessions[session_id] = new_status

        self._sessions[session_id] = new_status

    def heartbeat(self, session_id, new_timeout=None):
        """
        Set new heartbeat timeout (if specified)
        and reset heartbeat deadline
        """
        if new_timeout is not None:
            self._hb_timeout = new_timeout
        # if session_id == self._running_id and self._running_id is not None:
        #     self._hb_deadline = time.time() + self._hb_timeout

    def session_dir(self, session_id):
        """Return working directory for given session id"""
        return os.path.join(self._working_dir, session_id)

    def session_file(self, session_id, filename):
        """Return file path for given session id"""
        return os.path.join(self._working_dir, session_id, filename)

    def create_session_dir(self, offered_id):
        """
        Returns generated session id
        Should only be used if no tests are running
        """
        if not offered_id:
            offered_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        # This should use one or two attempts in typical cases
        for n_attempt in xrange(10000000000):
            session_id = "%s_%010d" % (offered_id, n_attempt)
            session_dir = self.session_dir(session_id)
            try:
                os.makedirs(session_dir)
            except OSError as err:
                if err.errno != errno.EEXIST:
                    raise RuntimeError("Failed to create session directory")
            if self.is_empty_session(session_id):
                return session_id
            n_attempt += 1
        raise RuntimeError("Failed to generate session id")

    def is_empty_session(self, session_id):
        """Return true if the session did not get past the lock stage"""
        return not os.path.exists(self.session_file(session_id, 'status.json'))

    def cmd(self, message):
        """Put commad into manager queue"""
        self._out_queue.put(message)

    @property
    def all_sessions(self):
        """Get session status by ID, can raise KeyError"""
        return self._sessions

    def status(self, session_id):
        """Get session status by ID, can raise KeyError"""
        return self._sessions[session_id]

    #@property
    #def running_id(self):
    #    """Return ID of running session"""
    #    return self._running_id

    #@property
    #def running_status(self):
    #    """Return status of running session , can raise KeyError"""
    #    return self.status(self._running_id)

    @property
    def running_sessions(self):
        """Return list of running sesions , can raise KeyError"""
        return self._running_sessions

    def serve(self, port):
        """ Run tornado ioloop """
        self.app.listen(port)
        ioloop = tornado.ioloop.IOLoop.instance()
        update_cb = tornado.ioloop.PeriodicCallback(self.check, 300, ioloop)
        update_cb.start()
        ioloop.start()


def main(webserver_queue, manager_queue, test_directory, allow_multiple, debug, port=9998):
    """Target for webserver process.
    The only function ever used by the Manager.
    webserver_queue
        Read statuses from Manager here.
    manager_queue
        Write commands for Manager there.
    test_directory
        Directory where tests are
    allow_multiple
        Allow multiple concurrent tests
    debug
        Enable debug logging
    """
    ApiServer(webserver_queue, manager_queue, test_directory, allow_multiple, debug).serve(port)


if __name__ == '__main__':
    import argparse
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] [wizard ui] %(filename)s:%(lineno)d %(message)s'
    )
    parser = argparse.ArgumentParser(description='Configures ui tornado server.')
    parser.add_argument('--port', dest='port', default=9998, help='port for webserver (default: 9998)')
    parser.add_argument('--debug', dest='debug', default=False, help='debug logging')
    parser.add_argument('--allow_multiple', dest='allow_multiple', default=True, help='allow multiple concurrent tests')
    args = parser.parse_args()

    manager_queue = multiprocessing.Queue()
    webserver_queue = multiprocessing.Queue()

    main(webserver_queue, manager_queue, '.', args.allow_multiple, args.debug, args.port)