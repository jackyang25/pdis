# Indication naming

`shared/indications.yaml` is the single authored context catalog. It is aligned
to the **NLM MeSH 2026 descriptor release**, not a list of approved indications,
portfolio commitments, or disease-specific tool capabilities.

## Naming rule

Use a readable, natural-order MeSH preferred or entry term. Lowercase it and join
words with underscores for `key`. Prefer explicit names over shorthand; `hiv`
remains because HIV is itself a MeSH heading. Display labels and downstream
search text are derived from that key. Do not store a separate display label or
search spelling, and do not expand queries with terminology synonyms.

Each record cites a descriptor ID, a concept ID within that descriptor, and the
exact NLM entry term. The concept matters: *Cervical Cancer* and *Nipah Virus
Infection* sit within broader descriptors. Citing only the descriptor would lose
that distinction. `mesh.term` is citation metadata, not an alternate runtime name.

Choose the concept, not merely a similar string. A pathogen is not its infection;
a genus is not one species; a symptom is not automatically a diagnosed disorder.
Existing pathogen contexts remain pathogen contexts. For example, `klebsiella`
still means the genus, and `depression` does not assert major depressive disorder.
The supplied document determines more specific scope.

## Explicit exceptions

Five existing contexts have no exact equivalent in the selected descriptor
release. They retain their specific meaning with `match: narrower` and a note:

| Context | Cited MeSH term | Additional local restriction |
| --- | --- | --- |
| Invasive nontyphoidal Salmonella infections | Salmonella Infections | Invasive and non-typhoidal |
| Human African trypanosomiasis | African Trypanosomiasis | Human disease |
| Soil-transmitted helminthiases | Helminthiasis | Soil transmission |
| Acute malnutrition | Malnutrition | Acute; no severity inferred |
| Childhood stunting | Stunting | Children; stunting rather than other growth disorders |

These are **MeSH-aligned local contexts, not exact MeSH terms**. Do not silently
broaden them, relabel acute malnutrition as *Severe Acute Malnutrition*, or remove
coverage to make the mapping count look complete. Any future replacement needs
an explicit scope review.

## Compatibility and ownership

`legacy_keys` records retired spellings only for validating existing Archivist
corpus artifacts. They are not new dropdown options and are never used to rewrite
saved result provenance. Portable tool results already carry their original
context strings; importing them does not require membership in today's picker.
Old results therefore continue to show their old names.

`shared/vocabulary.py` owns catalog reading and validation. The configuration API
publishes only canonical keys, retaining its `list[str]` response. Existing
selectors and service pipelines need no per-indication branches. Archivist filters
continue to reflect its corpus, including historical keys, rather than this list.

## Updating and verifying

1. Review the concept and scope in the [NLM MeSH Browser](https://meshb.nlm.nih.gov/search).
2. Add or amend the record once in the shared catalog. Record a narrower mapping
   explicitly if no exact entry term has the required scope.
3. Keep retired keys for artifact validation; never change old result contents.
4. Download the [official 2026 descriptors](https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc2026.gz)
   and run, from the repository root:

   ```sh
   uv run python -m scripts.check_indication_mesh /path/to/desc2026.gz
   uv run python -m unittest tests.test_indication_vocabulary tests.test_mesh_catalog tests.test_config_contexts
   ```

The offline check verifies descriptor/concept membership, the exact cited term,
and the spelling of canonical keys. It does not establish clinical equivalence
or validate the editorial scope of narrower mappings; those require review.
No NLM download or lookup runs in the application. A future annual MeSH update is
a reviewed catalog change, not an automatic rename of stored results.
