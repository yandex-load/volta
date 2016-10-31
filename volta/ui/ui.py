import tornado.ioloop
import tornado.web

import os
import pandas as pd
import seaborn as sns
import numpy as np
import collections
import matplotlib.pyplot as plt
import logging
import argparse
import datetime
import subprocess
import shlex
import webbrowser

from pkg_resources import resource_filename


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        """ index page w/ buttons """
        self.render(
            resource_filename(__name__, 'templates/index.html'),
            title="Volta UI"
        )


class BarplotBuilder(tornado.web.RequestHandler):
    def get(self):
        """ return available logs if exists """
        dir_files = os.listdir('./logs')
        #cwd = os.path.dirname(os.path.abspath(__file__))
        items = ['./logs/{filename}'.format(filename=filename) for filename in dir_files if filename.endswith('log')]
        self.render(
            resource_filename(__name__, 'templates/barplot.html'),
            title="Barplot builder", 
            items=items
        )

    def post(self):
        """ make barplot for specified log, save it and return plot """
        input_filenames = self.get_body_arguments('log')
        #cwd = os.path.dirname(os.path.abspath(__file__))

        if not input_filenames:
            self.send_error(status_code=404)

        df = input_files_to_df(input_filenames, ' ')
        for key, grouped_df in df.groupby('label'):
            logging.info('File: %s. Mean current: %s', key, grouped_df['curr'].mean())
        plot = render_barplot(df, './plots/', None)

        self.set_header("Content-Type", "image/jpeg")
        with open(plot) as img:
            data = img.read()
        self.write(data)


class LmplotBuilder(tornado.web.RequestHandler):
    def get(self):
        """ return available logs if exists """
        #cwd = os.path.dirname(os.path.abspath(__file__))
        dir_files = os.listdir('./logs')
        items = ['./logs/{filename}'.format(filename=filename) for filename in dir_files if filename.endswith('log')]
        self.render(
            resource_filename(__name__, 'templates/lmplot.html'),
            title="Lmplot builder", 
            items=items
        )

    def post(self):
        """ make lmplot for specified log, save it to dir and return the plot """
        input_filenames = self.get_body_arguments('log')
        #cwd = os.path.dirname(os.path.abspath(__file__))
        if not input_filenames:
            self.send_error(status_code=404)

        df = input_files_to_df(input_filenames, ' ')
        for key, grouped_df in df.groupby('label'):
            logging.info('File: %s. Mean current: %s', key, grouped_df['curr'].mean())
        plot = render_lmplot(df, './plots/', None)

        self.set_header("Content-Type", "image/jpeg")
        with open(plot) as img:
            data = img.read()
        self.write(data)


class Recorder(tornado.web.RequestHandler):
    """ return available usb devices and form w/ options for log recording """
    def get(self):
        devices = os.listdir('/dev')
        #cwd = os.path.dirname(os.path.abspath(__file__))
        arduino_devs = ['/dev/{device}'.format(device=device) for device in devices if device.startswith('cu')]

        self.render(
            resource_filename(__name__, 'templates/record.html'),
            title="Recorder", 
            devices=arduino_devs
        )

    def post(self):
        """ returns 'ok' and logfile name if log successfully recorded log from arduino
            pay attention, this method is not async
         """
        samples = self.get_body_argument('samples')
        device = self.get_body_argument('device')
        prefix = self.get_body_argument('prefix')
        #cwd = os.path.dirname(os.path.abspath(__file__))
        cmd = "serial-reader -device=%s -samples=%s" % (device, samples)
        logfile = './logs/%s%s.log' % (
                prefix,
                datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d_%H-%M-%S')
            )
        with open(logfile, "wb") as out:
            try:
                p = subprocess.Popen(
                    cmd,
                    stdout=out,
                    shell=True
                )
                p.communicate()
                p.wait()
            except Exception as exc:
                logging.error('Error trying to record samples', exc_info=True)
                stdout = exc
        self.write('Ok. Logfile: %s' % logfile)
        


#============================================================

def input_files_to_df(files, delimiter):
    """ reads files to dataframe """
    work_df = None
    for work_file in files:
        filename = work_file.split('/')[-1]
        if work_df is None:
            work_df = pd.read_csv(work_file, delimiter=delimiter, names="ts curr".split())
            work_df['label'] = '{name}'.format(name=filename)
            #work_df.dropna()
        else:
            df = pd.read_csv(work_file, delimiter=delimiter, names="ts curr".split())
            df['label'] = '{name}'.format(name=filename)
            #df.dropna()
            work_df = work_df.append(df)
    #convert unixtimestamp to datetime/s
    work_df['ts'] = pd.to_datetime(work_df['ts'],unit='s')
    return work_df

def render_barplot(df, path, suffix):
    """ make barplot, save to file and return filename  """
    logging.info("Started rendering barplot")
    sns.set(font_scale=1, rc={"figure.figsize": (12, 8)})
    ax = sns.barplot(x=df.label, y=df.curr, ci=None)
    for t in ax.get_xticklabels():
        t.set(rotation=60)

    for p in ax.patches:
        height = p.get_height()
        ax.text(p.get_x(), height+2, '%1.2f' % (height) )

    plt.ylabel('mean(current), mA')
    plt.xlabel('log names')
    plt.subplots_adjust(bottom=0.40)
    if not suffix:
        suffix = datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d_%H-%M-%S')
    try:
        logging.info('Saving plot to %s/barplot%s.png', path, suffix)
        filename = '%s/barplot%s.png' % (path, suffix)
        plt.savefig(filename)
    except:
        logging.info("Unable to save plot to file", exc_info=True)
    return filename

def render_lmplot(df, path, suffix):
    """ make lmplot, save it to file, return filename """
    logging.info("Started rendering lmplot")

    #plot settings
    fig, ax = sns.plt.subplots()
    fig.set_size_inches(12,8)
    sns.set_style("darkgrid", {"axes.facecolor": ".9"})

    logging.info('Calculating plot data')
    mean = df.groupby("ts").mean()
    #rolling = df.groupby("ts")[["curr"]].rolling(window=50).mean().dropna()
    cummulative = mean.sum()
    logging.info('Cummulative summ for test: %s', cummulative['curr'])
    logging.info('Rendering plots')
    mean.plot(ax=ax)
    #cummulative.plot(ax=ax, c="b")
    #rolling.plot(ax=ax)

    plt.ylabel('current, mA')
    plt.xlabel('time')
    plt.legend(
        (cummulative),scatterpoints=1, loc='upper right',
    )
    if not suffix:
        suffix = datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d_%H-%M-%S')
    try:
        logging.info('Saving plot to %s/lmplot%s.png', path, suffix)
        filename = '%s/lmplot%s.png' % (path, suffix)
        plt.savefig(filename)
    except:
        logging.error('Unable to save plot to file', exc_info=True)
    return filename


def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/barplot", BarplotBuilder),
        (r"/lmplot", LmplotBuilder),
        (r"/record", Recorder),
    ])

def main():
    logging.basicConfig(level=logging.DEBUG)

    work_dirs = {
        'plots' : './plots',
        'logs' : './logs',
    }
    for key, dirname in work_dirs.iteritems():
        try:
            os.stat(dirname)
        except:
            logging.debug('Directory %s not found, trying to create it', dirname)
            os.mkdir(dirname)
    app = make_app()
    app.listen(8888)
    url = "http://localhost:8888"
    webbrowser.open(url,new=2) #new=2 means open in new tab if possible
    tornado.ioloop.IOLoop.current().start()

if __name__ == "__main__":
    main()
