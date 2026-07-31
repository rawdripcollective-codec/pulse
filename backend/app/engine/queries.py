"""High-level query API that agents use to interact with the knowledge engine.

This module is the single interface agents call — they never touch the
raw parser, indexer, or graph directly. The indexer cache is in-memory;
in production with multiple workers, swap to Redis-backed caching.
"""

from pathlib import Path

import structlog

from app.engine.indexer import SemanticIndexer

logger = structlog.get_logger()

# In-memory indexer cache (one per repo)
_indexers: dict[str, SemanticIndexer] = {}


def get_indexer(
    repo_full_name: str, repo_path: str | None = None
) -> SemanticIndexer | None:
    """Get or create a SemanticIndexer for a repository."""
    if repo_full_name in _indexers:
        return _indexers[repo_full_name]

    if repo_path is None:
        return None

    path = Path(repo_path)
    if not path.exists():
        return None

    indexer = SemanticIndexer(repo_full_name, path)
    _indexers[repo_full_name] = indexer
    return indexer


async def semantic_search(
    repo_full_name: str,
    query: str,
    top_k: int = 10,
    kind_filter: str | None = None,
) -> list[dict]:
    """Natural-language semantic search over code entities."""
    indexer = _indexers.get(repo_full_name)
    if indexer is None:
        logger.warning("No indexer found for repo", repo=repo_full_name)
        return []
    return await indexer.semantic_search(query, top_k, kind_filter)


def get_blast_radius(repo_full_name: str, file_path: str) -> list[dict]:
    """Get all code entities outside a file that call into it."""
    indexer = _indexers.get(repo_full_name)
    if indexer is None:
        return []
    return indexer.blast_radius(file_path)


def get_callers(repo_full_name: str, function_name: str) -> list[str]:
    """Get all callers of a function."""
    indexer = _indexers.get(repo_full_name)
    if indexer is None:
        return []
    return indexer.callers_of(function_name)


def get_high_risk_files(repo_full_name: str, top_n: int = 10) -> list[dict]:
    """Get the files with the highest centrality (most incoming calls)."""
    indexer = _indexers.get(repo_full_name)
    if indexer is None:
        return []
    return indexer.graph.high_centrality_nodes(top_n)


def invalidate_indexer(repo_full_name: str) -> None:
    """Drop a cached indexer (e.g. after re-indexing)."""
    _indexers.pop(repo_full_name, None)
