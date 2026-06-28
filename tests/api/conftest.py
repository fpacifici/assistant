"""API test fixtures."""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from assistant.api.app import create_app
from assistant.api.dependencies import get_session
from assistant.auth.service import create_access_token
from assistant.models import schema as _schema  # noqa: F401
from assistant.models.database import Base
from assistant.models.schema import Credential, User

_TEST_JWT_SECRET = "test-jwt-secret-do-not-use-in-production"


@pytest.fixture(scope="session", autouse=True)
def _set_jwt_secret() -> Generator[None]:
    """Ensure JWT_SECRET is set for the entire test session."""
    os.environ["JWT_SECRET"] = _TEST_JWT_SECRET
    yield
    os.environ.pop("JWT_SECRET", None)


@pytest.fixture(scope="module")
def _api_engine():  # noqa: ANN202
    """Module-scoped engine with schema stripping for SQLite."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    tables = Base.metadata.sorted_tables
    original_schemas: dict[str, str | None] = {}

    for table in tables:
        original_schemas[table.fullname] = table.schema
        table.schema = None

    for table in tables:
        for col in table.columns:
            for fk in col.foreign_keys:
                fk._table_key = None  # type: ignore[attr-defined]
                ref_table_name = fk.column.table.name
                ref_col_name = fk.column.name
                ref_table = Base.metadata.tables.get(ref_table_name)
                if ref_table is not None:
                    fk.column = ref_table.columns[ref_col_name]  # type: ignore[assignment]

    Base.metadata.create_all(engine)

    yield engine

    Base.metadata.drop_all(engine)
    engine.dispose()

    for table in tables:
        table.schema = original_schemas[table.fullname]


@pytest.fixture
def db_session(
    _api_engine,  # noqa: ANN001
) -> Iterator[Session]:
    """Per-test session that rolls back after each test."""
    connection = _api_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(
        sess: Session,  # noqa: ARG001
        trans,  # noqa: ANN001
    ) -> None:
        nonlocal nested
        if trans.nested and not trans._parent.nested:  # type: ignore[attr-defined]
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def override_get_session() -> Generator[Session]:
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app, raise_server_exceptions=True) as tc:
        yield tc


@pytest.fixture
def test_user(db_session: Session) -> User:
    user = User(
        email="test@example.com",
        firstname="Test",
        lastname="User",
    )
    db_session.add(user)
    db_session.flush()

    credential = Credential(
        user_id=user.uid,
        provider="password",
        credential_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder$placeholder",
    )
    db_session.add(credential)
    db_session.flush()
    return user


def make_auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    """Create Authorization headers with a valid JWT for the given user."""
    token = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers(test_user: User) -> dict[str, str]:
    return make_auth_headers(test_user.uid)
