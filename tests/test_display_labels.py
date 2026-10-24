"""Server-written labels read the way the web writes them, from one shared word list."""

from shared.vocabulary import attribute_label, display_label


def test_a_variable_is_named_in_sentence_case_with_its_acronyms() -> None:
    assert attribute_label("vaccine.duration_of_protection") == "Duration of protection"
    assert attribute_label("vaccine.cogs") == "COGS"
    assert attribute_label("drug.who_prequalification") == "WHO prequalification"


def test_a_configuration_key_is_named_in_title_case_with_its_acronyms() -> None:
    assert display_label("respiratory_syncytial_virus") == "Respiratory Syncytial Virus"
    assert display_label("hiv") == "HIV"
    assert display_label("itpp") == "iTPP"
