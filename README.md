# Tic-Tac-Toe

A not so simple game of Tic-Tac-Toe: up to 12 players, human or computer, on a board of any size with a
scalable winning condition. Play it in the terminal (standard library only) or with friends in the browser.

## Run

```bash
python A_tictactoe.py
```

Needs Python 3.14 (see `pyproject.toml`) and a terminal with ANSI colors (the Windows console is switched on by the game).
`main.py` is only a placeholder.

### In the browser (multiplayer)

```bash
pip install flask waitress      # or: uv sync
python server.py                # http://localhost:8080
```

One game session for up to 12 humans, served by one Python process with the state in memory; the page (`static/index.html`) polls the
server about once a second. It also runs live on fly.io (see [Deployment](docs/architecture.md#deployment-flyio)).

- The first person to join is the host: they choose the number of extra computers, `z`, side and timeout, and start the game, the
  revanche or a new game. Everybody in the lobby can change their name and symbol.
- Moves: type a field number or click a free field at any time. It is queued and placed when your turn comes, if the field is
  still free. At most 60 s per move; after that the computer moves for you and you count as AFK until you act again.
- Joining a running game: take over any computer seat with your own name and symbol.
- Leaving or losing the connection (5 s without a request) turns your seat into a computer. The token in `localStorage` lets
  you take the seat back while the computer still has it. If the host leaves, the next human becomes host; if the last human
  leaves, the game pauses and waits for the next one.
- Tests: `python -m unittest test_game test_server`.

## How it works

**Setup**
- `<Enter>` takes the default: 2 players, winning condition 3, a 3 x 3 board. Any other key lets you set the variables.
- Every player gets a name and a symbol. `<Enter>` on the name makes a computer player, `<Enter>` on the symbol gives a
  random free one. Every player gets an own color, picked so that the colors are not too similar.
- The board is a square: the size you type is rounded to the closest perfect square (below 7 it is 9).
  For a board larger than 3 x 3 you also choose the winning condition `z`.
- The side of the board is raised to a minimum that grows with the number of players:
  `z + (n - 2) * step`, at least `z + margin` (defaults: `step = z - 2`, `margin = 1` for `z > 3`, else `0`).

**Playing**
- Type the number of a free field. An unanswered question takes its default after 6 seconds (a random free field for a move),
  shown by a timer bar.
- `z` of your symbols in a row, column or diagonal win the round.
- The turn order is shuffled randomly in every round of turns, from the very first one.
- A round ends in a draw as soon as nobody can win any more (the check allows every player the most moves he could still get,
  so a draw is always a real one).
- A revanche keeps the board settings without asking. The screen shows the scores of all players and the number of draws.

## Computer players

A computer player decides in this order:

1. **Win** by completing a line of its own.
2. **Block** an opponent who would win with the next symbol. With several players the computer may gamble instead and leave
   the block to a player who moves in between. The chance grows with the number and reliability of those blockers and with
   what the blocking move would cost the computer. Threats from players who already moved this round are taken more seriously the
   higher their overall score is. If nobody can block for it (it is the last one to move, or the threatener moves right
   after it), it always blocks.
3. **Open several win options** (a fork) by placing symbols next to each other.
4. **Prefer strategic fields** that lie in many open lines, counting the opponents' lines at half weight.

## Files

| File | Purpose |
|------|---------|
| `A_tictactoe.py` | the terminal game |
| `game.py` | the game core: rules, turn engine, computer player (no input or output) |
| `calibrate.py` | optional board-size recommendation by random playouts, stored in `simulations.json` |
| `server.py`, `static/index.html` | the web server (Flask, waitress) and the browser client |
| `test_game.py`, `test_server.py` | scripted tests without a real network |
| `sim_scale.py` | random playouts that test the minimum board sizes (draw rate, wins per seat, mean moves) |
| `Dockerfile`, `fly.toml`, `.github/workflows/fly-deploy.yml` | deployment to fly.io |
| `docs/architecture.md`, `docs/roadmap.md` | how it is built, and what is still open |

## License

MIT, in [LICENSE](LICENSE).
Copyright (c) 2026 Artjom Adamow.
