from services.assistant import knowledge
from services.assistant.agent import TOOLS, _system_prompt


def test_product_knowledge_has_stable_sections_and_search() -> None:
    overview = knowledge.overview()
    matches = knowledge.find("stateless")

    assert "architecture" in overview
    assert "assistant" in overview
    assert "[architecture] Architecture" in knowledge.read(["architecture"])
    assert "Services" in knowledge.read(["architecture"])
    architecture_docs = knowledge.read(["workflows"])
    assert "Inspector: Turns one parsed development document" in architecture_docs
    assert "Source-neutral intents" in architecture_docs
    assert "Bounded navigation loop" in architecture_docs
    assert "architecture" in matches
    scout_docs = knowledge.read(["scout"])
    assert "Linked product fields" in scout_docs
    assert "not synchronized database fields" in scout_docs
    assert "Included comparator cohort" in scout_docs


def test_assistant_exposes_bounded_product_documentation_tools() -> None:
    tool_names = {tool["function"]["name"] for tool in TOOLS}
    prompt = _system_prompt({}, "workspace")

    assert "find_product_docs" in tool_names
    assert "read_product_docs" in tool_names
    assert "PRODUCT DOCUMENTATION MAP" in prompt
    assert "Never present product documentation as evidence" in prompt


def test_unknown_product_knowledge_section_is_explicit() -> None:
    assert "unknown documentation section" in knowledge.read(["missing"])
