from werkzeug.routing import Map, Rule
from werkzeug.exceptions import HTTPException, abort
from werkzeug.urls import url_quote
from werkzeug.debug import DebuggedApplication
from mongrel2.handler import Connection
from mongrel2.request import Request
from mongrel2.config import model
from uuid import uuid4
import sys

WSGI_FORMAT = 'HTTP/1.1 {status}\r\n{headers}\r\n\r\n{body}'

class SvanaConnection(Connection):
    def recv(self):
        req_str = self.reqs.recv()
        print(req_str)
        return Request.parse(req_str)

    def reply_wsgi(self, req, app, environ=None):
        # setup wsgi environment & response callable
        if environ is None:
            environ = {'REQUEST_METHOD': req.headers['METHOD'],
                       'QUERY_STRING': req.headers.get('QUERY', ''),
                       'wsgi.errors': None}
        payload = {'status': None,
                   'headers': None}
        body = []
        def start_response(status, headers):
            payload['status'] = status
            payload['headers'] = headers
            return body.append
        # call app
        app = DebuggedApplication(app, show_hidden_frames=True)
        app_iter = app(environ, start_response)
        try:
            for item in app_iter:
                body.append(item)
        finally:
            if hasattr(app_iter, 'close'):
                app_iter.close()
        # format response
        payload['body'] = ''.join(body)
        header_keys = set(key.lower() for key, value in payload['headers'])
        if 'content-length' not in header_keys:
            payload['headers'].append(('Content-Length', len(payload['body'])))    
        payload['headers'] = '\r\n'.join('{0}: {1}'.format(k, v)
                                         for k, v in payload['headers'])
        response = WSGI_FORMAT.format(**payload)
        self.reply(req, response)

class Svana():

    def __init__(self, route,
                 sender_id=None,
                 host='localhost',
                 db='config.sqlite',
                 default_methods=None):
        self.mongrel_db = None
        self.url_map = Map()
        self.url_adapter = self.url_map.bind(host)
        self.default_methods = default_methods or ['GET']
        self.sender_id = sender_id or uuid4().hex
        if isinstance(route, (str, unicode)):
            route = self.get_pub_sub(route, db)
        self.pub, self.sub = route
        
    def get_pub_sub(self, route, db=None):
        if db is None:
            db = 'config.sqlite'
        store = model.begin(db)
        routes = store.find(model.Route, model.Route.path == unicode(route))
        if routes.count() == 1:
            target = routes.one().target
            try:
                return target.send_spec, target.recv_spec
            except AttributeError:
                raise Exception('route.target is not a mongrel2 handler: {0}'
                                .format(target))
        else:
            raise Exception('route is not unique: {0}'.format(', '.join()))

    def route(self, url, methods=None):
        def hitch(obj):
            route_methods = methods
            if methods is None:
                if hasattr(obj, '__call__'):
                    route_methods = self.default_methods
                else:
                    route_methods = [prop for prop in obj.__dict__
                                     if hasattr(getattr(obj, prop), '__call__')]
            self.url_map.add(Rule(url,
                                  endpoint=obj,
                                  methods=route_methods))
            return obj
        return hitch

    def url_for(self, endpoint, method=None, external=False,
                append_unknown=True, anchor=None, **values):
        if endpoint not in self.url_map._rules_by_endpoint:
            # check for unbound method
            if hasattr(endpoint, 'im_class'):
                endpoint = endpoint.im_class.__dict__[endpoint.__name__]
        rv = self.url_adapter.build(endpoint, values,
                                    method=method,
                                    force_external=external,
                                    append_unknown=append_unknown)
        if anchor is not None:
            rv += '#' + url_quote(anchor)
        return rv
        
    def dispatch(self, path_info=None, method=None):
        def app(environ, start_response):
            print('dispatching {0} {1}...'.format(path_info, method))
            endpoint, arguments = self.url_adapter.match(path_info, method)
            print('found endpoint {0}\n'.format(endpoint))
            try:
                start_response('200 OK', [])
                if hasattr(endpoint, '__call__'):
                    return [endpoint(**arguments)]
                else:
                    endpoint_class = endpoint()
                    return [getattr(endpoint_class, method.lower())(**arguments)]
            except TypeError:
                print('failed to call endpoint')
                #abort(500)
                raise
        return DebuggedApplication(app)

    def run(self):
        conn = SvanaConnection(self.sender_id, self.pub, self.sub)
        while True:
            print("WAITING FOR REQUEST...")
            req = conn.recv()
            if req.should_close():
                print("DISCONNECT")
                continue
            try:
                app = self.dispatch(req.path, req.headers.get('method', 'get')) or ''
                conn.reply_wsgi(req, app)
#                print(res)
#                conn.reply_http(req, res)
            except HTTPException as e:
                print('{req.sender} {req.path} {req.conn_id} - {error}\n'.format(req=req, error=e))
                conn.reply_wsgi(req, e)

