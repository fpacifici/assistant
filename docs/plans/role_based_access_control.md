# Implementation plan: Role-based access control

Implements `docs/specs/0003_role_based_access_control.md`, using the data model
sketched in `docs/architecture/notesservice.md`, per the decisions reached in
the `/grill-me` session on this spec.

## Context

Today access control is a single hardcoded rule: `require_notebook_owner`
(`src/assistant/api/dependencies.py:66-75`) checks `Notebook.owner_id ==
user_id` and is called at the top of **every** notebook, note, and node route
handler (`src/assistant/api/routes/{notebooks,notes,nodes}.py`). There is no
way to share a notebook or note with another user, and the check lives only
in the API layer — the service layer (`src/assistant/notes/service.py`) takes
no caller identity at all for reads/updates/deletes.

This plan replaces that single check with the full RBAC system from the spec:
an `Entitlement` table (permissions/roles are Python enums, not their own
tables — see Storage decision below), permission evaluation that lives in
the service layer (not just the API), sharing endpoints nested under the
existing routers, and a minimal share UI. It does **not** change the existing
`owner_id` columns on `Note`/`Notebook` (kept, per the grilling session, as a
denormalized field), and does not touch the HTML-import pipeline's
`find_or_create_notebook` semantics (see Out of Scope).

## Decisions recap (from grilling)

- `Role` is a fixed permission bundle applied **per-subject** via an
  `Entitlement` — never a group of users. `Entitlement.principal` is always a
  `User`.
- `Entitlement` has two mutually-exclusive-pair columns (subject: `note_id`/
  `notebook_id`; grant: `permission_name`/`role_name`, plain strings — see
  Storage decision), enforced with `CheckConstraint`s — mirroring the
  existing `Node.node_type` discriminator pattern (`schema.py:326-337`).
- Permissions and roles are **Python enums with no backing DB table** —
  `PermissionName`/`RoleName` plus a hardcoded `ROLE_PERMISSIONS` mapping,
  the same pattern this codebase already uses for `NodeType`/`FileState`/
  `MarkdownBlockType` (plain enum-backed `String` columns, validated in the
  service layer, no lookup table). Justified because roles are fixed for
  this version (no custom-role CRUD) and nothing needs to query the catalog
  as data — see Storage decision below.
- Ownership is modeled uniformly: creating a Note/Notebook auto-creates an
  `Entitlement` granting `note_owner`/`notebook_owner` to the creator. The
  `owner_id` column stays as a denormalized/display field. This entitlement
  is created in the same function call, on the same session, as the
  subject itself — never as a separate step that could commit independently
  (see the transactional-creation subsection under the authorization
  matrix).
- Grants are additive-only; revocation deletes the row.
- A direct note-level entitlement works independently of notebook-level
  access, but having *any* permission on a note makes the parent notebook
  visible (with just that note listed).
- `share_note`/`share_notebook` bounds both granting and revoking to "at or
  below your own current permission level" on that subject; violating this
  is a 403.
- Every notes-service function that touches an existing Note/Notebook takes
  an explicit caller identity and enforces permissions itself.
- 404 when the caller lacks even `view_note`/`view_notebook`; 403 when they
  have that but lack the specific permission for the action.
- Share endpoints nest under the existing routers; sharing targets a user by
  email (hard failure if unregistered).
- Fixed six roles only, no custom-role CRUD.

## Permission catalog (resolves spec ambiguities left implicit)

The spec names `view`, `delete`, and `share` as concepts that apply to both
Note and Notebook. Rather than reusing one ambiguous name across two subject
types and relying on `Entitlement`'s subject column to disambiguate it, each
is split into an explicit, subject-qualified pair — `view_note`/
`view_notebook`, `delete_note`/`delete_notebook`, `share_note`/
`share_notebook` — so a permission name alone always tells you which subject
type it applies to, with no need to cross-reference the entitlement row. The
catalog also adds `update_notebook` (see the gap noted below), for 13 names
total, not 9:

| Permission | Valid on |
|---|---|
| `view_note` | Note only |
| `update` | Note only |
| `delete_note` | Note only |
| `share_note` | Note only |
| `view_notebook` | Notebook only |
| `update_notebook` | Notebook only |
| `delete_notebook` | Notebook only |
| `create_notes` | Notebook only |
| `list_notes` | Notebook only |
| `own_notes` | Notebook only |
| `delete_notes` | Notebook only |
| `view_notes` | Notebook only |
| `share_notebook` | Notebook only |

Role → permission bundles (directly transcribed from the spec):

| Role | Subject type | Permissions |
|---|---|---|
| `notebook_owner` | notebook | all 9 notebook permissions |
| `notebook_viewer` | notebook | `view_notebook`, `list_notes`, `view_notes`, `share_notebook` |
| `notebook_editor` | notebook | `notebook_viewer`'s + `create_notes`, `own_notes`, `delete_notes`, `update_notebook` |
| `note_owner` | note | all 4 note permissions |
| `note_viewer` | note | `view_note`, `share_note` |
| `note_editor` | note | `note_viewer`'s + `update` |

**Gap the spec left open, now resolved:** the original spec had no notebook
`update` permission — renaming a notebook wasn't a named permission anywhere.
`update_notebook` closes that gap; it's held by `notebook_owner` and
`notebook_editor` but not `notebook_viewer`, matching how `update` is held
by `note_owner`/`note_editor` but not `note_viewer` on the note side.

### Storage decision: enums only, no `Permission`/`Role` tables

An earlier version of this plan modeled `Permission` and `Role` as their own
tables (with a `RolePermission` join table), FK'd from `Entitlement`, seeded
at startup. That's dropped in favor of plain `permission_name`/`role_name`
string columns on `Entitlement`, validated against the `PermissionName`/
`RoleName` enums in the service layer — no separate tables, no seeding step.

Rationale: this codebase already has three precedents for exactly this
shape of problem — `NodeType`, `FileState`, and `MarkdownBlockType` are all
small, fixed, code-defined enumerations stored as a plain `String` column on
the row that uses them, validated only in the service layer (e.g.
`_validate_block_type` in `notes/service.py` raising `InvalidBlockTypeError`
on a bad value), with no lookup table anywhere. There is no existing
precedent in this codebase for a DB-table-backed enum catalog. Since roles
are fixed for this version (no custom-role CRUD — Q5) and nothing needs to
query permissions/roles as data (the share dialog's role dropdown just
hardcodes the 3 options per subject type, the same way editor toolbars
hardcode `block_type` options), a table+FK design would add a second source
of truth (the seed function) that has to be hand-kept in sync with the
enums forever, for no behavior anything actually needs. The tradeoff this
accepts: no DB-level foreign-key rejection of a malformed `permission_name`/
`role_name` — enforcement is application-level only, exactly like every
other enum-backed column in this codebase.

## New/changed files

- `src/assistant/models/schema.py` — edit. `SubjectType`, `PermissionName`,
  `RoleName` enums; `Entitlement` model (plain `permission_name`/`role_name`
  string columns — no separate `Permission`/`Role` tables, see Storage
  decision above).
- `src/assistant/notes/permissions.py` — new. `ROLE_PERMISSIONS` mapping,
  effective-permission computation, and `require_*_access` guards.
- `src/assistant/notes/entitlements.py` — new. `grant_entitlement`,
  `revoke_entitlement`, `list_entitlements`, escalation-bound enforcement.
- `src/assistant/notes/exceptions.py` — edit. `PermissionDeniedError`.
- `src/assistant/notes/service.py` — edit. Every function touching an
  existing Note/Notebook gains a `caller_id` and calls into `permissions.py`;
  `create_notebook`/`create_note` gain the auto-owner-entitlement side
  effect; `list_notebooks`/`list_notes` become permission-scoped.
- `src/assistant/notes/user_service.py` — edit. Add `get_user_by_email`.
- `src/assistant/api/exceptions.py` — edit. Register `PermissionDeniedError`
  → 403.
- `src/assistant/api/dependencies.py` — edit. Remove `require_notebook_owner`
  (superseded by `permissions.py`, called from inside the service layer).
- `src/assistant/api/schemas/notebooks.py`, `.../notes.py` — edit. Add
  `permissions: list[str]` to the response models; add `EntitlementCreate`/
  `EntitlementResponse`.
- `src/assistant/api/routes/notebooks.py`, `.../notes.py`, `.../nodes.py` —
  edit. Thread `caller_id` through to service calls; add
  `POST/GET /notebook/{id}/share`, `DELETE /notebook/{id}/share/{entitlement_id}`
  and the note-level mirror.
- `docs/architecture/notesservice.md`, `docs/architecture/api.md` — edit.
  Document the implemented RBAC system (both currently describe it only as a
  target data model / describe auth as unimplemented, which is now stale).
- Frontend: `frontend/src/types/index.ts`, `frontend/src/api/notebooks.ts`,
  `.../notes.ts`, new `frontend/src/components/ShareDialog.tsx`, edits to
  `NotebookList.tsx`, `NoteList.tsx`, `NoteEditor.tsx`.
- Tests: `tests/notes/test_permissions.py`, `tests/notes/test_entitlements.py`
  (new), extensive additions to `tests/notes/test_service.py`,
  `tests/api/test_notebooks.py`, `tests/api/test_notes.py`, `tests/api/test_nodes.py`
  (existing files — confirm exact names during implementation), new
  `tests/api/test_sharing.py`; frontend `ShareDialog.test.tsx`.

## Schema changes (`src/assistant/models/schema.py`)

```python
class SubjectType(str, Enum):
    NOTE = "note"
    NOTEBOOK = "notebook"


class PermissionName(str, Enum):
    VIEW_NOTE = "view_note"
    UPDATE = "update"
    DELETE_NOTE = "delete_note"
    SHARE_NOTE = "share_note"
    VIEW_NOTEBOOK = "view_notebook"
    UPDATE_NOTEBOOK = "update_notebook"
    DELETE_NOTEBOOK = "delete_notebook"
    CREATE_NOTES = "create_notes"
    LIST_NOTES = "list_notes"
    OWN_NOTES = "own_notes"
    DELETE_NOTES = "delete_notes"
    VIEW_NOTES = "view_notes"
    SHARE_NOTEBOOK = "share_notebook"


class RoleName(str, Enum):
    NOTEBOOK_OWNER = "notebook_owner"
    NOTEBOOK_VIEWER = "notebook_viewer"
    NOTEBOOK_EDITOR = "notebook_editor"
    NOTE_OWNER = "note_owner"
    NOTE_VIEWER = "note_viewer"
    NOTE_EDITOR = "note_editor"


class Entitlement(Base):
    __tablename__ = "entitlements"
    __table_args__ = (
        CheckConstraint(
            "(note_id IS NOT NULL AND notebook_id IS NULL)"
            " OR (note_id IS NULL AND notebook_id IS NOT NULL)",
            name="ck_entitlement_one_subject",
        ),
        CheckConstraint(
            "(permission_name IS NOT NULL AND role_name IS NULL)"
            " OR (permission_name IS NULL AND role_name IS NOT NULL)",
            name="ck_entitlement_one_grant",
        ),
        UniqueConstraint(
            "principal_id", "note_id", "notebook_id", "permission_name", "role_name",
            name="uq_entitlement_no_duplicate_grant",
        ),
        {"schema": "assistant"},
    )

    id: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4)
    principal_id: Mapped[uuid_module.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assistant.users.uid"), nullable=False)
    note_id: Mapped[uuid_module.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("assistant.notes.id"), nullable=True)
    notebook_id: Mapped[uuid_module.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("assistant.notebooks.id"), nullable=True)
    permission_name: Mapped[str | None] = mapped_column(String(30), nullable=True)
    role_name: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    principal: Mapped[User] = relationship("User")
    note: Mapped[Note | None] = relationship("Note", back_populates="entitlements")
    notebook: Mapped[Notebook | None] = relationship("Notebook", back_populates="entitlements")
```

`permission_name`/`role_name` are unconstrained at the DB level (no CHECK
enumerating valid values), exactly like `Node.node_type`/`Node.block_type` —
validity is enforced by typing at the boundary: `grant_entitlement`'s
`role_name` parameter is a `RoleName` (never a raw `str`), and the one API
entrypoint that reaches it (`EntitlementCreate.role: RoleName`) is a Pydantic
enum field, so FastAPI itself 422s a bad value before it ever reaches the
service layer — the same trust boundary this repo already uses for
`block_type` (validated in `_validate_block_type`, not the DB).

`Note` and `Notebook` gain `entitlements: Mapped[list[Entitlement]] =
relationship(..., cascade="all, delete-orphan")` so deleting a note/notebook
cascades its entitlements at the ORM level, same pattern as `Note.nodes`.
`User` gains an equivalent `entitlements` relationship for the same reason
(deleting a user should not leave orphaned grants).

No seeding step, no migration helper, and no `database.py` changes at all —
`Base.metadata.create_all(engine)` is sufficient since there's no catalog
data to insert.

## `src/assistant/notes/exceptions.py`

```python
class PermissionDeniedError(NotesServiceError):
    """Raised when a caller has view access but lacks a specific permission."""

    def __init__(self, permission: PermissionName, subject_type: SubjectType, subject_id: uuid.UUID) -> None:
        self.permission = permission
        self.subject_type = subject_type
        self.subject_id = subject_id
        super().__init__(f"Missing '{permission.value}' permission on {subject_type.value} {subject_id}")
```

`src/assistant/api/exceptions.py` gains a handler registered **before** the
generic `NotesServiceError` catch-all (order matters for Starlette's MRO
dispatch — mirrors how `InvalidBlockTypeError`/`NodeVersionConflictError` are
special-cased ahead of the 404 default):

```python
@app.exception_handler(PermissionDeniedError)
async def permission_denied_handler(request, exc: PermissionDeniedError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})
```

Every other `NotesServiceError` subclass (including the not-found errors)
keeps falling through to the existing 404 default — so `NotebookNotFoundError`
raised for "you can't even see this" continues to produce 404 with zero
changes to that handler.

## `src/assistant/notes/permissions.py` (new)

Pure read-side module: computes effective permissions and enforces them. No
mutation. Owns the single source of truth for role→permission expansion —
the table in the Permission catalog section above is just this dict in
prose:

```python
ROLE_PERMISSIONS: dict[RoleName, frozenset[PermissionName]] = {
    RoleName.NOTEBOOK_OWNER: frozenset({
        PermissionName.VIEW_NOTEBOOK, PermissionName.UPDATE_NOTEBOOK,
        PermissionName.DELETE_NOTEBOOK, PermissionName.CREATE_NOTES,
        PermissionName.LIST_NOTES, PermissionName.OWN_NOTES,
        PermissionName.DELETE_NOTES, PermissionName.VIEW_NOTES,
        PermissionName.SHARE_NOTEBOOK,
    }),
    RoleName.NOTEBOOK_VIEWER: frozenset({
        PermissionName.VIEW_NOTEBOOK, PermissionName.LIST_NOTES,
        PermissionName.VIEW_NOTES, PermissionName.SHARE_NOTEBOOK,
    }),
    RoleName.NOTEBOOK_EDITOR: frozenset({
        PermissionName.VIEW_NOTEBOOK, PermissionName.LIST_NOTES,
        PermissionName.VIEW_NOTES, PermissionName.SHARE_NOTEBOOK,
        PermissionName.CREATE_NOTES, PermissionName.OWN_NOTES,
        PermissionName.DELETE_NOTES, PermissionName.UPDATE_NOTEBOOK,
    }),
    RoleName.NOTE_OWNER: frozenset({
        PermissionName.VIEW_NOTE, PermissionName.UPDATE,
        PermissionName.DELETE_NOTE, PermissionName.SHARE_NOTE,
    }),
    RoleName.NOTE_VIEWER: frozenset({PermissionName.VIEW_NOTE, PermissionName.SHARE_NOTE}),
    RoleName.NOTE_EDITOR: frozenset({
        PermissionName.VIEW_NOTE, PermissionName.SHARE_NOTE, PermissionName.UPDATE,
    }),
}
```

```python
def notebook_permissions(session: Session, principal_id: uuid.UUID, notebook_id: uuid.UUID) -> set[PermissionName]:
    """Direct + role-expanded permission names the principal holds on this notebook."""

def note_permissions(session: Session, principal_id: uuid.UUID, note: Note) -> set[PermissionName]:
    """Effective {VIEW_NOTE, UPDATE, DELETE_NOTE, SHARE_NOTE} on a note:
    direct grants on the note itself, plus notebook-derived implications
    (OWN_NOTES => full note_owner set; VIEW_NOTES => {VIEW_NOTE, SHARE_NOTE},
    matching note_viewer)."""

def can_view_notebook(session: Session, principal_id: uuid.UUID, notebook_id: uuid.UUID) -> bool:
    """True if the principal has VIEW_NOTEBOOK, OR holds any entitlement on
    at least one note inside it (an EXISTS subquery against Entitlement
    joined to Note.notebook_id == notebook_id — no per-note loop)."""

def require_notebook_access(session: Session, notebook_id: uuid.UUID, principal_id: uuid.UUID, permission: PermissionName) -> Notebook:
    """404 (NotebookNotFoundError) if not can_view_notebook; 403
    (PermissionDeniedError) if visible but `permission` not in
    notebook_permissions; else returns the Notebook."""

def require_note_access(session: Session, note_id: uuid.UUID, principal_id: uuid.UUID, permission: PermissionName) -> Note:
    """Same shape for notes: 404 if VIEW_NOTE not in note_permissions, 403
    if visible-but-not-`permission`, else returns the Note."""

def require_note_delete_access(session: Session, note_id: uuid.UUID, principal_id: uuid.UUID) -> Note:
    """Special case: deleting a note is allowed via DELETE_NOTE OR notebook
    DELETE_NOTES (a narrower per-notebook grant the spec defines separately
    from OWN_NOTES) OR notebook OWN_NOTES."""
```

`note_permissions` is where the spec's cross-subject rule
("both note and notebook permissions have to be evaluated") lives:

```python
def note_permissions(session, principal_id, note) -> set[PermissionName]:
    direct = _granted_permission_names(session, principal_id, note_id=note.id)
    notebook_perms = notebook_permissions(session, principal_id, note.notebook_id)
    if PermissionName.OWN_NOTES in notebook_perms:
        direct |= {
            PermissionName.VIEW_NOTE, PermissionName.UPDATE,
            PermissionName.DELETE_NOTE, PermissionName.SHARE_NOTE,
        }
    if PermissionName.VIEW_NOTES in notebook_perms:
        direct |= {PermissionName.VIEW_NOTE, PermissionName.SHARE_NOTE}
    return direct
```

`_granted_permission_names` is the shared primitive both `notebook_permissions`
and the direct half of `note_permissions` use: fetch the principal's
`Entitlement` rows on the subject, then union each row's contribution —
either its `permission_name` directly, or `ROLE_PERMISSIONS[role_name]`
expanded in Python (no join needed, since the mapping isn't in the DB):

```python
def _granted_permission_names(session, principal_id, *, note_id=None, notebook_id=None) -> set[PermissionName]:
    subject_filter = (Entitlement.note_id == note_id) if note_id is not None else (Entitlement.notebook_id == notebook_id)
    rows = session.scalars(
        select(Entitlement).where(Entitlement.principal_id == principal_id, subject_filter),
    )
    names: set[PermissionName] = set()
    for entitlement in rows:
        if entitlement.permission_name is not None:
            names.add(PermissionName(entitlement.permission_name))
        else:
            names |= ROLE_PERMISSIONS[RoleName(entitlement.role_name)]
    return names
```

Both `PermissionName(entitlement.permission_name)` and
`RoleName(entitlement.role_name)` convert the raw DB string back into its
enum the moment it's read — nothing downstream of this function ever
touches a bare permission/role string again.

## `src/assistant/notes/entitlements.py` (new)

Write-side: grant/revoke, both bounded by the escalation rule (Q1, round 3).

```python
def grant_entitlement(
    session: Session,
    granter_id: uuid.UUID,
    *,
    note_id: uuid.UUID | None = None,
    notebook_id: uuid.UUID | None = None,
    grantee_email: str,
    role_name: RoleName,
) -> Entitlement:
    """Grant `role_name` on the given subject to the user with `grantee_email`.

    Raises UserNotFoundError if no user has that email. Raises
    PermissionDeniedError if `granter_id` lacks `share_note`/`share_notebook`
    on the subject, or if the role being granted is not a subset of the
    granter's own effective permissions on that subject (escalation bound).
    """

def revoke_entitlement(
    session: Session,
    revoker_id: uuid.UUID,
    entitlement_id: uuid.UUID,
    *,
    note_id: uuid.UUID | None = None,
    notebook_id: uuid.UUID | None = None,
) -> None:
    """Same bound as grant: revoker must have `share_note`/`share_notebook`
    on the subject and the entitlement being removed must not exceed the
    revoker's own permission level on that subject."""

def list_entitlements(session: Session, viewer_id: uuid.UUID, *, note_id=None, notebook_id=None) -> list[Entitlement]:
    """Requires `share_note`/`share_notebook` on the subject (same gate as
    managing entitlements)."""
```

The escalation check expands `role_name`'s bundle via `ROLE_PERMISSIONS` and
verifies it's a subset of `note_permissions(...)`/`notebook_permissions(...)`
for `granter_id` on that subject — reusing `permissions.py`'s mapping, never
duplicating it.

## `src/assistant/notes/user_service.py`

Add, next to `get_user`:

```python
def get_user_by_email(session: Session, email: str) -> User:
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        raise UserNotFoundError(email)
    return user
```

## `src/assistant/notes/service.py` — authorization matrix

Every function that reads/mutates an *existing* Note/Notebook gains a
`caller_id: uuid.UUID` parameter and calls the matching `require_*` guard
from `permissions.py` before doing anything else. Functions that only ever
act on behalf of their own creator (`create_notebook`, `create_note`) reuse
the existing `owner_id` param as the caller — no separate parameter needed —
but `create_note` gains a permission check, and both gain the
auto-entitlement side effect.

| Service function | New caller param | Guard | Notes |
|---|---|---|---|
| `create_notebook` | (`owner_id` is the caller) | none — always allowed | Creates the owner `Entitlement` in the *same function, same session, same transaction* — see below |
| `find_or_create_notebook` | unchanged | **unchanged** | See Out of Scope. When it does create (no existing match by name), it calls `create_notebook`, so it inherits the same atomic owner-entitlement guarantee for free |
| `get_notebook`, `update_notebook`, `delete_notebook`, `list_notebooks` | `caller_id` | `require_notebook_access(..., PermissionName.VIEW_NOTEBOOK)` for get; `PermissionName.UPDATE_NOTEBOOK` for rename; `PermissionName.DELETE_NOTEBOOK` for delete; `list_notebooks` replaced by a permission-scoped query (below) | |
| `create_note` | (`owner_id` is the caller) | `require_notebook_access(notebook_id, owner_id, PermissionName.CREATE_NOTES)` | Creates the owner `Entitlement` in the *same function, same session, same transaction* — see below |
| `get_note`, `update_note`, `list_notes` | `caller_id` | `require_note_access(..., PermissionName.VIEW_NOTE)` for get; `PermissionName.UPDATE` for update; `list_notes` replaced by permission-scoped query | |
| `delete_note` | `caller_id` | `require_note_delete_access(...)` | |
| `add_text_node`, `add_attachment_node`, `insert_text_node`, `add_markdown_node`, `insert_markdown_node`, `update_markdown_node`, `update_text_node`, `split_text_node`, `merge_text_nodes`, `replace_markdown_nodes`, `delete_node` | `caller_id` | `require_note_access(note_id, caller_id, PermissionName.UPDATE)` (nodes are note content — mutating them is a note `update`) | For functions taking `node_id` rather than `note_id` directly (`update_markdown_node`, `split_text_node`, etc.), look up the node's `note_id` first |
| `get_ordered_nodes` | `caller_id` | `require_note_access(note_id, caller_id, PermissionName.VIEW_NOTE)` | |

### Owner entitlement creation is transactional with the subject's creation

Both `create_notebook` and `create_note` must never leave a Note/Notebook row
committed without its owner `Entitlement` (or vice versa). This holds for
free from a rule already true of every function in `notes/service.py`: **no
service function ever calls `session.commit()`** — only the API layer's
`get_session` dependency does (`dependencies.py:18-30`), on successful
completion of the whole request, and the test fixtures' `db_session` commit
nothing at all (they roll back a savepoint after every test). So as long as
the subject insert and its owner-entitlement insert happen on the *same*
`Session` inside the *same* function call, with no `commit()` between them,
they are necessarily part of one transaction: any exception raised by
either insert propagates uncaught out of the function (nothing here catches
it), which unwinds to `get_session`'s `except Exception: session.rollback();
raise`, discarding both inserts together. This isn't a new mechanism to
build — it's the existing commit-only-in-the-API-layer convention
(`AGENTS.md`'s API Layer section), applied deliberately here.

Concretely:

```python
def create_notebook(session: Session, name: str, owner_id: uuid.UUID) -> Notebook:
    notebook = Notebook(name=name, owner_id=owner_id)
    session.add(notebook)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise DuplicateNotebookNameError(name) from None
    session.add(Entitlement(
        principal_id=owner_id,
        role_name=RoleName.NOTEBOOK_OWNER,
        notebook_id=notebook.id,
    ))
    session.flush()
    return notebook
```

The existing duplicate-name `try`/`except`/`rollback` stays scoped to only
the notebook's own `flush()` — the entitlement insert happens strictly
*after* that block has already succeeded, never inside it, so a future bug
in entitlement creation can never be misreported as
`DuplicateNotebookNameError`. The final `session.flush()` (covering the
entitlement insert) is unguarded on purpose: any failure there should
surface as-is and unwind the whole transaction, including the notebook
insert that already flushed successfully but was never committed.

```python
def create_note(
    session: Session,
    notebook_id: uuid.UUID,
    owner_id: uuid.UUID,
    title: str,
    *,
    external_id: str | None = None,
) -> Note:
    require_notebook_access(session, notebook_id, owner_id, PermissionName.CREATE_NOTES)
    note = Note(
        notebook_id=notebook_id,
        owner_id=owner_id,
        title=title,
        external_id=external_id,
        update_timestamp=datetime.now(UTC),
    )
    session.add(note)
    session.flush()
    session.add(Entitlement(
        principal_id=owner_id,
        role_name=RoleName.NOTE_OWNER,
        note_id=note.id,
    ))
    session.flush()
    return note
```

Same shape: the permission check happens first (raising before anything is
added to the session at all if it fails), then the note insert, then the
entitlement insert, with one final `flush()` — all on the `session` passed
in by the caller, all inside whatever transaction that caller's request or
test is already running.

`list_notebooks` and `list_notes` change shape (no more raw `owner_id`
filter):

```python
def list_notebooks(session: Session, caller_id: uuid.UUID, *, offset=0, limit=None) -> list[Notebook]:
    """Notebooks the caller can view: explicit VIEW_NOTEBOOK, UNION
    notebooks containing at least one note the caller holds any entitlement
    on (per the round-2 clarification: a single shared note surfaces its
    parent notebook)."""

def list_notes(session: Session, notebook_id: uuid.UUID, caller_id: uuid.UUID, *, offset=0, limit=None) -> list[Note]:
    """Requires the caller can at least see the notebook (require_notebook_access
    PermissionName.VIEW_NOTEBOOK). Returns: ALL notes, if the caller has
    LIST_NOTES/VIEW_NOTES/OWN_NOTES on the notebook; otherwise only the notes
    the caller holds a direct entitlement on."""
```

Both are single queries built with SQLAlchemy `or_`/`exists()`, not a
Python-side filter over `list(session.scalars(...))` — the notebook/note
tables are the only thing paginated, so pagination (`offset`/`limit`) must
apply after the visibility predicate, not before.

## API layer

`require_notebook_owner` is deleted from `dependencies.py` — every route
becomes a thin pass-through of `user_id` (renamed `caller_id` at the service
boundary) into the now-self-checking service functions. Example
(`notebooks.py`):

```python
@router.get("/{notebook_id}", response_model=NotebookResponse)
def get_notebook_endpoint(notebook_id: uuid.UUID, session: SessionDep, user_id: CurrentUserId) -> NotebookResponse:
    notebook = get_notebook(session, notebook_id, caller_id=user_id)
    return NotebookResponse.model_validate(notebook)
```

`NotebookResponse`/`NoteResponse` gain a `permissions: list[PermissionName]`
field — the caller's effective permission set on that exact object —
computed at serialization time in the route handler (`notebook_permissions`/
`note_permissions` from `permissions.py`), not stored. Pydantic serializes a
`str`-backed enum to its plain string value over the wire, same as every
other enum-typed field in this API, so the JSON body is unaffected — just
`["view_note", "share_note", ...]`. This is what the frontend uses to decide
what to render (see Frontend below); it removes the need for the frontend to
know anything about roles, `own_notes`/`view_notes` implication, or the
escalation rule — it only ever checks `note.permissions.includes('delete_note')`
against the plain string it received.

New endpoints, nested per Q4:

```
POST   /notebook/{notebook_id}/share      body: {email, role}   -> EntitlementResponse (201)
GET    /notebook/{notebook_id}/share                             -> list[EntitlementResponse]
DELETE /notebook/{notebook_id}/share/{entitlement_id}            -> 204

POST   /notebook/{notebook_id}/note/{note_id}/share   body: {email, role}  -> EntitlementResponse (201)
GET    /notebook/{notebook_id}/note/{note_id}/share                        -> list[EntitlementResponse]
DELETE /notebook/{notebook_id}/note/{note_id}/share/{entitlement_id}       -> 204
```

`EntitlementCreate.role` is validated against the fixed `RoleName` enum
scoped to the right `subject_type` (a `note` share endpoint rejects a
notebook role, and vice versa) — a 422, not a 403, since it's a malformed
request rather than an authorization failure.

```python
class EntitlementCreate(BaseModel):
    email: str
    role: RoleName

class EntitlementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    principal_id: uuid.UUID
    principal_email: str  # populated via a lookup in the route handler, not a plain model_validate
    role: RoleName  # RoleName(entitlement.role_name); every API-created entitlement is role-based
    created_at: datetime
```

## Frontend

`frontend/src/types/index.ts`:

```ts
export interface Notebook {
  id: string;
  name: string;
  owner_id: string;
  permissions: string[];
}

export interface Note {
  id: string;
  notebook_id: string;
  owner_id: string;
  title: string;
  creation_timestamp: string;
  update_timestamp: string;
  permissions: string[];
}

export interface Entitlement {
  id: string;
  principal_id: string;
  principal_email: string;
  role: string;
  created_at: string;
}
```

`api/notebooks.ts` / `api/notes.ts` gain matching `fetchXEntitlements`,
`shareX(subjectId, email, role)`, `revokeXEntitlement(subjectId, entitlementId)`
wrappers over `apiFetch`, mirroring the existing `fetchNotebooks`/
`createNotebook` shape exactly (same file, no new module needed).

New `components/ShareDialog.tsx` — one reusable dialog for both subject
types:

```tsx
interface ShareDialogProps {
  subjectType: 'notebook' | 'note';
  subjectId: string;
  roleOptions: string[];  // ['notebook_viewer', 'notebook_editor', 'notebook_owner'] or the note equivalents
  onClose: () => void;
}
```

Internally: `useQuery` for the entitlement list, an email `<input>` + role
`<select>` + "Share" button wired to a `useMutation` calling `shareX`, and a
plain list of current entitlements (`principal_email` + role) each with a
"Revoke" button wired to `revokeXEntitlement`. `ApiError` from a 403
(escalation bound) or 404 (unknown email) surfaces as inline text under the
form — no special handling needed beyond what `ApiError.message` already
carries (`detail` from the JSON body).

`NotebookList.tsx` / `NoteList.tsx`: add a "Share" button next to the
existing delete button, rendered only when
`nb.permissions.includes('share_notebook')` /
`note.permissions.includes('share_note')`; opens `ShareDialog`. Delete
button's existing unconditional render becomes
`{nb.permissions.includes('delete_notebook') && <button .../>}` (and
`'delete_note'` for notes).

`NoteEditor.tsx`: `editor.isEditable` set to
`note.permissions.includes('update')` (BlockNote supports a read-only mode);
Save button additionally disabled when `!note.permissions.includes('update')`;
a "Share" button added to the existing toolbar row, same gating as above.

No changes needed to `NotebookList`'s/`NoteList`'s list-fetching logic —
the backend now returns only visible items, so there is no client-side
filtering to add.

## Documentation updates

- `docs/architecture/notesservice.md`: the "RBAC system" bullet (line ~109)
  currently just gestures at the ERD; expand it into a short paragraph
  pointing at the now-implemented `notes/permissions.py`/`entitlements.py`,
  matching how other implemented subsystems (Concurrent Editing) are
  documented in that same file.
- `docs/architecture/api.md`: this doc is currently stale on two points
  unrelated to this change (says auth uses `X-User-Id` and "is not yet
  implemented" — it's actually JWT-based and implemented). While touching
  the Notebooks/Notes sections for the new `permissions` field and share
  endpoints, correct the Authentication section too (small, adjacent fix;
  flagged here so it isn't mistaken for scope creep — the RBAC error-code
  changes make touching this section unavoidable anyway).

## Test plan

Follow this repo's TDD convention (`AGENTS.md`): module-level test functions,
`# --- Section ---` separators, tests before implementation per seam.

**`tests/notes/test_permissions.py`** — new seam, pure `db_session` (SQLite)
fixture + hand-rolled `_make_user`/`_make_notebook`/`_make_note` helpers
(matching `tests/notes/test_service.py`'s existing `_make_user` pattern) +
manually inserted `Entitlement` rows (no service-layer grant helper needed
here — this seam tests the read side in isolation). Cases per function:
direct permission grant visible; role-grant expands to its bundled
permissions; `own_notes` on notebook implies full note permission set;
`view_notes` implies `{view_note, share_note}` only (not
`update`/`delete_note`); `list_notes` alone does *not* imply `view_notes`; a
note-only entitlement with zero notebook-level grants still makes
`can_view_notebook` true; `require_note_access` raises `NoteNotFoundError`
(not `PermissionDeniedError`) when the caller has no `view_note` at all;
raises `PermissionDeniedError` when the caller has `view_note` but not the
requested permission; two users' entitlements never leak into each other's
effective sets.

**`tests/notes/test_entitlements.py`** — new seam, same fixture style. Cases:
`grant_entitlement` succeeds for a granter with `share_note`/`share_notebook`
and a role ⊆ their own permissions; fails with `PermissionDeniedError` when the role exceeds the
granter's own permissions (e.g. a `note_editor` granting `note_owner`); fails
with `UserNotFoundError` for an unregistered email; `revoke_entitlement`
succeeds for a revoker whose own level covers the entitlement being removed,
fails otherwise; owner (auto-created at creation) can always grant/revoke
anything up to full ownership; granting the same (principal, subject, role)
twice does not duplicate (relies on `uq_entitlement_no_duplicate_grant` —
assert the DB-level `IntegrityError` path or make `grant_entitlement`
idempotent, decide during implementation and document the choice in the
docstring).

**`tests/notes/test_service.py`** — extend existing file. For every function
in the authorization matrix table: a caller with sufficient permission
succeeds; a caller with `view_note`/`view_notebook` only gets
`PermissionDeniedError` on a mutating call; a caller with no relationship to
the subject gets a not-found error (404-shaped exception);
`list_notebooks`/`list_notes` return exactly the expected visible set for a
mix of owned/shared/unrelated notebooks/notes, including the "single shared
note surfaces its parent notebook" case; `delete_note` succeeds via
`delete_notes` on the notebook even without a direct `delete_note` grant;
`create_note` fails without
`create_notes` on the notebook even if the caller is a notebook `view_notes`
holder; `create_notebook` and `create_note` each produce exactly one
matching owner `Entitlement` (right role, right subject) as an observable
side effect; and — the atomicity guarantee itself — if the owner-entitlement
insert is made to fail (e.g. monkeypatch `session.add` to raise on the
`Entitlement` instance specifically, or, more directly, roll back the
session after calling `create_notebook`/`create_note` inside a `pytest.raises`
block and then assert via a *fresh* session/query that neither the
Notebook/Note row nor the Entitlement row exists) the subject row is not
left behind orphaned without its owner entitlement.

**`tests/api/test_notebooks.py`, `test_notes.py`, `test_nodes.py`** (existing
— confirm names) — extend using the `client`/`auth_headers`/`test_user`
fixtures in `tests/api/conftest.py`, plus a second `other_user`/
`other_auth_headers` fixture pair (new, same shape as `test_user`) to
exercise cross-user access: an unrelated user's request to
`GET /notebook/{id}` returns 404; a viewer-shared user's `DELETE` on the same
notebook returns 403; response bodies include the expected `permissions`
array for each role combination.

**`tests/api/test_sharing.py`** — new. Full share/revoke flow through the
HTTP layer for both notebooks and notes: share by email succeeds and the
grantee immediately gets access on their next request; share to an unknown
email returns 404; share exceeding the granter's own level returns 403;
share with an invalid role for the subject type returns 422; revoke by the
sharer succeeds and immediately removes access; revoke attempted by someone
below the required level returns 403; `GET .../share` requires
`share_note`/`share_notebook` (both are present on every fixed viewer role,
so also test the one case where the grantee genuinely has neither, e.g.
after a hypothetical narrower custom grant — if the fixed six roles make
this untestable in practice, document that and skip rather than inventing a
role that doesn't exist).

**Frontend `ShareDialog.test.tsx`** — new, matching existing
`NotebookList.test.tsx` conventions (Vitest + Testing Library +
`renderWithProviders`). Cases: renders current entitlements; submitting the
form calls the share mutation with the entered email/role; a 404 response
renders an inline "user not found" message; a 403 response renders an
inline permission message; clicking Revoke calls the revoke mutation.
`NotebookList.test.tsx`/`NoteList.test.tsx` gain cases asserting the Share/
Delete buttons are absent when `permissions` lacks the corresponding entry.

## Build order

1. Schema (`schema.py`: `SubjectType`/`PermissionName`/`RoleName` enums +
   `Entitlement` model). Sanity-check with
   `pytest tests/models tests/notes tests/api` immediately — expect failures
   only from tests exercising old signatures, not from schema errors.
2. `notes/exceptions.py` (`PermissionDeniedError`) + `api/exceptions.py`
   handler registration.
3. TDD: `tests/notes/test_permissions.py` → `notes/permissions.py`.
   Independent of everything except step 1.
4. TDD: `tests/notes/test_entitlements.py` → `notes/entitlements.py` +
   `get_user_by_email`. Depends on 3.
5. TDD: extend `tests/notes/test_service.py` → refactor every function in
   `notes/service.py` per the authorization matrix. Depends on 3. This is
   the largest single step — do it function-by-function, running
   `pytest tests/notes/test_service.py` after each.
6. API layer: remove `require_notebook_owner`; thread `caller_id` through
   `routes/{notebooks,notes,nodes}.py`; add `permissions` field to response
   schemas; add the six share/list/revoke endpoints. TDD against
   `tests/api/test_notebooks.py`/`test_notes.py`/`test_nodes.py`/
   `test_sharing.py`. Depends on 4 and 5.
7. Frontend: types, API client functions, `ShareDialog.tsx`, wiring into
   `NotebookList`/`NoteList`/`NoteEditor`. Depends on 6 (needs the real API
   shape). TDD against the new/extended `*.test.tsx` files.
8. Documentation: `notesservice.md`, `api.md`.
9. `make check` (backend) + `make frontend-check` + `make frontend-test`
   across everything touched.

## Verification

- `make check` passes (mypy strict, ruff, full pytest suite).
- `make frontend-check && make frontend-test` pass.
- Manual smoke test: `make services-up`, `python -m assistant.cli.setup_database`,
  create two users, log in as each in two browser sessions (or one normal +
  one incognito), create a notebook as user A, share a single note from it
  with user B as `note_viewer`, confirm user B sees the parent notebook with
  only that one note, cannot edit it, and cannot delete it; then share the
  whole notebook with user B as `notebook_editor` and confirm user B can now
  see and create notes, and can rename the notebook, but still cannot delete it;
  revoke the share and confirm user B loses access on their next request.

## Out of scope

- Custom role creation/management (fixed six roles only, per Q5).
- Group/team principals — `Entitlement.principal` is always an individual
  `User` (per Q1).
- Invite-by-email for unregistered users — sharing with an unknown email is
  a hard failure, no pending-invite flow.
- Changing `find_or_create_notebook`'s existing cross-owner name-matching
  behavior (used only by the trusted HTML-import CLI pipeline,
  `docs/plans/adapters-html-notes-import.md`) — left exactly as-is. Note
  that once notebooks carry entitlements, running that CLI against an
  existing notebook owned by someone else will, as an intentional side
  effect of nothing but the new `Note.notebook`-visibility rules existing,
  not itself be blocked (the function performs no permission check today and
  this plan does not add one to it) — flagged here only so it isn't
  mistaken for silently-changed behavior later.
- A backfill/migration script for pre-RBAC data (per Q5, round 2 — no real
  data exists yet).
- Admin/superuser bypass role — not in the spec; every access path goes
  through the same entitlement evaluation.
- Audit logging of grants/revokes.

## Further notes

- The notebook-rename-permission gap (no named `update` permission for
  Notebook) is now closed by adding `update_notebook` to the catalog, held by
  `notebook_owner`/`notebook_editor` — see the Permission catalog section.
- `NotebookResponse`/`NoteResponse.permissions` being computed fresh per
  request (rather than cached/stored) means listing endpoints do one extra
  permission-set query per row; fine at today's scale, worth revisiting if
  notebook/note lists grow large enough for N+1 query cost to matter.
