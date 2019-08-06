import serial
import struct
import time
import pandas as pd
import numpy as np


def measure():
    start_time = time.time()
    with serial.Serial('/dev/cu.usbmodem14121', 1000000, timeout=1) as inport:
        open_time = time.time()
        data = inport.read(100)
        read_time = time.time()
    close_time = time.time()
    return (open_time - start_time, read_time - open_time, close_time - read_time, len(data))

df = pd.DataFrame.from_records(
    (measure() for i in range(100)),
    columns=["open", "read", "close", "datalength"])

print(df)

print(df.describe())
