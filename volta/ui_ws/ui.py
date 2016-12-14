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


class WizardWebSocket(tornado.websocket.WebSocketHandler):
    def open(self):
        self.write_message("Volta wizard started")
        self.volta = VoltaWorker()
        self.phone = PhoneWorker()
        self.write_message(u'Подключите коробку')
        # 1 - подключение коробки
        self.volta.device = EventPoller(self.volta.isUsbConnected)
        self.write_message(u'Коробка найдена! Подключите телефон.')
        # 2 - подключение телефона
        phone = EventPoller(self.phone.isPhoneConnected)
        self.write_message(u'Телефон найден: %s' % phone)

    def on_message(self, message):
        # 3 - установка apk
        # TODO
        # 4 - параметризация теста
        if message:
            self.duration = int(message)
        else:
            self.write_message(u'Вы не ввели длительность теста.')
        self.volta.setTestDuration(self.duration)
        self.write_message(u'Длительность теста будет %s секунд.' % self.duration)
        # pre5 - сброс logcat
        self.write_message(u'Чистим логи на телефоне (logcat)')
        EventPoller(self.phone.clearLogcat)
        self.write_message(u'Теперь отключите телефон')
        # 5 - отключение телефона
        EventPoller(self.phone.isPhoneDisconnected)
        self.write_message(u'Начинается тест, не забудьте помигать фонариком!')
        # 6 - запуск теста, мигание фонариком
        grabber = grabberThread(self.volta)
        grabber.run()

        counter = 0
        while counter < self.duration:
            progress = 100 * counter / self.duration
            if progress < 100:
                self.write_message('Прогресс: %s %%' % progress)
            step=10
            counter = counter + step
            time.sleep(step)

        grabber.wait(self.duration * 2)
        EventPoller(self.volta.isTestFinished)
        self.write_message(u'Готово. Подключите телефон')
        # 7 - подключение телефона
        EventPoller(self.phone.isPhoneConnected)
        self.write_message(u'Найден телефон, забираем логи с телефона')
        EventPoller(self.phone.dumpLogcatEvents)
        EventPoller(self.phone.getInfoAboutDevice)
        # 8 - заливка логов
        self.write_message(u'Собираем логи и заливаем логи в Лунапарк. '
                           u'Это может занять какое-то время.')
        jobid = self.volta.upload('./output.bin', './events.log')
        self.write_message(u'<a target="_blank" href="%s">Lunapark URL</a>' % jobid)
        # work finished, closing the connection
        self.close()

    def on_close(self):
        self.write_message('Volta wizard finished')


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
