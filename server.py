"""
    The web server of Tic-Tac-Toe: one Game for up to MAX_PLAYERS players, state in memory, one process with one worker.
    Clients poll GET /state; a background loop calls Game.step. Run: python server.py
"""
import secrets
import threading
import time

from flask import Flask, jsonify, request

from game import MAX_PLAYERS, MAX_SIDE, SYMBOL_POOL, Game, min_side

COMPUTER_DELAY = 0.7    # seconds between two moves of computer players
TICK = 0.1              # seconds between two looks of the background loop
LOG_SIZE = 100          # messages kept for the clients
MAX_NAME = 20
PRESENCE_TIMEOUT = 5.0  # seconds without a request until a human counts as gone


class Refused(Exception):
    """
        A request the server does not accept, the message goes to the client with this status
    """

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Server:
    """
        people: token -> {'name', 'symbol', 'seat', 'seen'}, in the order of joining; seat is the name in the game, None for a watcher,
            seen is the time of the last request
        dropped: token -> {'name', 'symbol', 'seat'} of seated humans who are gone, so that they can take the seat back
        host: the token of the host (the first human in line), None if nobody is there
        setup: what the host chose for the next game (computers, z, side)
    """

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.people = {}
        self.dropped = {}
        self.host = None
        self.setup = {'computers': 0, 'z': 3, 'side': None}
        self.game = None
        self.version = 0
        self.log = []                       # (id, text), capped at LOG_SIZE
        self.next_id = 1
        self.last_move = 0.0                # when the last move was made, for the pace of the computers

    # helpers

    def changed(self):
        self.version += 1

    def say(self, text):
        self.log.append((self.next_id, text))
        self.next_id += 1
        del self.log[:-LOG_SIZE]

    def drain(self):
        """
            Moves the messages of the game into the log (the game list would grow without limit)
        """
        if self.game and self.game.messages:
            for text in self.game.messages:
                self.say(text)
            self.game.messages.clear()
            self.changed()

    def person(self, token):
        if token not in self.people:
            raise Refused("unknown token", 403)
        self.people[token]['seen'] = self.clock()
        return self.people[token]

    def require_host(self, token):
        self.person(token)
        if token != self.host:
            raise Refused("only the host may do this", 403)

    def taken_symbols(self, skip=None):
        symbols = {p['symbol'] for t, p in self.people.items() if t != skip}
        if self.game:
            symbols.update(self.game.symbols)
        return symbols

    def check_profile(self, name, symbol, skip=None):
        name = str(name or '').strip()
        symbol = str(symbol or '').strip()
        if not name or len(name) > MAX_NAME:
            raise Refused("name must have 1 to %d characters" % MAX_NAME)
        if not symbol or len(symbol) > 2 or symbol.isdigit():
            raise Refused("symbol must be 1 or 2 characters and not a number")
        if any(p['name'] == name for t, p in self.people.items() if t != skip):
            raise Refused("name is taken")
        if symbol in {p['symbol'] for t, p in self.people.items() if t != skip}:
            raise Refused("symbol is taken")
        return name, symbol

    def humans_seated(self):
        return self.game.humans if self.game else []

    def drop(self, token):
        """
            A human is gone (left or silent): the seat becomes a computer, the host moves on, nobody left pauses the game
        """
        who = self.people.pop(token)
        if self.game and who['seat'] in self.humans_seated():
            self.game.to_computer(who['seat'])
            self.dropped[token] = {'name': who['name'], 'symbol': who['symbol'], 'seat': who['seat']}
        self.say("%s left." % who['name'])
        self.drain()
        self.pass_host()
        if not self.people and self.game and self.game.state == 'playing':
            self.game.pause()
        self.changed()

    def pass_host(self):
        """
            The next human in line (seated first) becomes host, if the host is gone
        """
        if self.host in self.people:
            return
        seated = [t for t, p in self.people.items() if p['seat'] in self.humans_seated()]
        rest = list(self.people)
        self.host = (seated or rest or [None])[0]
        if self.host:
            self.say("%s is the host now." % self.people[self.host]['name'])

    # requests

    def join(self, data):
        token = data.get('token')
        if token and token in self.people:                  # editing name and symbol, only before the game
            if self.people[token]['seat']:
                raise Refused("the game has started")
            name, symbol = self.check_profile(data.get('name'), data.get('symbol'), token)
            self.people[token].update(name=name, symbol=symbol, seen=self.clock())
            self.changed()
            return {'token': token}
        gone = self.dropped.get(token)
        if gone:                                            # reconnect: the seat back, as long as the computer still has it
            self.check_profile(gone['name'], gone['symbol'])
            del self.dropped[token]
            self.people[token] = {'name': gone['name'], 'symbol': gone['symbol'], 'seat': None, 'seen': self.clock()}
            if self.game and gone['seat'] in self.game.computers:
                self.game.take_over(gone['seat'], gone['name'], gone['symbol'], self.clock())
                self.people[token]['seat'] = gone['name']
            self.say("%s is back." % gone['name'])
            if self.host is None:
                self.host = token
                self.say("%s is the host." % gone['name'])
            if self.game and self.game.state == 'paused':
                self.game.resume(self.clock())
            self.drain()
            self.changed()
            return {'token': token}
        name, symbol = self.check_profile(data.get('name'), data.get('symbol'))
        if len(self.people) + self.setup['computers'] >= MAX_PLAYERS and not self.game:
            raise Refused("the lobby is full")
        token = secrets.token_urlsafe(16)
        self.people[token] = {'name': name, 'symbol': symbol, 'seat': None, 'seen': self.clock()}
        self.say("%s joined." % name)
        if self.host is None:
            self.host = token
            self.say("%s is the host." % name)
        if self.game and self.game.state == 'paused':        # somebody is in the lobby again
            self.game.resume(self.clock())
        self.changed()
        return {'token': token}

    def start(self, data):
        """
            The host starts the first game, or a new game that replaces the current one (new: true), from everybody who is joined
        """
        self.require_host(data.get('token'))
        if self.game and not data.get('new'):
            raise Refused("a game exists, send new: true to replace it")
        try:
            computers = int(data.get('computers', self.setup['computers']))
            z = int(data.get('z', self.setup['z']))
            side = data.get('side', self.setup['side'])
            side = None if side in (None, '') else int(side)
            timeout = data.get('timeout')
            timeout = None if timeout in (None, '') else float(timeout)
        except (TypeError, ValueError):
            raise Refused("computers, z, side and timeout must be numbers")
        humans = list(self.people.items())
        n = len(humans) + computers
        if computers < 0 or n < 2 or n > MAX_PLAYERS:
            raise Refused("2 to %d players are needed" % MAX_PLAYERS)
        if z < 3:
            raise Refused("z must be at least 3")
        side = min_side(n, z) if side is None else side
        if side < min_side(n, z) or side > MAX_SIDE:
            raise Refused("side must be from %d to %d" % (min_side(n, z), MAX_SIDE))
        self.setup = {'computers': computers, 'z': z, 'side': side}
        players = [(p['name'], p['symbol']) for _, p in humans]
        names = {name for name, _ in players}
        free_symbols = [s for s in SYMBOL_POOL if s not in {symbol for _, symbol in players}]
        bots = []
        for i in range(computers):
            name = "Computer %d" % (i + 1)
            while name in names:
                name += "'"
            names.add(name)
            bots.append((name, free_symbols[i]))
        self.dropped.clear()
        self.game = Game(players + bots, [name for name, _ in bots], side, z, timeout)
        for _, p in humans:
            p['seat'] = p['name']
        self.game.start(self.clock())
        self.last_move = self.clock()
        self.say("A new game starts.")
        self.drain()
        self.changed()
        return {}

    def claim(self, data):
        """
            A joined human takes over a computer seat of the running game with their own name and symbol
        """
        token = data.get('token')
        who = self.person(token)
        if not self.game:
            raise Refused("no game yet")
        if who['seat']:
            raise Refused("you have a seat already")
        try:
            self.game.take_over(data.get('seat'), who['name'], who['symbol'], self.clock())
        except ValueError as error:
            raise Refused(str(error))
        who['seat'] = who['name']
        self.drain()
        self.pass_host()
        self.changed()
        return {}

    def queue(self, data):
        who = self.person(data.get('token'))
        if not self.game or not who['seat'] or who['seat'] in self.game.computers:
            raise Refused("you have no seat to move for")
        field = data.get('field')
        try:
            self.game.queue_move(who['seat'], None if field in (None, '') else int(field))
        except (TypeError, ValueError) as error:
            raise Refused(str(error))
        self.drain()
        self.changed()
        return {}

    def leave(self, data):
        token = data.get('token')
        self.person(token)
        self.drop(token)
        return {}

    def revanche(self, data):
        self.require_host(data.get('token'))
        if not self.game or self.game.state != 'over':
            raise Refused("no finished game")
        self.restart()
        return {}

    def restart(self):
        self.game.start(self.clock())
        self.last_move = self.clock()
        self.say("Revanche, the game starts again.")
        self.drain()
        self.changed()

    def state(self, token):
        who = self.people.get(token)
        if who:
            who['seen'] = self.clock()
        game = self.game
        result = {
            'version': self.version,
            'you': {'name': who['name'], 'symbol': who['symbol'], 'seat': who['seat'], 'host': token == self.host} if who else None,
            'people': [{'name': p['name'], 'symbol': p['symbol'], 'seat': p['seat'], 'host': t == self.host} for t, p in self.people.items()],
            'setup': self.setup,
            'messages': [{'id': i, 'text': text} for i, text in self.log[-30:]],
            'game': None,
        }
        if game:
            result['game'] = {
                'state': game.state, 'result': game.result, 'side': game.side, 'z': game.z, 'timeout': game.timeout,
                'players': [{'name': n, 'symbol': s, 'computer': n in game.computers, 'afk': n in game.afk, 'score': game.scores[n]}
                            for n, s in game.players],
                'draws': game.draws,
                'board': {str(k): v for k, v in game.board.items()},
                'order': game.order, 'turn': game.turn,
                'time_left': max(0.0, game.timeout - (self.clock() - game.turn_started)) if game.state == 'playing' else None,
                'queue': game.queue,
            }
        return result

    # the background loop

    def tick(self):
        """
            One look of the loop: silent humans are dropped, one move if one is due, and a new game when a finished game has no human left
            (a pause because nobody is in the lobby stays as it is)
        """
        now = self.clock()
        for token, who in list(self.people.items()):
            if now - who['seen'] > PRESENCE_TIMEOUT:
                self.drop(token)
        game = self.game
        if not game:
            return
        if game.state == 'playing':
            mover = game.order[game.turn]
            by_computer = mover in game.computers or mover in game.afk
            if not by_computer or now - self.last_move >= COMPUTER_DELAY:
                if game.step(now):
                    self.last_move = now
                    self.drain()
                    self.changed()
        elif game.state == 'over' and not game.humans and self.people and now - self.last_move >= COMPUTER_DELAY:
            self.restart()


def create_app(clock=time.monotonic, loop=True):
    app = Flask(__name__, static_folder='static', static_url_path='')
    server = Server(clock)
    app.server = server

    def handler(method):
        def view():
            try:
                with server.lock:
                    return jsonify(method(request.get_json(force=True, silent=True) or {}))
            except Refused as error:
                return jsonify({'error': str(error)}), error.status
        view.__name__ = method.__name__
        return view

    for name in ('join', 'start', 'claim', 'queue', 'leave', 'revanche'):
        app.add_url_rule('/' + name, name, handler(getattr(server, name)), methods=['POST'])

    @app.get('/')
    def index():
        return app.send_static_file('index.html')

    @app.get('/state')
    def state():
        with server.lock:
            return jsonify(server.state(request.args.get('token')))

    def run():
        while True:
            time.sleep(TICK)
            with server.lock:
                server.tick()

    if loop:
        threading.Thread(target=run, daemon=True).start()
    return app


if __name__ == '__main__':
    create_app().run(host='0.0.0.0', port=8080, threaded=True)
