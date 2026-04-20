"""Scout sources package — company-level lead discovery adapters."""
from systems.scout.sources.apollo_company import ApolloCompanyAdapter
from systems.scout.sources.base import CompanySourceAdapter, RawCompanyContact
from systems.scout.sources.csv_ingest import CSVIngestAdapter
from systems.scout.sources.utils import normalize_domain, parse_int_safe

__all__ = [
    "ApolloCompanyAdapter",
    "CSVIngestAdapter",
    "CompanySourceAdapter",
    "RawCompanyContact",
    "normalize_domain",
    "parse_int_safe",
]
