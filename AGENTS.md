# Assistant Development Guide for AI Agents

... docs ...

## Project Structure

```
assistant/
├── src/
│   └── assistant/          # Main package
│       └── __init__.py
├── tests/                  # Test suite
├── docs/                   # Documentation
│   ├── architecture/       # System architecture
│   ├── adr/               # Architecture Decision Records
│   ├── modules/           # Module documentation
│   └── agents/            # AI agent guidelines
├── .cursorrules           # Cursor AI configuration
├── .claude/               # Claude AI configuration
├── pyproject.toml         # Project configuration
└── README.md              # This file
```

# Working with This Codebase

## Project Overview

**Project Name**: assistant
**Type**: Python package
**Layout**: src layout with the package at `src/assistant/`
**Python Version**: >= 3.13
**Package Manager**: uv

## Quick Start

### Setup Development Environment

#### Quick Setup (Recommended)

```bash
# Install uv if not already installed
make install-uv

# Set up everything
make dev-setup

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

#### Manual Setup

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install package in development mode with dev dependencies
uv pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=assistant --cov-report=term-missing
```

### Code Quality Checks

#### Using Makefile (Recommended)

```bash
# Run all checks
make check

# Individual checks
make typecheck
make lint
make test

# Format code
make format

# Run pre-commit hooks
make pre-commit-run
```

#### Manual Commands

```bash
# Type checking
mypy src/

# Linting and formatting
ruff check src/
black --check src/

# Auto-fix issues
ruff check --fix src/
black src/
```

## Project Structure

```
/Users/filippopacifici/code/assistant/
├── src/
│   └── assistant/          # Main package
│       └── __init__.py
├── tests/                  # Test files (mirror src structure)
├── docs/
│   ├── architecture/       # High-level architecture docs
│   ├── adr/               # Architecture Decision Records
│   ├── modules/           # Per-module documentation
│   └── agents/            # AI agent-specific docs
├── .claude/               # Claude-specific configurations
├── .cursorrules           # Cursor AI code style rules
├── pyproject.toml         # Project configuration and dependencies
├── README.md              # User-facing documentation
└── LICENSE                # Project license
```

## Development Workflow

### Adding New Modules

1. Create the module file in `src/assistant/`
2. Add type hints to all functions and classes
3. Create corresponding test file in `tests/`
4. Document the module in `docs/modules/`
5. Update `src/assistant/__init__.py` if exposing public API

### Making Architecture Decisions

1. Create a new ADR in `docs/adr/` following the template
2. Discuss the decision, alternatives, and consequences
3. Update the index in `docs/adr/README.md`
4. Implement the decision
5. Reference the ADR in relevant code comments

### Writing Tests

- Place tests in `tests/` mirroring the `src/assistant/` structure
- Use `test_` prefix for test files and functions
- Use `Test` prefix for test classes
- Aim for high coverage but focus on meaningful tests
- Mock external dependencies

### Type Checking

This project uses strict typing:
- All functions must have complete type hints
- Use `typing` module for complex types
- Avoid `Any` unless absolutely necessary
- Use `TYPE_CHECKING` for avoiding circular imports

### Documentation Standards

- Public APIs must have docstrings (Google style preferred)
- Complex logic should have explanatory comments
- Update module documentation when changing behavior
- Keep examples in sync with code

## Common Tasks

### Adding a Dependency

```bash
# Add to pyproject.toml under [project.dependencies]
# or for dev dependencies under [project.optional-dependencies.dev]

# Then sync the environment
uv pip install -e ".[dev]"
```

### Running Individual Tests

```bash
pytest tests/test_specific.py
pytest tests/test_specific.py::test_function_name
```

### Updating Documentation

1. Code-level: Update docstrings in the code
2. Module-level: Update docs in `docs/modules/`
3. Architecture-level: Create or update ADRs in `docs/adr/`
4. Project-level: Update README.md

## Conventions

### Import Order
1. Standard library imports
2. Third-party imports
3. Local application imports

(Automatically organized by ruff/isort)

### Naming Conventions
- `snake_case` for functions, variables, and module names
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants
- Prefix private items with `_`

### File Organization
- One main class per file (unless closely related)
- Group related functions in modules
- Use `__init__.py` to define public API

## Resources

- [uv Documentation](https://github.com/astral-sh/uv)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)
- [pytest Documentation](https://docs.pytest.org/)
- [Ruff Rules](https://docs.astral.sh/ruff/rules/)



# Common Patterns

This document describes common design patterns and idioms used in the assistant package.

## Configuration Management

### Pattern: Config Dataclass

Use dataclasses for configuration with validation.

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

@dataclass
class AppConfig:
    """Application configuration."""

    # Required fields
    api_key: str
    endpoint: str

    # Optional with defaults
    timeout: int = 30
    max_retries: int = 3

    # Computed defaults
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "assistant")

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.timeout <= 0:
            raise ValueError("Timeout must be positive")
        if not self.cache_dir.exists():
            self.cache_dir.mkdir(parents=True)
```

## Resource Management

### Pattern: Context Manager

Use context managers for resource cleanup.

```python
from typing import Optional, TextIO
from pathlib import Path

class FileProcessor:
    """Process files with automatic cleanup."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: Optional[TextIO] = None

    def __enter__(self) -> "FileProcessor":
        """Open file."""
        self._file = self.path.open("r")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close file."""
        if self._file:
            self._file.close()

    def process(self) -> str:
        """Process file contents."""
        if not self._file:
            raise RuntimeError("File not opened")
        return self._file.read()

# Usage
with FileProcessor(Path("data.txt")) as processor:
    content = processor.process()
```

## Error Handling

### Pattern: Custom Exception Hierarchy

Create a hierarchy of custom exceptions.

```python
class AssistantError(Exception):
    """Base exception for assistant package."""
    pass

class ConfigurationError(AssistantError):
    """Configuration-related errors."""
    pass

class ValidationError(AssistantError):
    """Data validation errors."""

    def __init__(self, message: str, field: str) -> None:
        super().__init__(message)
        self.field = field

class ProcessingError(AssistantError):
    """Data processing errors."""

    def __init__(self, message: str, data: Optional[Any] = None) -> None:
        super().__init__(message)
        self.data = data
```

### Pattern: Result Type

Use a Result type for operations that can fail.

```python
from dataclasses import dataclass
from typing import Generic, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E", bound=Exception)

@dataclass
class Success(Generic[T]):
    """Successful result."""
    value: T

@dataclass
class Failure(Generic[E]):
    """Failed result."""
    error: E

Result = Union[Success[T], Failure[E]]

def divide(a: float, b: float) -> Result[float, ValueError]:
    """Divide two numbers."""
    if b == 0:
        return Failure(ValueError("Division by zero"))
    return Success(a / b)

# Usage
result = divide(10, 2)
match result:
    case Success(value):
        print(f"Result: {value}")
    case Failure(error):
        print(f"Error: {error}")
```

## Dependency Injection

### Pattern: Protocol-Based Injection

Use protocols (interfaces) for dependency injection.

```python
from typing import Protocol, List

class DataStore(Protocol):
    """Protocol for data storage."""

    def save(self, key: str, value: str) -> None:
        """Save data."""
        ...

    def load(self, key: str) -> str:
        """Load data."""
        ...

class FileStore:
    """File-based data store."""

    def save(self, key: str, value: str) -> None:
        """Save to file."""
        Path(key).write_text(value)

    def load(self, key: str) -> str:
        """Load from file."""
        return Path(key).read_text()

class DataProcessor:
    """Process and store data."""

    def __init__(self, store: DataStore) -> None:
        self.store = store

    def process(self, key: str, data: str) -> None:
        """Process and save data."""
        processed = data.upper()
        self.store.save(key, processed)

# Usage
processor = DataProcessor(FileStore())
processor.process("output.txt", "hello world")
```

## Factory Pattern

### Pattern: Registry-Based Factory

Use a registry for creating objects by name.

```python
from typing import Callable, Dict, Type, TypeVar

T = TypeVar("T")

class ProcessorRegistry:
    """Registry for processor types."""

    _processors: Dict[str, Type["Processor"]] = {}

    @classmethod
    def register(cls, name: str) -> Callable[[Type[T]], Type[T]]:
        """Register a processor type."""
        def decorator(processor_class: Type[T]) -> Type[T]:
            cls._processors[name] = processor_class  # type: ignore
            return processor_class
        return decorator

    @classmethod
    def create(cls, name: str, **kwargs) -> "Processor":
        """Create a processor by name."""
        if name not in cls._processors:
            raise ValueError(f"Unknown processor: {name}")
        return cls._processors[name](**kwargs)

class Processor(Protocol):
    """Processor protocol."""

    def process(self, data: str) -> str:
        """Process data."""
        ...

@ProcessorRegistry.register("upper")
class UpperProcessor:
    """Convert to uppercase."""

    def process(self, data: str) -> str:
        """Process data."""
        return data.upper()

@ProcessorRegistry.register("lower")
class LowerProcessor:
    """Convert to lowercase."""

    def process(self, data: str) -> str:
        """Process data."""
        return data.lower()

# Usage
processor = ProcessorRegistry.create("upper")
result = processor.process("Hello")
```

## Builder Pattern

### Pattern: Fluent Builder

Use builder pattern for complex object construction.

```python
from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class Query:
    """Database query."""
    table: str
    columns: List[str] = field(default_factory=list)
    where: Optional[str] = None
    limit: Optional[int] = None
    offset: Optional[int] = None

class QueryBuilder:
    """Build database queries fluently."""

    def __init__(self, table: str) -> None:
        self._query = Query(table=table)

    def select(self, *columns: str) -> "QueryBuilder":
        """Select columns."""
        self._query.columns.extend(columns)
        return self

    def where(self, condition: str) -> "QueryBuilder":
        """Add where clause."""
        self._query.where = condition
        return self

    def limit(self, limit: int) -> "QueryBuilder":
        """Add limit."""
        self._query.limit = limit
        return self

    def offset(self, offset: int) -> "QueryBuilder":
        """Add offset."""
        self._query.offset = offset
        return self

    def build(self) -> Query:
        """Build the query."""
        return self._query

# Usage
query = (QueryBuilder("users")
    .select("id", "name", "email")
    .where("age > 18")
    .limit(10)
    .build())
```

## Iterator Pattern

### Pattern: Generator-Based Iterator

Use generators for memory-efficient iteration.

```python
from pathlib import Path
from typing import Iterator, List

def read_large_file_in_chunks(
    path: Path,
    chunk_size: int = 1024
) -> Iterator[str]:
    """Read large file in chunks.

    Args:
        path: Path to file.
        chunk_size: Size of each chunk in bytes.

    Yields:
        File content chunks.
    """
    with path.open("r") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk

def process_items_in_batches(
    items: List[str],
    batch_size: int = 100
) -> Iterator[List[str]]:
    """Process items in batches.

    Args:
        items: Items to process.
        batch_size: Size of each batch.

    Yields:
        Batches of items.
    """
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]

# Usage
for chunk in read_large_file_in_chunks(Path("large_file.txt")):
    process(chunk)

for batch in process_items_in_batches(all_items, batch_size=50):
    process_batch(batch)
```

## Caching Pattern

### Pattern: LRU Cache with Expiration

Use caching for expensive operations.

```python
from functools import lru_cache
from time import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")

def timed_lru_cache(
    seconds: int,
    maxsize: int = 128
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """LRU cache with time-based expiration.

    Args:
        seconds: Cache lifetime in seconds.
        maxsize: Maximum cache size.

    Returns:
        Decorator function.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        func_with_cache = lru_cache(maxsize=maxsize)(func)
        func_with_cache.cache_info = func_with_cache.cache_info  # type: ignore
        func_with_cache.lifetime = seconds  # type: ignore
        func_with_cache.expiration = time() + seconds  # type: ignore

        def wrapped(*args: Any, **kwargs: Any) -> T:
            if time() > func_with_cache.expiration:  # type: ignore
                func_with_cache.cache_clear()  # type: ignore
                func_with_cache.expiration = time() + seconds  # type: ignore
            return func_with_cache(*args, **kwargs)

        wrapped.cache_clear = func_with_cache.cache_clear  # type: ignore
        wrapped.cache_info = func_with_cache.cache_info  # type: ignore
        return wrapped

    return decorator

@timed_lru_cache(seconds=300, maxsize=100)
def expensive_operation(param: str) -> str:
    """Expensive operation with caching."""
    # Simulate expensive operation
    return f"Result for {param}"
```

## Validation Pattern

### Pattern: Pydantic-Style Validation

Use validation for data integrity.

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class User:
    """User model with validation."""

    username: str
    email: str
    age: int
    tags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate user data."""
        self._validate_username()
        self._validate_email()
        self._validate_age()

    def _validate_username(self) -> None:
        """Validate username."""
        if len(self.username) < 3:
            raise ValidationError(
                "Username must be at least 3 characters",
                field="username"
            )
        if not self.username.isalnum():
            raise ValidationError(
                "Username must be alphanumeric",
                field="username"
            )

    def _validate_email(self) -> None:
        """Validate email."""
        if "@" not in self.email:
            raise ValidationError(
                "Invalid email format",
                field="email"
            )

    def _validate_age(self) -> None:
        """Validate age."""
        if self.age < 0 or self.age > 150:
            raise ValidationError(
                "Age must be between 0 and 150",
                field="age"
            )
```

## Testing Patterns

### Pattern: Test Fixtures

Use fixtures for reusable test setup.

```python
import pytest
from pathlib import Path
from typing import Iterator

@pytest.fixture
def temp_file(tmp_path: Path) -> Iterator[Path]:
    """Create temporary file for testing."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("test content")
    yield file_path
    # Cleanup happens automatically

@pytest.fixture
def sample_config() -> AppConfig:
    """Provide sample configuration."""
    return AppConfig(
        api_key="test_key",
        endpoint="http://localhost:8000"
    )

def test_file_processing(temp_file: Path) -> None:
    """Test file processing."""
    content = temp_file.read_text()
    assert content == "test content"

def test_config_usage(sample_config: AppConfig) -> None:
    """Test configuration."""
    assert sample_config.timeout == 30
```


# Coding Conventions

This document outlines the specific coding conventions used in the assistant package.

## Type Hints

### Required
All public functions, methods, and classes must have complete type hints.

```python
from typing import Optional, List, Dict, Any

def process_data(
    input_data: List[str],
    config: Dict[str, Any],
    timeout: Optional[int] = None
) -> Dict[str, List[str]]:
    """Process input data according to configuration."""
    ...
```

### Return Types
Always specify return types, even for functions returning `None`.

```python
def save_to_file(data: str, path: str) -> None:
    """Save data to file."""
    ...
```

### Complex Types
Use type aliases for complex types to improve readability.

```python
from typing import Dict, List, TypeAlias

UserData: TypeAlias = Dict[str, List[str]]

def get_user_data(user_id: str) -> UserData:
    """Retrieve user data."""
    ...
```

### Avoiding Circular Imports
Use `TYPE_CHECKING` for type hints that would cause circular imports.

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from assistant.models import User

def process_user(user: "User") -> None:
    """Process user data."""
    ...
```

## Docstrings

### Format
Use Google-style docstrings for all public APIs.

```python
def calculate_metrics(
    data: List[float],
    window_size: int = 10
) -> Dict[str, float]:
    """Calculate statistical metrics for the given data.

    Computes mean, median, and standard deviation over a sliding window.

    Args:
        data: List of numerical values to analyze.
        window_size: Size of the sliding window. Defaults to 10.

    Returns:
        Dictionary containing 'mean', 'median', and 'std' keys.

    Raises:
        ValueError: If data is empty or window_size is invalid.

    Example:
        >>> data = [1.0, 2.0, 3.0, 4.0, 5.0]
        >>> metrics = calculate_metrics(data, window_size=3)
        >>> print(metrics['mean'])
        3.0
    """
    ...
```

### Required Sections
- Brief summary (one line)
- Extended description (if needed)
- Args: For all parameters
- Returns: For non-None returns
- Raises: For exceptions that callers should handle
- Example: For public APIs (optional but encouraged)

## Error Handling

### Specific Exceptions
Raise specific exceptions, not generic ones.

```python
# Good
if len(data) == 0:
    raise ValueError("Data cannot be empty")

# Bad
if len(data) == 0:
    raise Exception("Data cannot be empty")
```

### Custom Exceptions
Create custom exceptions for domain-specific errors.

```python
class AssistantError(Exception):
    """Base exception for assistant package."""
    pass

class ConfigurationError(AssistantError):
    """Raised when configuration is invalid."""
    pass
```

### Exception Documentation
Document exceptions in docstrings.

```python
def load_config(path: str) -> Dict[str, Any]:
    """Load configuration from file.

    Args:
        path: Path to configuration file.

    Returns:
        Parsed configuration dictionary.

    Raises:
        FileNotFoundError: If configuration file doesn't exist.
        ConfigurationError: If configuration is invalid.
    """
    ...
```

## Function Design

### Pure Functions
Prefer pure functions when possible.

```python
# Good - pure function
def calculate_total(items: List[float], tax_rate: float) -> float:
    """Calculate total with tax."""
    subtotal = sum(items)
    return subtotal * (1 + tax_rate)

# Avoid - function with side effects
def calculate_and_save_total(items: List[float], tax_rate: float) -> float:
    """Calculate total and save to database."""
    total = sum(items) * (1 + tax_rate)
    save_to_db(total)  # Side effect
    return total
```

### Single Responsibility
Each function should do one thing well.

```python
# Good - separate concerns
def load_data(path: str) -> List[Dict[str, Any]]:
    """Load data from file."""
    ...

def validate_data(data: List[Dict[str, Any]]) -> bool:
    """Validate data structure."""
    ...

def transform_data(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Transform data to required format."""
    ...

# Avoid - doing too much
def load_validate_and_transform(path: str) -> List[Dict[str, Any]]:
    """Load, validate, and transform data."""
    ...
```

### Dependency Injection
Pass dependencies as parameters rather than importing globally.

```python
# Good
def process_data(
    data: List[str],
    processor: Callable[[str], str]
) -> List[str]:
    """Process data using provided processor."""
    return [processor(item) for item in data]

# Avoid
def process_data(data: List[str]) -> List[str]:
    """Process data using hardcoded processor."""
    from assistant.processors import default_processor
    return [default_processor(item) for item in data]
```

## Class Design

### Dataclasses
Use dataclasses for simple data containers.

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class UserConfig:
    """User configuration settings."""
    username: str
    email: str
    max_retries: int = 3
    timeout: Optional[int] = None
```

### Properties
Use properties for computed attributes or controlled access.

```python
class DataProcessor:
    """Process and manage data."""

    def __init__(self, data: List[int]) -> None:
        self._data = data

    @property
    def mean(self) -> float:
        """Calculate mean of data."""
        return sum(self._data) / len(self._data)

    @property
    def data(self) -> List[int]:
        """Get data (read-only)."""
        return self._data.copy()
```

### Magic Methods
Implement magic methods for intuitive usage.

```python
class Dataset:
    """Dataset container."""

    def __init__(self, items: List[Any]) -> None:
        self._items = items

    def __len__(self) -> int:
        """Return number of items."""
        return len(self._items)

    def __getitem__(self, index: int) -> Any:
        """Get item by index."""
        return self._items[index]

    def __repr__(self) -> str:
        """Return string representation."""
        return f"Dataset(items={len(self._items)})"
```

## Testing Conventions

### Test Structure
Follow Arrange-Act-Assert pattern.

```python
def test_calculate_total() -> None:
    """Test total calculation with tax."""
    # Arrange
    items = [10.0, 20.0, 30.0]
    tax_rate = 0.1

    # Act
    result = calculate_total(items, tax_rate)

    # Assert
    assert result == 66.0
```

### Test Naming
Use descriptive test names that explain the scenario.

```python
# Good
def test_calculate_total_with_empty_list_raises_error() -> None:
    ...

def test_load_config_returns_dict_with_expected_keys() -> None:
    ...

# Avoid
def test_1() -> None:
    ...

def test_calculate() -> None:
    ...
```

### Fixtures
Use pytest fixtures for shared test setup.

```python
import pytest
from typing import List

@pytest.fixture
def sample_data() -> List[int]:
    """Provide sample data for tests."""
    return [1, 2, 3, 4, 5]

def test_process_data(sample_data: List[int]) -> None:
    """Test data processing."""
    result = process_data(sample_data)
    assert len(result) == 5
```

## Code Organization

### Module Size
Keep modules focused and reasonably sized (< 500 lines typically).

### Import Organization
Organize imports in three groups with a blank line between each:

```python
# Standard library
import os
import sys
from typing import List, Optional

# Third-party
import numpy as np
import pandas as pd

# Local
from assistant.core import BaseProcessor
from assistant.utils import load_config
```

### Constants
Define constants at the module level.

```python
# At top of module
DEFAULT_TIMEOUT: int = 30
MAX_RETRIES: int = 3
SUPPORTED_FORMATS: List[str] = ["json", "yaml", "toml"]
```

## Comments

### When to Comment
- Explain "why", not "what"
- Document non-obvious behavior
- Explain complex algorithms
- Mark TODOs and FIXMEs

```python
def process_batch(items: List[str], batch_size: int = 100) -> None:
    """Process items in batches."""
    # Process in batches to avoid memory issues with large datasets
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        _process_single_batch(batch)
```

### When Not to Comment
Avoid obvious comments that just repeat the code.

```python
# Bad
counter = 0  # Initialize counter to 0
counter += 1  # Increment counter by 1

# Good - no comments needed, code is self-explanatory
counter = 0
counter += 1
```

## Anti-Patterns to Avoid

### Mutable Default Arguments
```python
# Bad
def append_to_list(item: str, items: List[str] = []) -> List[str]:
    items.append(item)
    return items

# Good
def append_to_list(item: str, items: Optional[List[str]] = None) -> List[str]:
    if items is None:
        items = []
    items.append(item)
    return items
```

### Bare Except
```python
# Bad
try:
    risky_operation()
except:
    pass

# Good
try:
    risky_operation()
except ValueError as e:
    logger.warning(f"Invalid value: {e}")
```

### Type Ignoring Without Reason
```python
# Bad
result = complex_function()  # type: ignore

# Good
result = complex_function()  # type: ignore[attr-defined]  # Third-party lib has incorrect stubs
```
