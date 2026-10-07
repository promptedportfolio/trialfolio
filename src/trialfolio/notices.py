"""The license's identity, and the notices every report carries (docs/disclaimers.md; LICENSE).

The texts here must match docs/disclaimers.md and LICENSE's Appendix A word for word, and a
contract test checks that they do. Changing the full notice or the concise notice makes a new
notice version (DSC-09), so `NOTICE_VERSION` changes with them. The Portfolio123 data statement
isn't part of either notice, so changing it doesn't (DSC-06).
"""

from typing import Final

LICENSE_NAME: Final = "Nathan Slaughter Personal Research License"
LICENSE_ID: Final = "LicenseRef-NSPRL-1.1"
NOTICE_VERSION: Final = "1.0"

FULL_NOTICE: Final = (
    (
        "This software, its documentation, examples, analyses, and outputs are provided for general"
        " research and informational purposes. They do not constitute personalized investment,"
        " financial, legal, accounting, or tax advice, an offer or solicitation concerning any"
        " security, or a recommendation to buy, sell, hold, or apply any investment strategy. Use of"
        " the software does not itself establish an advisory, fiduciary, brokerage, or client"
        " relationship with Nathan Slaughter or the project's contributors."
    ),
    (
        "Historical, hypothetical, simulated, and backtested results are not actual trading results"
        " unless expressly identified and supported as such. They depend on data, assumptions,"
        " modeling choices, and historical conditions and may be affected by hindsight, selection"
        " bias, overfitting, incomplete data, revisions, liquidity constraints, and costs or"
        " execution effects that are omitted or inaccurately modeled. Statistical significance does"
        " not establish future profitability or practical tradability."
    ),
    (
        "No result, ranking, score, comparison, example, or statement represents or promises that"
        " any person could or will realize financial gains, outperform a benchmark, avoid losses, or"
        " obtain similar results by investing in any security or applying any strategy. Past or"
        " simulated performance is not a reliable assurance of future results. Investments can lose"
        " some or all of their value; leveraged positions may produce losses beyond the initial"
        " capital."
    ),
    (
        "Users are responsible for independently evaluating information, obtaining appropriate"
        " professional advice, complying with applicable law and third-party terms, and making their"
        " own decisions. Nathan Slaughter does not undertake through this software to assess any"
        " user's financial situation, suitability, objectives, or tolerance for loss."
    ),
)
"""The full research and financial-result notice (DSC-01), by paragraph."""

CONCISE_NOTICE: Final = (
    "Research output only. Backtested and hypothetical results do not represent achievable"
    " returns. No financial gain, future performance, suitability, or protection from loss is"
    " represented or promised. This report is not personalized investment advice. See the full"
    " license and research limitations."
)
"""The concise report notice (DSC-02). A report may be shared only with it intact (D-07)."""

CONCISE_NOTICE_LINK: Final = "the full license and research limitations"
"""The words of the concise notice that a report links to the full notice (DSC-03)."""

PORTFOLIO123_DATA_LABEL: Final = "Portfolio123 data."
PORTFOLIO123_DATA_STATEMENT: Final = (
    "Trial Folio's license grants no rights to Portfolio123 data. Your use of any Portfolio123"
    " data in this report, including sharing the report, is governed by Portfolio123's terms,"
    " and you're responsible for following them. Sharing it publicly may need Portfolio123's"
    " consent."
)
"""The Portfolio123 data statement every report carries in its closing section, after its label
(DSC-06, D-21)."""

PORTFOLIO123_TERMS_LINK: Final = "Portfolio123's terms"
"""The words of the data statement that link to Portfolio123's terms."""

PORTFOLIO123_TERMS_URL: Final = "https://www.portfolio123.com/legal"
"""Portfolio123's terms, which DSC-10 cites: one of a report's two outside links (D-21)."""


def license_url(trialfolio_version: str) -> str:
    """The LICENSE published with a Trial Folio version, at its release tag: a report's other
    outside link (D-21). It works once the version is tagged."""
    return f"https://github.com/promptedportfolio/trialfolio/blob/v{trialfolio_version}/LICENSE"
