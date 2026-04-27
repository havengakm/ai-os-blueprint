"""FakeSupabaseClient — in-memory substitute for supabase.Client.

Covers the subset of the chainable Builder API used by the 8 backends
in ``systems/scout/supabase_backends/``:

    .table(name).select(cols).eq(col, val).limit(N).execute()
    .table(name).select(cols).eq(col, val).gte(col, val).is_(col, "null").execute()
    .table(name).select(cols).not_.is_(col, "null").execute()
    .table(name).select(cols).not_.in_(col, [v1, v2]).execute()
    .table(name).insert(row_or_rows).execute()          -> .data is the inserted row(s)
    .table(name).upsert(row, on_conflict=..., ignore_duplicates=True).execute()
    .table(name).update(patch).eq(...).execute()

Row IDs are auto-assigned ``str(uuid4())`` on insert/upsert when missing.
This fake is intentionally forgiving on filter types (mixes strings/ints).
It is *not* a Postgres emulator — only the behaviours exercised by the
backends are modelled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class FakeResult:
    """Mirror of supabase's APIResponse — tests only read ``.data``."""

    data: list[dict[str, Any]] = field(default_factory=list)


class _NotBuilder:
    """``.not_.is_(col, 'null')`` / ``.not_.in_(col, [...])`` sub-builder."""

    def __init__(self, parent: "_QueryBuilder") -> None:
        self._parent = parent

    def is_(self, col: str, value: str) -> "_QueryBuilder":
        self._parent._filters.append(("not_is", col, value))
        return self._parent

    def in_(self, col: str, values: list[Any]) -> "_QueryBuilder":
        self._parent._filters.append(("not_in", col, list(values)))
        return self._parent


class _QueryBuilder:
    """Chainable query builder backed by an in-memory table."""

    def __init__(self, client: "FakeSupabaseClient", table: str) -> None:
        self._client = client
        self._table = table
        self._op: str | None = None
        self._select_cols: str | None = None
        self._payload: Any = None
        self._on_conflict: str | None = None
        self._ignore_duplicates: bool = False
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._orders: list[tuple[str, bool]] = []

    # ---- op chain ----------------------------------------------------

    def select(self, cols: str) -> "_QueryBuilder":
        self._op = "select"
        self._select_cols = cols
        return self

    def insert(self, payload: Any) -> "_QueryBuilder":
        self._op = "insert"
        self._payload = payload
        return self

    def upsert(
        self,
        payload: dict[str, Any],
        on_conflict: str | None = None,
        ignore_duplicates: bool = False,
    ) -> "_QueryBuilder":
        self._op = "upsert"
        self._payload = payload
        self._on_conflict = on_conflict
        self._ignore_duplicates = ignore_duplicates
        return self

    def update(self, payload: dict[str, Any]) -> "_QueryBuilder":
        self._op = "update"
        self._payload = payload
        return self

    # ---- filter chain ------------------------------------------------

    def eq(self, col: str, val: Any) -> "_QueryBuilder":
        self._filters.append(("eq", col, val))
        return self

    def gte(self, col: str, val: Any) -> "_QueryBuilder":
        self._filters.append(("gte", col, val))
        return self

    def is_(self, col: str, val: str) -> "_QueryBuilder":
        self._filters.append(("is", col, val))
        return self

    def in_(self, col: str, vals: list[Any]) -> "_QueryBuilder":
        self._filters.append(("in", col, list(vals)))
        return self

    @property
    def not_(self) -> _NotBuilder:
        return _NotBuilder(self)

    def limit(self, n: int) -> "_QueryBuilder":
        self._limit = n
        return self

    def order(self, col: str, desc: bool = False) -> "_QueryBuilder":
        self._orders.append((col, desc))
        return self

    # ---- execute -----------------------------------------------------

    def execute(self) -> FakeResult:
        rows = self._client._tables.get(self._table, [])

        if self._op == "select":
            filtered = _apply_filters(rows, self._filters)
            if self._limit is not None:
                filtered = filtered[: self._limit]
            return FakeResult(data=[dict(r) for r in filtered])

        if self._op == "insert":
            payload = self._payload
            inserted: list[dict[str, Any]] = []
            table = self._client._tables.setdefault(self._table, [])
            rows_to_insert: list[dict[str, Any]] = (
                list(payload) if isinstance(payload, list) else [payload]
            )
            for row in rows_to_insert:
                row = dict(row)
                row.setdefault("id", str(uuid4()))
                table.append(row)
                inserted.append(row)
            self._client._insert_calls.append(
                {"table": self._table, "rows": [dict(r) for r in rows_to_insert]}
            )
            return FakeResult(data=[dict(r) for r in inserted])

        if self._op == "upsert":
            payload = dict(self._payload)
            table = self._client._tables.setdefault(self._table, [])
            key_fields = (self._on_conflict or "id").split(",")
            existing = None
            for r in table:
                if all(r.get(k) == payload.get(k) for k in key_fields):
                    existing = r
                    break
            if existing is None:
                payload.setdefault("id", str(uuid4()))
                table.append(payload)
                result_row = payload
            elif self._ignore_duplicates:
                result_row = existing
            else:
                existing.update(payload)
                result_row = existing
            self._client._upsert_calls.append(
                {
                    "table": self._table,
                    "payload": dict(self._payload),
                    "on_conflict": self._on_conflict,
                    "ignore_duplicates": self._ignore_duplicates,
                }
            )
            return FakeResult(data=[dict(result_row)])

        if self._op == "update":
            matched = _apply_filters(rows, self._filters)
            for r in matched:
                r.update(self._payload)
            self._client._update_calls.append(
                {
                    "table": self._table,
                    "payload": dict(self._payload),
                    "filters": list(self._filters),
                    "matched_count": len(matched),
                }
            )
            return FakeResult(data=[dict(r) for r in matched])

        raise RuntimeError(f"Unknown op on table {self._table!r}: {self._op}")


def _apply_filters(
    rows: list[dict[str, Any]],
    filters: list[tuple[str, str, Any]],
) -> list[dict[str, Any]]:
    out = list(rows)
    for kind, col, val in filters:
        if kind == "eq":
            out = [r for r in out if r.get(col) == val]
        elif kind == "gte":
            out = [r for r in out if (r.get(col) is not None and r.get(col) >= val)]
        elif kind == "is":
            # supabase is_(col, "null") -> col IS NULL
            if val == "null":
                out = [r for r in out if r.get(col) is None]
            else:
                out = [r for r in out if r.get(col) == val]
        elif kind == "not_is":
            if val == "null":
                out = [r for r in out if r.get(col) is not None]
            else:
                out = [r for r in out if r.get(col) != val]
        elif kind == "in":
            out = [r for r in out if r.get(col) in val]
        elif kind == "not_in":
            out = [r for r in out if r.get(col) not in val]
        else:
            raise RuntimeError(f"unknown filter kind: {kind}")
    return out


class _RpcBuilder:
    """Chainable RPC builder mirroring ``client.rpc(name, params).execute()``.

    The fake supports an arbitrary number of RPC stubs registered on the
    client via ``client.set_rpc(name, responder)`` where ``responder`` is
    either:
      - a static value (returned verbatim as ``FakeResult.data``)
      - a callable ``responder(params: dict) -> Any`` for dynamic responses
    """

    def __init__(self, client: "FakeSupabaseClient", name: str, params: dict[str, Any]) -> None:
        self._client = client
        self._name = name
        self._params = params

    def execute(self) -> FakeResult:
        if self._name not in self._client._rpcs:
            raise RuntimeError(
                f"FakeSupabaseClient: no RPC stub for {self._name!r}; "
                f"call client.set_rpc({self._name!r}, ...) in the test."
            )
        responder = self._client._rpcs[self._name]
        result = responder(self._params) if callable(responder) else responder
        # Real Supabase wraps RPC results in APIResponse(data=...).
        # Postgres functions returning a scalar deliver it as the scalar
        # itself in ``data``; we mirror that.
        return FakeResult(data=result)


class FakeSupabaseClient:
    """In-memory Supabase stand-in.

    ``tables`` is a dict of ``table_name -> list[row]`` the test seeds
    with whatever fixture data it needs. Call-history lists
    (``_insert_calls``, ``_upsert_calls``, ``_update_calls``) let tests
    assert on exact wire calls when shape-matters (e.g. the item-62
    gate test inspects the update payload).

    RPC support: register stubs via ``client.set_rpc(name, value_or_callable)``.
    Production code calls ``client.rpc(name, params).execute()``.
    """

    def __init__(
        self,
        tables: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = tables or {}
        self._insert_calls: list[dict[str, Any]] = []
        self._upsert_calls: list[dict[str, Any]] = []
        self._update_calls: list[dict[str, Any]] = []
        self._rpcs: dict[str, Any] = {}
        self._rpc_calls: list[dict[str, Any]] = []

    def table(self, name: str) -> _QueryBuilder:
        return _QueryBuilder(self, name)

    def rpc(self, name: str, params: dict[str, Any] | None = None) -> _RpcBuilder:
        self._rpc_calls.append({"name": name, "params": params or {}})
        return _RpcBuilder(self, name, params or {})

    def set_rpc(self, name: str, responder: Any) -> None:
        """Register a stub for an RPC. ``responder`` may be a static
        value or a callable taking the params dict."""
        self._rpcs[name] = responder

    # Convenience read-only views for tests ----------------------------

    def rows(self, table: str) -> list[dict[str, Any]]:
        return list(self._tables.get(table, []))

    def rpc_calls(self, name: str | None = None) -> list[dict[str, Any]]:
        if name is None:
            return list(self._rpc_calls)
        return [c for c in self._rpc_calls if c["name"] == name]
