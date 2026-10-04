# The API and the ingestion pipeline, built from backend/ alone.
# The deliveries are mounted at run time rather than copied in, so a file dropped into
# data/deliveries is picked up by the next "Run ingestion" without rebuilding the image.
FROM python:3.12-slim

WORKDIR /app

# Requirements before the code, so editing a .py file reuses the installed-packages layer instead
# of reinstalling everything.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Without these, config.py resolves both paths from the repo root, which inside the image is "/",
# and the database would land in a directory the app user cannot write to.
# PYTEST_ADDOPTS turns off pytest's cache for `docker compose exec backend pytest`: the app user
# cannot write /app, and the cache would otherwise end every clean test run with a warning.
ENV CDH_DATA_DIR=/data \
    CDH_DATABASE_URL=sqlite:////db/campaign_data_hub.db \
    PYTEST_ADDOPTS="-p no:cacheprovider"

# A non-root user that can write the database directory and nothing else. The deliveries are
# mounted read-only, so the pipeline has no way to modify its own input.
RUN useradd app && mkdir /db && chown app /db
USER app

EXPOSE 8000

# Ingest first so the app starts with data, then hand the process over to uvicorn.
# exec: uvicorn replaces the shell as PID 1, so the stop signal from `docker compose down` reaches
#       it directly instead of being swallowed by sh and ending in a kill ten seconds later.
# &&: if ingestion cannot run at all (no data mounted), the container exits with the traceback in
#     its logs rather than serving an empty app that looks like a broken page.
# --workers 1: the 409 lock in api/ingestions.py is per process; a second worker has its own.
CMD ["sh", "-c", "python -m app.ingest && exec uvicorn app.api.app:app --host 0.0.0.0 --port 8000 --workers 1"]
