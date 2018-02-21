from __future__ import absolute_import
from __future__ import print_function
from volta.common.resource import SerialOpener
from volta.providers.boxes.box_binary import BoxBinaryReader

def main():
    volta = BoxBinaryReader(
        SerialOpener(
            "/dev/cu.usbmodem1411",
            baud_rate=1000000,
            )(),
        10000,
        power_voltage=1,
        precision=0,
    )
    for chunk in volta:
        print(chunk)

if __name__ == '__main__':
    main()
