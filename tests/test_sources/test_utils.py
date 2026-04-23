"""Tests for shared source helpers — hardening coverage per 2026-04-20 CQ review."""
from systems.scout.sources.utils import normalize_domain, parse_int_safe


def test_normalize_domain_strips_scheme_and_www():
    assert normalize_domain("https://www.foo.com") == "foo.com"
    assert normalize_domain("http://foo.com") == "foo.com"
    assert normalize_domain("www.foo.com") == "foo.com"
    assert normalize_domain("foo.com") == "foo.com"


def test_normalize_domain_lowercases():
    assert normalize_domain("HTTPS://FOO.COM") == "foo.com"
    assert normalize_domain("Foo.COM") == "foo.com"


def test_normalize_domain_rejects_garbage():
    # CQ issue I1 — values without a hostname shape must return None
    assert normalize_domain("plainstring") is None
    assert normalize_domain("<>bad<>") is None
    assert normalize_domain("") is None
    assert normalize_domain(None) is None
    assert normalize_domain(" ") is None


def test_normalize_domain_handles_unicode():
    assert normalize_domain("https://müller.de") == "müller.de"


def test_parse_int_safe_basic():
    assert parse_int_safe("3000000") == 3_000_000
    assert parse_int_safe("3,000,000") == 3_000_000
    assert parse_int_safe("$3000000") == 3_000_000


def test_parse_int_safe_suffixes():
    assert parse_int_safe("$3M") == 3_000_000
    assert parse_int_safe("5K") == 5_000


def test_parse_int_safe_ranges_take_low_end():
    assert parse_int_safe("$3M-$5M") == 3_000_000


def test_parse_int_safe_rejects_non_numeric_prefix():
    # CQ C3-adjacent: "<$5M" is not parseable as a pure number
    assert parse_int_safe("<$5M") is None


def test_parse_int_safe_rejects_infinity():
    # CQ C3: "inf" previously caused OverflowError that aborted ingest
    assert parse_int_safe("inf") is None
    assert parse_int_safe("-inf") is None
    assert parse_int_safe("1e400") is None  # overflows float


def test_parse_int_safe_rejects_nan():
    assert parse_int_safe("nan") is None


def test_parse_int_safe_none_and_empty():
    assert parse_int_safe(None) is None
    assert parse_int_safe("") is None
    assert parse_int_safe("  ") is None
