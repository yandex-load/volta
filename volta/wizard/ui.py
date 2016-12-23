# -*- coding: utf-8 -*-

import tornado.websocket
import tornado.web
import os
import webbrowser
from tornado.ioloop import IOLoop
import logging
import argparse
import threading
import time
import json
import sys

from pkg_resources import resource_filename

from volta.analysis.wizard import VoltaWorker, EventPoller, PhoneWorker


logger = logging.getLogger(__name__)



class grabberThread(threading.Thread):
    """
    Drain a generator to a destination that answers to put(), in a thread
    """
    def __init__(self, source):
        super(grabberThread, self).__init__()
        self.source = source
        self._finished = threading.Event()
        self._interrupted = threading.Event()

    def run(self):
        self.source.startTest()
        self._finished.set()

    def wait(self, timeout=None):
        self._finished.wait(timeout=timeout)

    def close(self):
        self._interrupted.set()


def format_message(message, type):
    return json.dumps({'type': type, 'message': message})



class WizardWebSocket(tornado.websocket.WebSocketHandler):
    def open(self):
        self.write_message("Volta wizard started")
        #stderr_reader(sys.stderr).run()

    def on_message(self, message):
        config = json.loads(message)
        if not config['duration']:
            self.write_message(format_message(u'Вы не ввели длительность теста', 'message'))
            raise ValueError('Вы не ввели длительность теста.')
        else:
            self.duration = int(config['duration'])
        self.volta = VoltaWorker()
        self.phone = PhoneWorker()
        self.write_message(format_message(u'Подключите коробку', 'message'))
        # 1 - подключение коробки
        self.volta.device = EventPoller(self.volta.isUsbConnected)
        self.write_message(format_message(u'Коробка найдена!', 'message'))
        if config['events']:
            self.write_message(format_message(u'Подключите телефон.', 'message'))
            # 2 - подключение телефона
            phone = EventPoller(self.phone.isPhoneConnected)
            self.write_message(format_message(u'Телефон найден: %s' % phone, 'message'))
        # 3 - установка apk
        # TODO
        # 4 - параметризация теста
        self.volta.setTestDuration(self.duration)
        self.write_message(format_message(u'Длительность теста будет %s секунд.' % self.duration, 'message'))
        # pre5 - сброс logcat
        if config['events']:
            self.write_message(format_message(u'Чистим логи на телефоне (logcat)', 'message'))
            EventPoller(self.phone.clearLogcat)
            self.write_message(format_message(u'Теперь отключите телефон', 'message'))
            # 5 - отключение телефона
            EventPoller(self.phone.isPhoneDisconnected)
            self.write_message(format_message(u'Не забудьте помигать фонариком!', 'message'))
        # 6 - запуск теста, мигание фонариком
        self.write_message(format_message(u'Начинается тест', 'message'))
        grabber = grabberThread(self.volta)
        grabber.run()

        counter = 0
        if self.duration > 10:
            while counter < self.duration:
                progress = 100 * counter / self.duration
                if progress < 100:
                    self.write_message(format_message(u'Прогресс: %s %%' % progress, 'message'))
                step=10
                counter = counter + step
                time.sleep(step)

        grabber.wait(self.duration * 2)
        EventPoller(self.volta.isTestFinished)
        self.write_message(format_message(u'Готово', 'message'))

        if config['events']:
            self.write_message(format_message(u'Подключите телефон', 'message'))
            # 7 - подключение телефона
            EventPoller(self.phone.isPhoneConnected)
            self.write_message(format_message(u'Найден телефон, забираем логи с телефона', 'message'))
            EventPoller(self.phone.dumpLogcatEvents)
            EventPoller(self.phone.getInfoAboutDevice)

        if config['upload']:
            # 8 - заливка логов
            self.write_message(format_message(
                u'Собираем логи и заливаем логи в Лунапарк. Это может занять какое-то время.', 'message')
            )
            if config['events']:
                jobid = self.volta.upload('./output.bin', './events.log')
            else:
                jobid = self.volta.upload('./output.bin', None)

            self.write_message(format_message(u'<a target="_blank" href="%s">Lunapark URL</a>' % jobid, 'message'))
        # work finished, closing the connection
        self.close()

    def on_close(self):
        logger.info('Volta wizard finished')


class IndexPage(tornado.web.RequestHandler):
    def get(self):
        """ index page w/ buttons """
        self.render(
            resource_filename(__name__, 'index.html'),
            title="Volta UI"
        )


def make_app():
    static_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static')
    return tornado.web.Application([
        (r"/", IndexPage),
        (r"/wizard", WizardWebSocket),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": static_path}),
    ])

def main():
    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser(description='Configures ui tornado server.')
    parser.add_argument('--port', dest='port', default=9998, help='port for webserver (default: 9998)')
    args = parser.parse_args()

    app = make_app()
    app.listen(args.port)
    url = "http://localhost:{port}".format(port=args.port)
    webbrowser.open(url,new=2) #new=2 means open in new tab if possible
    IOLoop.instance().start()

if __name__ == "__main__":
    main()
