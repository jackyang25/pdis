"""One declaration per model prompt Aligner sends, for publication and testing.

Empty, because Aligner sends none: its analysis stages were removed and the
pipeline now only parses. The slot stays so the reference generator, the drift
test, and the documentation page need no per-tool special case for a suite member
that is between designs - `generate_prompt_reference` iterates every tool's
catalog and publishes nothing for this one.

When a stage is added it declares its prompt here, in the same shape the other
three tools use.
"""

from __future__ import annotations

from shared.prompt_catalog import CatalogEntry

TOOL = "aligner"

PROMPT_CATALOG: tuple[CatalogEntry, ...] = ()
