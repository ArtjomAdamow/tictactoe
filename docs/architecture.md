# Architecture (what exists today)

A terminal game on top of a game core, plus a test script. Standard library only, Python 3.14.
Line ranges follow `tools/index.yaml` for `A_tictactoe.py`; `game.py` and `calibrate.py` are not in the index yet, so their lines are read from the files.

## Files

| File | Role |
|------|------|
| `game.py` | the game core: `Game` (state, rules, computer player), no `print`, `input`, `render` or `sleep` |
| `calibrate.py` | optional board-size recommendation by random playouts, with a store (`simulations.json`, made at run time) |
| `A_tictactoe.py` | the terminal client: screen, timed input, setup, main loop; imports `game.py` |
| `test_game.py` | scripted games for the turn engine (`python -m unittest test_game`), no server needed |
| `sim_scale.py` | random playouts that test the minimum board sizes through `Game`; a test tool, not needed to start the game; uses `calibrate.play` |
| `main.py` | placeholder, unused |
| `tools/index.py`, `tools/index.yaml`, `index.md` | the component index and its tool (not part of the game) |

## Game core (`game.py`)

Module level: constants `SYMBOL_POOL`, `MAX_PLAYERS`, `MAX_TIMEOUT` (60 s), `GAMBLE_MIN`, `RELIABILITY`, `SCORE_EAGERNESS`;
`min_side` (16): minimum board side for `n` players and `z`; `window_keys` (28, cached): every line of `z` fields
(rows, columns, both diagonals) as key tuples; `board_generator` (41): field number -> field text.

`Game(players, computers, side, z, timeout=MAX_TIMEOUT)` (48) holds the state: `players` (list of `(name, symbol)`), `computers` (names),
`side`, `z`, `scores` (name -> score), `draws`, `board` (field number -> field text or symbol), `messages`.
A symbol is any text that is not a field number; the terminal stores it with a space on each side (`' X '`).
A field is free while its value is not in `symbols`. Clients read `messages` and clear the list.

- Rules: `place(name, field, later)` (89) puts the symbol on a free field (else `ValueError`), adds a message, and returns
  the winner's name, `'draw'` or `''`; a finished round updates `scores` and `draws`. `has_line` (107) checks for `z` in a row
  with `window_keys`. `draw_checker` (113): 'draw' when no player has an open line they can still fill with the moves left.
  `new_round` (73), `symbol_of` (79), `free_fields` (82).
- Turn engine (for clients that cannot block on input; the terminal client does not use it; line numbers not in the index yet).
  State: `state` (`lobby`, `playing`, `paused`, `over`), `result` (winner or `'draw'`), `order` and `turn` (the current round
  order, reshuffled when everybody has moved, the board stays), `turn_started`, `queue` (name -> queued field, one per human),
  `afk` (names), `timeout` (seconds, capped at `MAX_TIMEOUT`, never unlimited: `None` or 0 means the maximum).
  `start(now)` begins a game or the revanche (empty board, new order, scores stay; humans still AFK become computers for good),
  `step(now)` makes one move and returns whether it did: a computer moves at once (the caller sets the pace), a human moves
  with the queued field, else the turn waits; after `timeout` seconds `computer_pick` moves for the human with the message
  "The party moves on, the computer made your move." and the human is AFK ("Player x seems to be AFK."), from then on the
  computer moves for them at once on every turn until `touch(name)` or `queue_move` (any action of that human) clears it.
  `queue_move(name, field)` (field `None` clears; a queued field that is taken meanwhile is dropped by `step`), `touch`,
  `pause`/`resume(now)`, `to_computer(name)` (dropout, keeps the seat name), `take_over(seat, name, symbol)` (a human takes a
  computer seat, scores, turn and board marks move over), `humans`. `now` is a clock in seconds (default `time.monotonic`)
  so that tests script the time.
- Computer player: `open_windows` (138) and `win_cells` (151): lines still open for a symbol and the fields that complete one.
  `cell_scores` (157) and `best_cell` (181): rating of free fields (3 ** own symbols per open line, fork bonus, opponents'
  lines at half weight). `score_excess` (189) and `gamble_chance` (198): whether to leave a block to a player who moves in between.
  `computer_pick(name, later)` (230): win, block or gamble, else best cell; it only returns a field.

## Board-size simulation (`calibrate.py`)

Optional, asked once at the start of the terminal game (default: no). `play(n, side, z)` (18) is one random game through `Game`.
`candidate_sides` (37): the default formula's side minus 2 up to plus 3 (at least `z`). `recommend(n, z, progress, store)` (55)
plays `GAMES` (200) random games per side, small sides first, and stops at the first side whose draw rate is at most
`TARGET_DRAW` (0.2); if none is, the side with the lowest draw rate wins. Every finished side is saved at once in
`simulations.json` (`"n,z,side": {games, draws}`), `load` (44) and `save` (50); stored sides are never simulated again.
`progress(done, total, elapsed)` is called before every game and returns `False` to cancel (result `None`, finished sides stay
stored). It returns `(side, True if all data came from the store)`.

## Terminal client (`A_tictactoe.py`)

Globals: `messages` (screen lines), `colors` (symbol -> ANSI code), `game` (the `Game`, made after the setup; `None` before),
`x` (symbol padding), `TIMEOUT` (`None` or seconds, set by the first question), `banner`, `board_title`.

- Output: `paint`, `rainbow`, `say` (keeps the last `MESSAGE_LINES` messages), `enable_ansi`; `render` (316) redraws the whole
  screen in one write, `score_lines` (309) and `board_lines` (378) read `game`; `show_game_messages` (403) moves `game.messages`
  to the screen with the symbols colored.
- Input: `timer_bar` (57) and `timed_input` (71) read input with a timer bar (`msvcrt` on Windows, `select` elsewhere; plain
  `input()` without `TIMEOUT` or a tty). `ask` (124), `ask_int` (136), `ask_field` (422, a timeout takes a random free field).
- Setup: `formula_setup` (148): `n`, `z`, `step`, `margin`; `users_input` (254): names, symbols, colors (`<Enter>` on a name makes
  a computer); `pick_colors` (238) and `color_distance` (227); `board_square` (340): side rounded to a perfect square and raised
  to the minimum.
- Simulation: `simulate_side` (198) asks `calibrate.recommend` and says the result; `simulation_bar` (184) draws the progress bar
  with the time left (an upper bound) and polls `cancel_pressed` (169: `c`, on other systems than Windows `c` and Enter; Ctrl+C
  also cancels); a cancel falls back to the formula. `floor_side` (219) gives the simulated side (`rules['side']`) for the
  chosen `z`, else `min_side`; `board_square` uses it. A note tells when stored data was used.
- `computer_turn` (413): thinking message, `render`, a one-second pause, then `game.computer_pick`.
- Main loop (`__main__`, 438): timeout question, the simulation question (warning that large setups run long), setup, `Game` made once; per round: shuffled order, every player moves
  (`computer_turn` or `ask_field`), `game.place`; after the round a revanche is asked (`game.new_round`, scores stay).

## Web server (`server.py`)

Flask, one process, state in memory; run with `python server.py` (port 8080). Not in `tools/index.yaml` before the next index run; read lines from the file.
`Server` holds `people` (token -> name, symbol, `seat`, `seen`; a person without a seat is a watcher), `dropped` (token -> name, symbol, seat of seated humans who are gone), `host` (token), `setup`, the `Game`,
`version` (counts every change), and `log` (the last `LOG_SIZE` messages with ids; `drain` moves `game.messages` into it).
All requests run under one lock, `create_app(clock, loop)` registers them; `loop=False` and a fake clock let `test_server.py` call `tick()` itself.

| Request | Who | Effect |
|---------|-----|--------|
| `POST /join` `{name, symbol[, token]}` | anyone | returns a token; the first is host; with a token it edits name and symbol (before the game); resumes a paused game; the token of a dropped human takes their seat back while it is still a computer (name and symbol from `dropped`) |
| `POST /start` `{token[, computers, z, side, timeout, new]}` | host | first game from all joined humans plus `computers`; `new: true` replaces a running or paused game |
| `POST /claim` `{token, seat}` | watcher | takes a computer seat with their own name and symbol (`Game.take_over`) |
| `POST /queue` `{token, field}` | seated human | queued move (`null` clears) |
| `POST /leave` `{token}` | anyone | `drop`: the seat becomes a computer, the host moves on, nobody left pauses the game; the body is read as JSON whatever the content type, so `navigator.sendBeacon` on tab close works |
| `POST /revanche` `{token}` | host | restart after `over` |
| `GET /state?token=` | anyone | people, setup, last messages, board, scores, order, `time_left`, queue, `version` |

`tick()` (loop every `TICK` 0.1 s): one `Game.step` when due; moves of computers and AFK humans keep `COMPUTER_DELAY` (0.7 s),
queued human moves are immediate. A finished game with no human seat and somebody in the lobby starts the next game after the same delay.
Errors are `{"error": ...}` with status 400 or 403.
Presence: every request with a token and `GET /state` set `seen`; `tick()` drops everybody silent for more than `PRESENCE_TIMEOUT` (5 s)
with `drop`, the same as `/leave`. A reconnecting token gets no host role back. `dropped` is cleared when `new: true` replaces the game.
Clients must poll `/state` with their token (about once per second) to stay present.

## Test tool

`sim_scale.py` plays random games through `Game.place` for several `n`, `z` and sides and prints draw rate, win rate per seat
and mean moves. With `random.seed(1)` its output is reproducible (it was identical before and after the extraction of `game.py`).
