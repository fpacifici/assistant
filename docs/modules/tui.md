# `assistant.tui`

The `assistant.tui` package provides a **chat TUI** (text user interface) to ask the Ask AI agent about a user's notes in the terminal. The agent is described in [`docs/architecture/ask.md`](../architecture/ask.md).

## Public API

- **`ChatApp(thread_id, user_id, agent, *, on_question=None)`** – Textual app that shows a scrollable conversation log and an input line. `agent` is an `AskAgent`; `on_question` is called with each question before it is asked (the CLI uses it to title the thread). Run with `app.run()`.

## Usage

```bash
# Start a new thread
python -m assistant.cli.chat --email user@example.com
# Resume one (its id is printed when the TUI exits)
python -m assistant.cli.chat --email user@example.com --thread-id <uuid>
```

Needs `OPENAI_API_KEY`. The CLI configures LangSmith tracing (when `LANGSMITH_API_KEY` is set), builds the agent, finds or creates the user's `ChatThread` and launches `ChatApp`. Inside the TUI:

1. The stored conversation of the thread is shown.
2. Type a question and press Enter.
3. Tool calls are shown as they happen (`→ search_notes(query='...')`), then the answer and the notes it used.
4. Exit with **Ctrl+Q**.

Long lines in the message log wrap at the container width. Use **Up**/**Down** and **Page Up**/**Page Down** to scroll the message area (works even when the input line has focus). Mouse handling is disabled so you can select text with the mouse and copy as in a normal terminal (e.g. drag to select, then Cmd+C or your terminal’s copy shortcut).

## Dependencies

- **Textual** – UI framework (layout, `Input`, `RichLog`, workers).
- **`assistant.agents.rag`** – `AskAgent.stream(thread_id, user_id, question)` and `AskAgent.history(thread_id)`.

## Architecture

- **`app.py`** – Defines `ChatApp`, message types (`StreamChunk`, `QueryDone`, `QueryError`), and formatters for stored messages, tool events and sources. The agent's event stream runs in a **thread worker**; lines are posted to the app and appended to the log; errors are shown and the input is re-enabled.
- **`chat.css`** – Styles the log container and docks the input at the bottom.
- The **CLI** (`assistant.cli.chat`) resolves the user and thread and runs the app.
