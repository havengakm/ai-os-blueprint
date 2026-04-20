import pytest
from systems.scout.sources.csv_ingest import CSVIngestAdapter
from systems.scout.sources.base import RawCompanyContact


SAMPLE_CSV = """Company Name,Website,Industry,Employees,Revenue,Location
FocusCFO,https://focuscfo.com,Fractional CFO,15,$3M-$5M,Columbus OH
McCracken Alliance,mccrackenalliance.com,Executive Search,200,<$5M,Atlanta GA
FocusCFO,https://focuscfo.com,Fractional CFO,15,$3M-$5M,Columbus OH
New Life CFO,newlifecfo.com,Fractional CFO,8,$1M-$3M,Dallas TX
"""


@pytest.mark.asyncio
async def test_csv_ingest_parses_rows():
    adapter = CSVIngestAdapter(upload_id="testupload")
    rows = await adapter.pull(
        client_id="clymb",
        max_companies=10,
        csv_content=SAMPLE_CSV,
    )
    # 4 input rows, but FocusCFO is duplicated → 3 unique
    assert len(rows) == 3
    assert rows[0].company == "FocusCFO"
    assert rows[0].company_domain == "focuscfo.com"
    assert rows[0].company_website == "https://focuscfo.com"
    assert rows[0].industry == "Fractional CFO"
    assert rows[0].employees == 15
    assert rows[0].revenue_usd == 3_000_000  # low end of $3M-$5M
    assert rows[0].source == "csv:testupload"
    assert rows[0].source_id == "testupload-row0"
    assert isinstance(rows[0], RawCompanyContact)


@pytest.mark.asyncio
async def test_csv_ingest_respects_max_companies():
    adapter = CSVIngestAdapter(upload_id="cap")
    rows = await adapter.pull(
        client_id="clymb",
        max_companies=2,
        csv_content=SAMPLE_CSV,
    )
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_csv_ingest_skips_rows_without_company():
    csv_text = "Company Name,Website\n,no-company.com\nValidCo,validco.com\n"
    adapter = CSVIngestAdapter(upload_id="skip")
    rows = await adapter.pull(
        client_id="clymb",
        max_companies=10,
        csv_content=csv_text,
    )
    assert len(rows) == 1
    assert rows[0].company == "ValidCo"


@pytest.mark.asyncio
async def test_csv_ingest_requires_exactly_one_input():
    adapter = CSVIngestAdapter()
    with pytest.raises(ValueError):
        await adapter.pull(client_id="clymb", max_companies=10)


@pytest.mark.asyncio
async def test_csv_ingest_normalizes_www_prefix():
    csv_text = "Company Name,Website\nTest,https://www.test.com\n"
    adapter = CSVIngestAdapter(upload_id="wwwstrip")
    rows = await adapter.pull(
        client_id="clymb",
        max_companies=10,
        csv_content=csv_text,
    )
    assert rows[0].company_domain == "test.com"


@pytest.mark.asyncio
async def test_csv_ingest_preserves_extra_columns_in_raw_data():
    csv_text = "Company Name,Website,Custom Column\nTest,test.com,custom-value\n"
    adapter = CSVIngestAdapter(upload_id="extras")
    rows = await adapter.pull(
        client_id="clymb",
        max_companies=10,
        csv_content=csv_text,
    )
    assert rows[0].raw_data.get("Custom Column") == "custom-value"
