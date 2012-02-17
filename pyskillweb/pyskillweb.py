from werkzeug.routing import Map, Rule, BuildError
from werkzeug.urls import url_quote
from mongrel2.handler import Connection
from uuid import uuid4

class Svana():

    def __init__(self, sub, pub,
                 sender_id=None,
                 host='localhost',
                 default_methods=None):
        self.mongrel_db = None
        self.url_map = Map()
        self.url_adapter = self.url_map.bind(host)
        self.default_methods = default_methods or ['GET']
        self.sender_id = sender_id or uuid4().hex
        self.sub = sub
        self.pub = pub
        
    def route(self, url, methods=None):
        def hitch(obj):
            route_methods = methods
            if methods is None:
                if hasattr(obj, '__call__'):
                    route_methods = self.default_methods
                    print('decorating function {0}'.format(route_methods))
                else:
                    route_methods = [prop for prop in obj.__dict__
                                     if hasattr(getattr(obj, prop), '__call__')]
                    print('decorating class {0}'.format(route_methods))
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
        endpoint, arguments = self.url_adapter.match(path_info, method)
        print(endpoint, method)
        if hasattr(endpoint, '__call__'):
            return endpoint(**arguments)
        else:
            endpoint_class = endpoint()
            return getattr(endpoint_class, method.lower())(**arguments)
        
    def run(self):
        conn = Connection(self.sender_id, self.sub, self.pub)
        while True:
            print("WAITING FOR REQUEST...")
            req = conn.recv()
            res = self.dispatch(req.path, req.headers.get('method', 'get'))
            print(res)
            conn.reply_http(req, res)
        
app = Svana("tcp://127.0.0.1:9997",
            "tcp://127.0.0.1:9996")

@app.route('/<name>')
class HomePage():

    def get(self, name):
        return "Hello World {0}".format(name)
        
    def post(self, name):
        return "Goodbye World {0}".format(name)


class API():

    @app.route('/api', ['GET'])
    def get(self):
        return "Hello World"
        
    @app.route('/api', ['POST'])
    def post(self):
        return "Goodbye World"
        
        
@app.route('/test/<name>')
def test(name):
    return 'test {0}'.format(name)

if __name__ == '__main__':        
    try:
        app.run()
    except KeyboardInterrupt:
        print('shutting down...')

