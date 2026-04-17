"""
Knowledge Store — Expert brains retrieval.

Queries the knowledge_base table for relevant expert knowledge.
Searches both global knowledge (shared across all instances) and
client-specific knowledge (swipe files, case studies).

Usage:
    store = KnowledgeStore(db, embedder)

    # Before generating outreach copy
    frameworks = await store.retrieve(
        client_id="kirsten-client-zero",
        query="cold email for agency founder, growth-mode, no signal",
        source="nick_saraev",  # optional: filter by source
        limit=3,
    )

    # Returns relevant knowledge chunks to include in the AI prompt
    # e.g. Nick Saraev's AIDA framework, his "AI makes things profitable" principle

    # Format for prompt inclusion
    prompt_section = store.format_for_prompt(frameworks)
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class KnowledgeStore:
    """Retrieves expert knowledge from the knowledge_base table."""

    def __init__(self, db, embedder=None):
        self.db = db
        self.embedder = embedder

    async def retrieve(
        self,
        client_id: str,
        query: str,
        source: str | None = None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant knowledge chunks via vector similarity."""
        if not self.embedder:
            logger.debug("No embedder configured, falling back to keyword search")
            return await self._keyword_search(client_id, query, source, limit)

        try:
            embedding = await self.embedder(query)

            result = await self.db.rpc(
                "match_knowledge_base",
                {
                    "query_embedding": embedding,
                    "client_id_filter": client_id,
                    "source_filter": source,
                    "match_count": limit,
                },
            ).execute()

            matches = result.data or []

            if matches:
                logger.info(
                    "KNOWLEDGE: %d chunks retrieved for '%s' (source: %s)",
                    len(matches), query[:50], source or "all",
                )

            return [
                {
                    "source": m["source"],
                    "category": m["category"],
                    "title": m["title"],
                    "content": m["content"],
                    "similarity": m.get("similarity"),
                }
                for m in matches
            ]

        except Exception as e:
            logger.warning("Knowledge retrieval failed: %s", e)
            return []

    async def _keyword_search(
        self,
        client_id: str,
        query: str,
        source: str | None = None,
        limit: int = 3,
    ) -> list[dict]:
        """Fallback: simple keyword search when embedder is unavailable."""
        try:
            q = (
                self.db.table("knowledge_base")
                .select("source, category, title, content")
                .or_(f"client_id.eq.{client_id},client_id.eq.global")
                .eq("active", True)
            )

            if source:
                q = q.eq("source", source)

            q = q.limit(limit)
            result = await q.execute()

            return [
                {
                    "source": r["source"],
                    "category": r["category"],
                    "title": r["title"],
                    "content": r["content"],
                    "similarity": None,
                }
                for r in (result.data or [])
            ]
        except Exception as e:
            logger.warning("Keyword search failed: %s", e)
            return []

    def format_for_prompt(self, knowledge_chunks: list[dict]) -> str:
        """Format knowledge chunks for inclusion in an AI prompt."""
        if not knowledge_chunks:
            return ""

        lines = ["## Expert knowledge relevant to this task:\n"]

        for chunk in knowledge_chunks:
            lines.append(f"### {chunk['title']} ({chunk['source']})")
            lines.append(chunk["content"][:1000])
            lines.append("")

        return "\n".join(lines)

    async def load_from_markdown(
        self,
        client_id: str,
        source: str,
        category: str,
        filepath: str,
        tags: list[str] | None = None,
    ) -> int:
        """Load knowledge from a markdown file, splitting by ## headings."""
        import re

        with open(filepath) as f:
            content = f.read()

        # Split by ## headings
        sections = re.split(r'\n## ', content)
        loaded = 0

        for section in sections:
            if not section.strip():
                continue

            # First line is the title
            lines = section.strip().split("\n", 1)
            title = lines[0].strip().lstrip("#").strip()
            body = lines[1].strip() if len(lines) > 1 else ""

            if not body or len(body) < 50:
                continue

            record = {
                "client_id": client_id,
                "source": source,
                "category": category,
                "title": title,
                "content": body[:5000],
                "tags": tags or [],
            }

            # Embed if embedder available
            if self.embedder:
                try:
                    embed_text = f"{title}: {body[:500]}"
                    record["embedding"] = await self.embedder(embed_text)
                except Exception:
                    pass

            try:
                await self.db.table("knowledge_base").upsert(
                    record,
                    on_conflict="client_id,source,title",
                ).execute()
                loaded += 1
            except Exception as e:
                logger.warning("Failed to load knowledge chunk '%s': %s", title, e)

        logger.info("KNOWLEDGE LOADED: %d chunks from %s (%s)", loaded, filepath, source)
        return loaded
