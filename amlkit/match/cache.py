"""In-memory cache for name_tokens to avoid repeated SQLite reads.

A simple dict-based cache that maps tokens to entity IDs. Invalidated on
refresh to pick up newly-loaded entities. No external dependencies, no TTL
logic — the cache lives until explicitly cleared or the process restarts.
"""

from __future__ import annotations

import sqlite3
from typing import Iterable

# Global cache: token -> list[entity_id]
_token_cache: dict[str, list[int]] = {}


def get_entities_for_tokens(
    conn: sqlite3.Connection, tokens: Iterable[str]
) -> list[tuple[str, int]]:
    """Retrieve entity IDs for the given tokens, using cache when available.

    Returns a list of (token, entity_id) tuples. Uses the cache for tokens
    already seen; queries SQLite for cache misses and populates the cache.
    """
    tokens_list = list(tokens)
    if not tokens_list:
        return []

    results: list[tuple[str, int]] = []
    uncached_tokens: list[str] = []

    # Check cache first
    for token in tokens_list:
        if token in _token_cache:
            for entity_id in _token_cache[token]:
                results.append((token, entity_id))
        else:
            uncached_tokens.append(token)

    # Fetch uncached tokens from database
    if uncached_tokens:
        placeholders = ",".join("?" * len(uncached_tokens))
        rows = conn.execute(
            f"SELECT token, entity_id FROM name_tokens WHERE token IN ({placeholders})",
            uncached_tokens,
        ).fetchall()

        # Group by token for caching
        token_to_entities: dict[str, list[int]] = {}
        for row in rows:
            token = row["token"]
            entity_id = row["entity_id"]
            results.append((token, entity_id))
            token_to_entities.setdefault(token, []).append(entity_id)

        # Update cache
        for token, entity_ids in token_to_entities.items():
            _token_cache[token] = entity_ids

        # Cache empty results too (tokens with no matches)
        for token in uncached_tokens:
            if token not in token_to_entities:
                _token_cache[token] = []

    return results


def invalidate() -> None:
    """Clear the cache, typically after a sanctions list refresh."""
    global _token_cache
    _token_cache.clear()


def cache_size() -> int:
    """Return the number of tokens currently cached."""
    return len(_token_cache)
