FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --system --uid 10001 sync

USER sync
ENTRYPOINT ["beeper-pg-sync"]
CMD ["run"]
