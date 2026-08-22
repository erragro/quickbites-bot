"""Contract Reader — upload → OCR → three-stage translation reasoning.

Package layout:
  schemas.py   Pydantic DTOs for the /api/contracts surface.
  storage.py   Storage backends. LocalStorage (dev) + a Protocol so
               a GCS-backed variant can drop in for Cloud Run without
               touching the service or route code.
  service.py   Business logic: validate, persist file + row, load, delete.
  routes.py    FastAPI router. All routes are user-scoped — a contract
               that exists but belongs to another user returns 404.
"""
