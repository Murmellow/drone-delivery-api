# Drone Delivery API - Distribution Guide

## Quick Start for Recipients

You've received the Drone Delivery API package. Here's how to get it running:

### Prerequisites

- Docker Desktop (easiest option) OR Python 3.11+
- Git (to clone/download the project)

### Option A: Docker (5 minutes)

1. Extract the package or clone the repository
2. Open terminal in the project directory
3. Run:
   ```bash
   docker-compose up -d
   ```
4. Access the API at `http://localhost:8000/docs`
5. Try the demo: 
   ```bash
   curl -X POST http://localhost:8000/api/v1/demo/flow \
     -H "Content-Type: application/json" \
     -d '{"flow":"single","reset":true}'
   ```

### Option B: Python (10 minutes)

1. Extract/clone and open terminal in project directory
2. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # OR
   .\venv\Scripts\Activate.ps1  # Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the server:
   ```bash
   uvicorn app.main:app --reload
   ```
5. Access at `http://127.0.0.1:8000/docs`

## What's Included

```
drone-delivery-api/
├── Dockerfile              # Container definition
├── docker-compose.yml      # One-command deployment
├── requirements.txt        # Python dependencies
├── README.md              # Full documentation
├── DISTRIBUTION.md        # This file
├── app/                   # Application code
│   ├── main.py
│   ├── core/
│   ├── models/
│   ├── routers/
│   └── schemas/
└── features/              # BDD tests
```

## Hosting Options

See `README.md` → "Deployment Options" section for detailed instructions on:

- Cloud container services (AWS ECS, Google Cloud Run, Azure, etc.)
- PaaS platforms (Heroku, Render, Railway, Fly.io)
- Traditional servers (Linux + Gunicorn + nginx)
- Kubernetes/orchestration

## Configuration

Set environment variables (or edit `app/core/config.py`):

- `API_V1_STR`: API path prefix (default: `/api/v1`)
- `DATABASE_URL`: Database connection (default: `sqlite:///./sql_app.db`)
- `PROJECT_NAME`: API title in docs

## Next Steps

1. Read `README.md` for full API documentation
2. Try the demo flows via curl (examples in README)
3. Run BDD tests: `behave -f progress`
4. Explore Swagger UI at `/docs`
5. Customize for your use case

## Support

For questions about the code, consult the Development Story section in README.md to understand how this was built with GitHub Copilot.
