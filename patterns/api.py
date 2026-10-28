"""Uvicorn factory: uvicorn patterns.api:app_factory --factory --host 127.0.0.1."""

import os
from patterns.application.api import create_app
from patterns.application.service import Service


def app_factory():
    service = Service(os.getenv("DEMO_DATA_DIR", ".local-data"))
    service.seed()
    return create_app(service)
