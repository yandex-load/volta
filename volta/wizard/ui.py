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

from pkg_resources import resource_filename

from volta.analysis.wizard import VoltaWorker, EventPoller, PhoneWorker


logger = logging.getLogger(__name__)


def format_message(message, type):
    return json.dumps({'type': type, 'message': message})


class consoleLogger(threading.Thread):
    """ streams console logging to websocket debug div """
    def __init__(self, ws):
        super(consoleLogger, self).__init__()
        self.ws = ws
        self.finished = False

    def run(self):
        with open('wizard.log') as wiz_log:
            while not self.finished:
                message = wiz_log.readline()
                if message:
                    self.ws.write_message(format_message(message, 'debug'))
                else:
                    time.sleep(1)


class WizardWebSocket(tornado.websocket.WebSocketHandler):
    def open(self):
        self.write_message("Volta wizard started")
        self.initConsoleLogger()

    def initConsoleLogger(self):
        self.consoleLogger = consoleLogger(self)
        self.consoleLogger.setDaemon(True)
        self.consoleLogger.start()

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
        self.volta.startTest()
        self.write_message(format_message(u'Готово', 'message'))

        # 7 - подключение телефона
        if config['events']:
            self.write_message(format_message(u'Подключите телефон', 'message'))
            EventPoller(self.phone.isPhoneConnected)
            self.write_message(format_message(u'Найден телефон, забираем логи с телефона', 'message'))
            EventPoller(self.phone.dumpLogcatEvents)
            EventPoller(self.phone.getInfoAboutDevice)

        # 8 - заливка логов
        if config['upload']:
            self.write_message(format_message(
                u'Собираем логи и заливаем логи в Лунапарк. Это может занять какое-то время.', 'message')
            )
            if config['events']:
                jobid = self.volta.upload('./output.bin', './events.log')
            else:
                jobid = self.volta.upload('./output.bin', None)

            self.write_message(format_message(u'<a target="_blank" href="%s">Lunapark URL</a>' % jobid, 'message'))
        # work finished, closing the connection
        time.sleep(3)
        self.close()

    def on_close(self):
        self.consoleLogger.finished = True
        self.consoleLogger.join(10)
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
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] [wizard ui] %(filename)s:%(lineno)d %(message)s'
    )

    wizard_logger = logging.getLogger('')
    with open('wizard.log', 'w'):
        pass
    fh = logging.FileHandler('wizard.log')
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    wizard_logger.addHandler(fh)

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
