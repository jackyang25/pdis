# Inspector ICH coverage extension

Goal: add the approved E8(R1), E9/E9(R1), E10, Q8(R2), Q9(R1), and M3(R2)
planning adaptations through the existing peer-rubric contract.

Architecture: authored YAML contains requirements and source locators; the profile
catalog selects reviews. No changes to runtime engines, transport, or result UI.
Implementation remains in the current worktree, uncommitted and unstaged.

1. Read the official source sections; distinguish their scope from PDIS's authored
   adaptation. Keep iTPP expectations aspirational and IPDP expectations strategic.
2. Add `tests/test_inspector_ich_coverage.py` pinning profile selection, M3's explicit
   small-molecule gate, source coverage, and common result-contract behavior.
3. Add ten rubric YAMLs: E8 IPDP; E9 and E10 cTPP/IPDP; Q8 iTPP/cTPP/IPDP;
   Q9 IPDP; M3 IPDP. Q8 starts with drug profiles; clinical guidance covers medicinal
   products. Do not add pharmaceutical guidance to diagnostic/device profiles.
4. Wire `configs/profiles/catalog.yaml`; retain all prior reviews and order, then
   append new reviews. Update exact catalog expectations in existing tests.
5. Document scope and source ownership in the service README and regenerate prompt
   reference data. Run focused and full backend tests, frontend checks, and review
   the authored requirements against their sources before refreshing localhost.

Verification commands use the existing `pdis-api` Docker image with the workspace
mounted at `/workspace`: `python -m unittest tests.test_inspector_ich_coverage
tests.test_inspector_multiple_rubrics -q`, then `python -m unittest discover -s tests -q`.
No provider calls are needed for contract tests; they cannot establish model accuracy.
