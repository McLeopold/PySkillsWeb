from svana import Svana

app = Svana('/',
            db='/home/scott/test/config.sqlite',
            host='172.16.0.9',
            port=8000,
            template_path='templates',
            debug=True)

def make_id_gen(name):
    if name not in make_id_gen.data:
        make_id_gen.data[name] = 0
    def get_id():
        make_id_gen.data[name] += 1
        return str(make_id_gen.data[name])
    return get_id
make_id_gen.data = {}

next_contest_id = make_id_gen('contest')

class Contests(dict):
    def new_contest(self):
        pass
    def data(self):
        return {'fields': ('contest_id', 'name', 'link'),
                'values': [(c.contest_id, c.name, c.link())
                           for c in self.values()]}

class Contest(object):
    def __init__(self, contest_id, name):
        self.contest_id = contest_id
        self.name = name
        self.players = Players(self)
        self.games = Games(self)
        self.next_game_id = make_id_gen('game:' + self.contest_id)
    def link(self):
        return app.url_for(ContestRoute.get,
                           contest_id=self.contest_id)
    def new_player(self, player_id):
        if player_id not in self.players:
            self.players[player_id] = Player(self, player_id)
    def post_game(self, data):
        game_id = self.next_game_id()
        self.games[game_id] = Game(self, game_id, data)
    def data(self):
        return {'contest_id': self.contest_id,
                'name': self.name,
                'link': app.url_for(ContestRoute.get,
                                    contest_id=self.contest_id),
                'players': app.url_for(PlayersRoute.get,
                                       contest_id=self.contest_id),
                'games': app.url_for(GamesRoute.get,
                                     contest_id=self.contest_id)}

class Players(dict):
    def __init__(self, contest):
        self.contest = contest
    def data(self):
        return {'count': len(self),
                'players': {key: app.url_for(PlayerRoute.get,
                                             contest_id=self.contest.contest_id,
                                             player_id=key)
                            for key in self}}

class Player(object):
    def __init__(self, contest, player_id):
        self.contest = contest
        self.player_id = player_id
    def data(self):
        return {'player_id': self.player_id,
                'link': app.url_for(PlayerRoute.get,
                                    contest_id=self.contest.contest_id,
                                    player_id=self.player_id)}

class Games(dict):
    def __init__(self, contest):
        self.contest = contest
    def data(self):
        return {'count': len(self),
                'games': {key: app.url_for(GameRoute.get,
                                           contest_id=self.contest.contest_id,
                                           game_id=key)}}

class Game(object):
    def __init__(self, contest, game_id, data):
        self.contest = contest
        self.game_id = game_id
        self.data = data
    def data(self):
        return {'game_id': self.game_id,
                'link': app.url_for(GameRoute.get,
                                    contest_id=self.contest.contest_id,
                                    game_id=self.game_id),
                'data': data}

contests = Contests()
sample_contest = Contest('0', u'\u2126sample')
sample_contest.new_player(u'b\u00f8b')
contests[sample_contest.contest_id] = sample_contest

@app.route_json('/contests/')
class ContestsRoute(object):

    def get(self, req):
        'Get list of contests'
        return contests.data()
        return {key: app.url_for(ContestRoute.get, contest_id=key)
                           for key in contests}

    def post(self, req):
        'Create new contest with name'
        contest_id = next_contest_id()
        contests[contest_id] = Contest(contest_id, req.json['name'])
        return {contest_id: app.url_for(ContestRoute.get, contest_id=contest_id)}

@app.route_json('/contests/<contest_id>')
class ContestRoute(object):

    def get(self, req, contest_id):
        'Get contest info'
        contest = contests[contest_id]
        return contest.data()


@app.route_json('/contests/<contest_id>/players/')
class PlayersRoute(object):

    def get(self, req, contest_id):
        contest = contests[contest_id]
        return contest.players.data()

    def put(self, req, contest_id):
        'Create new player in contest'
        contest = contests[contest_id]
        player_id = req.json['player_id']
        if player_id not in contest.players:
            contest.new_player(player_id)
        return contest.players[player_id].data()

@app.route_json('/contests/<contest_id>/players/<player_id>')
class PlayerRoute(object):

    def get(self, req, contest_id, player_id):
        contest = contests[contest_id]
        player = contest.players[player_id]
        return player.data()

@app.route_json('/contests/<contest_id>/games/')
class GamesRoute(object):

    def get(self, req, contest_id):
        contest = contests[contest_id]
        return contest.games.data()

@app.route_json('/contests/<contest_id>/games/<game_id>')
class GameRoute(object):

    def get(self, req, contest_id, game_id):
        contest = contests[contest_id]
        game = contest.games[game_id]
        return game.data()

@app.route_json('/api')
def list_routes(req):
    routes = []
    for rule in app.url_map.iter_rules():
        if 'GET' in rule.methods:
            try:
                routes.append(app.url_for(rule.endpoint))
            except:
                pass
    return routes

@app.route('/')
def main(req):
    return app.render_template('layout')

if __name__ == '__main__':
    for rule in app.url_map.iter_rules():
        print(rule)
    try:
        app.run()
    except KeyboardInterrupt:
        print('shutting down...')
