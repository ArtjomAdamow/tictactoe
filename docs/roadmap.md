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

5. **Browser client** `static/index.html`: join form, lobby with live name and symbol editing, board table in the player
   colors, scores, messages, one always-active number input, "take over computer N" buttons, host controls, the
   "join as host / new game" choice for the first human after a pause.
6. **Deploy to fly.io:** `Dockerfile`, `fly.toml` with one machine, no autostop (it would lose the state), one worker,
   `pyproject.toml` gets `flask` and a production server (`gunicorn`, one worker with threads, or `waitress`). Check with 2 to 3 browsers.
7. **Docs:** update `README.md` and `docs/architecture.md`.

## Risks

- A single in-memory process loses the game on every deploy or restart; acceptable for this app.
- Free-tier machines may stop when idle; configure fly.io so that the machine stays running while a game exists.
- Step 2 is now the largest change; scripted games without a server are the safety net, and `sim_scale.py` (same output before and after) guards the rules.
- `game.messages` grows without a limit; the server must cap or drain it (the terminal client drains it).
