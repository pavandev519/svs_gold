# SVS Gold — FastAPI + Docker

This project exposes a minimal FastAPI wrapper around the existing `insert_sample_account()` function.

Quick start (local):

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate   # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. Set database environment variables (example):

```bash
export DB_HOST=your-db-host
export DB_PORT=5432
export DB_NAME=postgres
export DB_USER=postgres
export DB_PASSWORD=your-secret
export DB_SSLMODE=require
```

3. Run the app:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Docker build & run:

```bash
docker build -t svs-gold:latest .
docker run -e DB_HOST=... -e DB_USER=... -e DB_PASSWORD=... -p 80:80 svs-gold:latest
```

Endpoints:

- `GET /` — health check
- `POST /insert-sample` — insert a sample account into the configured database

Notes:

- The repository previously contained hard-coded DB credentials in `app.py`. The code now reads credentials from environment variables. Remove any secrets from the repository and configure them via environment variables or a secret manager.
