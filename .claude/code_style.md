# Code Style Guide for Claude

This document provides specific instructions for Claude when working with the assistant package.

## Overview

This is a Python package with strict typing, comprehensive documentation, and agent-friendly design. Every piece of code should be easily understood and maintained by AI agents.

## Core Principles

### 1. Explicitness Over Implicitness
- Never rely on implicit behavior
- Make all dependencies explicit
- Type hints are mandatory, not optional
- No magic or clever tricks

### 2. Comprehensive Documentation
- Every public function/class has a docstring
- Complex logic has explanatory comments
- Architecture decisions are recorded in ADRs
- Module documentation explains the "why"

### 3. Strict Typing
- All functions have complete type hints
- Use specific types, avoid `Any`
- Use `typing` module for complex types
- Type check with mypy in strict mode

### 4. Testability
- Write testable code (pure functions, dependency injection)
- Tests mirror source structure
- High coverage on critical paths
- Use fixtures for shared test setup

## Code Style Standards

### Type Hints

**Always Required:**
```python
from typing import Optional, List, Dict, Any

def process_items(
    items: List[str],
    config: Dict[str, Any],
    timeout: Optional[int] = None
) -> Dict[str, List[str]]:
    """Process items with given configuration."""
    ...
```

**Type Aliases for Clarity:**
```python
from typing import TypeAlias

UserID: TypeAlias = str
UserData: TypeAlias = Dict[str, Any]

def get_user(user_id: UserID) -> UserData:
    """Retrieve user data."""
    ...
```

**Protocols for Interfaces:**
```python
from typing import Protocol

class DataStore(Protocol):
    """Data storage interface."""

    def save(self, key: str, value: str) -> None:
        """Save data."""
        ...

    def load(self, key: str) -> str:
        """Load data."""
        ...
```

### Docstrings

**Google Style (Required):**
```python
def calculate_metrics(
    data: List[float],
    window_size: int = 10
) -> Dict[str, float]:
    """Calculate statistical metrics for data.

    Computes mean, median, and standard deviation over a sliding window.
    This is useful for analyzing time-series data.

    Args:
        data: List of numerical values to analyze. Must not be empty.
        window_size: Size of the sliding window. Must be positive.
            Defaults to 10.

    Returns:
        Dictionary with keys 'mean', 'median', and 'std', each mapping
        to the computed statistical value.

    Raises:
        ValueError: If data is empty or window_size is not positive.

    Example:
        >>> data = [1.0, 2.0, 3.0, 4.0, 5.0]
        >>> metrics = calculate_metrics(data, window_size=3)
        >>> print(metrics['mean'])
        3.0
    """
    if not data:
        raise ValueError("Data cannot be empty")
    if window_size <= 0:
        raise ValueError("Window size must be positive")

    # Implementation...
    ...
```

### Error Handling

**Specific Exceptions:**
```python
# Good
def divide(a: float, b: float) -> float:
    """Divide two numbers."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b

# Bad
def divide(a: float, b: float) -> float:
    """Divide two numbers."""
    if b == 0:
        raise Exception("Error")  # Too generic
    return a / b
```

**Custom Exception Hierarchy:**
```python
class AssistantError(Exception):
    """Base exception for assistant package."""
    pass

class ValidationError(AssistantError):
    """Data validation failed."""

    def __init__(self, message: str, field: str) -> None:
        super().__init__(message)
        self.field = field
```

**Document All Exceptions:**
```python
def load_config(path: str) -> Dict[str, Any]:
    """Load configuration from file.

    Args:
        path: Path to configuration file.

    Returns:
        Parsed configuration dictionary.

    Raises:
        FileNotFoundError: If configuration file doesn't exist.
        ValidationError: If configuration format is invalid.
        PermissionError: If file cannot be read due to permissions.
    """
    ...
```

### Function Design

**Pure Functions When Possible:**
```python
# Good - pure function
def calculate_total(items: List[float], tax_rate: float) -> float:
    """Calculate total with tax."""
    return sum(items) * (1 + tax_rate)

# Avoid - side effects
def calculate_and_log_total(items: List[float], tax_rate: float) -> float:
    """Calculate total and log it."""
    total = sum(items) * (1 + tax_rate)
    logging.info(f"Total: {total}")  # Side effect
    return total
```

**Single Responsibility:**
```python
# Good - each function does one thing
def load_data(path: str) -> List[Dict[str, Any]]:
    """Load data from file."""
    ...

def validate_data(data: List[Dict[str, Any]]) -> None:
    """Validate data structure."""
    ...

def transform_data(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Transform data to required format."""
    ...

# Avoid - doing too much
def load_validate_transform(path: str) -> List[Dict[str, Any]]:
    """Load, validate, and transform data."""
    ...
```

**Dependency Injection:**
```python
# Good - dependencies are parameters
from typing import Callable

def process_data(
    data: List[str],
    processor: Callable[[str], str]
) -> List[str]:
    """Process data using provided processor."""
    return [processor(item) for item in data]

# Avoid - hard-coded dependency
def process_data(data: List[str]) -> List[str]:
    """Process data."""
    from assistant.processors import default_processor
    return [default_processor(item) for item in data]
```

### Class Design

**Dataclasses for Data:**
```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class UserConfig:
    """User configuration."""
    username: str
    email: str
    max_retries: int = 3
    tags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not self.username:
            raise ValueError("Username is required")
        if "@" not in self.email:
            raise ValueError("Invalid email format")
```

**Properties for Computed Values:**
```python
class DataProcessor:
    """Process and analyze data."""

    def __init__(self, data: List[int]) -> None:
        self._data = data
        self._cache: Optional[float] = None

    @property
    def mean(self) -> float:
        """Calculate mean (cached)."""
        if self._cache is None:
            self._cache = sum(self._data) / len(self._data)
        return self._cache

    @property
    def data(self) -> List[int]:
        """Get data (read-only copy)."""
        return self._data.copy()
```

### Code Organization

**Module Structure:**
```python
"""Module docstring explaining purpose.

This module handles X, Y, and Z. It is designed to be used
in the following contexts...
"""

# Standard library imports
import os
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

# Third-party imports
import numpy as np
import pandas as pd

# Local imports
from assistant.core import BaseProcessor
from assistant.utils import load_config, validate_input

# Constants
DEFAULT_TIMEOUT: int = 30
MAX_RETRIES: int = 3

# Type aliases
UserData: TypeAlias = Dict[str, Any]

# Classes and functions...
```

**Import Guidelines:**
- Group imports (stdlib, third-party, local)
- Alphabetical within groups
- One blank line between groups
- Absolute imports preferred

## Testing Guidelines

### Test Structure

**Arrange-Act-Assert:**
```python
def test_calculate_total_with_tax() -> None:
    """Test total calculation includes tax."""
    # Arrange
    items = [10.0, 20.0, 30.0]
    tax_rate = 0.1
    expected = 66.0

    # Act
    result = calculate_total(items, tax_rate)

    # Assert
    assert result == expected
```

### Test Naming

**Descriptive Names:**
```python
# Good
def test_divide_by_zero_raises_value_error() -> None:
    """Test that division by zero raises ValueError."""
    ...

def test_user_config_validates_email_format() -> None:
    """Test that invalid email format raises error."""
    ...

# Bad
def test_divide() -> None:
    ...

def test_config() -> None:
    ...
```

### Fixtures

**Reusable Setup:**
```python
import pytest
from typing import List, Dict, Any

@pytest.fixture
def sample_data() -> List[int]:
    """Provide sample numerical data."""
    return [1, 2, 3, 4, 5]

@pytest.fixture
def sample_config() -> Dict[str, Any]:
    """Provide sample configuration."""
    return {
        "api_key": "test_key",
        "endpoint": "http://localhost:8000",
        "timeout": 30
    }

def test_process_data(sample_data: List[int]) -> None:
    """Test data processing with sample data."""
    result = process(sample_data)
    assert len(result) == 5
```

## Documentation Workflow

### When Adding New Code

1. **Write the docstring first** (helps clarify purpose)
2. **Add type hints** (makes interface clear)
3. **Implement the function** (with the contract defined)
4. **Write tests** (verify implementation)
5. **Update module docs** in `docs/modules/`

### When Making Architecture Decisions

1. **Create ADR** in `docs/adr/`
2. **Follow the template** (Status, Context, Decision, Consequences)
3. **Consider alternatives** (document what you didn't choose)
4. **Update the index** in `docs/adr/README.md`

### When Changing Public API

1. **Update docstrings**
2. **Update module documentation**
3. **Update examples** in docs
4. **Update README** if needed
5. **Create ADR** if breaking change

## Common Patterns

Refer to `docs/agents/common-patterns.md` for:
- Configuration management
- Resource management (context managers)
- Error handling (Result types)
- Dependency injection (protocols)
- Factory pattern (registries)
- Builder pattern (fluent APIs)
- Iterator pattern (generators)
- Caching strategies
- Validation patterns

## Anti-Patterns to Avoid

### 1. Mutable Default Arguments
```python
# NEVER do this
def append_item(item: str, items: List[str] = []) -> List[str]:
    items.append(item)
    return items

# ALWAYS do this
def append_item(item: str, items: Optional[List[str]] = None) -> List[str]:
    if items is None:
        items = []
    items.append(item)
    return items
```

### 2. Bare Except Clauses
```python
# NEVER do this
try:
    risky_operation()
except:
    pass

# ALWAYS do this
try:
    risky_operation()
except (ValueError, KeyError) as e:
    logger.error(f"Operation failed: {e}")
    raise
```

### 3. Untyped Code
```python
# NEVER do this
def process(data):
    return [x.upper() for x in data]

# ALWAYS do this
def process(data: List[str]) -> List[str]:
    """Convert all strings to uppercase."""
    return [x.upper() for x in data]
```

### 4. Magic Numbers
```python
# NEVER do this
def calculate_score(value: float) -> float:
    return value * 0.85 + 42

# ALWAYS do this
SCORE_MULTIPLIER: float = 0.85
BASE_SCORE: float = 42.0

def calculate_score(value: float) -> float:
    """Calculate score from value."""
    return value * SCORE_MULTIPLIER + BASE_SCORE
```

## Workflow for Claude

### Starting a New Task

1. **Understand the requirement**
2. **Check existing documentation** in `docs/agents/`
3. **Review similar code** for patterns
4. **Check relevant ADRs** for decisions
5. **Plan the implementation**

### Implementing Code

1. **Create the structure** (classes, functions)
2. **Add type hints** (complete typing)
3. **Write docstrings** (Google style)
4. **Implement logic** (following patterns)
5. **Add error handling** (specific exceptions)
6. **Write tests** (comprehensive coverage)

### Finishing Up

1. **Run type checker**: `mypy src/`
2. **Run linter**: `ruff check src/`
3. **Run formatter**: `black src/`
4. **Run tests**: `pytest`
5. **Update documentation**:
   - Module docs in `docs/modules/`
   - ADR if needed in `docs/adr/`
   - README if API changed
6. **Review the code** (is it agent-friendly?)

## Questions to Ask Yourself

Before committing code:

- [ ] Are all functions fully typed?
- [ ] Do all public APIs have docstrings?
- [ ] Are exceptions specific and documented?
- [ ] Are there tests for new functionality?
- [ ] Is the code pure and testable where possible?
- [ ] Are dependencies injected, not hard-coded?
- [ ] Is module documentation updated?
- [ ] Is an ADR needed for this change?
- [ ] Does the code follow established patterns?
- [ ] Would another AI agent understand this code?

## Resources

- **Getting Started**: `docs/agents/working-with-this-codebase.md`
- **Conventions**: `docs/agents/coding-conventions.md`
- **Patterns**: `docs/agents/common-patterns.md`
- **ADRs**: `docs/adr/`
- **Module Docs**: `docs/modules/`
- **Project Config**: `pyproject.toml`

## Remember

> Code is read far more often than it is written. Write code that AI agents
> (and humans) can easily understand, modify, and maintain. Be explicit,
> be thorough, and document your decisions.
