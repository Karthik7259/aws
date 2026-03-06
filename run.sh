#!/bin/bash

# Run the FastAPI server with uvicorn
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env
