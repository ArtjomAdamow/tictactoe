# Roadmap: multiplayer in the browser (open steps)

Goal: one game session, up to 12 humans, served by one Python process on fly.io (account exists).
Stack: Flask, one static `index.html` with vanilla JS, state in memory, the client polls `GET /state` about once per second.
Run it as a single machine with a single worker, since the state is in memory. Workflow: navigate the code with
`tools/index.yaml`, and run `tools/index.py` after every finished step. `index.md` is not edited.

## Decisions

- **Roles:** the first user to join is the host and sets up the game.
- **Lobby:** players see each other, everybody can edit name and symbol. The host starts. Players = all joined humans plus
  extra computers if the host sets a higher number.
- **Running game:** a joining human can take over any computer seat with their own name and symbol.
- **Queued move:** every human can send a field at any time. It is placed when their turn comes, if free; otherwise the
  server clears it as soon as the field is taken. The client shows the queue from the server state.
- **Timeout:** at most 60 s per move, also the default, never no timer. When it runs out the computer logic makes the move
  ("The party moves on, the computer made your move."); the human is AFK ("Player x seems to be AFK."), the computer moves
  for them at once until they act again; one still AFK at the revanche counts as dropped out.
- **Dropout:** the seat becomes a computer at once; message "Player x dropped out, computer y took over".
- **Reconnect:** a token in `localStorage` lets a dropped human take their seat back, as long as it is still the computer that took over.
- **Revanche:** the host restarts with the same setup; dropouts stay computers. If a finished game has no human seat left
  (only computers, or the last human dropped out) and somebody is in the lobby, the next game starts by itself after the
  computer delay. With nobody in the lobby the game stays paused.
- **Host drops out:** the next human in line becomes host.
- **Last human drops out:** the game pauses but stays in memory. It runs again while a human is in the lobby. That human
  can watch; when the first one joins, they choose between joining the current game as host or starting a new one.

## Steps

7. **Docs:** update `README.md` and `docs/architecture.md`.

## Keeping `simulations.json` safe

Goal: the file grows while the game is used, survives restarts and deploys, is written only by the game, and collects nothing from the internet.
Not built yet; do it before or together with step 6.

1. **Persistent volume on fly.io:** create a volume, mount it at `/data`, store the file at `/data/simulations.json`. The path comes from an
   env var (default `simulations.json` for local use). Volumes survive restarts and deploys. The file is not in the image and not in git
   (`simulations.json` is in `.gitignore`).
2. **Written only by the game:** only the server process writes it, and the content comes from `calibrate.play` results, never from request
   data. No HTTP route reads or writes it, and the volume is not under `static/`, so it cannot be downloaded or uploaded.
3. **Validated on load and save:** a key must match `n,z,side` with integers inside the limits of `server.py` (`MAX_PLAYERS`, `MAX_SIDE`);
   a value must be `{games, draws}` with `0 <= draws <= games <= GAMES`. Anything else is dropped and logged.
4. **Atomic writes:** write a temp file in the same folder, then `os.replace`, under a lock, so a crash cannot leave a half-written file.
5. **Tamper check (later):** an HMAC over the content with a secret from `fly secrets set` (`SIM_KEY`); on a bad HMAC the file is ignored
   and simulated again.
6. **Bounded growth:** the key space is small (a few players counts x `z` x side) and a hard cap on entries guards the rest.
7. **Backup:** optionally a `.bak` copy before each replace, plus a Fly volume snapshot.

Order: 1 to 4 first, 5 to 7 when wanted. The store path moves into `calibrate.py` behind the env var.

## Risks

- A single in-memory process loses the game on every deploy or restart; acceptable for this app.
- Step 2 is now the largest change; scripted games without a server are the safety net, and `sim_scale.py` (same output before and after) guards the rules.
- `game.messages` grows without a limit; the server must cap or drain it (the terminal client drains it).
