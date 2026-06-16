"""Direct NCBI PubMed/PMC retrieval: query -> list[Finding]."""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from ..models import Finding

logger = logging.getLogger(__name__)

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
REQUEST_TIMEOUT_SECONDS = 20
REQUEST_PAUSE_SECONDS = 0.12
MAX_EXCERPT_CHARS = 6000


def search_pubmed(
    query: str,
    *,
    max_results: int = 20,
    api_key: str | None = None,
) -> list[Finding]:
    """Search PubMed and enrich open-access PMC records with full text.

    This backend is deliberately robust: any HTTP/parse/rate-limit problem
    returns no PubMed findings, leaving other search backends unaffected.
    """
    try:
        pmids = _esearch(query, max_results=max_results, api_key=api_key)
        if not pmids:
            return []
        records = _efetch_pubmed(pmids, api_key=api_key)
        pmc_texts = _fetch_pmc_texts(records, api_key=api_key)
    except Exception:
        logger.exception("PubMed retrieval failed for query %r", query)
        return []

    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for record in records:
        pmid = record.get("pmid", "")
        if not pmid:
            continue
        pmcid = record.get("pmcid", "")
        abstract = record.get("abstract", "")
        full_text = pmc_texts.get(pmcid, "") if pmcid else ""
        excerpt = _clean_text(full_text or abstract) or None
        if excerpt and len(excerpt) > MAX_EXCERPT_CHARS:
            excerpt = excerpt[:MAX_EXCERPT_CHARS].rstrip() + "..."
        findings.append(
            Finding(
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                title=record.get("title") or f"PubMed {pmid}",
                query=query,
                retrieved_at=retrieved_at,
                excerpt=excerpt,
                published_at=_parse_pubdate(record.get("pubdate", "")),
                source="pubmed",
            )
        )
    return findings


def _esearch(
    query: str,
    *,
    max_results: int,
    api_key: str | None,
) -> list[str]:
    root = _request_xml(
        "esearch.fcgi",
        {
            "db": "pubmed",
            "term": query,
            "retmax": str(max_results),
            "sort": "relevance",
            "retmode": "xml",
        },
        api_key=api_key,
    )
    return [
        (node.text or "").strip()
        for node in root.findall(".//IdList/Id")
        if (node.text or "").strip()
    ]


def _efetch_pubmed(pmids: list[str], *, api_key: str | None) -> list[dict[str, str]]:
    root = _request_xml(
        "efetch.fcgi",
        {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        },
        api_key=api_key,
    )
    records: list[dict[str, str]] = []
    for article in root.findall(".//PubmedArticle"):
        pmid = _text(article.find(".//MedlineCitation/PMID"))
        title = _text(article.find(".//ArticleTitle"))
        abstract = " ".join(
            _iter_text(node) for node in article.findall(".//Abstract/AbstractText")
        ).strip()
        journal = _text(article.find(".//Journal/Title"))
        pubdate = _pubdate_from_article(article)
        doi = ""
        pmcid = ""
        for id_node in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
            id_type = id_node.attrib.get("IdType", "")
            value = _text(id_node)
            if id_type == "doi":
                doi = value
            elif id_type == "pmc":
                pmcid = value
        title_parts = [part for part in [title, journal] if part]
        if doi:
            title_parts.append(f"DOI: {doi}")
        records.append(
            {
                "pmid": pmid,
                "title": " - ".join(title_parts) if title_parts else f"PubMed {pmid}",
                "abstract": abstract,
                "pubdate": pubdate,
                "doi": doi,
                "pmcid": pmcid,
            }
        )
    return records


def _fetch_pmc_texts(
    records: list[dict[str, str]],
    *,
    api_key: str | None,
) -> dict[str, str]:
    pmcids = [record["pmcid"] for record in records if record.get("pmcid")]
    if not pmcids:
        return {}
    out: dict[str, str] = {}
    for pmcid in pmcids:
        try:
            root = _request_xml(
                "efetch.fcgi",
                {
                    "db": "pmc",
                    "id": pmcid.removeprefix("PMC"),
                    "retmode": "xml",
                },
                api_key=api_key,
            )
        except Exception:
            logger.exception("PMC full-text fetch failed for %s", pmcid)
            continue
        texts = [
            _iter_text(node)
            for node in root.findall(".//body//p")
            if _iter_text(node).strip()
        ]
        if not texts:
            texts = [
                _iter_text(node)
                for node in root.findall(".//abstract//p")
                if _iter_text(node).strip()
            ]
        out[pmcid] = _clean_text(" ".join(texts))
    return out


def _request_xml(
    endpoint: str,
    params: dict[str, str],
    *,
    api_key: str | None,
) -> ET.Element:
    if api_key:
        params["api_key"] = api_key
    url = f"{EUTILS_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    time.sleep(REQUEST_PAUSE_SECONDS)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "pdis-monitor/0.1 (mailto:devnull@example.com)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        logger.exception("NCBI request failed: %s", endpoint)
        raise
    return ET.fromstring(payload)


def _pubdate_from_article(article: ET.Element) -> str:
    pub_date = article.find(".//JournalIssue/PubDate")
    if pub_date is None:
        pub_date = article.find(".//ArticleDate")
    if pub_date is None:
        return ""
    year = _text(pub_date.find("Year"))
    month = _text(pub_date.find("Month"))
    day = _text(pub_date.find("Day"))
    medline = _text(pub_date.find("MedlineDate"))
    return " ".join(part for part in [year, month, day] if part) or medline


def _parse_pubdate(raw: str) -> datetime | None:
    if not raw:
        return None
    parts = raw.replace("-", " ").split()
    if not parts:
        return None
    try:
        year = int(parts[0])
    except ValueError:
        return None
    month = _parse_month(parts[1]) if len(parts) > 1 else 1
    day = 1
    if len(parts) > 2:
        try:
            day = int(parts[2])
        except ValueError:
            day = 1
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return datetime(year, 1, 1, tzinfo=timezone.utc)


def _parse_month(raw: str) -> int:
    months = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    if raw.isdigit():
        value = int(raw)
        return value if 1 <= value <= 12 else 1
    return months.get(raw[:3].lower(), 1)


def _text(node: ET.Element | None) -> str:
    return "" if node is None or node.text is None else node.text.strip()


def _iter_text(node: ET.Element) -> str:
    return "".join(node.itertext()).strip()


def _clean_text(text: str) -> str:
    return " ".join(text.split())
