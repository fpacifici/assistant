# Project Structure

```
assistant/
├── src/                        # The backend code
│   └── assistant/              # Main Python package
│       ├── adapters/           # Note import (Evernote HTML export)
│       │   └── plugins/        # Import sources (HTML directory)
│       ├── agents/             # Ask AI agent, its tools, LangSmith tracing
│       ├── api/                # FastAPI REST API
│       │   ├── routes/         # Route handlers (users, notebooks, notes)
│       │   └── schemas/        # Pydantic request/response schemas
│       ├── blogs/              # Blog sources and the collection job
│       ├── categories/         # Categories shared by blogs and the reading list
│       ├── chat/               # Ask AI threads
│       ├── cli/                # CLI entry points (server, client, db tools, chat)
│       ├── data/               # Static data assets
│       │   └── documents/
│       ├── evals/              # Evaluation framework
│       ├── golib/              # ctypes wrappers of the Go shared library
│       ├── models/             # SQLAlchemy ORM models & DB schema
│       ├── notes/              # Notes service layer (CRUD, positions, users)
│       ├── reading/            # Reading list: links, analysis, background worker
│       ├── tui/                # Terminal UI (Textual chat app)
│       ├── vectors/            # Note embeddings (pgvector), indexer, worker
│       └── web/                # Safe fetcher, URL identity, HTML page extraction
├── go/                         # Go module, built into a C shared library
│   ├── bindings/               # C ABI exports (package main, cgo)
│   └── greeting/               # Logic packages, free of cgo
├── frontend/                   # React/TypeScript web UI (Vite)
│   └── src/
│       ├── api/                # API client layer
│       ├── components/         # React components (Layout, NoteEditor, etc.)
│       │   └── blogs/          # Blog post cards, lists and forms
│       ├── contexts/           # React context providers
│       ├── hooks/              # Reusable hooks (unsaved-changes guard)
│       ├── layout/             # Layout mode (mobile/desktop) detection
│       ├── markdown/           # Markdown parsing & rendering
│       ├── pages/              # Standalone pages (auth, invites)
│       ├── test/               # Frontend test utilities
│       ├── routes.tsx          # Data-router route table
│       └── types/              # TypeScript type definitions
├── tests/                      # Python test suite (mirrors src/ structure)
├── data/                       # Runtime data assets
│   ├── documents/
│   └── evals/
├── scripts/                    # Utility scripts (e.g. verify_setup.sh)
├── docs/                       # Documentation
│   ├── architecture/           # System architecture
│   ├── adr/                    # Architecture Decision Records
│   ├── specs/                  # Specifications
│   └── modules/                # Module documentation
├── .claude/                    # Claude AI configuration
├── config.yaml                 # Application configuration
├── docker-compose.yml          # Dev services (Postgres)
├── Makefile                    # Build & dev commands
├── pyproject.toml              # Python project configuration
└── README.md
```
