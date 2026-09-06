## Implement role based access control

We want to support access to notes by multiple users. The current system
has a concept of User as owner of Notes and Notebooks. Today is not possible
to share notes between users.

We want to allow users to grant different levels of permissions (read, create
update, delete, share) on both notebooks and notes.

# Role based access control

The system is based on roles, permissions and entitlements. The data model
has been designed [here](../architecture/notesservice.md).

- Notes and notebooks have owners. The owner has full control on the `subject`.

- Actions that can be performed are listed in the `Permissions` table.

- Valid `Permissions` on notes are: `view_note`, `update`, `delete_note`, `share_note`.

- Valid `Permissions` on notebooks are: `view_notebook`, `update_notebook`,
  `delete_notebook`, `create_notes`, `list_notes`, `own_notes`, `delete_notes`,
  `view_notes`, `share_notebook`. See the permission rules below for how
  `own_notes`/`view_notes`/`delete_notes` project onto the notes a notebook
  contains.

- `view`, `delete`, and `share` are deliberately **not** reused as permission names
  across both subject types: `view_note`/`view_notebook`, `delete_note`/`delete_notebook`,
  and `share_note`/`share_notebook` are distinct, unambiguous permissions.

- A user can have a specific permission on a subject via `Entitlement`.

- Permissions can be grouped into roles. Roles group permissions that can be
  associated to a subject.

- An entitlement grants a principal — always an individual user, never a
  group — either a specific permission or a role (a bundle of permissions)
  on a subject. A role only groups permissions; it never groups users.

- Entitlements are additive only: there is no explicit deny. Revoking access
  means deleting the entitlement.

- Users can always create a new notebook, becoming its owner. There is no
  concept of workspace. Creating a note inside an *existing* notebook still
  requires `create_notes` permission on that notebook (owners have this
  automatically).

# Roles definition

These are the six fixed roles. Custom roles are not supported in this
version.

*notebook_owner*: has all permissions on a Notebook.

*notebook_viewer*: has these permissions on notebooks: `view_notebook`, `list_notes`,
  `view_notes`, `share_notebook`

*notebook_editor*: has these permissions on notebooks: all the `notebook_viewer`
  permissions plus `create_notes`, `own_notes`, `delete_notes`, `update_notebook`

*note_owner*: has all permissions on a note

*note_viewer*: has these permissions on a note: `view_note`, `share_note`

*note_editor*: has all the `note_viewer` permissions on a note plus `update`

# Permissions rules: Notebooks

- Note `view_note` permission: The user can read a note.

- Note `update` permissions: The user can make changes to a note whether they own
  it or not but cannot delete it.

- Note `delete_note` permission: The user can delete the note

- Note `share_note` permission: The user can grant to, or revoke from, another
  user any permission they themselves currently hold on the note — never
  more than that.

- Notebook `view_notebook` permission: The user can see the notebook in the list in the interface
  and API. This does not grant any permission on the notes contained. The user cannot
  even list the notes in a notebook with this permission alone.

- Notebook `delete_notebook` permission: The user can delete the notebook and all the notes
  contained.

- Notebook `update_notebook` permission: The user can rename the notebook.

- Notebook `create_notes` permission: The user can create a note in the notebook.
  The user is owner of the created note as it is granted the `note_owner` role
  on the note itself.

- Notebook `list_notes`: Allows the user to list the notes contained in a notebook.
  This does not guarantee the ability to read the content of the notes. Just the
  titles.

- Notebook `view_notes`: Allows the user to view the content of all the notes in
  the notebook. This is equivalent to having `note_viewer` role on all notes in
  the notebook.

- Notebook `own_notes`: Allows the user to make changes to all the notes in the
  notebook. This is equivalent to having `note_owner` on all notes in the notebook.

- Notebook `delete_notes`: Allows the user to delete any note in the notebook,
  even without `own_notes` or a direct `delete_note` grant on that note.

- Notebook `share_notebook`: Allows the user to grant to, or revoke from, another user
  any permission they themselves currently hold on the notebook — never more
  than that.

# Permission evaluation

- Permissions are evaluated in depth in the `services` used to maintain the data model.
  We do not make these checks in the API only. This means propagating the user
  down to the service.

- When accessing a note, both the permissions on the note and on the notebook have
  to be evaluated.

- A permission granted directly on a note is independent of the notebook: sharing
  a single note does not require also granting any notebook-level permission.

# User experience

- There is no workspace. When the user uses the UI, the list of notebooks includes
  all those the user has `view_notebook` on, plus any notebook containing at least one
  note the user has any permission on — in that case only the accessible
  note(s) are shown, not the rest of the notebook's contents.

- When the user opens a notebook, they can list all the notes if they have
  `list_notes`, `view_notes`, or `own_notes` on the notebook, plus any notes
  they have permission on individually.

- When the user opens a note they have `view_note` on, they see every edit control
  disabled unless they have `update`.
