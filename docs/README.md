# Documentation Overview

Welcome to the assistant package documentation!

## Directory Structure

```
docs/
├── architecture/        # High-level system architecture
├── adr/                # Architecture Decision Records
├── modules/            # Per-module documentation
└── agents/             # AI agent working guidelines
```

## Documentation Types

### Architecture Documentation (`architecture/`)
**Audience**: Developers, architects, AI agents
**Purpose**: Understand the overall system design

High-level documentation about the system structure, component relationships, and design philosophy. Start here to understand how the system fits together.

### Architecture Decision Records (`adr/`)
**Audience**: Everyone
**Purpose**: Understand why decisions were made

Records of significant architectural decisions, including context, alternatives considered, and consequences. Read these to understand the "why" behind the code.

### Module Documentation (`modules/`)
**Audience**: Developers, AI agents
**Purpose**: Understand specific components

Detailed documentation for each module in the package. Includes public APIs, usage examples, and implementation notes.

### Agent Documentation (`agents/`)
**Audience**: AI agents (Claude, Cursor, etc.)
**Purpose**: Guide AI agents working with the codebase

Specific guidelines, conventions, and patterns for AI agents. Human developers will also find this useful for understanding coding standards.

## Quick Start Guides

### For New Developers
1. Read `agents/working-with-this-codebase.md`
2. Review `architecture/README.md`
3. Check out `adr/README.md` for decision records
4. Explore `modules/` for specific components

### For AI Agents
1. **Start here**: `agents/README.md`
2. **Before coding**: `agents/coding-conventions.md`
3. **When implementing**: `agents/common-patterns.md`
4. **Reference**: Project root `.cursorrules` or `.claude/code_style.md`

### For Understanding Architecture
1. Read `architecture/README.md`
2. Review relevant ADRs in `adr/`
3. Check component relationships in architecture docs
4. Dive into specific modules in `modules/`
