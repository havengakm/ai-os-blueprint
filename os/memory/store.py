"""
MemoryStore — Unified retrieval across all foundation layers.

The single interface every system uses to access the AI OS brain.
Pulls from: business_context (RAG), context_registry, knowledge_base,
client_facts, conversation_history, and decision_log.

Usage:
    store = MemoryStore(db, embedder)

    # Load everything needed for a system prompt
    context = await store.load_full_context(client_id)
    # Returns: {
    #   "business_context": [...],      # RAG chunks from business_context
    #   "context_registry": [...],      # Structured context (people, strategy, brand)
    #   "client_facts": [...],          # Persistent facts from conversation
    #   "conversation_history": [...],  # Last N turns
    #   "relevant_knowledge": [...],    # Expert knowledge matching current task
    # }

    # Retrieve specific context for a task
    knowledge = await store.retrieve_knowledge(client_id, "writing cold email for CRO agency")
    decisions = await store.retrieve_past_decisions(client_id, "copy_variant", context_text)
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MemoryStore:
    """Unified memory interface for the AI OS."""

    def __init__(self, db, embedder=None):
        """
        Args:
            db: Supabase async client
            embedder: Optional async callable(text) -> list[float] for Voyage embeddings
        """
        self.db = db
        self.embedder = embedder

    # ── Business Context (RAG) ────────────────────────────────────────────

    async def retrieve_business_context(
        self,
        client_id: str,
        query: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """Retrieve business context chunks. Vector search if query provided, else all."""
        if query and self.embedder:
            try:
                embedding = await self.embedder(query)
                result = await self.db.rpc(
                    "match_business_context",
                    {
                        "query_embedding": embedding,
                        "client_id_filter": client_id,
                        "match_count": limit,
                    },
                ).execute()
                return result.data or []
            except Exception as e:
                logger.warning("Business context RAG failed, falling back: %s", e)

        # Fallback: return all business context
        result = await (
            self.db.table("business_context")
            .select("section, content")
            .eq("client_id", client_id)
            .execute()
        )
        return result.data or []

    # ── Context Registry ──────────────────────────────────────────────────

    async def retrieve_context_registry(
        self,
        client_id: str,
        context_type: str | None = None,
        query: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Retrieve structured context from context_registry."""
        if query and self.embedder:
            try:
                embedding = await self.embedder(query)
                result = await self.db.rpc(
                    "match_context_registry",
                    {
                        "query_embedding": embedding,
                        "client_id_filter": client_id,
                        "match_count": limit,
                    },
                ).execute()
                return result.data or []
            except Exception:
                pass

        # Direct query
        q = (
            self.db.table("context_registry")
            .select("context_type, key, value, summary")
            .eq("client_id", client_id)
            .eq("active", True)
        )
        if context_type:
            q = q.eq("context_type", context_type)

        result = await q.limit(limit).execute()
        return result.data or []

    # ── Client Facts ──────────────────────────────────────────────────────

    async def retrieve_facts(self, client_id: str) -> list[dict]:
        """Retrieve all persistent facts for a client."""
        result = await (
            self.db.table("client_facts")
            .select("key, value, source")
            .eq("client_id", client_id)
            .execute()
        )
        return result.data or []

    async def save_fact(
        self,
        client_id: str,
        key: str,
        value: str,
        source: str = "conversation",
    ) -> None:
        """Upsert a persistent fact."""
        await (
            self.db.table("client_facts")
            .upsert({
                "client_id": client_id,
                "key": key,
                "value": value,
                "source": source,
            })
            .execute()
        )

    # ── Conversation History ──────────────────────────────────────────────

    async def retrieve_history(
        self,
        client_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[dict]:
        """Retrieve last N conversation turns."""
        result = await (
            self.db.table("conversation_history")
            .select("role, content, created_at")
            .eq("client_id", client_id)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = result.data or []
        rows.reverse()  # Oldest first
        return rows

    async def save_turn(
        self,
        client_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        """Save a conversation turn."""
        await (
            self.db.table("conversation_history")
            .insert({
                "client_id": client_id,
                "user_id": user_id,
                "role": role,
                "content": content,
                "metadata": metadata or {},
            })
            .execute()
        )

    # ── Knowledge Base ────────────────────────────────────────────────────

    async def retrieve_knowledge(
        self,
        client_id: str,
        query: str,
        source: str | None = None,
        limit: int = 3,
    ) -> list[dict]:
        """Retrieve relevant expert knowledge. Searches global + client-specific."""
        if not self.embedder:
            return []

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
            return result.data or []
        except Exception as e:
            logger.warning("Knowledge retrieval failed: %s", e)
            return []

    # ── Decision Log ──────────────────────────────────────────────────────

    async def retrieve_past_decisions(
        self,
        client_id: str,
        decision_type: str,
        context_text: str,
        limit: int = 5,
    ) -> list[dict]:
        """Retrieve similar past decisions for pattern matching."""
        if not self.embedder:
            return []

        try:
            embedding = await self.embedder(context_text)
            result = await self.db.rpc(
                "match_decisions",
                {
                    "query_embedding": embedding,
                    "client_id_filter": client_id,
                    "decision_type_filter": decision_type,
                    "match_count": limit,
                },
            ).execute()
            return result.data or []
        except Exception as e:
            logger.warning("Decision retrieval failed: %s", e)
            return []

    # ── Unified Context Load ──────────────────────────────────────────────

    async def load_full_context(
        self,
        client_id: str,
        user_id: str | None = None,
        task_query: str | None = None,
    ) -> dict[str, Any]:
        """
        Load the complete context needed for a system prompt.
        This is the primary method every system calls before acting.
        """
        import asyncio

        # Parallel fetch for speed
        tasks = {
            "business_context": self.retrieve_business_context(client_id, task_query),
            "context_registry": self.retrieve_context_registry(client_id),
            "client_facts": self.retrieve_facts(client_id),
        }

        if user_id:
            tasks["conversation_history"] = self.retrieve_history(client_id, user_id)

        if task_query:
            tasks["relevant_knowledge"] = self.retrieve_knowledge(client_id, task_query)
            tasks["past_decisions"] = self.retrieve_past_decisions(
                client_id, "copy_variant", task_query
            )

        results = {}
        gathered = await asyncio.gather(
            *tasks.values(),
            return_exceptions=True,
        )

        for key, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                logger.warning("Failed to load %s: %s", key, result)
                results[key] = []
            else:
                results[key] = result

        return results

    # ── Format for System Prompt ──────────────────────────────────────────

    def format_context_for_prompt(self, context: dict[str, Any]) -> str:
        """Format the full context dict into a string for the system prompt."""
        sections = []

        # Business context
        bc = context.get("business_context", [])
        if bc:
            sections.append("## Business Context\n")
            for chunk in bc:
                section = chunk.get("section", "")
                content = chunk.get("content", "")
                if section and content:
                    sections.append(f"### {section}\n{content}\n")

        # Context registry
        cr = context.get("context_registry", [])
        if cr:
            sections.append("## Structured Context\n")
            for item in cr:
                sections.append(
                    f"**{item.get('context_type', '')} / {item.get('key', '')}:** "
                    f"{item.get('summary', '')}\n"
                )

        # Client facts
        facts = context.get("client_facts", [])
        if facts:
            sections.append("## Known Facts\n")
            for fact in facts:
                sections.append(f"- {fact['key']}: {fact['value']}\n")

        # Relevant knowledge
        knowledge = context.get("relevant_knowledge", [])
        if knowledge:
            sections.append("## Relevant Expert Knowledge\n")
            for k in knowledge:
                sections.append(f"### {k.get('title', '')} ({k.get('source', '')})\n")
                sections.append(f"{k.get('content', '')[:500]}\n")

        # Past decisions
        decisions = context.get("past_decisions", [])
        if decisions:
            sections.append("## Similar Past Decisions\n")
            for d in decisions:
                outcome = d.get("outcome", "pending")
                sections.append(
                    f"- {d.get('decision', '')[:100]} → {outcome}\n"
                )

        return "\n".join(sections)
