from __future__ import annotations

import pandas as pd

from services.search_service import (
    build_cas_supplier_queries,
    direct_supplier_search_urls,
    filter_likely_supplier_results,
    serpapi_search,
    discover_product_links_from_page,
)
from services.page_extractor import extract_product_data_from_url


def _dedupe_results(results):
    seen = set()
    unique = []
    for result in results:
        if result.url in seen:
            continue
        seen.add(result.url)
        unique.append(result)
    return unique


def discover_live_suppliers(
    cas_number: str,
    chemical_name: str | None = None,
    serpapi_key: str | None = None,
    max_pages_to_extract: int = 12,
    include_direct_links: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Discover supplier pages and extract visible product/pricing fields.

    v6 behavior:
    - Preserves v5 strict discovery.
    - Adds embedded-script price extraction in page_extractor.
    - Deduplicates supplier/product rows so the UI is cleaner.
    """
    queries = build_cas_supplier_queries(cas_number, chemical_name)
    serp_results = filter_likely_supplier_results(serpapi_search(queries, serpapi_key or ""))
    direct_results = direct_supplier_search_urls(cas_number) if include_direct_links else []

    seed_results = _dedupe_results(serp_results + direct_results)

    expanded = []
    for result in seed_results[:30]:
        expanded.extend(discover_product_links_from_page(result, cas_number, max_links=5))
    expanded = _dedupe_results(expanded)

    # Extract product-detail candidates first. Search-page seed extraction is fallback only.
    if expanded:
        candidate_results = expanded + serp_results
    else:
        candidate_results = serp_results + direct_results
    candidate_results = _dedupe_results(candidate_results)

    discovery_records = []
    for r in _dedupe_results(expanded + seed_results):
        discovery_records.append(r.__dict__)
    discovery_df = pd.DataFrame(discovery_records)

    extracted_rows = []
    for result in candidate_results[:max_pages_to_extract]:
        extracted = extract_product_data_from_url(
            cas_number,
            result.url,
            supplier_hint=result.supplier_hint or None,
            discovery_title=result.title,
            discovery_snippet=result.snippet,
        )
        # Reduce table noise: keep confirmed CAS rows, visible-price rows, or rows that clearly communicate quote/availability.
        keep = (
            extracted.cas_exact_match
            or extracted.listed_price_usd is not None
            or extracted.stock_status not in ["Not visible", "Extraction failed"]
            or result.source.startswith("serpapi")
        )
        if not keep:
            continue
        extracted_rows.append(
            {
                "cas_number": cas_number,
                "chemical_name": chemical_name or "",
                "supplier": extracted.supplier,
                "region": "Unknown",
                "purity": extracted.purity or "Not visible",
                "pack_size": extracted.pack_size,
                "pack_unit": extracted.pack_unit,
                "listed_price_usd": extracted.listed_price_usd,
                "stock_status": extracted.stock_status,
                "lead_time": "Not visible",
                "product_url": extracted.product_url,
                "notes": extracted.evidence,
                "page_title": extracted.title,
                "cas_exact_match": extracted.cas_exact_match,
                "extraction_status": extracted.extraction_status,
                "extraction_confidence": extracted.confidence,
                "extraction_method": extracted.extraction_method,
                "raw_matches": extracted.raw_matches,
                "data_source": "live_extraction_v6",
            }
        )

    extracted_df = pd.DataFrame(extracted_rows)
    if not extracted_df.empty:
        sort_cols = [c for c in ["listed_price_usd", "extraction_confidence"] if c in extracted_df.columns]
        if sort_cols:
            extracted_df = extracted_df.sort_values(sort_cols, ascending=[False] * len(sort_cols))
        dedupe_cols = [c for c in ["supplier", "cas_number", "purity", "pack_size", "pack_unit", "product_url"] if c in extracted_df.columns]
        if dedupe_cols:
            extracted_df = extracted_df.drop_duplicates(subset=dedupe_cols, keep="first")

    return extracted_df, discovery_df
