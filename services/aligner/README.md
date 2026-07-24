# Aligner

Builds a traceable comparison between two product-development documents. The
reference artifact supplies the commitments expected to carry forward; the
comparison artifact is the later or downstream document being checked.

## Boundary

Aligner answers one question: what was preserved, changed, contradicted,
omitted, or newly introduced across the two documents? It does not grade
document quality, search external evidence, estimate feasibility, or assign
investment risk.

## Pipeline

```text
two source documents
→ Chunker parse + section mapping (concurrent)
→ explicit AlignmentUnits (concurrent, bounded batches)
→ reference-to-comparison links (bounded batches)
→ deterministic missing/introduced completion and counts
```

Both documents use Chunker's public `(org, source_type, intervention_class)`
configuration contract. The shared indication and all document identities are
retained as result provenance.

## Controlled semantics

Units use exactly one type from `target`, `activity`, `milestone`, `requirement`,
`dependency`, or `risk_response`. Links use exactly one relation from `aligned`,
`modified`, `conflict`, `missing`, or `introduced`. Human-owned definitions and
document-role framing live in `configs/alignment.yaml` and travel with the
result so saved artifacts remain self-describing.

Every unit cites exact source block IDs. Code rejects invented IDs and labels,
fills any reference unit omitted by the model as `missing`, derives
`introduced` from comparison units that were never linked, and calculates the
summary counts. Images are passed to extraction with their exact block IDs.
Semantic unit IDs do not change when duplicate source occurrences add more
provenance. Before a result leaves the service, a deterministic integrity check
verifies document ownership, unit/link lineage, exhaustive reference coverage,
introduced-unit completion, and summary counts.
Structurally invalid extraction/linking responses fail the run after one retry;
invented labels or lineage are never converted into apparently valid results.
Valid linking responses may omit a reference unit, which is deliberately and
deterministically completed as `missing` by the service contract after one
attempt to recover a complete response.

## Public contract

Consumers import configuration, models, serialization, and `run_pipeline` only
from `services.aligner`. Aligner imports Chunker only through
`services.chunker.__init__` and remains stateless.
