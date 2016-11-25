import tornado.web
import os
import seaborn as sns
import datetime
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import logging
import base64

from pkg_resources import resource_filename


class LmplotBuilder(tornado.web.RequestHandler):
    def get(self):
        """ Helper lmplot page w/ list of logs

        Returns:
            lmplot template filled by logs found in 'logs'
        """
        dir_files = os.listdir('logs')
        # use any files in './logs' that endswith 'log'
        items = ['logs/{filename}'.format(filename=filename) for filename in dir_files if filename.endswith('log')]
        self.render(
            resource_filename(__name__, 'lmplot.html'),
            title="Lmplot builder",
            items=items
        )

    def post(self):
        """ Make lmplot for specified log, save it to dir and return the plot

        Args:
            POST body argument 'log'
            POST body argument 'type'

        Returns:
            image of plot
        """
        input_filename = self.get_body_argument('log')
        if not input_filename:
            self.send_error(status_code=404)
            return None

        # read log to dataframe, make ts and reindex
        df = pd.read_csv(input_filename, delimiter=' ', names="ts curr".split())
        df['ts'] = df.ts.astype(int)
        df['ts'] = pd.to_datetime(df['ts'],unit='s')
        df.set_index(['ts'], inplace=True)

        fig, ax = sns.plt.subplots()

        # two types of graphs, quantile and mean
        graph_type = self.get_body_argument('type', default='mean')
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

        # plot settings
        fig.set_size_inches(12,8)
        sns.set_style("darkgrid", {"axes.facecolor": ".9"})
        plt.ylabel('current, mA')
        plt.xlabel('time')
        suffix = datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d_%H-%M-%S')
        path = 'plots'

        # save plot to file
        try:
            logging.info('Saving plot to %s/lmplot%s.png', path, suffix)
            filename = '%s/lmplot%s.png' % (path, suffix)
            plt.savefig(filename)
        except:
            logging.error('Unable to save plot to file', exc_info=True)
            return None
        plt.close()

        # read file and return contents
        with open(filename) as img:
            data = img.read()
            b64_data = base64.b64encode(data)

        self.render(
            resource_filename(__name__, 'result.html'),
            title="Result",
            data=b64_data,
            message=None
        )
