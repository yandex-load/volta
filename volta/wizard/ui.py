# -*- coding: utf-8 -*-

import tornado.websocket
import tornado.web
import tornado.gen
import os
import webbrowser
from tornado.ioloop import IOLoop
import logging
import argparse
import threading
import time
import json
import requests

from pkg_resources import resource_filename

from volta.analysis.wizard import VoltaWorker, EventPoller, PhoneWorker, create_work_dirs
from volta.wizard.handlers.barplot import BarplotBuilder
from volta.wizard.handlers.lmplot import LmplotBuilder
from volta.analysis import uploader

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
    wait = True

    def open(self):
        self.write_message("Volta wizard started")
        self.initConsoleLogger()

    def initConsoleLogger(self):
        self.consoleLogger = consoleLogger(self)
        self.consoleLogger.setDaemon(True)
        self.consoleLogger.start()

    @tornado.gen.coroutine
    def wait_user_action(self, message):
        self.write_message(format_message(message, 'wait'))
        self.wait = True
        while self.wait:
            yield tornado.gen.sleep(0.5)

    def check_task(self, task):
        try:
            check = requests.get('https://lunapark.yandex-team.ru/api/task/'+task+'/joblist.json', verify=False)
            check.raise_for_status()
        except:
            return False
        return True

    @tornado.gen.coroutine
    def perform_test(self, config):
        if not config['duration']:
            self.write_message(format_message(u'Вы не ввели длительность теста', 'message'))
            raise ValueError('Вы не ввели длительность теста.')
        else:
            self.duration = int(config['duration'])
        self.volta = VoltaWorker()
        self.phone = PhoneWorker()
        self.write_message(format_message(u'Подключите коробку', 'message'))
        yield self.wait_user_action(u'Подключите коробку')

        # 1 - подключение коробки
        self.volta.device = True #EventPoller(self.volta.isUsbConnected)
        self.write_message(format_message(u'Коробка найдена!', 'message'))
        if config['events']:
            self.write_message(format_message(u'Подключите телефон.', 'message'))
            # 2 - подключение телефона
            # phone = EventPoller(self.phone.isPhoneConnected)
            # self.write_message(format_message(u'Телефон найден: %s' % phone, 'message'))

        # 3 - установка apk
        # TODO

        # 4 - параметризация теста
        self.volta.setTestDuration(self.duration)
        self.volta.setVoltaFormat(config['binary'])
        self.write_message(format_message(u'Длительность теста будет %s секунд.' % self.duration, 'message'))

        # pre5 - сброс logcat
        if config['events']:
            self.write_message(format_message(u'Подключите телефон', 'message'))
            yield self.wait_user_action(u'Подключите телефон')
            self.write_message(format_message(u'Чистим логи на телефоне (logcat)', 'message'))
            EventPoller(self.phone.clearLogcat)
            self.write_message(format_message(u'Теперь отключите телефон', 'message'))
            # 5 - отключение телефона
            yield self.wait_user_action(u'Отключите телефон')
            # EventPoller(self.phone.isPhoneDisconnected)
        # 6 - запуск теста, мигание фонариком
        self.write_message(format_message(u'Начинается тест', 'message'))
        if config['events']:
            yield self.wait_user_action(u'В течение 15 секунд помигайте фонариком на телефоне.')
        self.write_message(format_message(u'Начинается тест', 'start'))
        try:
            self.volta.startTest()
        except RuntimeError:
            self.write_message(format_message(u'Не удалось запустить тест. Подробности в терминале', 'message'))
            logger.error('Не удалось запустить тест', exc_info=True)
            raise NotImplementedError()
        else:
            self.write_message(format_message(u'Готово', 'message'))
        # 7 - подключение телефона
        if config['events']:
            self.write_message(format_message(u'Подключите телефон', 'message'))
            yield self.wait_user_action(u'Подключите телефон')
            #EventPoller(self.phone.isPhoneConnected)
            self.write_message(format_message(u'Найден телефон, забираем логи с телефона', 'message'))
            EventPoller(self.phone.dumpLogcatEvents)
            EventPoller(self.phone.getInfoAboutDevice)

        # 8 - заливка логов
        if config['upload']:
            self.write_message(format_message(
                u'Собираем логи и заливаем логи в Лунапарк. Это может занять какое-то время.', 'message')
            )
            args = {
                'filename': 'output.bin',
                'events': 'events.log' if config['events'] else None,
                'slope': float(5000./2**12),
                'offset': 0,
                'samplerate': self.volta.samplerate,
                'binary': config['binary'],
                'job_config': config
            }
            jobid = uploader.main(args)
            self.write_message(format_message(u'%s' % jobid, 'results'))
            self.wait_user_action(u'Тест завершился!')
        # work finished, closing the connection
        time.sleep(3)
        self.close()

    def on_message(self, message):
        try:
            msg = json.loads(message)
            if msg["message"] == "run_test":
                config = msg["config"]
                task_status = self.check_task(msg["config"]["task"])
                if not task_status:
                    self.write_message(format_message(u'Таск в Лунапарке не найден!'
                                                      u'В стартреке нужно нажать в таске '
                                                      u'"Действие->Нагрузочное тестирование"', 'message'))
                    raise RuntimeError('Не найден таск: %s' % msg['config'])
                self.perform_test(config)
            elif msg["message"] == "done":
                self.wait = False
            else:
                raise NotImplementedError(json.dumps(msg))
        except ValueError:
            logger.error("Couldn't parse msg:\n%s\n" % message)

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
        (r"/barplot", BarplotBuilder),
        (r"/lmplot", LmplotBuilder),        
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

    create_work_dirs()

    app = make_app()
    app.listen(args.port)
    url = "http://localhost:{port}".format(port=args.port)
    webbrowser.open(url,new=2) #new=2 means open in new tab if possible
    IOLoop.instance().start()

if __name__ == "__main__":
    main()
