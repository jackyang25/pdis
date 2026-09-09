# Tool inputs

Sharing follows responsibility, not a distinction between default and bespoke
fields. A tool chooses its field order; shared controls do not create separate
visual groups.

| Responsibility | Owner |
| --- | --- |
| Field layout, labels, help associations, text/date/select presentation | `ui/config-field.tsx` |
| Context and document-type catalog loading, caching, tool-support filtering | `../lib/use-configuration-catalog.ts` |
| Context and document-type selector meaning, dependent-choice resets | `configuration-fields.tsx` |
| Configuration/upload/run layout | `run-panel.tsx` |
| Field order, local parameters, validation, request assembly | Each tool's `../app/<tool>/page.tsx` |

`ConfigurationShell` owns one responsive `ConfigFieldGrid`. `ContextFields` and
`SourceTypeField` supply fields without nested grids or separators. The
`ConfigurationFields` preset combines these for a single-document tool.
`ConfigField` names one control and associates its optional `note`; compound
controls must name their individual inputs explicitly.

For long option lists, `ConfigSelect.searchLabel` enables the shared searchable
picker. Indication opts in; short configuration lists keep the standard selector.
Filtering is local to displayed labels and never changes keys or commits typed
text. Selection, empty results, keyboard navigation and focus restoration live in
`ui/searchable-select.tsx`, composed with the existing popover primitive.

Organization, intervention class, document type and stage gate options reflect
implemented configurations. Indication is different: `shared/indications.yaml`
supplies one curated context list for every supported class, not a disease-specific
support matrix. Add MeSH-aligned canonical keys and reviewed citations following
the [naming guide](../../docs/indication-vocabulary.md); the same key is stored with
results and converted to words for downstream prompts and searches. Archivist
continues to offer only indications present in its corpus.

Use `ConfigSectionHeading` for reader-facing sections (Context, Document selection,
Run options), within the one field grid—not nested layouts or shared/bespoke groups.
`ConfigField.help` places supplementary guidance in a labelled, keyboard-accessible
popover beside the field label. `ConfigHelp` keeps essential instructions, caveats,
and unavailability reasons visible beneath the control. Compound fields use the same
`ConfigFieldHelp` affordance. `ConfigChip` shares selection styling, not selection rules.

`RunPanel` owns uploads, the secondary Import result picker (`onImport`), and the run
action directly below the uploads, independent of the configuration rail's height.
Pages retain saved-result parsing and compatibility. The panel explains empty document
collections; tools supply a more specific next-step instruction where needed.

`RunPanel.documentFormats` selects one capability from `lib/document-formats.ts`
for picker acceptance, drag/drop validation, format hints, and limitations.
The default remains DOCX/PPTX. Screener opts into PDF text extraction; the panel
does not branch on tool names. Parser-authored result limitations render through
`DocumentExtractionNotice`, including after saved-result import.

## Tool composition

| Tool | Shared selectors | Tool-owned inputs |
| --- | --- | --- |
| Chunker | Single-document preset | Document upload |
| Inspector | Single-document preset | Document upload |
| Scout | Context and document type | Publication date bound, document upload |
| Aligner | Context and repeated document types | Document collection and configured comparison preview |
| Screener | Context | Stage gate and document collection |
| Searcher | Presentation primitives, wide field grid | Query, search facets, named subjects and sources |
| Archivist | Existing shared UI primitives | Corpus filters and archive query action |
| Ask | Workspace conversation controls | Conversation and attached workspace material |

Searcher search terms and Archivist corpus filters are not document configuration
selectors, even when their labels resemble context fields. Ask is a conversation,
not a document run form. Their behavior stays with those features.

## Adding an input

Use a presentation primitive for a new local parameter and keep its state and
request mapping on the tool page. Reuse a domain selector only when its meaning,
options and reset rules are the same. Move genuinely shared mechanics to their
own module when a second consumer needs them; do not build a universal form
schema to accommodate unrelated behavior. Result presentation and backend
pipeline contracts are separate from this input composition.
