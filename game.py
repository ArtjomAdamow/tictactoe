"""
    The rules and the computer player of Tic-Tac-Toe, with no input, output or waiting.
    A Game holds the whole state of one session, the clients (terminal, later the web server) call its methods.
"""
import math
import random
import time
from functools import lru_cache

SYMBOL_POOL = "#@%&*+$~^?!=<>ABCDEFGHJKLMNOPQRSTUVWXYZ"
MAX_PLAYERS = 12
MAX_SIDE = 30           # the largest board side the web server accepts, also the limit for stored simulations
MAX_TIMEOUT = 60        # seconds, the longest a human may take for a move in the turn engine, also the default
GAMBLE_MIN = 0.1        # the smallest share of the gamble chance that stays even when blocking costs nothing
RELIABILITY = {True: 0.9, False: 0.6}       # how likely a computer / a human blocks a threat for somebody else
SCORE_EAGERNESS = 0.7   # how much a leader's score takes from the gamble chance, only for threats that wait for the next round


def min_side(n, z, step=None, margin=None):
    """
        Minimum side of the board for n players and the winning condition z:
        z + (n - 2) * step, but at least z + margin
        Defaults: step = z - 2, margin = 1 for z > 3 (0 for z = 3, which keeps the classic 3x3)
        None means the default
    """
    step = z - 2 if step is None else step
    margin = (1 if z > 3 else 0) if margin is None else margin
    return max(z + (n - 2) * step, z + margin)

@lru_cache(maxsize=None)
def window_keys(side, length):
    """
        All lines of `length` consecutive fields (rows, columns, both diagonals) as tuples of dictionary keys
    """
    windows = []
    for row in range(side):
        for col in range(side):
            for d_row, d_col in ((0, 1), (1, 0), (1, 1), (1, -1)):
                end_row, end_col = row + (length - 1) * d_row, col + (length - 1) * d_col
                if 0 <= end_row < side and 0 <= end_col < side:
                    windows.append(tuple((row + i * d_row) * side + col + i * d_col + 1 for i in range(length)))
    return windows

def board_generator(side):
    """
        Generates the board as a dictionary with a key list from 1 to side^2 and fills values to serve as coordinates
    """
    return {field: str(field) for field in range(1, side ** 2 + 1)}


class Game:
    """
        One session: players, board, scores and the messages the clients should show
        players: list of (name, symbol), computers: the names of the computer players, side: board side, z: winning condition
        A symbol may be any text that is not a field number, a field is free while its value is not a symbol
    """

    def __init__(self, players, computers, side, z, timeout=MAX_TIMEOUT):
        self.players = list(players)
        self.computers = set(computers)
        self.side = side
        self.z = z
        self.timeout = min(timeout or MAX_TIMEOUT, MAX_TIMEOUT)     # seconds a human has for a move before the computer makes it, never unlimited
        self.afk = set()                # humans who missed the timeout, the computer moves for them at once until they act again
        self.scores = {name: 0 for name, _ in self.players}
        self.draws = 0                  # how many rounds ended in a draw
        self.messages = []              # collected here, the client shows them and clears the list
        self.board = {}
        self.state = 'lobby'            # 'lobby', 'playing', 'paused', 'over', see the turn engine
        self.result = ''                # of the last finished round: the winner's name or 'draw'
        self.order = []                 # the names in the order of the current round
        self.turn = 0                   # index in order of the player who moves now
        self.turn_started = 0.0         # clock time (see step) when that turn began
        self.queue = {}                 # name -> field a human wants to take when the turn comes
        self.new_round()

    @property
    def symbols(self):
        return [symbol for _, symbol in self.players]

    def say(self, *parts):
        self.messages.append(' '.join(str(part) for part in parts))

    def new_round(self):
        """
            Clears the board for the next round, the scores stay
        """
        self.board = board_generator(self.side)

    def symbol_of(self, name):
        return dict(self.players)[name]

    def free_fields(self):
        """
            The keys of all fields without a symbol
        """
        symbols = self.symbols
        return [k for k, value in self.board.items() if value not in symbols]

    def place(self, name, field, later=()):
        """
            The player puts the symbol on a free field (later = names still to move after this player in this round)
            Returns the result of the move: the name of the winner, 'draw' when winning is impossible for everybody, else ''
            A finished round updates the scores and the draws
        """
        if field not in self.free_fields():
            raise ValueError("field %r is not free" % (field,))
        symbol = self.symbol_of(name)
        self.board[field] = symbol
        self.say("Excellent, '%s' put on field: %d" % (symbol, field))
        result = name if self.has_line(symbol) else self.draw_checker(later)
        if result == 'draw':
            self.draws += 1
        elif result:
            self.scores[result] += 1
        return result

    def has_line(self, symbol):
        """
            True if the symbol holds z consecutive fields in a row, a column or a diagonal
        """
        return any(all(self.board[k] == symbol for k in keys) for keys in window_keys(self.side, self.z))

    def draw_checker(self, pending=None):
        """
            Checks if winning is impossible on the current board
            pending: names still to move in the current round (default: all), the order of the next rounds is random
            A player can only win with a line that holds no other symbol and whose empty fields
            he can still fill: he moves once per round, so with e empty fields he gets at most one move
            in the current round (if pending) and one in each of the following rounds (n moves each).
            That is an upper bound, so a 'draw' is always a real one.
            If nobody has such a line it returns 'draw', else ''
        """
        symbols = self.symbols
        empty = sum(1 for value in self.board.values() if value not in symbols)
        n = len(self.players)
        pending = [name for name, _ in self.players] if pending is None else pending
        after_round = max(0, empty - len(pending))
        for name, symbol in self.players:
            moves = (1 if name in pending and empty > 0 else 0) + (after_round + n - 1) // n        # the fields this player still gets to fill
            for keys in window_keys(self.side, self.z):
                cells = [self.board[k] for k in keys]
                if all(c == symbol or c not in symbols for c in cells) and sum(c not in symbols for c in cells) <= moves:
                    return ''                              # this player can still win
        return 'draw'

    # turn engine (for clients that cannot block on input, the terminal client does not use it)

    @property
    def humans(self):
        return [name for name, _ in self.players if name not in self.computers]

    def start(self, now=None):
        """
            Starts a game from the lobby, or the revanche after 'over': empty board, new order, scores stay
            A human who is still AFK counts as dropped out: their seat stays a computer
        """
        for name in sorted(self.afk):
            self.to_computer(name)
        self.new_round()
        self.queue = {}
        self.result = ''
        self.state = 'playing'
        self.next_round(now)

    def next_round(self, now=None):
        """
            A new random order of all players, the board stays
        """
        self.order = [name for name, _ in self.players]
        random.shuffle(self.order)
        self.turn = 0
        self.turn_started = time.monotonic() if now is None else now

    def touch(self, name):
        """
            The human acted (any key, any request): no longer AFK
        """
        if name in self.afk:
            self.afk.discard(name)
            self.say("Player %s is back." % name)

    def queue_move(self, name, field):
        """
            A human sends a field at any time, it is taken when the turn comes if it is still free (field None clears it)
        """
        if name not in dict(self.players) or name in self.computers:
            raise ValueError("%r is not a human player" % (name,))
        if field is not None and field not in self.free_fields():
            raise ValueError("field %r is not free" % (field,))
        self.touch(name)
        if field is None:
            self.queue.pop(name, None)
        else:
            self.queue[name] = field

    def step(self, now=None):
        """
            Advances the game by one move if there is one to make, else changes nothing and returns False
            - a computer moves at once (the pace is the caller's business)
            - a human moves with the queued field; without one the turn waits, until the timeout lets the computer logic move for them
            - a human who missed the timeout is AFK: the computer logic moves for them at once, until `touch` or `queue_move`
            Needs the state 'playing'; `now` is a clock in seconds (default time.monotonic), to test with scripted time
        """
        if self.state != 'playing':
            return False
        now = time.monotonic() if now is None else now
        name = self.order[self.turn]
        if name in self.computers:
            field = self.computer_pick(name, self.order[self.turn + 1:])
        elif name in self.queue:
            field = self.queue[name]
        elif name in self.afk:
            field = self.computer_pick(name, self.order[self.turn + 1:])
        elif now - self.turn_started >= self.timeout:
            field = self.computer_pick(name, self.order[self.turn + 1:])
            self.say("%s: The party moves on, the computer made your move." % name)
            self.afk.add(name)
            self.say("Player %s seems to be AFK." % name)
        else:
            return False
        self.queue.pop(name, None)
        self.result = self.place(name, field, self.order[self.turn + 1:])
        if self.result:
            self.state = 'over'
            self.queue = {}
            return True
        for other, queued in list(self.queue.items()):      # fields that are taken now are dropped
            if queued not in self.free_fields():
                del self.queue[other]
        self.turn += 1
        self.turn_started = now
        if self.turn == len(self.order):
            self.next_round(now)
        return True

    def pause(self):
        if self.state == 'playing':
            self.state = 'paused'

    def resume(self, now=None):
        """
            Continues a paused game, the running turn gets its whole time again
        """
        if self.state == 'paused':
            self.state = 'playing'
            self.turn_started = time.monotonic() if now is None else now

    def to_computer(self, name):
        """
            The seat of a human goes on as a computer player (dropout)
        """
        if name not in dict(self.players):
            raise ValueError("%r is not a player" % (name,))
        if name not in self.computers:
            self.computers.add(name)
            self.queue.pop(name, None)
            self.afk.discard(name)
            self.say("Player %s dropped out, the computer took over." % name)

    def take_over(self, seat, name, symbol, now=None):
        """
            A human takes the seat of a computer player with their own name and symbol, scores and turn stay with the seat
        """
        if seat not in self.computers:
            raise ValueError("%r is not a computer seat" % (seat,))
        others = [(n, s) for n, s in self.players if n != seat]
        if any(name == n for n, _ in others) or any(symbol == s for _, s in others) or symbol.strip().isdigit():
            raise ValueError("name or symbol is taken")
        old_symbol = self.symbol_of(seat)
        self.players = [(name, symbol) if n == seat else (n, s) for n, s in self.players]
        self.computers.discard(seat)
        self.afk.discard(seat)
        self.scores = {(name if n == seat else n): v for n, v in self.scores.items()}
        self.order = [name if n == seat else n for n in self.order]
        self.board = {k: (symbol if v == old_symbol else v) for k, v in self.board.items()}
        self.turn_started = time.monotonic() if now is None else now
        self.say("%s took over the seat of computer %s." % (name, seat))

    # computer player

    def open_windows(self, symbol):
        """
            The lines (see window_keys) that hold no other symbol than the given one, so the player can still win with them
            Returns tuples of (keys, own symbols in the line, keys of the empty fields)
        """
        symbols = self.symbols
        result = []
        for keys in window_keys(self.side, self.z):
            cells = [self.board[k] for k in keys]
            if all(c == symbol or c not in symbols for c in cells):
                result.append((keys, sum(c == symbol for c in cells), [k for k, c in zip(keys, cells) if c not in symbols]))
        return result

    def win_cells(self, symbol):
        """
            The fields that complete a line for the symbol right now
        """
        return {empty[0] for _, _, empty in self.open_windows(symbol) if len(empty) == 1}

    def cell_scores(self, symbol):
        """
            Rates every free field for the symbol:
            every open line through the field counts 3 ** own symbols in it, so a field in many and well filled lines is strategic
            a field that brings two or more lines one step before the win (a fork) gets a bonus
            the open lines of the opponents count half, so a field that spoils them is a little better
        """
        scores = dict.fromkeys(self.free_fields(), 0.0)
        forks = dict.fromkeys(scores, 0)
        for _, own, empty in self.open_windows(symbol):
            for k in empty:
                scores[k] += 3 ** own
                if own == self.z - 2:
                    forks[k] += 1
        for _, other_symbol in self.players:
            if other_symbol != symbol:
                for _, own, empty in self.open_windows(other_symbol):
                    for k in empty:
                        scores[k] += 0.5 * 3 ** own
        for k, count in forks.items():
            if count >= 2:
                scores[k] += 50 * (count - 1)
        return scores

    def best_cell(self, cells, symbol):
        """
            The best rated of the cells, a random one of the equally good
        """
        scores = self.cell_scores(symbol)
        top = max(scores[c] for c in cells)
        return random.choice([c for c in cells if scores[c] == top])

    def score_excess(self, name):
        """
            How far the player is above the average score, from 0 (average or below) to 1 (has all the points)
        """
        total = sum(self.scores.values())
        if total == 0 or len(self.scores) < 2:
            return 0.0
        return max(0.0, self.scores[name] * len(self.scores) / total - 1) / (len(self.scores) - 1)

    def gamble_chance(self, symbol, threats, later):
        """
            How likely the computer leaves the threats (field -> names of the players who win there) to the players behind it
            0 means it must block. Otherwise: p_gamble = p_cover * (GAMBLE_MIN + (1 - GAMBLE_MIN) * gain) * eagerness
            - blockers: the players who move after this one and before the first threatener of the field,
              a threatener who already moved comes only in the next round, so all players in later are in front of it
              if nobody is left, or fewer blockers than threatened fields, it must block
            - p_cover: all fields get blocked by somebody, a blocker is reliable as RELIABILITY says (computer or human)
            - gain: how much better the best field is than the best block, so a block that is the best move anyway is no gamble
            - eagerness: only for a field whose threateners all wait for the next round (random order then): the higher
              the score of the leading threatener, the more the others want to block it instead of gambling
              for threateners of the current round the scores do not count
        """
        chance_cover = 1.0
        eagerness = 1.0
        all_blockers = set()
        for cell, who in threats.items():
            current = [later.index(w) for w in who if w in later]
            blockers = later[:min(current)] if current else later
            if not blockers:
                return 0.0
            all_blockers.update(blockers)
            chance_cover *= 1 - math.prod(1 - RELIABILITY[b in self.computers] for b in blockers)
            if not current:
                eagerness = min(eagerness, 1 - SCORE_EAGERNESS * max(self.score_excess(w) for w in who))
        if len(all_blockers) < len(threats):
            return 0.0
        rating = self.cell_scores(symbol)
        best = max(rating.values())
        gain = (best - max(rating[c] for c in threats)) / best if best > 0 else 0.0
        return chance_cover * (GAMBLE_MIN + (1 - GAMBLE_MIN) * gain) * eagerness

    def computer_pick(self, name, later=()):
        """
            The field a computer player takes:
            1) completes a line of its own if it can
            2) blocks the opponents that could win with their next symbol, or gambles on the players behind it, see gamble_chance
               (later = names still to move after this player in this round)
            3) and 4) takes the best rated field, see cell_scores
        """
        symbol = self.symbol_of(name)
        own_wins = self.win_cells(symbol)
        if own_wins:
            return random.choice(sorted(own_wins))
        threats = {}                                    # field -> names of the players who win there
        for other, other_symbol in self.players:
            if other != name:
                for cell in self.win_cells(other_symbol):
                    threats.setdefault(cell, set()).add(other)
        if threats and random.random() >= self.gamble_chance(symbol, threats, list(later)):
            return self.best_cell(list(threats), symbol)
        return self.best_cell(self.free_fields(), symbol)
