"""The colours of user avatars and remote cursors on a shared note.

A user's colour is the same for everyone who sees them. It is the user's
preferred colour (`User.avatar_color`, a name from `AVATAR_COLORS`) when they
have one, otherwise a palette colour picked from their id.

The palette is the hues the presence components used to derive from the user
id, at the same saturation and lightness (`hsl(h 60% 42%)`), so they stay
readable behind white text in both themes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

AVATAR_COLORS: dict[str, str] = {
    "red": "#ab2b2b",
    "orange": "#ab602b",
    "green": "#2bab40",
    "teal": "#2babab",
    "blue": "#2b60ab",
    "indigo": "#362bab",
    "purple": "#812bab",
    "pink": "#ab2b76",
}
"""Colour name to CSS colour. Names are what `User.avatar_color` stores."""


def avatar_color(user_id: uuid.UUID, preferred: str | None) -> str:
    """The CSS colour of a user's avatar.

    Args:
        user_id: The user's id, which picks the colour when there is no
            preference.
        preferred: The user's `avatar_color`. A name no longer in the palette
            counts as no preference.
    """
    if preferred is not None and preferred in AVATAR_COLORS:
        return AVATAR_COLORS[preferred]
    palette = list(AVATAR_COLORS.values())
    return palette[user_id.int % len(palette)]
