"""Note embeddings for semantic search (pgvector).

Notes are rendered to markdown, chunked and embedded into
`assistant.note_chunk_embedding`, apart from the notes themselves. Writes
only mark a note stale (`staleness`); embedding happens after commit, in a
background worker (`worker`), or in bulk with
`python -m assistant.cli.reindex_search --vectors`. See
docs/architecture/vectors.md.
"""
