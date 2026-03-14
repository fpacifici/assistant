# `assistant.tui`

The `assistant.tui` package provides a **chat TUI** (text user interface) for sending queries to the RAG agent and streaming responses in the terminal.

## Public API

- **`ChatApp`** – Textual app that shows a scrollable conversation log and an input line. Accepts `thread_id` and `agent` (a `SearchAgent` instance) in the constructor. Run with `app.run()`.

## Usage

Start the chat TUI via the CLI with a conversation thread ID:

```bash
python -m assistant.cli.chat <thread_id>
```

Example:

```bash
python -m assistant.cli.chat my-conversation-1
```

The CLI calls `init_environment()`, creates a `SearchAgent`, and launches `ChatApp`. Inside the TUI:

1. Type a query and press Enter.
2. The query is sent to `SearchAgent.query(thread_id, query)`; yielded messages are streamed into the log.
3. When streaming finishes, the input is re-enabled for the next query.
4. Exit with **Ctrl+Q**.

## Dependencies

- **Textual** – UI framework (layout, `Input`, `RichLog`, workers).
- **`assistant.agents.rag`** – `SearchAgent` and its `query(thread_id, query)` generator.
- **`assistant.agents.infra`** – `init_environment()` (used by the CLI only).

## Architecture

- **`app.py`** – Defines `ChatApp`, message types (`StreamChunk`, `QueryDone`, `QueryError`), and `_format_message()` for `BaseMessage` display. The agent’s generator runs in a **thread worker**; each chunk is posted to the app and appended to the log; errors are shown and the input is re-enabled.
- **`chat.css`** – Styles the log container and docks the input at the bottom.
- The **CLI** (`assistant.cli.chat`) parses `thread_id`, initializes the environment and agent, and runs `ChatApp(thread_id=..., agent=...).run()`.
