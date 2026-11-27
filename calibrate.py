"""
    Recommends a board side for n players and the winning condition z by random playouts of game.py
    Every finished side is stored in simulations.json, a stored side is never simulated again
    No input or output: the client gives a progress function and shows the bar itself
"""
import json
import logging
import os
import random
import threading
import time
from pathlib import Path

from game import MAX_PLAYERS, MAX_SIDE, Game, min_side

STORE = Path(os.environ.get('SIM_STORE') or Path(__file__).with_name('simulations.json'))    # on fly.io: /data/simulations.json
GAMES = 200             # random games per side
LOCK = threading.Lock()
TARGET_DRAW = 0.2       # the smallest side whose draw rate in random games is at most this is recommended


def play(n, side, z):
    """
        One game of random moves, returns (seat of the winner or None for a draw, number of moves)
    """
    players = [(f"P{i + 1}", f" {chr(97 + i)} ") for i in range(n)]
    session = Game(players, [], side, z)
    free = list(session.board)
    random.shuffle(free)
    moves = 0
    while True:
        for seat, (name, symbol) in enumerate(players):
            later = [p[0] for p in players[seat + 1:]]
            result = session.place(name, free.pop(), later)
            moves += 1
            if result == 'draw':
                return None, moves
            if result:
                return seat, moves

def candidate_sides(n, z):
    """
        The sides that are looked at, around the default formula
    """
    base = min_side(n, z)
    return range(max(z, base - 2), base + 4)

def valid_entry(key, value):
    """
        A key is "n,z,side" with integers inside the limits of the game, a value is {games, draws} with 0 <= draws <= games <= GAMES
    """
    try:
        n, z, side = (int(part) for part in key.split(','))
        games, draws = value['games'], value['draws']
    except (AttributeError, KeyError, TypeError, ValueError):
        return False
    if key != "%d,%d,%d" % (n, z, side) or set(value) != {'games', 'draws'}:
        return False
    if not all(type(number) is int for number in (games, draws)):
        return False
    return 2 <= n <= MAX_PLAYERS and 3 <= z <= side <= MAX_SIDE and 0 <= draws <= games <= GAMES

def clean(data):
    """
        Keeps the valid entries, logs and drops the rest
    """
    if not isinstance(data, dict):
        logging.warning("simulations: content is not an object, ignored")
        return {}
    good = {}
    for key, value in data.items():
        if valid_entry(key, value):
            good[key] = value
        else:
            logging.warning("simulations: dropped entry %r", key)
    return good

def load(store=STORE):
    try:
        return clean(json.loads(Path(store).read_text(encoding='utf-8')))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logging.warning("simulations: %s unreadable, ignored", store)
        return {}

def save(data, store=STORE):
    """
        Validated, written to a temp file in the same folder, then replaced under a lock, so a crash leaves no half-written file
    """
    store = Path(store)
    with LOCK:
        temporary = store.with_suffix('.tmp')
        temporary.write_text(json.dumps(clean(data), indent=1, sort_keys=True), encoding='utf-8')
        os.replace(temporary, store)

def recommend(n, z, progress=None, store=STORE):
    """
        Looks at the candidate sides from the small ones up and stops at the first with a draw rate of at most TARGET_DRAW,
        if there is none the side with the lowest draw rate wins
        progress(done, total, elapsed) is called before every game, total is the most games that may be needed;
        it returns False to cancel. A cancel gives None, the sides finished so far stay stored
        Returns (side, True if everything came from the store)
    """
    data = load(store)
    sides = list(candidate_sides(n, z))
    total = GAMES * sum(1 for side in sides if "%d,%d,%d" % (n, z, side) not in data)
    start = time.monotonic()
    done = 0
    simulated = False
    rates = {}
    for side in sides:
        key = "%d,%d,%d" % (n, z, side)
        if key not in data:
            simulated = True
            draws = 0
            for _ in range(GAMES):
                if progress and not progress(done, total, time.monotonic() - start):
                    return None
                draws += play(n, side, z)[0] is None
                done += 1
            data[key] = {'games': GAMES, 'draws': draws}
            save(data, store)
        rates[side] = data[key]['draws'] / data[key]['games']
        if rates[side] <= TARGET_DRAW:
            return side, not simulated
    return min(rates, key=lambda side: (rates[side], side)), not simulated
