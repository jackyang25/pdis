# Aligner

Trace commitments and changes between a reference and comparison document.

## Background

Aligner reports what was preserved, modified, contradicted, omitted, or newly
introduced. It does not grade either document, search external evidence, assign
feasibility, or estimate investment risk.

## Usage

Import `run_pipeline`, `load_config`, public result models, and serializers from
`services.aligner`.

## Contract

| Direction | Value |
|---|---|
| Input | Two documents, their source types, shared product context, config, and an injected model client |
| Output | Two unit ledgers, traceable links, and deterministic relation counts |

Units use the closed `target`, `activity`, `milestone`, `requirement`,
`dependency`, and `risk_response` vocabulary. Relations are `aligned`,
`modified`, `conflict`, `missing`, or `introduced`. Every unit and link retains
exact source block IDs; code derives omissions, additions, and counts.

## Development

Shared unit and relation definitions live in `configs/alignment.yaml`. Aligner
uses Chunker through its public package and keeps document-type differences in
configuration rather than pipeline branches.
