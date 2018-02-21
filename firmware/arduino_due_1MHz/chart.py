#!/usr/bin/env python

# from http://forum.arduino.cc/index.php?topic=137635.msg1270996#msg1270996

from __future__ import absolute_import
import pyqtgraph as pg
import time, threading, sys
import serial
import numpy as np


class SerialReader(threading.Thread):
    """ Defines a thread for reading and buffering serial data.
    By default, about 5MSamples are stored in the buffer.
    Data can be retrieved from the buffer by calling get(N)"""
    def __init__(self, port, chunkSize=1024, chunks=5000):
        threading.Thread.__init__(self)
        # circular buffer for storing serial data until it is
        # fetched by the GUI
        self.buffer = np.zeros(chunks*chunkSize, dtype=np.uint16)
        self.chunks = chunks        # number of chunks to store in the buffer
        self.chunkSize = chunkSize  # size of a single chunk (items, not bytes)
        self.ptr = 0                # pointer to most (recently collected buffer index) + 1
        self.port = port            # serial port handle
        self.sps = 0.0              # holds the average sample acquisition rate
        self.exitFlag = False
        self.exitMutex = threading.Lock()
        self.dataMutex = threading.Lock()


    def run(self):
        exitMutex = self.exitMutex
        dataMutex = self.dataMutex
        buffer = self.buffer
        port = self.port
        count = 0
        sps = None
        lastUpdate = pg.ptime.time()

        while True:
            # see whether an exit was requested
            with exitMutex:
                if self.exitFlag:
                    break

            # read one full chunk from the serial port
            data = port.read(self.chunkSize*2)
            # convert data to 16bit int numpy array
            data = np.fromstring(data, dtype=np.uint16)

            # keep track of the acquisition rate in samples-per-second
            count += self.chunkSize
            now = pg.ptime.time()
            dt = now-lastUpdate
            if dt > 1.0:
                # sps is an exponential average of the running sample rate measurement
                # if sps is None:
                #     sps = count / dt
                # else:
                #     sps = sps * 0.9 + (count / dt) * 0.1
                sps = count / dt
                count = 0
                lastUpdate = now

            # write the new chunk into the circular buffer
            # and update the buffer pointer
            with dataMutex:
                buffer[self.ptr:self.ptr+self.chunkSize] = data
                self.ptr = (self.ptr + self.chunkSize) % buffer.shape[0]
                if sps is not None:
                    self.sps = sps

    def get(self, num, downsample=1):
        """ Return a tuple (time_values, voltage_values, rate)
          - voltage_values will contain the *num* most recently-collected samples
            as a 32bit float array.
          - time_values assumes samples are collected at 1MS/s
          - rate is the running average sample rate.
        If *downsample* is > 1, then the number of values returned will be
        reduced by averaging that number of consecutive samples together. In
        this case, the voltage array will be returned as 32bit float.
        """
        with self.dataMutex:  # lock the buffer and copy the requested data out
            ptr = self.ptr
            if ptr-num < 0:
                data = np.empty(num, dtype=np.uint16)
                data[:num-ptr] = self.buffer[ptr-num:]
                data[num-ptr:] = self.buffer[:ptr]
            else:
                data = self.buffer[self.ptr-num:self.ptr].copy()
            rate = self.sps

        # Convert array to float and rescale to voltage.
        # Assume 3.3V / 12bits
        # (we need calibration data to do a better job on this)
        data = data.astype(np.float32) * (3.3 / 2**12)
        if downsample > 1:  # if downsampling is requested, average N samples together
            data = data.reshape(num/downsample,downsample).mean(axis=1)
            num = data.shape[0]
            return np.linspace(0, (num-1)*1e-6*downsample, num), data, rate
        else:
            return np.linspace(0, (num-1)*1e-6, num), data, rate

    def exit(self):
        """ Instruct the serial thread to exit."""
        with self.exitMutex:
            self.exitFlag = True


# Get handle to serial port
# (your port string may vary; windows users need 'COMn')
s = serial.Serial('/dev/cu.usbmodem1421')

# Create the GUI
app = pg.mkQApp()
plt = pg.plot()
plt.setLabels(left=('ADC Signal', 'V'), bottom=('Time', 's'))
plt.setYRange(0.0, 3.3)

# Create thread to read and buffer serial data.
thread = SerialReader(s)
thread.start()

# Calling update() will request a copy of the most recently-acquired
# samples and plot them.
def update():
    global plt, thread
    t,v,r = thread.get(1000*1024, downsample=100)
    plt.plot(t, v, clear=True)
    plt.setTitle('Sample Rate: %0.2f'%r)

    if not plt.isVisible():
        thread.exit()
        timer.stop()

# Set up a timer with 0 interval so Qt will call update()
# as rapidly as it can handle.
timer = pg.QtCore.QTimer()
timer.timeout.connect(update)
timer.start(0)

# Start Qt event loop.
if sys.flags.interactive == 0:
    app.exec_()
