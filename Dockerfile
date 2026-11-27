FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY game.py calibrate.py server.py ./
COPY static ./static
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8080
# one process and one worker (the state is in memory), many threads for the polling clients
CMD ["waitress-serve", "--factory", "--host=0.0.0.0", "--port=8080", "--threads=8", "server:create_app"]
