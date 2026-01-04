# Architecture Documentation

This directory contains high-level architecture documentation for the assistant package.

## Purpose

Architecture documentation provides:
- System overview and design philosophy
- Component relationships and interactions
- Key design decisions and rationale
- Guidelines for architectural evolution

## Contents

### Planned Documents

- `overview.md` - High-level system architecture
- `design-philosophy.md` - Core principles guiding design decisions
- `component-diagram.md` - Visual representation of system components
- `data-flow.md` - How data flows through the system
- `deployment.md` - Deployment considerations and patterns

## For Developers and AI Agents

When working on the system:

1. **Understand the big picture** - Read overview.md first
2. **Follow design principles** - Align with design-philosophy.md
3. **Respect boundaries** - Understand component responsibilities
4. **Document changes** - Update architecture docs when making structural changes
5. **Create ADRs** - Record significant architectural decisions in `/docs/adr/`

## Relationship to Other Documentation

```
docs/
├── architecture/        ← High-level system design (you are here)
├── adr/                ← Specific decisions with rationale
├── modules/            ← Detailed per-module documentation
└── agents/             ← AI agent working guidelines
```

- **Architecture docs**: What the system looks like from 10,000 feet
- **ADRs**: Why specific decisions were made
- **Module docs**: How individual components work
- **Agent docs**: How to work effectively with the codebase

## When to Update Architecture Documentation

Update architecture docs when:
- Adding new major components
- Changing system boundaries
- Introducing new patterns or paradigms
- Refactoring significant portions of the system
- Changing data flow or component interactions

## Guidelines

### Keep It Current
Architecture docs should reflect reality, not aspirations. Update them when the system changes.

### Be Visual
Include diagrams when helpful. Use tools like:
- Mermaid (markdown-compatible)
- ASCII art (simple and version-control friendly)
- PlantUML (for complex diagrams)

### Focus on Structure
Architecture docs explain:
- What components exist
- How they relate to each other
- Why the structure is designed this way

They don't explain:
- Implementation details (that's for module docs)
- Specific decisions (that's for ADRs)
- How to use the system (that's for README)

## Example Architecture Document Structure

```markdown
# Component Name

## Purpose
Why this component exists and what problem it solves.

## Responsibilities
- What this component is responsible for
- What it explicitly is NOT responsible for

## Dependencies
- What other components does it depend on?
- What external systems does it integrate with?

## Interfaces
- Public API surface
- Integration points
- Communication protocols

## Design Constraints
- Performance requirements
- Scalability considerations
- Security requirements

## Future Considerations
- Known limitations
- Planned improvements
- Areas for evolution
```

## Quick Reference

For common architectural questions:

- **"What does component X do?"** → Check this directory
- **"Why was decision Y made?"** → Check `/docs/adr/`
- **"How does module Z work?"** → Check `/docs/modules/`
- **"How do I work with this codebase?"** → Check `/docs/agents/`
