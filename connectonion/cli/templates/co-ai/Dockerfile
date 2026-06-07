FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN apt-get update && apt-get install -y --no-install-recommends git xvfb xauth && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install --with-deps chrome
COPY . .
ENV PORT=8000
ENV DISPLAY=:99
# Run Xvfb in the background and exec the agent as the main process so its exit
# propagates to Docker (restart-on-failure works; failures aren't masked the way
# `xvfb-run` as PID 1 masks them).
CMD ["sh", "-c", "Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp & exec python agent.py"]
