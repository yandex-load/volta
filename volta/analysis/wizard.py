# -*- coding: utf-8 -*-

import time
import logging
import sqlite3
import usb
import subprocess
import glob
import json
import argparse
import sys
import os
from pkg_resources import resource_string, resource_filename

from volta.analysis import grab, uploader


logger = logging.getLogger(__name__)

def create_work_dirs():
    work_dirs = {
        'plots' : 'plots',
        'logs' : 'logs',
        'events': 'events',
    }
    for key, dirname in work_dirs.iteritems():
        try:
            os.stat(dirname)
        except:
            logging.debug('Directory %s not found, trying to create it', dirname)
            os.mkdir(dirname)
    return

def EventPoller(event):
    while True:
        rc = event()
        if rc is not None:
            return rc
        else:
            time.sleep(1)

class VoltaWorker(object):
    def __init__(self):
        self.volta = None
        self.test_duration = None
        self.worker = None
        self.volta_idVendor = 0x1a86 # CH341 idVendor=0x1a86, idProduct=0x7523
        self.volta_idProduct = 0x7523
        self.samplerate = None
        self.format = True # True is binary


    def isUsbConnected(self):
        logger.info("Подключите коробочку в USB и нажмите enter")
        raw_input()
        return True
        # this autodetection logic works unstable and unpredictable
        # especially on macbook pros
        #
        # debug_devices = [dev for dev in usb.core.find(find_all=1)]
        # logger.debug('Found devices: %s', debug_devices)
        # device = usb.core.find(idVendor=self.volta_idVendor, idProduct=self.volta_idProduct)
        # if device:
        #     logger.info('Найдена коробочка')
        #     return device

    def getTestDuration(self):
        logger.info('Введите длительность теста в секундах (сколько секунд коробочка будет записывать данные тока)')
        try:
            duration = int(raw_input())
        except ValueError:
            logger.error('Введите только число, длительность теста в секундах', exc_info=True)
        else:
            logger.info('Принято. Длительность теста будет %s секунд', duration)
            self.test_duration = duration
            return True

    def setTestDuration(self, duration):
        self.test_duration = duration
        return True

    def setVoltaFormat(self, fmt):
        self.format = fmt
        return True

    def startTest(self):
        if sys.platform.startswith('linux'):
            ports = glob.glob('/dev/ttyUSB[0-9]*')
        elif sys.platform.startswith('darwin'):
            ports = glob.glob('/dev/cu.wchusbserial[0-9]*')
        else:
            raise Exception('Your OS is not supported yet')
        try:
            device = [port for port in ports if 'Bluetooth' not in port][0]
        except IndexError:
            raise RuntimeError('Не найдена коробочка\n'
                               'Проверьте, что вы подключили её и правильно установили драйвера.\n'
                               'Ссылка: https://github.com/yandex-load/volta/tree/master/volta/drivers/ch341ser')
        logger.info('Не забудьте помигать на телефоне фонариком!')
        args = {
            'device': device,
            'seconds': self.test_duration,
            'output': "output.bin",
            'debug': False,
            'binary': self.format
        }
        self.grabber = grab.main(args)
        self.samplerate = self.grabber.samplerate


class PhoneWorker(object):
    def __init__(self):
        self.db = sqlite3.connect(resource_filename("volta.analysis", 'usb_list.db')).cursor()
        self.known_phones = [
            u'SAMSUNG_Android', u'Android', u'Nexus 5X', u'FS511',
            u'iPhone',
        ]
        self.device_serial = None
        self.device_name = None
        self.android_version = None
        self.android_api_version = None

    def isPhoneConnected(self):
        logger.info("Подключите телефон к компьютеру.")
        logger.info("Удостоверьтесь, что подключён только один телефон в USB (и хабы) и нажмите enter")
        raw_input()
        return True
        # ищем все подключенные известные нам телефоны по атрибуту product
        # logger.debug('Found devices: %s', usb.core.find(find_all=1))
        # phones = []
        # for device in usb.core.find(find_all=1):
        #    try:
        #        logger.debug('Trying to detect device: %s', device)
        #        if device.product in self.known_phones:
        #            logger.info('Found phone: %s', device.product)
        #            phones.append(device)
        #    except:
        #        logger.warning('Unable to detect device product')
        #        logger.debug('Unable to detect device product', exc_info=True)
        #if len(phones) == 1 :
        #    # id'шники преобразовываем в hex, соблюдая формат
        #    self.db.execute(
        #        'SELECT name FROM devices WHERE manufacturer_id="{man_id}" AND id="{device_id}"'.format(
        #            man_id=format(phones[0].idVendor, '04x'),
        #            device_id=format(phones[0].idProduct, '04x'),
        #        )
        #    )
        #    # известного нам девайса может не быть в базе vendor->usb устройств
        #    try:
        #        device_name = self.db.fetchone()[0].encode('utf-8')
        #    except:
        #        device_name = 'Unknown device'
        #    logger.info('Найден телефон: %s. id: %s', device_name, phones[0].serial_number.encode('utf-8'))
        #    self.device_serial = phones[0].serial_number
        #    self.device_name = device_name
        #    return self.device_serial
        #elif len(phones) > 1:
        #    logger.info('Найдено более 1 телефона! Отключите те, что не будут участвовать в измерениях.')
        #return

    def isPhoneDisconnected(self):
        logger.info("Отключите телефон от USB... и нажмите enter")
        raw_input()
        return True
        # phones = []
        #for device in usb.core.find(find_all=1):
        #    try:
        #        if device.product in self.known_phones:
        #            logger.info('Found phone: %s', device.product)
        #            phones.append(device)
        #        else:
        #            continue
        #    except:
        #        logger.warning('Unable to detect device product', exc_info=True)
        #if len(phones) >= 1 :
        #    q = 'SELECT name FROM devices WHERE manufacturer_id="{man_id}" AND id="{device_id}"'.format(
        #        man_id=format(phones[0].idVendor, '04x'),
        #        device_id=format(phones[0].idProduct, '04x'),
        #    )
        #    self.db.execute(q)
        #    try:
        #        device_name = self.db.fetchone()[0].encode('utf-8')
        #    except:
        #        device_name = 'Unknown device'
        #    logging.info('Найден телефон: %s. id: %s', device_name, phones[0].serial_number.encode('utf-8'))
        #    return
        #elif len(phones) == 0:
        #    logging.info('Телефон отключён. Запускаем тест.')
        #    return True

    def clearLogcat(self):
        logger.info('Чистим logcat на телефоне')
        logcat_clear = subprocess.Popen('adb logcat -c', shell=True)
        rc = logcat_clear.wait()
        logging.info('Logcat clear завершился с RC: %s', rc)
        if rc is not None:
            return rc

    def dumpLogcatEvents(self, output='./events.log'):
        logger.info('Забираем лог эвентов с телефона и складываем в %s', output)
        logcat_dump = subprocess.Popen('adb logcat -d > {output}'.format(output=output), shell=True)
        rc = logcat_dump.wait()
        logging.info('Logcat dump завершился с RC: %s', rc)
        if rc is not None:
            return rc

    def getInfoAboutDevice(self):
        logger.info('Получаем информацию об устройстве')
        adb = subprocess.Popen('adb shell getprop ro.build.version.release', stdout=subprocess.PIPE, shell=True)
        adb.wait()
        self.android_version = adb.communicate()[0].strip('\n')
        adb2 = subprocess.Popen('adb shell getprop ro.build.version.sdk ', stdout=subprocess.PIPE, shell=True)
        self.android_api_version = adb2.communicate()[0].strip('\n')
        adb2.wait()

        #dump to file
        res = {
            'android_version': self.android_version,
            'android_api_version': self.android_api_version,
            'device_name': self.device_name,
            'device_id': self.device_serial
        }
        with open('meta.json', 'w') as fname:
            fname.write(json.dumps(res))
        return True


def run():
    parser = argparse.ArgumentParser(
        description='wizard for volta.')
    parser.add_argument(
        '-b', '--binary',
        help='enable binary volta format',
        action='store_true',
        default=False)
    parser.add_argument(
        '-d', '--debug',
        help='enable debug logging',
        action='store_true')
    parser.add_argument(
        '-t', '--task',
        help='lunapark task id',
        default=None)
    parser.add_argument(
        '-o', '--withoutphone',
        help='electrical currents only, without phone',
        action='store_true',
        default=False)
    args = vars(parser.parse_args())
    main(args)


def main(args):
    logging.basicConfig(
        level="DEBUG" if args.get('debug') else "INFO",
        format='%(asctime)s [%(levelname)s] [wizard] %(filename)s:%(lineno)d %(message)s'
    )
    logger.info("Volta wizard started")

    create_work_dirs()
    volta = VoltaWorker()
    phone = PhoneWorker()

    # 1 - подключение коробки
    volta.device = EventPoller(volta.isUsbConnected)
    if not args.get('withoutphone'):
        # 2 - подключение телефона
        EventPoller(phone.isPhoneConnected)
    # 3 - установка apk
    # TODO
    # 4 - параметризация теста
    EventPoller(volta.getTestDuration)
    if not args.get('withoutphone'):
        # pre5 - сброс logcat
        EventPoller(phone.clearLogcat)
        # 5 - отключение телефона
        EventPoller(phone.isPhoneDisconnected)
    # 6 - запуск теста, мигание фонариком
    volta.setVoltaFormat(args.get('binary'))
    volta.startTest()
    if not args.get('withoutphone'):
        # 7 - подключение телефона
        EventPoller(phone.isPhoneConnected)
        EventPoller(phone.dumpLogcatEvents)
        EventPoller(phone.getInfoAboutDevice)
        args['events'] = 'events.log'
    # 8 - заливка логов
    args['filename'] = 'output.bin'
    args['slope'] = 1
    args['offset'] = 0
    args['binary'] = args.get('binary')
    args['samplerate'] = volta.grabber.samplerate
    args['job_config'] = {
        'jobname': 'test',
        'version': 'version',
        'devicename': 'devicename',
        'app': 'app'
    }
    if args.get('task', None):
        args['job_config']['task'] = args.get('task')
    jobid = uploader.main(args)
    logger.info('Jobid: %s', jobid)
    logger.info('Volta wizard finished')

if __name__ == "__main__":
    run()
