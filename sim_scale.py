"""
    Random playouts to test the board sizes of game.py: its own min_side(n, z) and the sizes next to it
    Per (players n, win length z, side y): draw rate, win rate per seat, mean moves
    Usage: python sim_scale.py [games per row, default 300]
"""
import random
import sys

import game
from calibrate import play


def run(n, y, z, games):
    wins = [0] * n
    draws = 0
    total = 0
    for _ in range(games):
        seat, moves = play(n, y, z)
        total += moves
        if seat is None:
            draws += 1
        else:
            wins[seat] += 1
    return draws / games, [w / games for w in wins], total / games


if __name__ == "__main__":
    random.seed(1)
    GAMES = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    print(f"{GAMES} random games each; * = the game's minimum side, min_side(n, z)")
    print(f"{'n':>2} {'z':>2} {'y':>2}  {'draw':>5}  {'moves':>5}  win rate per seat")
    for z in (3, 4, 5):
        for n in (2, 3, 4, 5):
            ym = game.min_side(n, z)
            for y in range(max(z, ym - 1), ym + 2):
                d, w, m = run(n, y, z, GAMES)
                mark = "*" if y == ym else " "
                print(f"{n:>2} {z:>2} {y:>2}{mark} {d:5.0%}  {m:5.1f}  " + " ".join(f"{x:4.0%}" for x in w))
