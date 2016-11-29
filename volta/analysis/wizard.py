# -*- coding: utf-8 -*-

import time
import logging
import sqlite3
import os
import usb


from usb_ids import ids_file_to_sqlite

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
    if device: return True


def isPhoneConnected():
    logger.info("Подключите телефон в USB...")
    conn = sqlite3.connect('usb_list.db')
    c = conn.cursor()
    devices = usb.core.find(find_all=1)
    for device in devices:
        known_phones = [u'SAMSUNG_Android',
                        u'iPhone']
        if not device.product in known_phones:
            continue
        q = 'SELECT name FROM devices WHERE manufacturer_id="{man_id}" AND id="{device_id}"'.format(
            man_id=format(device.idVendor, '04x'),
            device_id=format(device.idProduct, '04x'),
        )
        c.execute(q)

        device_name = c.fetchone()
        if device_name:
            logging.info('Найден телефон: %s. id: %s', device_name[0].encode('utf-8'), device.serial_number.encode('utf-8'))
            return True
    return False

def main():
    logging.basicConfig(
        level="INFO",
        format='%(asctime)s [%(levelname)s] [volta wizard] %(filename)s:%(lineno)d %(message)s'
    )
    logger.info("Volta wizard started")
    if EventPoller(isUsbConnected):
        logger.info('Надйена подключенная коробочка!')
    EventPoller(isPhoneConnected)

if __name__ == "__main__":
    main()
