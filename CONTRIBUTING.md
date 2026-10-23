# Contributing to PDIS

For anyone keeping PDIS current: updating rubrics, question banks, configuration, product
documentation and release notes, and deploying the result. Coding agents read it for the
same tasks.

Each task below says which file to edit, what not to touch, and which check proves the
change. Background lives in the linked READMEs and is not repeated here.

## Three rules first

1. **Content is configuration; behaviour is code.** Rubrics, question banks, sources and
   vocabularies are YAML or JSON. If a content change seems to need a Python or TypeScript
   edit, stop and ask — [AGENTS.md](AGENTS.md) treats that as a design error.
2. **Saved results are never rewritten.** A rubric or bank change applies to new runs. Old
   results keep the snapshot they were run with.
3. **`make check` and `git diff --check` pass before merging.** CI runs the same checks.
   A failing test usually guards a rule; read its docstring rather than editing the test.

## Where things live

| To change | Edit | Background |
| --- | --- | --- |
| A template rubric (PDID) | `services/inspector/configs/rubrics/pdid/` | [Inspector](services/inspector/README.md#development) |
| A guideline rubric (ICH, WHO, FDA, EMA) | `services/inspector/configs/rubrics/<authority>/` and `profiles/catalog.yaml` | [Inspector](services/inspector/README.md#profiles-rubrics-and-sources) |
| A stage-gate question bank | `services/screener/configs/bmgf_<gate>.yaml` | [Screener](services/screener/README.md#the-bank) |
| Scout sources, query guidance, institutions, languages | `services/scout/configs/bmgf_<type>_<class>.yaml` | [Scout](services/scout/README.md#development) |
| Fixed TPP attributes | `shared/attributes.yaml` | [Scout](services/scout/README.md) |
| Drafter sources and search guidance | `services/drafter/configs/bmgf_itpp_<class>.yaml` | [Drafter](services/drafter/README.md#configuration) |
| Which documents Aligner compares | `services/aligner/configs/alignment.yaml` | [Aligner](services/aligner/README.md#configuration-is-the-whole-design) |
| The disease / condition list | `shared/indications.yaml` | [Indication naming](docs/indication-vocabulary.md) |
| Product documentation and FAQ | `shared/product_knowledge.json` | [README](README.md#configuration) |
| Assistant skills | `services/assistant/skills/*.md` | [Assistant](services/assistant/README.md) |
| Release notes | `web/lib/releases.ts` | [Deployment](docs/deployment.md#product-versions-and-release-notes) |
| Credentials | `.env` locally, Drone secrets when deployed | [.env.example](.env.example) |

## Common tasks

### Update an existing rubric

1. Edit the rubric file. A section or unit declares `name`, `description`, `optional` and
   `expectations`; guideline sections also cite `source_refs`.
2. If the change alters what is assessed, bump `revision`, set `updated_on` to today as a
   quoted `"YYYY-MM-DD"`, and update the matching revision pin in
   `profiles/catalog.yaml` — all three together. Wording-only changes bump nothing.
3. If the external guideline published a new version, update its entry in `sources`. That
   revision is separate from the PDIS `revision`.
4. Check: `uv run pytest tests -q -k inspector`.

### Add a guideline rubric

1. Copy a sibling file in the same authority folder. Give it a new `id`, `revision: "1.0"`
   and today's `updated_on`.
2. Use `evidence_scope: whole_document`. Guideline section names group requirements; they
   are not headings the document has to contain.
3. Leave out `org`, `source_type` and `intervention_class`. The profile supplies them, and
   the loader rejects a rubric that declares them.
4. Add `{id, revision, definition}` to each profile in `profiles/catalog.yaml` that should
   run it. If it applies only to some products, add `applicability` using an existing fact
   key, or declare a new one under `fact_definitions`.
5. Add the rubric to the coverage table in the [Inspector README](services/inspector/README.md#selected-ich-coverage)
   and write a release note.
6. Check: `uv run pytest tests -q -k inspector`.

### Update a stage-gate question bank

1. Transcribe by hand from the source document. Never paraphrase, merge or round a count:
   a bank holds exactly the questions its source does.
2. Update `mirrors` to the new source version. It is carried onto every result as the
   bank's authority.
3. State `requirement` (`required` or `anticipatory`) on every question. Set `applies_to`
   only where the question text itself names the restriction.
4. Check: `uv run pytest tests -q -k screener`.

### Adjust a Scout configuration

1. Edit `sources`, `query_extraction_guidance`, `priority_institutions` or `languages` in
   the config for that document type and product class.
2. A source key must already be registered in Searcher. Adding a new source is code — an
   adapter — and belongs to the [Searcher README](services/searcher/README.md#development).
3. Check: `uv run pytest tests -q -k scout`.

### Add or rename a disease / condition

Follow [Updating and verifying](docs/indication-vocabulary.md#updating-and-verifying). Each
entry cites a reviewed MeSH descriptor, and the offline check verifies it.

### Update product documentation or the FAQ

1. Edit `shared/product_knowledge.json`. The documentation page and the Assistant both read
   it, so there is no second copy to update.
2. Check: `uv run pytest tests -q -k product_knowledge`.

### Change a prompt

Prompts are code. After editing one, regenerate the published reference, which the
documentation page shows:

```sh
uv run python -m scripts.generate_prompt_reference
```

`tests/test_prompt_reference.py` fails if the committed file is stale.

### Add a document type or health product type

This touches several services that must agree on the same
`(org, source_type, intervention_class)`, so start from each service's
`CONFIG_TEMPLATE.yaml`. `tests/test_config_identity.py` fails when they disagree; read
its docstring first, and ask before merging a first attempt.

### Add a credential

1. Add the variable, without its value, to `.env.example`. `tests/test_env_var_parity.py`
   fails otherwise.
2. Never commit a value. Deployed values are Drone secrets, bound through `__NAME__`
   placeholders in both jobspecs; `tests/test_deploy_secrets.py` and
   `tests/test_jobspec_parity.py` check both.

## Checking a change

| When | Run |
| --- | --- |
| While editing | `uv run pytest tests -q -k <tool>` |
| Before merging | `make check` and `git diff --check` |
| To see it working | `docker compose up --build`, then run the tool on a real document |

Tests do not call models. A rubric or prompt change is only shown to work by running the
tool on a real document.

## Releasing and deploying

1. Add a release note in `web/lib/releases.ts` for any change users will notice, following
   the [release rules](docs/deployment.md#product-versions-and-release-notes).
2. Merging to `main` deploys to acceptance through Drone ([cicd.bmgf.io](https://cicd.bmgf.io)).
   Check the change there.
3. Promote that same build to production:

   ```sh
   drone build promote gatesfoundation/pdis <build> production
   ```

A Drone step that fails pulling an image with a timeout reaching Docker Hub is a network
failure. Restart the build. Infrastructure and capacity are described in
[deployment and releases](docs/deployment.md).

## Stop and ask when

- a content change seems to need a code change;
- a test fails and its docstring does not explain why;
- a change alters a saved result's shape, which needs a version bump in
  `web/lib/result-file.ts`;
- you are unsure whether a rubric or bank change alters what is assessed.

## Keeping sources current

Nothing in the repository can tell that a source has changed. Each file names its source —
`sources` on a guideline rubric, `mirrors` on a PDID rubric or question bank — so a check
starts there.

| Source | Who can check it | Then update |
| --- | --- | --- |
| Public guidelines (ICH, WHO, FDA, EMA) | A coding agent can find the current version online and draft the change | The `sources` entry's revision, and the rubric's `revision` if what is assessed changes |
| MeSH | A coding agent, using the [offline check](docs/indication-vocabulary.md#updating-and-verifying) | `shared/indications.yaml` |
| Foundation templates and question banks (PDID, stage gates) | A person; agents cannot reach foundation resources | `mirrors` with the new version, after transcribing the changes or giving the agent the file |

An agent drafts; a person checks the result against the source before merging, because no
test can.

## Working with a coding agent

Point the agent at the task in this file and at [AGENTS.md](AGENTS.md) for the rules, and
ask it to run the check the task names. AGENTS.md holds the invariants; this file holds
the procedures.
