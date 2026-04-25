from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin, urlparse
import re
import requests
from bs4 import BeautifulSoup


DEFAULT_SUPPLIER_DOMAINS = [
    "sigmaaldrich.com",
    "fishersci.com",
    "thermofisher.com",
    "tcichemicals.com",
    "combi-blocks.com",
    "oakwoodchemical.com",
    "chemimpex.com",
    "vwr.com",
    "avantorsciences.com",
    "ambeed.com",
    "emolecules.com",
    "molport.com",
    "chemblink.com",
    "lookchem.com",
    "chemicalbook.com",
    "benchchem.com",
    "bldpharm.com",
    "enaminestore.com",
    "a2bchem.com",
]

SUPPLIER_NAME_HINTS = {
    "sigmaaldrich.com": "Sigma-Aldrich",
    "fishersci.com": "Fisher Scientific",
    "thermofisher.com": "Thermo Fisher",
    "tcichemicals.com": "TCI Chemicals",
    "combi-blocks.com": "Combi-Blocks",
    "oakwoodchemical.com": "Oakwood Chemical",
    "chemimpex.com": "Chem-Impex",
    "vwr.com": "VWR / Avantor",
    "avantorsciences.com": "Avantor",
    "ambeed.com": "Ambeed",
    "emolecules.com": "eMolecules",
    "molport.com": "MolPort",
    "chemblink.com": "ChemBlink",
    "lookchem.com": "LookChem",
    "chemicalbook.com": "ChemicalBook",
    "benchchem.com": "BenchChem",
    "bldpharm.com": "BLD Pharm",
    "enaminestore.com": "Enamine",
    "a2bchem.com": "A2B Chem",
}


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str
    supplier_hint: str = ""


def supplier_hint_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    for domain, name in SUPPLIER_NAME_HINTS.items():
        if domain in host:
            return name
    root = host.split(".")[0] if host else "Unknown supplier"
    return root.replace("-", " ").title()


def build_cas_supplier_queries(cas_number: str, chemical_name: str | None = None) -> list[str]:
    cas = cas_number.strip()
    chem = (chemical_name or "").strip()
    base_terms = [
        f'"{cas}" supplier price',
        f'"{cas}" catalog price',
        f'"{cas}" buy chemical',
        f'"{cas}" quote',
        f'"{cas}" "pack size" price',
        f'"{cas}" "CAS" "Price"',
    ]
    if chem:
        base_terms.extend([
            f'"{cas}" "{chem}" supplier',
            f'"{chem}" "{cas}" price',
            f'"{chem}" "{cas}" "pack size"',
        ])
    return base_terms


def direct_supplier_search_urls(cas_number: str) -> list[SearchResult]:
    cas = cas_number.strip()
    templates = [
        ("Sigma-Aldrich", "https://www.sigmaaldrich.com/US/en/search/{cas}"),
        ("Fisher Scientific", "https://www.fishersci.com/us/en/catalog/search/products?keyword={cas}"),
        ("Thermo Fisher", "https://www.thermofisher.com/search/results?keyword={cas}"),
        ("TCI Chemicals", "https://www.tcichemicals.com/US/en/search?text={cas}"),
        ("Combi-Blocks", "https://www.combi-blocks.com/cgi-bin/find.cgi?search={cas}"),
        ("VWR / Avantor", "https://us.vwr.com/store/search?keyword={cas}"),
        ("Oakwood Chemical", "https://oakwoodchemical.com/Search?term={cas}"),
        ("Chem-Impex", "https://www.chemimpex.com/search?search={cas}"),
        ("MolPort", "https://www.molport.com/shop/find-chemicals-by-cas-number/{cas}"),
        ("eMolecules", "https://search.emolecules.com/search/#?query={cas}"),
        ("Ambeed", "https://www.ambeed.com/search.html?search={cas}"),
        ("ChemBlink", "https://www.chemblink.com/search.aspx?search={cas}"),
        ("ChemicalBook", "https://www.chemicalbook.com/Search_EN.aspx?keyword={cas}"),
        ("LookChem", "https://www.lookchem.com/cas-{cas}.html"),
    ]
    return [
        SearchResult(
            title=f"{name} CAS search",
            url=template.format(cas=cas),
            snippet="Direct supplier/search page for this CAS. Extraction depends on page accessibility.",
            source="direct_supplier_link",
            supplier_hint=name,
        )
        for name, template in templates
    ]


def serpapi_search(
    queries: Iterable[str],
    api_key: str,
    max_results_per_query: int = 8,
    timeout: int = 20,
) -> list[SearchResult]:
    if not api_key:
        return []

    results: list[SearchResult] = []
    seen_urls: set[str] = set()
    endpoint = "https://serpapi.com/search.json"

    for query in queries:
        params = {"engine": "google", "q": query, "api_key": api_key, "num": max_results_per_query}
        try:
            response = requests.get(endpoint, params=params, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            continue

        for item in payload.get("organic_results", [])[:max_results_per_query]:
            url = item.get("link") or ""
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append(
                SearchResult(
                    title=item.get("title") or "Untitled search result",
                    url=url,
                    snippet=item.get("snippet") or "",
                    source="serpapi",
                    supplier_hint=supplier_hint_from_url(url),
                )
            )
    return results


def filter_likely_supplier_results(results: list[SearchResult]) -> list[SearchResult]:
    filtered: list[SearchResult] = []
    seen: set[str] = set()
    for result in results:
        if result.url in seen:
            continue
        seen.add(result.url)
        haystack = f"{result.title} {result.url} {result.snippet}".lower()
        if any(domain in haystack for domain in DEFAULT_SUPPLIER_DOMAINS):
            filtered.append(result)
            continue
        if any(term in haystack for term in ["supplier", "price", "quote", "buy", "catalog", "chemical", "cas"]):
            filtered.append(result)
    return filtered


_PRODUCT_HINT_RE = re.compile(r"(product|catalog|item|sku|compound|chemical|shop|store|/p/|/pd/|details|order|cart)", re.I)
_BAD_LINK_RE = re.compile(
    r"(privacy|terms|basket|login|signin|register|contact|about|careers|linkedin|facebook|twitter|youtube|instagram|cookie|pdf|orders$|order-status|quick-order|promotions|sustainable|all-product-categories)",
    re.I,
)


def _same_domain(url_a: str, url_b: str) -> bool:
    try:
        a = urlparse(url_a).netloc.replace("www.", "")
        b = urlparse(url_b).netloc.replace("www.", "")
        return a and b and (a == b or a.endswith("." + b) or b.endswith("." + a))
    except Exception:
        return False


def _clean_short(text: str, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:limit]


def _node_context(a_tag, limit: int = 1500) -> str:
    """Return a product-card style context around an anchor."""
    contexts = []
    for parent in [a_tag, a_tag.parent, a_tag.find_parent("li"), a_tag.find_parent("tr"), a_tag.find_parent("div")]:
        if parent is None:
            continue
        txt = parent.get_text(" ", strip=True)
        if txt and txt not in contexts:
            contexts.append(txt)
    return _clean_short(" | ".join(contexts), limit)


def _link_score(href: str, text: str, context: str, cas_number: str) -> int:
    hay = f"{href} {text} {context}".lower()
    score = 0
    if cas_number.lower() in hay:
        score += 70
    if _PRODUCT_HINT_RE.search(hay):
        score += 15
    if any(term in hay for term in ["price", "pricing", "$", "pack", "size", "purity", "assay", "cas"]):
        score += 10
    if _BAD_LINK_RE.search(hay):
        score -= 80
    # Strong penalty for generic navigation links even on relevant pages.
    if len(text.strip()) < 3 and cas_number.lower() not in href.lower():
        score -= 20
    return score


def discover_product_links_from_page(result: SearchResult, cas_number: str, timeout: int = 12, max_links: int = 8) -> list[SearchResult]:
    """Open a supplier/search page and pull only strong product-detail candidates.

    v5 change: generic links are no longer expanded. A candidate must have CAS in the
    URL/text/card context OR a strong product/price/pack signal in the same card.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CAS-Sourcing-MVP/5.0; procurement research; human reviewed)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = requests.get(result.url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    candidates: list[tuple[int, SearchResult]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(resp.url, a.get("href", ""))
        if not href.startswith("http") or href in seen:
            continue
        if not _same_domain(resp.url, href):
            continue
        text = _clean_short(a.get_text(" ", strip=True))
        context = _node_context(a)
        score = _link_score(href, text, context, cas_number)
        # Require a meaningful product candidate. This prevents false rows like Order Status or Earth Days.
        if score < 70:
            continue
        seen.add(href)
        candidates.append((score, SearchResult(
            title=text or result.title,
            url=href,
            snippet=f"Expanded from {result.url}. Context: {context[:500]}",
            source="expanded_product_link_v5",
            supplier_hint=result.supplier_hint or supplier_hint_from_url(result.url),
        )))

    candidates.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in candidates[:max_links]]
