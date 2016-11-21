import tornado.web
import os

from pkg_resources import resource_filename


class PlotDisplayer(tornado.web.RequestHandler):
    def get(self):
        """ Helper page for plot displayer w/ list of available plots

        Returns:
            temples w/ list of plots
        """
        plots = os.listdir('plots')
        self.render(
            resource_filename(__name__, 'plots.html'),
            title="Plots",
            plots=plots
        )

    def post(self):
        """ Read file w/ plot image from file and return it

        Args:
            POST body argument 'plot'
        Returns:
            image of plot
        """
        plot = self.get_body_argument('plot')
        if not plot:
            self.send_error(status_code=404)
            return None

        self.set_header("Content-Type", "image/jpeg")
        plot_fpath = os.path.join('plots', plot)
        with open(plot_fpath) as img:
            data = img.read()
        self.write(data)
