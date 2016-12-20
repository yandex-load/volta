import os

from tornado import web
from tornadio2 import SocketConnection, TornadioRouter, SocketServer, event
import tornadio2
import datetime

from pkg_resources import resource_filename


class MyConnection(tornadio2.SocketConnection):
    def on_message(self, message):
        print "message %s" % message

class PingConnection(SocketConnection):
    @event
    def ping(self, client):
        now = datetime.datetime.now()
        print now
        return client, [now.hour, now.minute, now.second, now.microsecond / 1000]


class IndexPage(web.RequestHandler):
    def get(self):
        """ index page w/ buttons """
        self.render(
            resource_filename(__name__, 'index2.html'),
            title="Volta UI"
        )


if __name__ == '__main__':
    import logging
    logging.getLogger().setLevel(logging.DEBUG)

    router = TornadioRouter(MyConnection)
    static_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static')
    application = web.Application(
        router.apply_routes(
            [
                (r"/", IndexPage),
                (r"/static/(.*)", web.StaticFileHandler, {"path": static_path}),
            ]
        ),
        socket_io_port = 9998
    )
    socketio_server = SocketServer(application)

