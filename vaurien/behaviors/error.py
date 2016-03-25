import os
import random

try:
    from http_parser.parser import HttpParser
except ImportError:
    from http_parser.pyparser import HttpParser

from vaurien.behaviors.dummy import Dummy
from vaurien.util import get_data


_ERRORS = {
    500: ("Internal Server Error",
          ('<p>The server encountered an internal error and was unable to '
           'complete your request.  Either the server is overloaded or there '
           'is an error in the application.</p>')),

    501: ("Not Implemented",
          ('<p>The server does not support the action requested by the '
           'browser.</p>')),

    502: ("Bad Gateway",
          ('<p>The proxy server received an invalid response from an upstream'
           ' server.</p>')),

    503: ("Service Unavailable",
          ('<p>The server is temporarily unable to service your request due '
           'to maintenance downtime or capacity problems.  Please try again '
           'later.</p>'))
}


_ERROR_CODES = _ERRORS.keys()

_TMP = """\
HTTP/1.1 %(code)s %(name)s
Content-Type: text/html; charset=UTF-8
Connection: close

<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
<title>%(code)s %(name)s</title>
<h1>%(name)s</h1>
%(description)s
"""


def random_http_error():
    data = {}
    data['code'] = code = random.choice(_ERROR_CODES)
    data['name'], data['description'] = _ERRORS[code]
    return _TMP % data


class Error(Dummy):
    """Reads the packets that have been sent then send back "errors".

    Used in cunjunction with the HTTP Procotol, it will randomly send back
    a 501, 502 or 503.

    For other protocols, it returns random data.

    The *inject* option can be used to inject data within valid data received
    from the backend. The Warmup option can be used to deactivate the random
    data injection for a number of calls. This is useful if you need the
    communication to settle in some speficic protocols before the random
    data is injected.

    The *inject* option is deactivated when the *http* protocol is used.
    """
    name = 'error'
    options = {'inject': ("Inject errors inside valid data", bool, False),
               'warmup': ("Number of calls before erroring out", int, 0)}
    options.update(Dummy.options)

    def __init__(self):
        super(Error, self).__init__()
        self.current = 0

    def on_before_handle(self, protocol, source, dest, to_backend):
        if self.current < self.option('warmup'):
            self.current += 1
            return super(Error, self).on_before_handle(protocol, source,
                                                       dest, to_backend)

        # read the data
        data = get_data(source)
        if not data:
            return False

        # error out
        if protocol.name in 'http' and to_backend:
            # we'll just send back a random error
            if self.option('inject'):
                self.inject(dest, to_backend, data, http=True)
                return True, True
            else:
                source.sendall(random_http_error())
                source.close()
                source._closed = True
                return False, False

        if self.option('inject'):
            self.inject(dest, to_backend, data, )
            return True, True

        else:
            if not to_backend:
                # XXX find how to handle errors (which errors should we send)
                # depends on the protocol
                dest.sendall(os.urandom(1000))

            else:          # sending the data tp the backend
                dest.sendall(data)
            return True, True

        return True, True

    def init(self):
        self.current = 0

    def inject(self, dest, to_backend, data, http=False):
        modified_data = data
        if http:
            # to_backend = not to_backend
            parser = HttpParser()
            parser.execute(data, len(data))

            query = parser.get_query_string()
            url = parser.get_url()
            body = parser.recv_body()
            if body:
                inject_in = body
            elif query:
                inject_in = query
            else:
                inject_in = url
            modified_data = data.replace(
                inject_in, "%s%s" % (inject_in, os.urandom(100))
            )

            # modified_data = data.replace(inject_in, new_inject_in)
        if not to_backend:      # back to the client
            middle = len(data) / 2
            modified_data = data[:middle] + os.urandom(100) + data[middle:]

        # sending the data tp the backend
        dest.sendall(modified_data)
