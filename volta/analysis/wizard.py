# -*- coding: utf-8 -*-

import time
import logging
import sqlite3
import os
import usb
import subprocess


logger = logging.getLogger(__name__)


def EventPoller(event):
    while True:
        if event():
            return True
        else:
            time.sleep(1)
    return False


def isUsbConnected():
    logger.info("Подключите коробочку в USB...")
    device = usb.core.find(idVendor=0x1a86, idProduct=0x7523) # CH341 idVendor=0x1a86, idProduct=0x7523
    if device:
        logging.info('Найдена коробочка!')
        return True


def isPhoneConnected():
    logger.info("Подключите телефон в USB...")
    conn = sqlite3.connect('usb_list.db')
    c = conn.cursor()
    devices = usb.core.find(find_all=1)
    phones = []
    for device in devices:
        known_phones = [
            u'SAMSUNG_Android',
            u'iPhone',
            u'Android',
            u'Nexus 5X'
        ]
        if not device.product in known_phones:
            continue
        else:
            phones.append(device)
    if len(phones) == 1 :
        q = 'SELECT name FROM devices WHERE manufacturer_id="{man_id}" AND id="{device_id}"'.format(
            man_id=format(phones[0].idVendor, '04x'),
            device_id=format(phones[0].idProduct, '04x'),
        )
        c.execute(q)
        try:
            device_name = c.fetchone()[0].encode('utf-8')
        except:
            device_name = 'Unknown device'
        logging.info('Найден телефон: %s. id: %s', device_name, phones[0].serial_number.encode('utf-8'))
        return True
    elif len(phones) > 1:
        logging.info('Найдено более 1 телефона! Отключите те, что не будут участвовать в измерениях.')
        return False
    return False

def isPhoneDisconnected():
    logger.info("Отключите телефон от USB...")
    conn = sqlite3.connect('usb_list.db')
    c = conn.cursor()
    devices = usb.core.find(find_all=1)
    phones = []
    for device in devices:
        known_phones = [
            u'SAMSUNG_Android',
            u'iPhone',
            u'Android',
            u'Nexus 5X'
        ]
        if not device.product in known_phones:
            continue
        else:
            phones.append(device)
    if len(phones) >= 1 :
        q = 'SELECT name FROM devices WHERE manufacturer_id="{man_id}" AND id="{device_id}"'.format(
            man_id=format(phones[0].idVendor, '04x'),
            device_id=format(phones[0].idProduct, '04x'),
        )
        c.execute(q)
        try:
            device_name = c.fetchone()[0].encode('utf-8')
        except:
            device_name = 'Unknown device'
        logging.info('Найден телефон: %s. id: %s', device_name, phones[0].serial_number.encode('utf-8'))
        return False
    elif len(phones) == 0:
        logging.info('Телефон отключён. Запускаем тест.')
        return True
    return False

def main():
    logging.basicConfig(
        level="INFO",
        format='%(asctime)s [%(levelname)s] [volta wizard] %(filename)s:%(lineno)d %(message)s'
    )
    logger.info("Volta wizard started")
    EventPoller(isUsbConnected)
    EventPoller(isPhoneConnected)
    logging.info('Введите длительность теста в секундах (сколько секунд коробочка будет записывать данные тока)')
    test_duration = raw_input()
    logging.info('Принято. Длительность теста будет %s секунд', test_duration)
    EventPoller(isPhoneDisconnected)
    test = subprocess.Popen('python grab.py -s {duration}'.format(
        duration=test_duration
        ),
        shell=True
    )
    logging.info('Тест уже начался. Не забудьте помигать на телефоне фонариком!')
    rc = test.wait()
    logging.info('Return code: %s', rc)
    logging.info('TODO: Здесь будет сохранялка логов с телефона')
    logging.info('TODO: Здесь будет заливка логов коробки и эвентов телефона в Лунапарк')
    logging.info('Volta wizard finished')




if __name__ == "__main__":
    main()
