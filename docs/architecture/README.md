# Architecture Documentation

Assistant is an AI agent that organizes your knowledge and summarizes topics.

- Assistant consumes your notes in a variety of formats from a variety of sources.
  From here it uses an LLM to produce summaries of specific topics and store them
  locally to be consulted later.
- The user interacts with Assistant through a CLI ui for now where the user can
  ask for the summary for a specific topic.
- Assistant is able to find references onnline for the content of a specific
  statement in the summary. Sometime the reference are parts of the original
  content.
- Summaries are stored locally in markdown format to be consulted and updated later on.

## High level components

These are the logical components involved in the system at the highest level.

```mermaid
graph
    %% External Sources
    Evernote[Evernote]
    OtherSources[Other Sources]

    %% Adapters Layer
    Adapters[Adapters Layer]

    subgraph Context Layer
        LocalStore[(Local content store)]
        VectorDB[(Vector Database<br/>Tokenized Content)]

        %% Processing Layer

        RAG[RAG System]
    end

    Agent[Summarization<br/>Agent]

    %% User Interface
    CLI[CLI UI]

    %% Output
    Summaries[(Markdown Summaries)]

    %% Connections
    Evernote --> Adapters
    OtherSources --> Adapters
    Adapters --> LocalStore
    Adapters --> VectorDB
    VectorDB --> RAG
    LocalStore --> Agent
    RAG -- context --> Agent
    CLI --> Agent
    Agent --> Summaries
    Agent -- fetch --> Adapters
    Summaries --> CLI
```

- User's knowledge is fetched from a variety of external systems. These are plugins
  which provide a unified interface in the [Adapters Layer](./adapters.md).
- We store documents fetched online in both plain text and a Vector DB: [Context Layer](./context.md).
  The Vector DB is used for the RAG pipeline to provide context to the agent.
  The `Local content store` contains the downloaded content together with metadata
  in order not to download all content each time.
- The [Summarization Agent](./summarization.md) is provide with context and messages, the agent can
  fetch online data via a tool that uses the [Adapters Layer](./adapters.md)
- Summaries are presented to the user who can decide whether to store them.
- Existing summaries can also be replaced. We keep versions

## Main workflows

This section describes how the components above interact.

### Knowledge update flow

The Adapters Layer provides a common interface and a common data model to retrieve
knowledge from external sources.

- A background job triggers the knowledge update flow.
- The job reads the local store to know what we need to fetch
- Then it fetches new items.

```mermaid
sequenceDiagram
    participant Job as Background Job
    participant LocalStore as Local Store
    participant Adapters as Adapters Layer
    participant External as External Sources
    participant VectorDB as Vector Database

    Note over Job: Knowledge update flow triggered
    Job->>LocalStore: Read what needs to be fetched
    LocalStore-->>Job: Return list of items to fetch

    loop For each item to fetch
        Job->>Adapters: Fetch new items
        Adapters->>External: Request items
        External-->>Adapters: Return items
        Adapters->>LocalStore: Store plain text content
        Adapters->>VectorDB: Store tokenized content
        Adapters-->>Job: Confirm items stored
    end
```

### Agent loop

The agent follows a standard RAG flow.

- it receives the question
- it runs the query for additional context on the Vector DB
- it adds the response to the prompt and summarizes the content
- it uses a tool to fetch sources online

```mermaid
sequenceDiagram
    participant User as User/CLI
    participant Agent as Summarization Agent
    participant VectorDB as Vector Database
    participant Tool as Tool/Adapters Layer

    User->>Agent: Send question
    Note over Agent: Receive question

    Agent->>VectorDB: Query for additional context
    VectorDB-->>Agent: Return context results

    Note over Agent: Add context to prompt<br/>and summarize content
    Agent->>Agent: Generate summary

    alt Need to fetch sources online
        Agent->>Tool: Use tool to fetch sources
        Tool-->>Agent: Return source data
        Note over Agent: Update summary<br/>with sources
    end

    Agent-->>User: Return summary
```

## General architectural principles

There are some cross-cutting concerns in the design of the application.

### Storage and databases

- Our main storage is Postgres with pgvector installed.
- The entire data model is in a single schema calles `assitant`
- The application accesses Postgres with SQLAlchemy.
- Models are defined in the `assistant/moduels` module
- We have use Docker Compose to set up the external systems. We use it to start postgres.

### Configuration management

- The application configuration is defined by a yaml config file.
- Secrets are provided as environment variable or with the `.env` file.

### Logging and error management

- We use the logging package to log information. Standard level is INFO
- Each model defines some specific exceptions
