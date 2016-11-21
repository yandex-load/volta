import tornado.web

from pkg_resources import resource_filename


class IndexPage(tornado.web.RequestHandler):
    def get(self):
        """ index page w/ buttons """
        self.render(
            resource_filename(__name__, 'index.html'),
            title="Volta UI"
        )
