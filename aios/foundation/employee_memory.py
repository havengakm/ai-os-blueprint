"""Employee Memory — per-employee semantic memory store.

Phase 1 of the structural rewrite (per docs/architecture/aios-structural-plan-2026-04-29.md).

Each AI employee has its own memory of past job completions, learnings consumed
from peers, observations, and recaps. Memories are vector-indexed via the
existing foundation embedder so an employee can ``recall(query, k=5)`` the
top-k semantically similar prior memories before its next run.

Per-deployment isolation: every read + write filters by ``client_id``. There
is no global memory store — each deployment has its own slice.

Three first-class operations:

  - ``remember`` — write a new memory row (with embedding if embedder provided)
  - ``recall``   — semantic-similarity search over this employee's memories
  - ``subscribe`` — declare that ``employee_id`` wants to consume learning_events
                    emitted by ``source_employee_id``

The pgvector implementation backs onto the ``employee_memory`` and
``employee_subscriptions`` tables (see scripts/sql/024_employee_memory_and_standup.sql).
The Protocol lets tests inject an in-memory fake.

Usage:
    memory = EmployeeMemoryPgVector(supabase_client, embedder)

    # Write
    await memory.remember(
        client_id="kirsten-client-zero",
        employee_id="prospect-researcher",
        content="Found 18 new agencies on /branding last week. 11 scored 70+.",
        kind="job_completion",
        metadata={"playbook": "lead_generation", "scored_count": 11},
    )

    # Read
    matches = await memory.recall(
        client_id="kirsten-client-zero",
        employee_id="prospect-researcher",
        query="What did I find on Clutch lately?",
        k=5,
    )

    # Subscribe
    await memory.subscribe(
        client_id="kirsten-client-zero",
        employee_id="content-writer",
        source_employee_id="outreach-manager",
        kind_filter={"job_completion", "outcome"},
    )
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Public types                                                                 #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Memory:
    """One row from employee_memory, returned by recall()."""

    id: str
    employee_id: str
    kind: str
    content: str
    metadata: dict[str, Any]
    created_at: datetime
    similarity: float | None = None  # set by recall(); None for direct lookups


# --------------------------------------------------------------------------- #
# Protocol — what employees and the COO depend on                              #
# --------------------------------------------------------------------------- #


class EmployeeMemory(Protocol):
    """Per-employee semantic memory store. Implementations: pgvector (prod),
    in-memory (tests). All methods are per-deployment-isolated by ``client_id``."""

    async def remember(
        self,
        *,
        client_id: str,
        employee_id: str,
        content: str,
        kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Persist a new memory row. Returns the row id. Embeds ``content``
        if an embedder is wired; otherwise the row is stored without an
        embedding (recall() will skip it for similarity but it remains in
        time-ordered queries)."""
        ...

    async def recall(
        self,
        *,
        client_id: str,
        employee_id: str,
        query: str,
        k: int = 5,
        kind_filter: set[str] | None = None,
    ) -> list[Memory]:
        """Return the top-k semantically similar memories for this employee
        within this deployment. Filtered by ``kind`` if ``kind_filter`` given.
        Returns [] if no embedder is wired (similarity not computable)."""
        ...

    async def subscribe(
        self,
        *,
        client_id: str,
        employee_id: str,
        source_employee_id: str,
        kind_filter: set[str] | None = None,
    ) -> None:
        """Declare that ``employee_id`` wants to consume ``source_employee_id``'s
        learning_events. Idempotent — re-subscribing updates the kind_filter."""
        ...


# --------------------------------------------------------------------------- #
# pgvector implementation                                                      #
# --------------------------------------------------------------------------- #


_DEFAULT_KINDS_FOR_RECALL = frozenset({
    "job_completion", "learning", "observation", "recap", "synthesis",
})

_DEFAULT_SUBSCRIPTION_KIND_FILTER = ("job_completion", "learning")


class EmployeeMemoryPgVector:
    """Supabase pgvector implementation. Backs onto the ``employee_memory``
    and ``employee_subscriptions`` tables defined in
    scripts/sql/024_employee_memory_and_standup.sql.
    """

    def __init__(self, db: Any, embedder: Any | None = None) -> None:
        """db: Supabase async client. embedder: optional callable(text) -> list[float]."""
        self._db = db
        self._embedder = embedder

    async def remember(
        self,
        *,
        client_id: str,
        employee_id: str,
        content: str,
        kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        record: dict[str, Any] = {
            "client_id": client_id,
            "employee_id": employee_id,
            "kind": kind,
            "content": content,
            "metadata": json.dumps(metadata or {}),
        }

        if self._embedder is not None:
            try:
                vector = await self._embedder(content)
                record["embedding"] = vector
            except Exception:
                # Embedding failure is non-fatal — store without it.
                logger.exception(
                    "employee_memory: embedder failed client=%s employee=%s",
                    client_id, employee_id,
                )

        resp = await self._db.table("employee_memory").insert(record).execute()
        rows = resp.data or []
        if not rows:
            raise RuntimeError(
                f"employee_memory insert returned no rows: client={client_id} employee={employee_id}"
            )
        return rows[0]["id"]

    async def recall(
        self,
        *,
        client_id: str,
        employee_id: str,
        query: str,
        k: int = 5,
        kind_filter: set[str] | None = None,
    ) -> list[Memory]:
        if self._embedder is None:
            logger.debug(
                "employee_memory.recall called without embedder — returning []"
            )
            return []

        try:
            query_embedding = await self._embedder(query)
        except Exception:
            logger.exception(
                "employee_memory.recall: embedder failed client=%s employee=%s",
                client_id, employee_id,
            )
            return []

        kinds = list(kind_filter or _DEFAULT_KINDS_FOR_RECALL)

        resp = await self._db.rpc(
            "match_employee_memory",
            {
                "p_client_id": client_id,
                "p_employee_id": employee_id,
                "p_query_embedding": query_embedding,
                "p_kind_filter": kinds,
                "p_match_count": k,
            },
        ).execute()
        rows = resp.data or []

        return [_row_to_memory(r) for r in rows]

    async def subscribe(
        self,
        *,
        client_id: str,
        employee_id: str,
        source_employee_id: str,
        kind_filter: set[str] | None = None,
    ) -> None:
        record = {
            "client_id": client_id,
            "employee_id": employee_id,
            "source_employee_id": source_employee_id,
            "kind_filter": list(kind_filter or _DEFAULT_SUBSCRIPTION_KIND_FILTER),
        }
        # upsert on the composite primary key
        await self._db.table("employee_subscriptions").upsert(
            record,
            on_conflict="client_id,employee_id,source_employee_id",
        ).execute()


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #


def _row_to_memory(row: dict[str, Any]) -> Memory:
    """Convert a Supabase row dict to a Memory instance.

    Tolerates both stringified-JSON metadata (from insert path) and dict
    metadata (from older rows)."""
    metadata_raw = row.get("metadata") or {}
    if isinstance(metadata_raw, str):
        try:
            metadata = json.loads(metadata_raw)
        except json.JSONDecodeError:
            metadata = {}
    else:
        metadata = metadata_raw

    created_at_raw = row.get("created_at")
    if isinstance(created_at_raw, str):
        created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
    elif isinstance(created_at_raw, datetime):
        created_at = created_at_raw
    else:
        created_at = datetime.now()

    return Memory(
        id=str(row["id"]),
        employee_id=str(row["employee_id"]),
        kind=str(row["kind"]),
        content=str(row.get("content") or ""),
        metadata=metadata,
        created_at=created_at,
        similarity=row.get("similarity"),
    )
