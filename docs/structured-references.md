# Structured document references

Document citation schemas use `shared.references.reference_schema` (one ID) or
`reference_array` (several IDs). Services continue to consume canonical string IDs.
`shared.ai.request_structured` owns the provider transport; callers do not encode
or decode references themselves.

Small schemas retain their original string enums and prompts. When the complete
schema exceeds the provider's enum count or string budget, explicitly marked
references become bounded integers. Each field names a request-local lookup table
in the prompt. Tables preserve the complete allowed ID collection, including
separate text and visual domains. Identical domains share a table.

The response is decoded to the exact canonical IDs before service validation.
Invalid numeric references reject the whole reply, invoking the caller's existing
retry or failure policy. There is no unrestricted-string fallback, citation
truncation, evidence selection, or additional model call. Source text, image
labels, verdict enums, line numbers, and saved result shapes are unchanged.

Screener, Inspector, Aligner, Scout's document citations, and priority nominations
use this boundary. Chunker keeps its existing bounded output shards (each reads
the complete document) and shares the same schema-budget predicate. Non-reference
enums are not rewritten. Compact reference fields currently require explicit
object/array paths; references inside unions or definitions fail preflight rather
than guessing which domain applies.

This removes citation-enum limits, not input context, output token, or memory
limits. Offline regressions verify exact round trips, rejected invalid IDs, schema
budgets, and retained evidence. Live model quality still requires representative
document runs; mechanical equivalence does not promise identical model wording.
