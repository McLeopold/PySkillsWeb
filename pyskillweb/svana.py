from werkzeug.routing import Map, Rule, UnicodeConverter
from werkzeug.exceptions import HTTPException, InternalServerError
from werkzeug.urls import url_quote, url_unquote_plus
from werkzeug.debug import DebuggedApplication
from werkzeug.wrappers import BaseRequest, BaseResponse
from mongrel2.handler import Connection
from mongrel2.request import Request
from mongrel2.config import model
from uuid import uuid4
import sys
import types
from cStringIO import StringIO
import json

WSGI_FORMAT = 'HTTP/1.1 {status}\r\n{headers}\r\n\r\n{body}'

class UnquoteConverter(UnicodeConverter):

    def to_python(self, value):
        return url_unquote_plus(value)

class JSONResponse(BaseResponse):
    default_mimetype = 'application/json; charset=utf-8'

class SvanaConnection(Connection):
    def recv(self):
        req_str = self.reqs.recv()
        #print(req_str)
        return Request.parse(req_str)

    def reply_wsgi(self, req, app, environ=None):
        # setup wsgi environment & response callable
        if environ is None:
            environ = {'REQUEST_URI': req.path,
                       'REQUEST_METHOD': req.headers.get('METHOD', 'HEAD'),
                       'QUERY_STRING': req.headers.get('QUERY', ''),
                       'wsgi.errors': sys.stdout,
                       'wsgi.input': StringIO(req.body)}
        payload = {'status': None,
                   'headers': None}
        body = []
        def start_response(status, headers):
            payload['status'] = status
            payload['headers'] = headers
            return body.append
        # call app
        app_iter = app(environ, start_response)
        try:
            for item in app_iter:
                body.append(item)
        finally:
            if hasattr(app_iter, 'close'):
                app_iter.close()
        # format response
        payload['body'] = ''.join(body)
        payload['headers'] = '\r\n'.join('{0}: {1}'.format(k, v)
                                         for k, v in payload['headers'])
        response = WSGI_FORMAT.format(**payload)
        self.reply(req, response)

class SvanaDebugged(DebuggedApplication):
    def __call__(self, environ, start_response):
        """Dispatch the requests."""
        # important: don't ever access a function here that reads the incoming
        # form data!  Otherwise the application won't have access to that data
        # any more!
        request = BaseRequest(environ)
        response = self.debug_application
        if request.args.get('__debugger__') == 'yes':
            cmd = request.args.get('cmd')
            arg = request.args.get('f')
            secret = request.args.get('s')
            traceback = self.tracebacks.get(request.args.get('tb', type=int))
            frame = self.frames.get(request.args.get('frm', type=int))
            if cmd == 'resource' and arg:
                response = self.get_resource(request, arg)
            elif (cmd == 'paste' and traceback is not None 
                    and secret == self.secret):
                response = self.paste_traceback(request, traceback)
            elif cmd == 'source' and frame and self.secret == secret:
                response = self.get_source(request, frame)
            elif (self.evalex and cmd is not None and frame is not None and
                    self.secret == secret):
                response = self.execute_command(request, cmd, frame)
        elif (self.evalex and self.console_path is not None and
                request.path == self.console_path):
            response = self.display_console(request)
        return response(environ, start_response)

class Svana():

    def __init__(self, route,
                 sender_id=None,
                 host='localhost',
                 db='config.sqlite',
                 default_methods=None,
                 debug=False):
        self.url_map = Map(converters={'default': UnquoteConverter})
        self.url_adapter = self.url_map.bind(host)
        self.default_methods = default_methods or ['GET']
        self.endpoint_lookup = {}
        self.sender_id = sender_id or uuid4().hex
        if isinstance(route, (str, unicode)):
            route = self.get_pub_sub(route, db)
        self.pub, self.sub = route
        self.debug = debug

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

    def route(self, url, methods=None, wrapper=None):
        def hitch(obj):
            if isinstance(obj, types.FunctionType):
                route_methods = methods or self.default_methods
                endpoint = wrapper(obj) if wrapper else obj
                self.endpoint_lookup[obj] = endpoint
                self.url_map.add(Rule(url, endpoint=endpoint, methods=route_methods))
            else:
                for prop in list(obj.__dict__.keys()):
                    method = getattr(obj, prop)
                    if hasattr(method, '__call__'):
                        def instantiator(req, prop=prop, *args, **kwds):
                            instance = obj()
                            return getattr(instance, prop)(req, *args, **kwds)
                        endpoint = wrapper(instantiator) if wrapper else instantiator
                        self.url_map.add(Rule(url, endpoint=endpoint, methods=[prop]))
                        self.endpoint_lookup[method] = endpoint
            return obj
        return hitch

    def route_json(self, url, methods=None):
        def json_wrapper(fn):
            def go(req, *args, **kwds):
                req.json = json.loads(req.body) if req.body else None
                res = fn(req, *args, **kwds)
                return JSONResponse(json.dumps(res, ensure_ascii=False))
            return go
        return self.route(url, methods, json_wrapper)

    def url_for(self, endpoint, method=None, external=False,
                append_unknown=True, anchor=None, **values):
        if endpoint not in self.url_map._rules_by_endpoint:
            # check for method
            if endpoint in self.endpoint_lookup:
                endpoint = self.endpoint_lookup[endpoint]
            # check for unbound method
            elif hasattr(endpoint, 'im_class'):
                endpoint = endpoint.im_class.__dict__[endpoint.__name__]
        print('building for {0} values {1}'.format(endpoint, values))
        rv = self.url_adapter.build(endpoint, values,
                                    method=method,
                                    force_external=external,
                                    append_unknown=append_unknown)
        if anchor is not None:
            rv += '#' + url_quote(anchor)
        return rv
        
    def dispatch(self, req):
        path = req.path
        method = req.headers.get('METHOD', 'HEAD')
        for key, value in req.headers.items():
            print(key, value)
        print('dispatching {0} {1} ... '.format(path, method))
        if req.body:
            print(req.body)
        endpoint, arguments = self.url_adapter.match(path, method)
        print('found endpoint {0}'.format(endpoint))
        result = endpoint(req, **arguments)
        if not isinstance(result, BaseResponse):
            result = BaseResponse(result)
        return result

    def run(self):
        # setup debugging if needed
        conn = SvanaConnection(self.sender_id, self.pub, self.sub)
        if self.debug:
            def app(environ, start_response):
                result = self.dispatch(req)
                return result(environ, start_response)
            app = SvanaDebugged(app, evalex=True)
            while True:
                req = conn.recv()
                try:
                    conn.reply_wsgi(req, app)
                except HTTPException as e:
                    print('failing debug mode')
                    print('{req.sender} {req.path} {req.conn_id} - {error}\n'.format(req=req, error=e))
                    conn.reply_wsgi(req, e)
        else:
            while True:
                req = conn.recv()
                try:
                    res = self.dispatch(req)
                    conn.reply_wsgi(req, res)
                except HTTPException as e:
                    conn.reply_wsgi(req, e)
                except Exception as e:
                    print(e)
                    conn.reply_wsgi(req, InternalServerError())

