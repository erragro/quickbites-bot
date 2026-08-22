"""Idiom library admin surface.

  admin_routes.py  /api/admin/idioms/* — super-admin CRUD for the
                   idiom_library + idiom_translations tables. Every
                   mutation calls translate.idioms.reset_cache() so
                   the Aho-Corasick automaton picks up changes on the
                   next translation without a process restart.

  schemas.py       Pydantic DTOs.

Runtime detection lives at app/translate/idioms.py; this package owns
only the editing surface.
"""
