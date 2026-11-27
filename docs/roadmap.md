# Roadmap (open steps)

Goal: one game session, up to 12 humans, served by one Python process on fly.io (account exists).
Stack: Flask, one static `index.html` with vanilla JS, state in memory, the client polls `GET /state` about once per second.
Run it as a single machine with a single worker, since the state is in memory. Workflow: navigate the code with
`tools/index.yaml`, and run `tools/index.py` after every finished step. `index.md` is not edited.

## Keeping `simulations.json` safe

Goal: the file grows while the game is used, survives restarts and deploys, is written only by the game, and collects nothing from the internet.
Not built yet; the server does not use `calibrate.py` today, so do it when it starts to.

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
