"""Keyword search over notes.

See `docs/architecture/search.md` and `docs/adr/0002-postgres-fts-search.md`.
The public entry point is `assistant.search.service.search`; indexing
happens through `assistant.search.indexer.index_note`, called by the notes
service on every note write.
"""
