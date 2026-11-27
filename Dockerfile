FROM python:3.14-slim
WORKDIR /app
RUN pip install --no-cache-dir "flask>=3.1.3" "waitress>=3.0.2"
COPY game.py calibrate.py server.py ./
COPY static ./static
EXPOSE 8080
# one process and one worker (the state is in memory), many threads for the polling clients
CMD ["waitress-serve", "--host=0.0.0.0", "--port=8080", "--threads=8", "--call", "server:create_app"]
