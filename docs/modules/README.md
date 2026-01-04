# Module Documentation

This directory contains detailed documentation for each module in the assistant package.

## Purpose

Module documentation helps AI agents and developers understand:
- The purpose and responsibility of each module
- Public APIs and their usage
- Internal architecture and design patterns
- Dependencies and relationships with other modules
- Examples and common usage patterns

## Structure

Each module should have its own markdown file named after the module:
- `module_name.md` - For top-level modules
- `subpackage/module_name.md` - For modules in subpackages

## Template

Use this template for documenting modules:

```markdown
# Module: [module.name]

## Purpose
Brief description of what this module does and why it exists.

## Public API

### Classes
- `ClassName`: Description
  - Key methods and their purpose

### Functions
- `function_name(args) -> return_type`: Description

### Constants/Types
- `CONSTANT_NAME`: Description

## Architecture

### Design Patterns
What patterns are used and why?

### Dependencies
- Internal: What other modules does this depend on?
- External: What third-party packages are used?

## Usage Examples

```python
# Common usage patterns
```

## Implementation Notes
Important details about implementation that agents should know.

## Testing Considerations
What to keep in mind when testing this module.
```

## Guidelines for AI Agents

When creating or modifying modules:
1. Always update the corresponding module documentation
2. Include type hints for all public APIs
3. Document any non-obvious behavior or edge cases
4. Keep examples up to date with the code
5. Note any performance considerations or limitations
