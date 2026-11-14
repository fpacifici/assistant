# Categories

A user's single-level folders, shared by [Blogs](blogs.md) and the reading
list. Code: `src/assistant/categories/`, routes in
`src/assistant/api/routes/categories.py`.

Nothing is shared: a category has an `owner_id`, and a service function loads
it filtered by owner, so another user's category is a 404. There are no
entitlements.

## Storage

| Column | Content |
| --- | --- |
| `name` | Unique per user (`uq_category_owner_name`). |
| `description` | Free text, nullable. What the reading list's model reads to file a link. Blank means none. |

`blog_sources.category_id` points at it with `ON DELETE SET NULL`. Deleting a
category moves what was filed under it to Unfiled; the service also clears
the column explicitly, so the session and SQLite (which ignores foreign keys)
agree. Deleting a user deletes their categories.

The table was `blog_directories` until the reading list: migration
`d8a2f5c1e047` renamed it, its constraints and `blog_sources.directory_id`, and
added `description`. Existing rows kept their id and name.

## API

```
GET    /category                                -> CategoryResponse[] (by name, ignoring case)
POST   /category       {"name", "description"}  -> 201 CategoryResponse
PUT    /category/{id}  {"name", "description"}  -> CategoryResponse
DELETE /category/{id}                           -> 204 (items move to Unfiled)
```

- A name already in use is a 409.
- `PUT` replaces both fields: a missing or blank `description` clears it.
- A new description applies to what is filed from now on. Nothing is
  re-categorized.

## Frontend

`components/ManageCategoriesDialog.tsx` creates, renames, describes and
deletes categories, and marks those with no description. The Blogs tab opens
it from the sources page. The category list is cached under the
`['categories']` query key; a change also invalidates `['blogs']` and `['reading']`, since
sources and links show their category, and Reading counts per category.
