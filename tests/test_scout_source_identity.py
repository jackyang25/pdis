"""How a cited source is fingerprinted for deduplication.

The identity is not looked up anywhere. It is read off what the connector already returned,
and its only job is to let two entries for the same paper collapse into one. It matters
beyond deduplication for one reason: `calibrationStatus` will not report a verified basis
unless every admitted measurement is canonical, so a missed identifier caps a cohort.

The gap these tests close: a DOI was only recognised in a `doi.org` link. Connectors return a
paper as its PubMed or publisher URL and put the DOI in the title, so on a real run 40 of 64
measurements fell through to a title hash while carrying a DOI the whole time.
"""

import unittest

from services.scout.models import Finding
from services.scout.stages.conformity import _source_record_identity


def finding(title: str = "", url: str = "") -> Finding:
    return Finding(title=title, url=url, excerpt="", query="", retrieved_at="2026-01-01")


class SourceRecordIdentityTests(unittest.TestCase):
    def test_doi_in_the_title_is_an_identifier(self):
        """The real case: a PubMed link whose title carries the DOI."""
        _, status = _source_record_identity(
            finding(
                title="Combination therapy for tuberculosis. - Sci Rep - DOI: 10.1038/s41598-017-05453-3",
                url="https://pubmed.ncbi.nlm.nih.gov/28710351/",
            )
        )
        self.assertEqual(status, "canonical")

    def test_the_same_paper_reached_two_ways_gets_one_key(self):
        """The point of the fingerprint. A doi.org link and a publisher link are one paper."""
        by_doi, _ = _source_record_identity(finding(url="https://doi.org/10.1038/s41598-017-05453-3"))
        by_title, _ = _source_record_identity(
            finding(
                title="Combination therapy. DOI: 10.1038/s41598-017-05453-3",
                url="https://www.nature.com/articles/s41598-017-05453-3",
            )
        )
        self.assertEqual(by_doi, by_title)

    def test_trailing_punctuation_does_not_make_a_second_key(self):
        """A DOI at the end of a sentence collects the full stop."""
        plain, _ = _source_record_identity(finding(title="x DOI: 10.1038/s41598-017-05453-3"))
        stopped, _ = _source_record_identity(finding(title="x DOI: 10.1038/s41598-017-05453-3."))
        self.assertEqual(plain, stopped)

    def test_a_pubmed_link_is_an_identifier_on_its_own(self):
        key, status = _source_record_identity(
            finding(title="A paper with no doi in its title", url="https://pubmed.ncbi.nlm.nih.gov/28710351/")
        )
        self.assertEqual(status, "canonical")
        self.assertEqual(key, "pmid:28710351")

    def test_a_bare_number_in_a_title_is_not_a_pubmed_id(self):
        """Read from the host and path only. Titles are full of numbers."""
        _, status = _source_record_identity(
            finding(title="28710351 patients were enrolled", url="https://example.org/report")
        )
        self.assertNotEqual(status, "canonical")

    def test_a_trial_registration_still_wins_where_there_is_no_doi(self):
        key, status = _source_record_identity(
            finding(title="A trial NCT01234567", url="https://clinicaltrials.gov/study/NCT01234567")
        )
        self.assertEqual(status, "canonical")
        self.assertEqual(key, "nct:nct01234567")

    def test_a_record_id_from_the_connector_is_preferred(self):
        """Nothing is inferred when the connector already said what the record is."""
        item = finding(title="DOI: 10.1038/s41598-017-05453-3", url="https://doi.org/10.1038/x")
        item.development_records = [
            type("R", (), {"record_type": "trial", "record_id": "NCT01234567"})()
        ]
        key, status = _source_record_identity(item)
        self.assertEqual(status, "canonical")
        self.assertEqual(key, "trial:nct01234567")

    def test_a_pmc_article_is_an_identifier(self):
        key, status = _source_record_identity(
            finding(title="A paper", url="https://pmc.ncbi.nlm.nih.gov/articles/PMC9360445/")
        )
        self.assertEqual(status, "canonical")
        self.assertEqual(key, "pmc:pmc9360445")

    def test_a_bookshelf_record_is_an_identifier(self):
        key, status = _source_record_identity(
            finding(title="A chapter", url="https://www.ncbi.nlm.nih.gov/books/NBK588567/")
        )
        self.assertEqual(status, "canonical")
        self.assertEqual(key, "nbk:nbk588567")

    def test_a_dailymed_set_id_is_read_from_the_query(self):
        """The set id is the label's identity across its revisions, and it is not in the path."""
        key, status = _source_record_identity(
            finding(
                title="Some drug label",
                url="https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=fd12cd86-bbb2-4a3d-81e3-6b46e5f11e37",
            )
        )
        self.assertEqual(status, "canonical")
        self.assertEqual(key, "setid:fd12cd86-bbb2-4a3d-81e3-6b46e5f11e37")

    def test_an_eu_trial_number_is_an_identifier(self):
        key, status = _source_record_identity(
            finding(title="A trial", url="https://euclinicaltrials.eu/ctis-public/view/2023-509075-17-00")
        )
        self.assertEqual(status, "canonical")
        self.assertEqual(key, "euct:2023-509075-17-00")

    def test_a_who_document_is_left_to_its_title(self):
        """Deliberate. One WHO guideline is published under three hosts with three different
        identifiers, so reading them would keep three copies of one document apart. The title
        hash merges them, which is the answer that serves deduplication."""
        for url in (
            "https://www.who.int/publications/i/item/9789240107243",
            "https://iris.who.int/bitstream/handle/10665/378536/9789240096196-eng.pdf",
            "https://tbksp.who.int/en/node/2178",
        ):
            _, status = _source_record_identity(
                finding(title="WHO consolidated guidelines on tuberculosis treatment", url=url)
            )
            self.assertEqual(status, "title_fallback", url)

    def test_one_who_document_under_three_hosts_gets_one_key(self):
        """The consequence of the decision above, stated as the behaviour it buys."""
        title = "WHO consolidated guidelines on tuberculosis treatment"
        keys = {
            _source_record_identity(finding(title=title, url=url))[0]
            for url in (
                "https://www.who.int/publications/i/item/9789240107243",
                "https://iris.who.int/bitstream/handle/10665/378536/9789240096196-eng.pdf",
                "https://tbksp.who.int/en/node/2178",
            )
        }
        self.assertEqual(len(keys), 1)

    def test_a_title_with_no_identifier_still_falls_back(self):
        """Unchanged behaviour where there is genuinely nothing to read."""
        _, status = _source_record_identity(
            finding(title="A study of long acting injectables in adults", url="https://example.org/a")
        )
        self.assertEqual(status, "title_fallback")

    def test_no_title_and_no_identifier_falls_back_to_the_link(self):
        _, status = _source_record_identity(finding(title="Untitled", url="https://example.org/a"))
        self.assertEqual(status, "url_fallback")

    def test_two_different_papers_do_not_collide(self):
        first, _ = _source_record_identity(finding(url="https://doi.org/10.1038/s41598-017-05453-3"))
        second, _ = _source_record_identity(finding(url="https://doi.org/10.1007/s00228-020-02943-8"))
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
