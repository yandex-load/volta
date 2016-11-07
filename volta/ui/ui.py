# -*- coding: utf-8 -*-

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
import json
import requests
#%matplotlib inline

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
        dir_files = os.listdir('logs')
        #cwd = os.path.dirname(os.path.abspath(__file__))
        items = ['./logs/{filename}'.format(filename=filename) for filename in dir_files if filename.endswith('log')]
        self.render(
            resource_filename(__name__, 'templates/barplot.html'),
            title="Barplot builder", 
            items=items
        )

    def post(self):
        """ make barplot for specified log, save it and return plot """
        logging.info(self.get_body_arguments('log'))
        input_filenames = self.get_body_arguments('log')
        #cwd = os.path.dirname(os.path.abspath(__file__))

        if not input_filenames:
            self.send_error(status_code=404)

        df = input_files_to_df(input_filenames, ' ')

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
        suffix = datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d_%H-%M-%S')
        path = 'plots'

        try:
            logging.info('Saving plot to %s/barplot%s.png', path, suffix)
            filename = '%s/barplot%s.png' % (path, suffix)
            plt.savefig(filename)
        except:
            logging.info("Unable to save plot to file", exc_info=True)

        self.set_header("Content-Type", "image/jpeg")
        with open(filename) as img:
            data = img.read()
        plt.close()
        self.write(data)


class LmplotBuilder(tornado.web.RequestHandler):
    def get(self):
        """ return available logs if exists """
        #cwd = os.path.dirname(os.path.abspath(__file__))
        dir_files = os.listdir('logs')
        items = ['logs/{filename}'.format(filename=filename) for filename in dir_files if filename.endswith('log')]
        self.render(
            resource_filename(__name__, 'templates/lmplot.html'),
            title="Lmplot builder", 
            items=items
        )

    def post(self):
        """ make lmplot for specified log, save it to dir and return the plot """
        input_filename = self.get_body_argument('log')
        graph_type = self.get_body_argument('type', default='mean')
        if not input_filename:
            self.send_error(status_code=404)

        df = pd.read_csv(input_filename, delimiter=' ', names="ts curr".split())
        df['ts'] = df.ts.astype(int)
        df['ts'] = pd.to_datetime(df['ts'],unit='s')
        df.set_index(['ts'], inplace=True)

        #convert timestamps to datetime

        fig, ax = sns.plt.subplots()

        if graph_type == 'mean':
            df.groupby(level=0).mean().plot()
        elif graph_type == 'qplot':
            def percentile(n):
                def percentile_(x):
                    return np.percentile(x, n)
                percentile_.__name__ = 'percentile_%s' % n
                return percentile_

            percentiles = [percentile(n) for n in [100, 75, 50, 25, 0]]
    
            df.groupby(level=0).curr.agg(percentiles).plot(title='Percentiles by second', kind='area', stacked=False, figsize=(12, 10), linewidth=0)

        #make lmplot, save it to file, return filename
        #plot settings
        fig.set_size_inches(12,8)
        sns.set_style("darkgrid", {"axes.facecolor": ".9"})

        plt.ylabel('current, mA')
        plt.xlabel('time')
        suffix = datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d_%H-%M-%S')
        path = 'plots'
        try:
            logging.info('Saving plot to %s/lmplot%s.png', path, suffix)
            filename = '%s/lmplot%s.png' % (path, suffix)
            plt.savefig(filename)
        except:
            logging.error('Unable to save plot to file', exc_info=True)

        plt.close()
        self.set_header("Content-Type", "image/jpeg")
        with open(filename) as img:
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
        logfile = 'logs/%s%s.log' % (
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
        
class PlotDisplayer(tornado.web.RequestHandler):
    """ returns a template w/ list of available plots """
    def get(self):
        plots = os.listdir('plots')
        self.render(
            resource_filename(__name__, 'templates/plots.html'),
            title="Plots",
            plots=plots
        )

    def post(self):
        """ read specified plot from disk and return as an image """
        plot = self.get_body_argument('plot')
        if not plot:
            self.send_error(status_code=404)

        self.set_header("Content-Type", "image/jpeg")
        plot_fpath = os.path.join('plots', plot)
        #.encode('ascii','ignore')
        with open(plot_fpath) as img:
            data = img.read()
        self.write(data)







#==============================================

class LogcatMeta(tornado.web.RequestHandler):
    """ return metadata for front """
    def get(self):
        #добавил к датам год, потому что в логах его нет и почистил логи от мусора, когда при запуске даты были кривые
        logcat_start = datetime.datetime.strptime("10-19 18:17:49.204", "%m-%d %H:%M:%S.%f").replace(year=2016)
        logcat_start_epoch = (logcat_start - datetime.datetime(1970,1,1)).total_seconds()
        logcat_syncflash = datetime.datetime.strptime("10-19 18:24:11.630", "%m-%d %H:%M:%S.%f").replace(year=2016)
        logcat_syncflash_epoch = (logcat_syncflash - datetime.datetime(1970,1,1)).total_seconds()
        logcat_end = datetime.datetime.strptime("10-19 18:28:11.531", "%m-%d %H:%M:%S.%f").replace(year=2016)
        logcat_end_epoch = (logcat_end - datetime.datetime(1970,1,1)).total_seconds()
        
        #id события в логе коробки с 2 включением фонарика
        sync = 12170
        #считаем timestamp конца лога - количество событий после sync'а, учитывая rate 1000000
        end = 164381619
        volta_start = logcat_syncflash_epoch - sync/1000 
        volta_end = logcat_syncflash_epoch + end/1000000

        #dump to json
        js_temp = {}
        js_temp['logcat'] = {
            'start': logcat_start_epoch,
            'end': logcat_end_epoch
        }
        js_temp['volta'] = {
            'rate': 1000000,
            'start': volta_start,
            'end': volta_end
        }
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(js_temp))


class Logcat(tornado.web.RequestHandler):
    """ returns data for front """
    def post(self):
        pass

    def get(self):
        data = os.listdir('data')

        #читаем лог с сырыми данными
        df = pd.DataFrame(
            np.fromfile(
                "data/browser_download_lte.bin",
                dtype=np.uint16
            ).astype(np.float32) * (3300 / 2**12)
        )
        logging.info('readed')
        #усредняем по миллисекунды
        logging.info('mean')
        df_r1000 = df.groupby(df.index//1000).mean()
        logging.info(df_r1000)
        #сходим в самого себя, почитаем meta информацию
        try:
            with open('data/meta.json') as meta:
                meta_json = json.loads(meta.read())
        except:
            self.write('There is no metafile. Call <a href="/logcatmeta">meta</a> method first')
            self.send_error(status_code=404)

        logging.info(meta_json)

        #смотрим старт лога из мета информации
        start = datetime.datetime.fromtimestamp(meta_json['volta']['start'])
        logging.info(start)
        #строим индекс по старту с частотой в миллисекунду
        index = pd.date_range(start, periods=len(df_r1000), freq='ms')
        logging.info('done index')
        #строим series по построенному индексу и значениям, прочитанным из лога
        series = pd.Series(df_r1000.ix[:,0].values, index=index)
        logging.info(series)
        logging.info('done series')
        #приходит фронт за нужным slice
        s2 = series['2016-10-19 21:23':'2016-10-19 21:24']
       
        #считаем количество данных в slice
        nsamples_origin = s2.count()
        #print ('Origin samples count: %s' % nsamples_origin)
        
        #фронт говорит сколько сэмлов ему нужно
        nsamples = 5000
        
        #в случае, если данных за slice больше, чем запрошенных,
        #считаем коэффициент resampling'а и делаем resample.
        if nsamples < nsamples_origin:
            k = str(int(nsamples_origin/nsamples))+'L'
            #print ('Coeff: %s' % k)
            #делаем resample
            logging.info('started resampling')
            resampled = s2.resample(k).mean()
            logging.info(resampled)
            logging.info('end resampling')
            #print ('Resampled count: %s' % resampled.count())
            #print ('Resampled slice: \n \n%s' % resampled[:10])
        #в случае, если данных меньше, resample делать можно, но нужно понять как правильно интерполировать
        else:
            #print ('nsamples %s more than origin %s' % (nsamples, nsamples_origin))
            resampled = s2
        
        
        #теперь сформатируем данные так, как это нужно фронту (БОЛЬ)
        resampled_dict = resampled.to_dict()
        res = []
        for ts, value in resampled_json.items():
            work = {}
            work['x'] = ts.timestamp()
            work['y'] = value
            res.append(work)
        self.set_header("Content-Type", "application/json") 
        self.write(res)
                
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








def make_app():
    static_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static')
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/barplot", BarplotBuilder),
        (r"/lmplot", LmplotBuilder),
        (r"/record", Recorder),
        (r"/plot", PlotDisplayer),
        (r"/logcat", Logcat),
        (r"/logcatmeta", LogcatMeta),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": static_path}),
    ])

def main():
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser(description='Configures ui tornado server.')
    parser.add_argument('--port', dest='port', default=8888, help='port for webserver (default: 8888)')
    args = parser.parse_args()

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
    app.listen(args.port)
    url = "http://localhost:{port}".format(port=args.port)
    webbrowser.open(url,new=2) #new=2 means open in new tab if possible
    tornado.ioloop.IOLoop.current().start()

if __name__ == "__main__":
    main()
