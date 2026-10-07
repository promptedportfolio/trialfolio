"""The notices a report carries match the documents that own them, word for word: the full notice
and the concise notice in docs/disclaimers.md (DSC-01, DSC-02) and LICENSE's Appendix A, the
Portfolio123 data statement (DSC-06), the license's name, version, and identifier in LICENSE,
which agree (D-27), the notice version, and the two outside links docs/contracts.md gives a report.

Traces to R01-AC13 (the report's notices, license name, identifier, and notice version) and to
DSC-09 (a notice's text changes only with its version) and LIC-11.
"""

import re
from pathlib import Path

from trialfolio.notices import (
    CONCISE_NOTICE,
    CONCISE_NOTICE_LINK,
    FULL_NOTICE,
    LICENSE_ID,
    LICENSE_NAME,
    NOTICE_VERSION,
    PORTFOLIO123_DATA_LABEL,
    PORTFOLIO123_DATA_STATEMENT,
    PORTFOLIO123_TERMS_LINK,
    PORTFOLIO123_TERMS_URL,
    license_url,
)

ROOT = Path(__file__).resolve().parents[2]
DISCLAIMERS = (ROOT / "docs" / "disclaimers.md").read_text(encoding="utf-8")
LICENSE = (ROOT / "LICENSE").read_text(encoding="utf-8")
CONTRACTS = (ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")


def section(text: str, start: str, end: str) -> str:
    return text[text.index(start) : text.index(end, text.index(start))]


def quoted_paragraphs(markdown: str) -> list[str]:
    """The paragraphs of each block quote in `markdown`, with their `>` markers removed."""
    paragraphs: list[str] = []
    current: list[str] = []
    for line in [*markdown.splitlines(), ""]:
        if line.startswith(">") and line.removeprefix(">").strip():
            current.append(line.removeprefix(">").strip())
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    return paragraphs


def unwrapped_paragraphs(text: str) -> list[str]:
    """The paragraphs of plain text wrapped at a fixed width, each on one line."""
    return [" ".join(block.split()) for block in text.strip().split("\n\n")]


def test_the_full_notice_is_dsc_01_and_licenses_appendix_a_part_1() -> None:
    documented = quoted_paragraphs(section(DISCLAIMERS, "### DSC-01", "### DSC-02"))
    appendix = unwrapped_paragraphs(section(LICENSE, "Part 1. Full notice", "Part 2."))

    assert list(FULL_NOTICE) == documented
    assert ["Part 1. Full notice", *FULL_NOTICE] == appendix


def test_the_concise_notice_is_dsc_02_and_licenses_appendix_a_part_2() -> None:
    (documented,) = quoted_paragraphs(section(DISCLAIMERS, "### DSC-02", "## Placement"))
    appendix = unwrapped_paragraphs(LICENSE[LICENSE.index("Part 2. Concise report notice") :])

    assert documented == CONCISE_NOTICE
    assert appendix == ["Part 2. Concise report notice", CONCISE_NOTICE]
    assert CONCISE_NOTICE.endswith(f"{CONCISE_NOTICE_LINK}.")


def test_the_portfolio123_data_statement_is_dsc_06s() -> None:
    statements = [
        paragraph
        for paragraph in quoted_paragraphs(section(DISCLAIMERS, "### DSC-06", "### DSC-10"))
        if paragraph.startswith("**Portfolio123 data.**")
    ]

    assert statements == [f"**{PORTFOLIO123_DATA_LABEL}** {PORTFOLIO123_DATA_STATEMENT}"]
    assert PORTFOLIO123_DATA_STATEMENT.count(PORTFOLIO123_TERMS_LINK) == 1


def test_the_license_name_identifier_and_notice_version_are_licenses_and_the_disclaimers() -> None:
    lines = LICENSE.splitlines()

    assert lines[0] == LICENSE_NAME
    assert lines[1] == f"Version {LICENSE_ID.removeprefix('LicenseRef-NSPRL-')}"
    assert f"License identifier: {LICENSE_ID}" in lines[:5]
    assert f"**Notice version:** {NOTICE_VERSION}." in DISCLAIMERS
    assert f"`{LICENSE_ID}`" in DISCLAIMERS
    assert (
        f"Appendix A. Research and financial-result notice (Notice version {NOTICE_VERSION})"
        in (LICENSE)
    )


def test_the_outside_links_are_the_two_docs_contracts_gives_a_report() -> None:
    reports = section(CONTRACTS, "## Reports", "## CLI behavior")
    links = set(re.findall(r"`(https://[^`]+)`", reports))

    assert links == {
        "https://github.com/promptedportfolio/trialfolio/blob/v<version>/LICENSE",
        PORTFOLIO123_TERMS_URL,
    }
    assert license_url("0.1.0") == (
        "https://github.com/promptedportfolio/trialfolio/blob/v0.1.0/LICENSE"
    )
