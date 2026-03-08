# Frontend Docker Configuration

React + Vite application served via Nginx.

## Files

- `Dockerfile` - Production build (multi-stage)
- `nginx.conf` - Nginx configuration
- `svsgold-frontend/` - React application source

## Build & Run

```bash
# Build
docker build -t svsgold-frontend .

# Run
docker run -d -p 3000:80 svsgold-frontend

# Access
http://localhost:3000
```

## Features

- Multi-stage build (optimized production image)
- SPA routing support (React Router)
- API proxying to backend (`/api/` → backend:5000)
- Gzip compression enabled
- Static asset caching
