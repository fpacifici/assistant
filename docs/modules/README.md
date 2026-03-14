# Module Documentation

This directory contains detailed documentation for each module in the assistant package.

## Purpose

Module documentation helps AI agents and developers understand:
- The purpose and responsibility of each module
- Public APIs and their usage
- Internal architecture and design patterns
- Dependencies and relationships with other modules
- Examples and common usage patterns

## Available module docs

- [`config.md`](config.md): configuration loading, env overrides, and typed schema
- [`registry/registry.md`](registry/registry.md): adapter registry, instance caching, and resolution from config + DB
- [`tui.md`](tui.md): chat TUI for the RAG agent (thread_id, streaming, Ctrl+Q exit)
