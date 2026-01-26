# `assistant.config`

The `assistant.config` module is the **single entry point** for reading configuration from
`config.yaml` and overriding it via environment variables.

## YAML structure

The repository root `config.yaml` is expected to follow this high-level shape:

```yaml
database:
  host: localhost
  port: 5432
  user: assistant
  password: assistant
  name: assistant
  # Optional: full connection string
  # url: postgresql://assistant:assistant@localhost:5432/assistant

document_storage_path: data/documents

external_sources:
  fake:
    enabled: true
    timeout: 30
```

## Environment-variable override mechanism

Any config key can be overridden by setting an environment variable derived from the key path.

- **rule**: `ENVVAR = key_path.upper().replace(".", "_")`
- **examples**:
  - `document_storage_path` → `DOCUMENT_STORAGE_PATH`
  - `database.url` → `DATABASE_URL`
  - `database.host` → `DATABASE_HOST`
  - `external_sources.fake.enabled` → `EXTERNAL_SOURCES_FAKE_ENABLED`

Overrides are **checked first**, before reading from the YAML file.

### Type coercion

Environment variables are strings, but `Config.get()` will attempt to coerce them to the expected
type when it can infer it from:

- the YAML value type (preferred), otherwise
- the provided default type.

Supported coercions:

- **bool**: `true/false` (case-insensitive)
- **int**: base-10 integers
- **float**: Python `float()` parsing
- **str**: left as-is

If coercion fails, a `ValueError` is raised that includes the env var name and the config key.

## Typed config schema

`assistant.config` models the YAML structure with `TypedDict` types:

- `AssistantConfig`: top-level file structure
- `DatabaseConfig`: database configuration (returned as a fully-resolved structure)
- `ExternalSourceProviderConfig`: common fields for provider configs

## Recommended usage patterns

### Use higher-level typed structures

Prefer retrieving a typed structure that already reflects overrides:

- `Config.get_database_config()` returns a `DatabaseConfig` whose values already incorporate any
  `DATABASE_*` environment variable overrides.

### Generic reads

Use `Config.get("some.nested.key", default)` for one-off values, relying on the global override
rule described above.

## Extending the configuration

When adding a new config section:

- add a new `TypedDict` for the section in `src/assistant/config.py`
- add it to `AssistantConfig`
- add a dedicated “high-level” getter (similar to `get_database_config()`) if multiple call sites
  will use the section
- add tests under `tests/test_config.py` covering:
  - YAML parsing
  - env override naming and precedence
  - type coercion and coercion failures
