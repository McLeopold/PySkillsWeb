from werkzeug.routing import Map, Rule, UnicodeConverter
from werkzeug.exceptions import HTTPException, InternalServerError, NotFound
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
from htmlr.environment import Environment

WSGI_FORMAT = 'HTTP/1.1 {status}\r\n{headers}\r\n\r\n{body}'
HTTP_FORMAT = 'HTTP/1.1 {status}\r\n{headers}{body}'

class UnquoteConverter(UnicodeConverter):

    def to_python(self, value):
        return url_unquote_plus(value)

class HTMLResponse(BaseResponse):
    default_mimetype = 'text/html'

class JSONResponse(BaseResponse):
    default_mimetype = 'application/json; charset=utf-8'

class SvanaConnection(Connection):

    def __init__(self, sender_id, sub_addr, pub_addr, host='localhost', port=8000):
        super(SvanaConnection, self).__init__(sender_id, sub_addr, pub_addr)
        self.host = host
        self.port = port

    def recv(self):
        req_str = self.reqs.recv()
        print(req_str)
        return Request.parse(req_str)

    def reply_wsgi(self, req, app, environ=None):
        # setup wsgi environment & response callable
        if environ is None:
            environ = {'SERVER_NAME': self.host,
                       'SERVER_PORT': str(self.port),
                       'REQUEST_URI': req.path,
                       'REQUEST_METHOD': req.headers.get('METHOD', 'GET'),
                       'QUERY_STRING': req.headers.get('QUERY', ''),
                       'wsgi.url_scheme': 'http',
                       'wsgi.errors': sys.stdout,
                       'wsgi.input': StringIO(req.body),
                       'svana.req': req}
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
        print(response)
        self.reply(req, response)
        self.close(req)

    def reply_http(self, req, res):
        'Pull the response out of the werkzeug Response object with WSGI overhead'
        payload = {'status': res.status,
                   'headers': res.headers,
                   'body': res.data}
        response = HTTP_FORMAT.format(**payload)
        print(response)
        self.reply(req, response)
        self.close(req)


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
                 port=8000,
                 db='config.sqlite',
                 default_methods=None,
                 debug=False,
                 template_path=None,
                 template_environment=None):
        self.url_map = Map(converters={'default': UnquoteConverter})
        self.url_adapter = self.url_map.bind('{0}:{1}'.format(host, port))
        self.default_methods = default_methods or ['GET']
        self.endpoint_lookup = {}
        self.sender_id = sender_id or uuid4().hex
        if isinstance(route, (str, unicode)):
            route = self.get_pub_sub(route, db)
        self.pub, self.sub = route
        self.debug = debug
        self.host = host
        self.port = port
        if template_path:
            if template_environment is None:
                self.templates = Environment(template_path)
            else:
                self.templates = template_environment(template_path)
        else:
            self.templates = None

    def render_template(self, name, *datalist, **datadict):
        if self.templates:
            t = self.templates.get_template(name)
            datalist = list(datalist)
            while True:
                try:
                    r = t.render(*datalist, **datadict)
                except KeyError as exc:
                    print(exc)
                    print(exc.message)
                    datadict[exc.message] = ''
                    print(datadict)
                except IndexError as exc:
                    print(exc)
                    datalist.append('')
                    print(datalist)
                else:
                    break

            return HTMLResponse(r)
        else:
            raise NotFound

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
        conn = SvanaConnection(self.sender_id, self.pub, self.sub, self.host, self.port)
        if self.debug:
            def app(environ, start_response):
                try:
                    result = self.dispatch(environ['svana.req'])
                except HTTPException as exc:
                    result = exc
                return result(environ, start_response)
            app = DebuggedApplication(app, evalex=True, lodgeit_url=None)
            while True:
                print('waiting for request')
                req = conn.recv()
                if req.is_disconnect():
                    continue
                print('received {0}{1} {2}'.format(req.path,
                                                   req.headers.get('QUERY', None),
                                                   req.headers.get('METHOD', None)))
                try:
                    print('start WSGI')
                    conn.reply_wsgi(req, app)
                    print('end WSGI')
                except HTTPException as e:
                    print('failing debug mode')
                    print('{req.sender} {req.path} {req.conn_id} - {error}\n'.format(req=req, error=e))
                    conn.reply_wsgi(req, e)
        else:
            while True:
                req = conn.recv()
                if req.is_disconnect():
                    continue
                try:
                    res = self.dispatch(req)
                    conn.reply_http(req, res)
                except HTTPException as e:
                    conn.reply_wsgi(req, e)
                except Exception as e:
                    print(e)
                    conn.reply_wsgi(req, InternalServerError())

