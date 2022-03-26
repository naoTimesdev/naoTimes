from typing import Any


def parse_playlists(data: dict):
    tracks = data["tracks"]
    return tracks


class _MissingSentinel:
    def __str__(self):
        return "..."

    def __repr__(self) -> str:
        return "..."

    def __bool__(self):
        return False


MISSING: Any = _MissingSentinel()
