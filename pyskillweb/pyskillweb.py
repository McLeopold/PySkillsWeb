from svana import Svana

app = Svana('/', db='/home/scott/test/config.sqlite')

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

