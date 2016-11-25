import tornado.web
import logging
import seaborn as sns
import datetime
import matplotlib.pyplot as plt
import pandas as pd
import os
import base64

from pkg_resources import resource_filename


class BarplotBuilder(tornado.web.RequestHandler):
    def get(self):
        """ Helper barplot page w/ list of logs

        Returns:
            barplot template, fills it with logs found at 'logs'
        """
        dir_files = os.listdir('logs')
        # use any files in './logs' that endswith 'log'
        items = ['./logs/{filename}'.format(filename=filename) for filename in dir_files if filename.endswith('log')]
        self.render(
            resource_filename(__name__, 'barplot.html'),
            title="Barplot builder",
            items=items
        )

    def post(self):
        """ Make barplot for specified logs, save it and return plot

        Args:
            POST body argument 'log'
        Returns:
            image of plot
        """
        input_filenames = self.get_body_arguments('log')

        if not input_filenames:
            self.send_error(status_code=404)
            return None

        # read multiple files to dataframe
        df = input_files_to_df(input_filenames, ' ')

        # plot
        sns.set(font_scale=1, rc={"figure.figsize": (12, 8)})
        ax = sns.barplot(x=df.label, y=df.curr, ci=None)
        for t in ax.get_xticklabels():
            t.set(rotation=60)
        for p in ax.patches:
            height = p.get_height()
            ax.text(p.get_x(), height+2, '%1.2f' % (height))
        plt.ylabel('mean(current), mA')
        plt.xlabel('log names')
        plt.subplots_adjust(bottom=0.40)
        suffix = datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d_%H-%M-%S')
        path = 'plots'

        # save plot to file
        try:
            logging.info('Saving plot to %s/barplot%s.png', path, suffix)
            filename = '%s/barplot%s.png' % (path, suffix)
            plt.savefig(filename)
        except:
            logging.info("Unable to save plot to file", exc_info=True)
            return None

        # read plot and return contents
        with open(filename) as img:
            data = img.read()
            b64_data = base64.b64encode(data)
        plt.close()

        self.render(
            resource_filename(__name__, 'result.html'),
            title="Result",
            data=b64_data,
            message=None
        )


def input_files_to_df(files, delimiter):
    """ Read files to dataframe

    Args:
        files: list of filenames
        delimiter: file columns delimiter
    Returns:
        pandas DataFrame
    """
    work_df = None
    for work_file in files:
        filename = work_file.split('/')[-1]
        if work_df is None:
            work_df = pd.read_csv(work_file, delimiter=delimiter, names="ts curr".split())
            work_df['label'] = '{name}'.format(name=filename)
        else:
            df = pd.read_csv(work_file, delimiter=delimiter, names="ts curr".split())
            df['label'] = '{name}'.format(name=filename)
            work_df = work_df.append(df)
    # convert unixtimestamp to datetime/s
    work_df['ts'] = pd.to_datetime(work_df['ts'] ,unit='s')
    return work_df
