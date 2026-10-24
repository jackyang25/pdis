"""Direct NCBI PubMed/PMC retrieval: query -> list[Finding]."""

from __future__ import annotations

import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from ..calls import note_provider_query, note_warning, provider_call
from ..dates import partial_date
from ..errors import RetrievalError
from ..models import Finding, SearchRuntime
from ..transport import fetch, user_agent

logger = logging.getLogger(__name__)

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# Generous: NCBI is usually sub-second, but PMC full-text fetches and extra
# latency (e.g. a corporate tunnel like Cloudflare WARP) can push a call past a
# tight limit. 35s recovers those rare slow-but-valid responses.
REQUEST_TIMEOUT_SECONDS = 35
MAX_EXCERPT_CHARS = 6000
# Full-text PMC fetches per request — each is its own NCBI call, so cap the fan-out.
# Articles beyond this keep their abstract alone.
MAX_PMC_FULLTEXT = 5
#: Registered with NCBI's E-utilities as the calling tool. NCBI asks for `tool` and
#: `email` on every call; the address is sent only when the deployment configured one.
NCBI_TOOL = "pdis"
#: NCBI's quota covers every E-utilities call from one client, whichever lane makes it.
NCBI_RATE_GROUP = "ncbi"
# NCBI rate limits: ~3 req/s without an API key, ~10 req/s with one, per call.
RATE_INTERVAL_NO_KEY = 0.35
RATE_INTERVAL_WITH_KEY = 0.11


def search_pubmed(
    query: str,
    runtime: SearchRuntime,
    *,
    max_results: int,
    published_since: str = "",
) -> list[Finding]:
    """Search PubMed and add the Results section of open-access PMC records.

    Transport/parse failures propagate to the source controller, which records
    a failed outcome without affecting other adapters.
    """
    if not query.strip():
        return []
    pmids = _esearch(
        runtime,
        query,
        max_results=max_results,
        published_since=published_since,
    )
    if not pmids:
        return []
    records = _efetch_pubmed(runtime, pmids)
    results_sections = _fetch_pmc_results(runtime, records)

    retrieved_at = datetime.now(timezone.utc)
    findings: list[Finding] = []
    for record in records:
        pmid = record["pmid"]
        if not pmid:
            continue
        pmcid = record["pmcid"]
        # The abstract states the headline findings; the Results section, where the
        # article declares one, carries the numbers behind them.
        combined = "\n\n".join(
            part
            for part in (record["abstract"], results_sections.get(pmcid, ""))
            if part
        )
        excerpt = _clean_text(combined) or None
        if excerpt and len(excerpt) > MAX_EXCERPT_CHARS:
            excerpt = excerpt[:MAX_EXCERPT_CHARS].rstrip() + "..."
        findings.append(
            Finding(
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                title=record["title"] or f"PubMed {pmid}",
                query=query,
                retrieved_at=retrieved_at,
                excerpt=excerpt,
                published_at=record["published_at"],
                published_precision=record["published_precision"],
                identifiers={
                    "pmid": pmid,
                    "doi": record["doi"],
                    "pmcid": pmcid,
                },
                record_key=f"pubmed:{pmid}",
                source="pubmed",
            )
        )
    return findings


def _esearch(
    runtime: SearchRuntime,
    query: str,
    *,
    max_results: int,
    published_since: str = "",
) -> list[str]:
    """Ask for the window, rather than asking for everything and discarding.

    `mindate` and `datetype` are E-utilities parameters, not query terms, which is the
    whole reason the bound belongs here: putting a year in `term` would match records
    that mention the year, while `datetype=pdat` bounds the ones published in it. The
    ranking is `relevance` within the window, so a narrow window returns the most
    relevant recent work instead of the most relevant work of all time, filtered down.

    NCBI reports how it read the term - its query translation, any phrase it could not
    find and searched without - and those are recorded on the request's outcome, since
    they are the only explanation of a result set that does not match the query asked.
    """
    parameters = {
        "db": "pubmed",
        "term": query,
        "retmax": str(max_results),
        "sort": "relevance",
        "retmode": "xml",
    }
    if published_since:
        parameters.update(
            {
                "datetype": "pdat",
                "mindate": published_since.replace("-", "/"),
                # An open upper bound still needs a value; NCBI reads 3000 as "now".
                "maxdate": "3000",
            }
        )
    root = _request_xml(runtime, "esearch.fcgi", parameters)
    translation = (root.findtext("QueryTranslation") or "").strip()
    if translation:
        note_provider_query(translation)
    for list_name, code in (("WarningList", "provider_warning"), ("ErrorList", "provider_error")):
        for listing in root.findall(list_name):
            for item in listing:
                if item.tag == "OutputMessage":
                    detail = _iter_text(item)
                else:
                    detail = f"{item.tag}: {_iter_text(item)}"
                if detail.strip():
                    note_warning(code, detail)
    return [
        (node.text or "").strip()
        for node in root.findall(".//IdList/Id")
        if (node.text or "").strip()
    ]


def _efetch_pubmed(runtime: SearchRuntime, pmids: list[str]) -> list[dict]:
    root = _request_xml(
        runtime,
        "efetch.fcgi",
        {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        },
    )
    records: list[dict] = []
    for article in root.findall(".//PubmedArticle"):
        pmid = _text(article.find(".//MedlineCitation/PMID"))
        title = _iter_text_or_blank(article.find(".//ArticleTitle"))
        abstract = " ".join(
            _iter_text(node) for node in article.findall(".//Abstract/AbstractText")
        ).strip()
        journal = _text(article.find(".//Journal/Title"))
        doi = ""
        pmcid = ""
        for id_node in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
            id_type = id_node.attrib.get("IdType", "")
            value = _text(id_node)
            if id_type == "doi":
                doi = value
            elif id_type == "pmc":
                pmcid = value
        published_at, precision = _pubdate_from_article(article)
        # Identifiers are carried as identifiers. The DOI used to be appended to the title,
        # and consumers then read it back out with a pattern.
        title_parts = [part for part in [title, journal] if part]
        records.append(
            {
                "pmid": pmid,
                "title": " - ".join(title_parts) if title_parts else f"PubMed {pmid}",
                "abstract": abstract,
                "published_at": published_at,
                "published_precision": precision,
                "doi": doi,
                "pmcid": pmcid,
            }
        )
    return records


def _fetch_pmc_results(runtime: SearchRuntime, records: list[dict]) -> dict[str, str]:
    pmcids = [record["pmcid"] for record in records if record.get("pmcid")]
    out: dict[str, str] = {}
    for pmcid in pmcids[:MAX_PMC_FULLTEXT]:
        try:
            text = _pmc_results_section(runtime, pmcid)
        except RetrievalError as exc:
            # The record keeps its abstract; the outcome says what it is missing.
            note_warning("content_unavailable", f"PMC full text for {pmcid}: {exc}")
            continue
        if text:
            out[pmcid] = text
    return out


def _pmc_results_section(runtime: SearchRuntime, pmcid: str) -> str:
    """Return the text of the article's declared Results section, or blank.

    Read from JATS `sec-type`, the article's own markup for what a section is, and from
    nothing else. The earlier excerpt took the first characters of the body, which in a
    research article is the Introduction: background, not findings. A section titled
    "Results" without the attribute is not guessed at from its heading; the abstract
    remains the excerpt there.
    """
    root = _request_xml(
        runtime,
        "efetch.fcgi",
        {"db": "pmc", "id": pmcid.removeprefix("PMC"), "retmode": "xml"},
    )
    sections = [
        section
        for section in root.findall(".//body/sec")
        if "results" in section.attrib.get("sec-type", "").casefold().split("|")
    ]
    texts = [
        _iter_text(paragraph)
        for section in sections
        for paragraph in section.findall(".//p")
        if _iter_text(paragraph).strip()
    ]
    return _clean_text(" ".join(texts))[:MAX_EXCERPT_CHARS]


def _request_xml(
    runtime: SearchRuntime,
    endpoint: str,
    params: dict[str, str],
) -> ET.Element:
    api_key = runtime.ncbi_api_key or ""
    query = dict(params, tool=NCBI_TOOL)
    if runtime.contact_email:
        query["email"] = runtime.contact_email
    url_params = dict(query, api_key=api_key) if api_key else query
    url = f"{EUTILS_BASE}/{endpoint}?{urllib.parse.urlencode(url_params)}"

    def load() -> bytes:
        return fetch(
            url,
            provider="NCBI E-utilities",
            headers={"User-Agent": user_agent(runtime.contact_email)},
            timeout=REQUEST_TIMEOUT_SECONDS,
            # NCBI's rate-limit body echoes the key it was sent.
            secrets=(api_key,),
        )

    body = provider_call(
        runtime,
        rate_group=NCBI_RATE_GROUP,
        interval_seconds=RATE_INTERVAL_WITH_KEY if api_key else RATE_INTERVAL_NO_KEY,
        operation=endpoint,
        # The key is not part of the question, so it is not part of the memo key.
        arguments=query,
        load=load,
    )
    try:
        return ET.fromstring(body)
    except ET.ParseError as exc:
        raise RetrievalError(
            "NCBI E-utilities", "invalid_response", f"{endpoint} returned malformed XML"
        ) from exc


def _pubdate_from_article(article: ET.Element) -> tuple[datetime | None, str]:
    """The issue date with the precision PubMed states it, else the electronic date.

    The issue date is read first because a window is a lower bound and the issue date is
    the later of the two, which is how PubMed's own `pdat` reads a record too.
    """
    pub_date = article.find(".//JournalIssue/PubDate")
    if pub_date is None:
        pub_date = article.find(".//ArticleDate")
    if pub_date is None:
        return None, ""
    year = _text(pub_date.find("Year"))
    if not year:
        # "2019 Nov-Dec", "1998 Dec-1999 Jan": a span, stated only to its year. The last
        # year it names is the latest the record can be, so a lower bound cannot drop it.
        years = re.findall(r"\b(\d{4})\b", _text(pub_date.find("MedlineDate")))
        return partial_date(int(years[-1])) if years else (None, "")
    if not year.isdigit():
        return None, ""
    month = _parse_month(_text(pub_date.find("Month")))
    day = _text(pub_date.find("Day"))
    if month is None:
        # No month, or a season: stated to the year.
        return partial_date(int(year))
    return partial_date(int(year), month, int(day) if day.isdigit() else None)


def _parse_month(raw: str) -> int | None:
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
        return value if 1 <= value <= 12 else None
    return months.get(raw[:3].lower())


def _text(node: ET.Element | None) -> str:
    return "" if node is None or node.text is None else node.text.strip()


def _iter_text(node: ET.Element) -> str:
    return "".join(node.itertext()).strip()


def _iter_text_or_blank(node: ET.Element | None) -> str:
    return "" if node is None else _iter_text(node)


def _clean_text(text: str) -> str:
    return " ".join(text.split())
