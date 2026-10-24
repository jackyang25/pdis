"""Which source record a measurement's passage belongs to.

The identity matters beyond deduplication: evidence-unit deduplication counts records,
and `calibrationStatus` will not report a verified basis unless every admitted
measurement is identified by a provider identifier. It used to be read out of URLs and
titles by a list of patterns - a DOI anywhere in a title, a PubMed path, a DailyMed query
string - and every new lane needed a new pattern. Searcher now states identity on the
finding itself (`record_key`, `identifiers`), so this reads that and nothing else.
"""

import unittest
from datetime import datetime

from services.searcher import Finding
from services.scout.stages.conformity import _record_identities


def finding(*, url: str, record_key: str = "", **identifiers: str) -> Finding:
    return Finding(
        url=url, title="A title with DOI 10.1038/s41598-017-05453-3 in it", query="",
        retrieved_at=datetime(2026, 1, 1), record_key=record_key, identifiers=identifiers,
    )


class RecordIdentityTests(unittest.TestCase):
    def test_a_cross_lane_identifier_names_the_record(self):
        [(key, status)] = _record_identities([
            finding(url="https://pubmed.ncbi.nlm.nih.gov/28710351/", record_key="pubmed:28710351",
                    pmid="28710351", doi="10.1038/s41598-017-05453-3"),
        ])
        self.assertEqual((key, status), ("doi:10.1038/s41598-017-05453-3", "canonical"))

    def test_the_same_paper_from_two_lanes_is_one_record(self):
        """Joined by a shared identifier, and named by the strongest any of them states."""
        keys = _record_identities([
            finding(url="https://pubmed.ncbi.nlm.nih.gov/28710351/", record_key="pubmed:28710351",
                    pmid="28710351"),
            finding(url="https://europepmc.org/article/MED/28710351", record_key="europepmc:MED/28710351",
                    pmid="28710351", doi="10.1038/s41598-017-05453-3"),
        ])
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(keys[0], ("doi:10.1038/s41598-017-05453-3", "canonical"))

    def test_a_lane_record_id_is_canonical_without_a_cross_lane_identifier(self):
        [(key, status)] = _record_identities([
            finding(url="https://dailymed.nlm.nih.gov/x", record_key="fda:label:abc"),
        ])
        self.assertEqual((key, status), ("fda:label:abc", "canonical"))

    def test_identity_is_never_read_out_of_a_title(self):
        """The title carries a DOI; the lane stated none, so the page is the identity."""
        [(key, status)] = _record_identities([finding(url="https://example.org/a")])
        self.assertEqual((key, status), ("url:https://example.org/a", "url_fallback"))

    def test_different_papers_stay_different(self):
        first, second = _record_identities([
            finding(url="https://doi.org/a", doi="10.1038/s41598-017-05453-3"),
            finding(url="https://doi.org/b", doi="10.1007/s00228-020-02943-8"),
        ])
        self.assertNotEqual(first, second)

    def test_two_records_sharing_a_page_stay_two(self):
        """FAERS counts for two reactions share one page and are two records."""
        first, second = _record_identities([
            finding(url="https://api.fda.gov/x", record_key="fda_safety:faers:a:fever"),
            finding(url="https://api.fda.gov/x", record_key="fda_safety:faers:a:rash"),
        ])
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
