# Project Structure

```
assistant/
├── src/                        # The backend code
│   └── assistant/              # Main Python package
│       ├── adapters/           # Data source adapters & plugin system
│       │   └── plugins/        # Adapter plugins (e.g. fake for testing)
│       ├── agents/             # RAG agent, vector search, infra
│       ├── api/                # FastAPI REST API
│       │   ├── routes/         # Route handlers (users, notebooks, notes)
│       │   └── schemas/        # Pydantic request/response schemas
│       ├── cli/                # CLI entry points (server, client, db tools, chat)
│       ├── data/               # Static data assets
│       │   └── documents/
│       ├── evals/              # Evaluation framework
│       ├── models/             # SQLAlchemy ORM models & DB schema
│       ├── notes/              # Notes service layer (CRUD, positions, users)
│       └── tui/                # Terminal UI (Textual chat app)
├── frontend/                   # React/TypeScript web UI (Vite)
│   └── src/
│       ├── api/                # API client layer
│       ├── components/         # React components (Layout, NoteEditor, etc.)
│       ├── contexts/           # React context providers
│       ├── markdown/           # Markdown parsing & rendering
│       ├── test/               # Frontend test utilities
│       └── types/              # TypeScript type definitions
├── tests/                      # Python test suite (mirrors src/ structure)
├── data/                       # Runtime data assets
│   ├── documents/
│   └── evals/
├── scripts/                    # Utility scripts (e.g. verify_setup.sh)
├── docs/                       # Documentation
│   ├── architecture/           # System architecture
│   ├── adr/                    # Architecture Decision Records
│   └── modules/                # Module documentation
│       └── registry/
├── .claude/                    # Claude AI configuration
├── config.yaml                 # Application configuration
├── docker-compose.yml          # Dev services (Postgres)
├── Makefile                    # Build & dev commands
├── pyproject.toml              # Python project configuration
└── README.md
```
