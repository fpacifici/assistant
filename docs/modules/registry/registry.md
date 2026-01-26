# `assistant.adapters.registry`

The `assistant.adapters.registry` module provides a **runtime registry and cache** for external
source adapter plugins.

It solves two related problems:

- **Mapping provider types to implementations** (e.g. `evernote` → `EvernoteExternalSource`)
- **Instantiating and caching configured provider instances** keyed by the database
  `assistant.models.schema.ExternalSource.id` (instance id)

## Responsibilities

- **Plugin registration**: register an `ExternalSource` implementation for a provider type.
- **Instance resolution**: given an external source instance id (UUID), load the DB row, read YAML
  provider-type config, parse DB query parameters, and instantiate the plugin.
- **Caching**: preserve the initialized instance for repeated use in the same process.
- **Enable/disable**: honor `external_sources.<provider>.enabled` from config; disabled provider
  types are considered unavailable (callers typically skip them).

## Key concepts

### Provider type vs instance id

- **Provider type**: `assistant.models.schema.ExternalSource.provider` (string), identifies the
  adapter plugin class (e.g. `evernote`, `fake`).
- **Instance id**: `assistant.models.schema.ExternalSource.id` (UUID), identifies a specific
  configured integration (e.g. Evernote notebook A vs notebook B).

### Configuration sources

An adapter instance is built from two configuration inputs:

- **Provider-type config (YAML/env)**: read via `Config.get_external_source_config(provider_type)`
  from `config.yaml` under `external_sources.<provider_type>`.
- **Instance query params (DB)**: read from `assistant.models.schema.ExternalSource.provider_query`
  (JSON string) and bound into the instance during construction.

## Public API

### `Registry.register(provider_type, provider_class)`

Registers a plugin class for a provider type.

### `Registry.get_provider(source_id, *, session=None)`

Returns a configured `ExternalSource` instance for a specific external source **instance id**.

Behavior:

- loads the `ExternalSource` DB row for `source_id`
- selects the plugin class using `row.provider`
- reads provider-type YAML config using `row.provider`
- parses `row.provider_query` JSON into `query_params`
- creates an `ExternalSourceInstanceConfig(provider_config=..., query_params=...)`
- instantiates the plugin and caches it by `source_id`

Errors (raised for callers to decide how to handle):

- `ProviderDisabledError`: provider type is disabled in config (`enabled: false`)
- `ExternalSourceNotFoundError`: the DB instance id does not exist
- `ValueError`: provider type is not registered

## Example usage

Register plugins once at process startup (e.g. CLI entrypoint), then resolve instances by id:

```python
import uuid

from assistant.adapters.plugins.fake import FakeExternalSource
from assistant.adapters.registry import get_registry


registry = get_registry()
registry.register("fake", FakeExternalSource)

source_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
provider = registry.get_provider(source_id)

external_ids = provider.list_documents(...)
```

## Relationships

- **Depends on**:
  - `assistant.config.Config` for provider-type config (`external_sources.<provider>`)
  - `assistant.models.schema.ExternalSource` (DB row) for `provider` and `provider_query`
  - `assistant.models.database.get_session_factory()` when a session is not provided
- **Used by**:
  - `assistant.adapters.dataload` to resolve and reuse adapter instances during ingestion

## Notes for implementers of `ExternalSource`

Plugins receive an `ExternalSourceInstanceConfig` at construction time:

- `provider_config` contains YAML/env configuration (credentials, timeouts, etc.)
- `query_params` contains DB-provided query params (e.g. notebook id) that the plugin should apply
  to its external API requests
