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

- Valid `Permissions` on notes are: `view`, `update`, `delete`, `share`.

- Valid `Permissions` on notebooks are: `view`, `delete`, `create_notes`, `list_notes`,
  `own_notes`, `delete_notes`, `view_notes`, `share`. If a user has create, udpate, delete, view
  notes on a notebook, the user has those permissions and all the contained notes.
  Share works like for notes permissions.

- A user can have a specific permission on a subject via `Entitlement`.

- Permissions can be grouped into roles. Roles group permissions that can be
  associated to a subject.

- An entitlement can grant specific permissions on a subject to a principal (user)
  or a role (group of permissions) to a principal on a subject.

- User can always create notes and notebooks. There is no concept of workspace

# Roles definition

These are the roles:

*notebook_owner*: has all permissions on a Notebook.

*notebook_viewer*: has these permissions on notebooks: `view`, `list_notes`,
  `view_notes`, `share`

*notebook_editor*: has these permissions on notebooks: all the `notebook_viewer`
  permissions plus `create_notes`, `own_notes`, `delete_notes`

*note_owner*: has all permissions on a note

*note_viewer*: has these permissions on a note: `view`, `share`

*note_editor*: has all the `note_viewer` permissions on a note plus `update`

# Permissions rules: Notebooks

- Note `viewer` permissions: The user can read a note.

- Note `update` permissions: The user can make changes to a note whether they own
  it or not but cannot delte it.

- Note `delete` permission: The user can delete the note

- Note `share` permission: The user can grant to another user permissions they have
  on the note itself.

- Notebook `view` permission: The user can see the notebook in the list in the interface
  and API. This does not grant any permission on the notes contained. The user cannot
  even list the notes in a notebook with this permission alone.

- Notebook `delete` permission: The user can delete the notebook and all the notes
  contained.

- Notebook `create_note` permission: The user can create a note in the notebook.
  The user is owner of the created note as it is granted the `note_owner` role
  on the note itself.

- Notebook `list_notes`: Allows the user to list the notes contained in a notebook.
  This does not guarantee the ability to read the content of the notes. Just the
  titles.

- Notebook `view_notes`: Allows the user to view the content of all the ntoes in
  the notebook. This is equivalent to having `note_viewer` role on all notes in
  the notebook.

- Notebook `own_notes`: Allows the user to make changes to all the notes in the
  notebook. This is equivalent to having `note_owner` on all notes in the notebook.

- Notebook `share`: Allows the user to grant all the permissions they have to
  another user.

# Permission evaluation

- Permissions are evaluated in depth in the `services` used to maintain the data model.
  We do not make these checks in the API only. This means propagating the user
  down to the service.

- When accessing a note, both the permissions on the note and on the notebook have
  to be evaluated.

# User experience

- There is no workspace. When the user uses the UI, the list of notebooks includes
  all those the user has `viewer` on.

- When the user opens a notebook, they can list all the notes if the have `list_notes`
  and those notes the user has `viewer` on.

- Then the user opens a note they have `viewer` on, the user sees every update
  disabled unless they have `update`.
