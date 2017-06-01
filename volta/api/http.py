import tornado.web
import logging
import webbrowser
import yaml
import time
from tornado import httpserver
from tornado import gen
from tornado.ioloop import IOLoop
import json
import traceback


from volta.core.core import Core


logger = logging.getLogger(__name__)

active_test = None

class StartHandler(tornado.web.RequestHandler):
    def post(self):
        global active_test
        cfg, cfg_data = None, None
        try:
            cfg_data = self.get_body_argument("config")
            cfg = yaml.load(cfg_data)
        except Exception:
            self.set_status(400)
            self.write('Error parsing config: %s. \nTraceback: %s' % (cfg_data, traceback.format_exc()))
            return
        logger.debug('Received config: %s. Starting test', cfg)
        try:
            self.core = Core(cfg)
            self.core.configure()
            self.perform_test()
            active_test = self.core
            self.write(json.dumps({'test_id': self.core.test_id}))
            return
        except Exception:
            logger.warning('Failed to start the test', exc_info=True)
            self.set_status(500)
            self.write('Failed to start the test: %s' % traceback.format_exc())
            return

    @gen.coroutine
    def perform_test(self):
        logger.info('Starting test... You can interrupt test w/ Ctrl+C or SIGTERM signal')
        self.core.start_test()


class StopHandler(tornado.web.RequestHandler):
    def post(self):
        global active_test
        if active_test:
            self.core = active_test
            self.core.end_test()
            self.write('Finished active test: %s' % self.core.test_id)
        else:
            self.set_status(404)
            self.write('There are no active tests')
        return


class VoltaApplication(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/api/v1/start/?", StartHandler),
            (r"/api/v1/stop/?", StopHandler)
        ]
        tornado.web.Application.__init__(self, handlers)

def main():
    import argparse
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] [wizard ui] %(filename)s:%(lineno)d %(message)s'
    )
    parser = argparse.ArgumentParser(description='Configures ui tornado server.')
    parser.add_argument('--port', dest='port', default=9998, help='port for webserver (default: 9998)')
    args = parser.parse_args()



    app = VoltaApplication()
    app.settings['debug'] = True
    app.listen(9998)

    url = "http://localhost:{port}".format(port=args.port)
    #webbrowser.open(url,new=2) #new=2 means open in new tab if possible

    IOLoop.instance().start()


if __name__ == '__main__':
    main()