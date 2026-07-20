"""UniProtKB protein retrieval via ToolUniverse."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from ..models import (
    Finding,
    RetrievalIntent,
    SearchRequest,
    SearchRuntime,
    SourceAttribution,
    SourceSpec,
)
from .literature import active_tracks
from .planning import request_lineage
from .tooluniverse_records import (
    TOOLUNIVERSE_INTEGRATION,
    relevant_excerpt,
    result_records,
    run_tool,
    text,
)

SEARCH_TOOL = "UniProt_search"
MAX_RESULTS = 10
ENTITY_TYPES = ("antigen", "biomarker", "gene", "protein")


class UniProtSource:
    spec = SourceSpec(
        key="uniprot",
        label="UniProtKB",
        worker_limit=4,
        default_enabled=False,
        integration_key=TOOLUNIVERSE_INTEGRATION,
        operations=(SEARCH_TOOL,),
        evidence_domains=("biological",),
        required_entity_types=ENTITY_TYPES,
        attribution=SourceAttribution(
            label="UniProt Consortium",
            url="https://www.uniprot.org/",
            prefix="Protein data provided by",
        ),
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        queries = list(intent.queries)
        intent_ids, input_queries, document_refs = request_lineage(queries)
        entities = list(
            dict.fromkeys(
                entity
                for entity in intent.entities
                if entity.entity_type in ENTITY_TYPES
            )
        )
        return [
            SearchRequest(
                scope_ref=intent.scope_ref,
                source=self.spec.key,
                query=f"protein:{entity.name}",
                tracks=tuple(active_tracks(intent)),
                document_refs=document_refs,
                intent_ids=intent_ids,
                input_queries=input_queries,
                connector=TOOLUNIVERSE_INTEGRATION,
                operation=SEARCH_TOOL,
                options=(("entity_name", entity.name), ("limit", str(MAX_RESULTS))),
            )
            for entity in entities[:6]
        ]

    def search(
        self,
        request: SearchRequest,
        runtime: SearchRuntime,
        *,
        max_tokens: int,
        max_uses: int,
    ) -> list[Finding]:
        result = run_tool(
            runtime,
            SEARCH_TOOL,
            {"query": request.option("entity_name"), "limit": MAX_RESULTS},
        )
        retrieved_at = datetime.now(timezone.utc)
        findings: list[Finding] = []
        for record in result_records(result, "results")[:MAX_RESULTS]:
            accession = text(record.get("accession"))
            if not accession:
                continue
            findings.append(
                Finding(
                    url=(
                        "https://www.uniprot.org/uniprotkb/"
                        f"{quote(accession)}/entry"
                    ),
                    title=text(record.get("protein_name")) or accession,
                    query=request.query,
                    retrieved_at=retrieved_at,
                    excerpt=relevant_excerpt(
                        record,
                        (
                            ("gene_names", "Gene names"),
                            ("organism", "Organism"),
                            ("length", "Sequence length"),
                            ("id", "Entry name"),
                        ),
                        request,
                    ),
                    source=self.spec.key,
                )
            )
        return findings
