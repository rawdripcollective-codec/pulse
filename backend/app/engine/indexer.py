"""Semantic indexing engine using LanceDB for vectors + tree-sitter for structure.

For each repository, the indexer:
  1. Walks the working tree and parses every supported file
  2. Builds an in-memory property graph
  3. Generates embeddings for every code entity (batch)
  4. Stores vectors + metadata in a per-repo LanceDB table
"""

from pathlib import Path
from typing import Optional

import lancedb
import pyarrow as pa
import structlog

from app.config import settings
from app.engine.graph import PropertyGraph
from app.engine.parser import CodeEntity, CodeParser, ParsedFile

logger = structlog.get_logger()


class SemanticIndexer:
    """Builds and manages the semantic knowledge index for a repository."""

    def __init__(self, repo_full_name: str, repo_path: Path):
        self.repo_full_name = repo_full_name
        self.repo_path = repo_path
        self.parser = CodeParser()
        self.graph = PropertyGraph()

        # LanceDB connection
        self.db = lancedb.connect(settings.lancedb_path)
        self._init_table()

    def _init_table(self) -> None:
        """Initialize or open the per-repo entities table."""
        table_name = self._sanitize_table_name(self.repo_full_name)
        if table_name not in self.db.table_names():
            self.db.create_table(
                table_name,
                schema=pa.schema(
                    [
                        pa.field("id", pa.string()),
                        pa.field("name", pa.string()),
                        pa.field("kind", pa.string()),
                        pa.field("file_path", pa.string()),
                        pa.field("signature", pa.string()),
                        pa.field("code_text", pa.string()),
                        pa.field("docstring", pa.string()),
                        pa.field("parent_name", pa.string()),
                        pa.field("calls", pa.list_(pa.string())),
                        pa.field(
                            "vector",
                            pa.list_(pa.float32(), list_size=settings.embedding_dimensions),
                        ),
                    ]
                ),
            )
        self.table = self.db.open_table(table_name)

    @staticmethod
    def _sanitize_table_name(full_name: str) -> str:
        return full_name.replace("/", "_").replace("-", "_").replace(".", "_")

    # ─── Full repository indexing ─────────────────────────────

    async def index_repository(self) -> dict:
        """Full repository index: parse all files, build graph, embed entities."""
        logger.info("Starting repository index", repo=self.repo_full_name)

        all_entities: list[CodeEntity] = []
        parsed_files: list[ParsedFile] = []

        for file_path in self.repo_path.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix not in self.parser.SUPPORTED_EXTENSIONS:
                continue
            if file_path.stat().st_size > settings.max_file_size_bytes:
                continue
            # Skip common ignore patterns
            if any(
                p in file_path.parts
                for p in ["node_modules", ".git", "__pycache__", "venv", ".venv", "dist", "build"]
            ):
                continue

            try:
                source = file_path.read_text(encoding="utf-8", errors="ignore")
                parsed = self.parser.parse_file(file_path, source)
                parsed_files.append(parsed)
                all_entities.extend(parsed.entities)
            except Exception as e:
                logger.warning("Failed to parse file", path=str(file_path), error=str(e))

        logger.info(
            "Parsing complete",
            repo=self.repo_full_name,
            files=len(parsed_files),
            entities=len(all_entities),
        )

        # Build the property graph from parsed entities
        self.graph.build(all_entities, parsed_files)

        # Generate embeddings for each entity (batch for efficiency)
        await self._embed_and_store(all_entities)

        summary = {
            "files_parsed": len(parsed_files),
            "entities_indexed": len(all_entities),
            "graph_nodes": self.graph.node_count(),
            "graph_edges": self.graph.edge_count(),
            "language_breakdown": self._language_breakdown(parsed_files),
        }

        logger.info("Indexing complete", repo=self.repo_full_name, **summary)
        return summary

    # ─── Embedding & storage ──────────────────────────────────

    async def _embed_and_store(self, entities: list[CodeEntity]) -> None:
        """Generate embeddings and store in LanceDB."""
        if not entities:
            return

        texts: list[str] = []
        for e in entities:
            text_parts = [
                f"Kind: {e.kind}",
                f"Name: {e.name}",
                f"Signature: {e.signature}",
            ]
            if e.docstring:
                text_parts.append(f"Docstring: {e.docstring}")
            if e.parent_name:
                text_parts.append(f"Parent: {e.parent_name}")
            text_parts.append(f"Code: {e.code_text[:2000]}")  # truncate for embedding
            texts.append("\n".join(text_parts))

        # Generate embeddings via litellm
        from litellm import embedding

        try:
            response = await embedding(
                model=f"{settings.llm_provider}/{settings.embedding_model}",
                input=texts,
                api_key=settings.embedding_api_key or settings.llm_api_key,
            )
            vectors = [d["embedding"] for d in response.data]
        except Exception as e:
            logger.error("Embedding generation failed", error=str(e))
            # Fallback: zero vectors so the system can still operate
            vectors = [[0.0] * settings.embedding_dimensions for _ in texts]

        records: list[dict] = []
        for entity, vector in zip(entities, vectors):
            records.append(
                {
                    "id": f"{entity.file_path}:{entity.name}:{entity.start_line}",
                    "name": entity.name,
                    "kind": entity.kind,
                    "file_path": entity.file_path,
                    "signature": entity.signature,
                    "code_text": entity.code_text,
                    "docstring": entity.docstring or "",
                    "parent_name": entity.parent_name or "",
                    "calls": entity.calls,
                    "vector": vector,
                }
            )

        self.table.add(records, mode="append")

        # Create ANN index for fast similarity search.
        # Skip for very small batches — LanceDB's KMeans needs many vectors
        # to train a single centroid. Below ~256 records, brute force is fine.
        if records and len(records) >= 256:
            self.table.create_index(
                metric="cosine",
                num_partitions=min(256, max(1, len(records) // 100)),
            )

    # ─── Queries ──────────────────────────────────────────────

    def _language_breakdown(self, parsed_files: list[ParsedFile]) -> dict:
        breakdown: dict[str, int] = {}
        for pf in parsed_files:
            breakdown[pf.language] = breakdown.get(pf.language, 0) + 1
        return breakdown

    async def semantic_search(
        self,
        query: str,
        top_k: int = 10,
        kind_filter: Optional[str] = None,
    ) -> list[dict]:
        """Natural-language semantic search over code entities."""
        from litellm import embedding

        try:
            response = await embedding(
                model=f"{settings.llm_provider}/{settings.embedding_model}",
                input=[query],
                api_key=settings.embedding_api_key or settings.llm_api_key,
            )
            query_vector = response.data[0]["embedding"]
        except Exception:
            return []

        results = self.table.search(query_vector).limit(top_k * 2).to_list()
        if kind_filter:
            results = [r for r in results if r["kind"] == kind_filter]
        return results[:top_k]

    def blast_radius(self, file_path: str) -> list[dict]:
        """Compute the blast radius for a given file: all entities that call into it."""
        return self.graph.blast_radius(file_path)

    def callers_of(self, function_name: str) -> list[dict]:
        """Find all callers of a specific function."""
        return self.graph.callers_of(function_name)
