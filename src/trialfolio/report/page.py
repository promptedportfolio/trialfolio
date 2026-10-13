"""The report's HTML: the primitives every kind of report is written with, and the page they're
put together into, with the notices every report holds and its only styling.

- `text`, `code`, and `moment` write a value: text Trial Folio didn't write, escaped; the same as
  code; and a moment in UTC.
- `table` and `facts` write a table in its scrolling wrapper, and a description list of terms and
  their values.
- `page` writes the whole document: the head, with the CSS; the header, with the kind of report,
  the title, the concise notice, the report's status, and the contents; the ten sections, each
  numbered and headed; and the closing section, with the Portfolio123 data statement and the full
  notice.

Each writes what the report always wrote, in the same order, so each kind of report keeps its
bytes.
"""

import html
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Final

from trialfolio.display import visible
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

FULL_NOTICE_ID: Final = "full-notice"
"""The `id` of the `<details>` element that holds the full notice."""

_CSS: Final = """\
:root{color-scheme:light dark;--text:#1d232b;--muted:#5b6573;--back:#ffffff;--panel:#f4f5f7;\
--rule:#d5d9df;--mark:#46556b}
@media (prefers-color-scheme:dark){:root{--text:#e3e6ea;--muted:#9aa3ae;--back:#14171b;\
--panel:#1d2127;--rule:#363c45;--mark:#a9b6c8}}
*{box-sizing:border-box}
body{margin:0;background:var(--back);color:var(--text);\
font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.page{max-width:70rem;margin:0 auto;padding:2rem 1rem 4rem}
h1{font-size:1.75rem;line-height:1.25;margin:.25rem 0 1rem}
h2{font-size:1.25rem;margin:2.5rem 0 .75rem;padding-top:1rem;border-top:1px solid var(--rule)}
h3{font-size:1rem;margin:1.5rem 0 .5rem}
p,ul{margin:.5rem 0}
.kind{margin:0;color:var(--muted);font-size:.875rem;letter-spacing:.04em;text-transform:uppercase}
.notice{margin:1rem 0;padding:.75rem 1rem;background:var(--panel);border:1px solid var(--rule);\
border-left:4px solid var(--mark)}
.synthetic{margin:1rem 0;padding:.75rem 1rem;border:2px dashed var(--mark)}
.muted{color:var(--muted)}
dl{display:grid;grid-template-columns:max-content 1fr;gap:.25rem 1.25rem;margin:.75rem 0}
dt{color:var(--muted)}
dd{margin:0}
.wide{overflow-x:auto;margin:.5rem 0 1rem}
table{border-collapse:collapse;width:100%;font-size:.9375rem}
caption{text-align:left;color:var(--muted);padding:.25rem 0}
th,td{text-align:left;vertical-align:top;padding:.375rem .625rem;border-bottom:1px solid var(--rule)}
th{font-weight:600;background:var(--panel)}
td{font-variant-numeric:tabular-nums}
code{font:.875em/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap;\
overflow-wrap:break-word}
.long code{overflow-wrap:anywhere}
a{color:inherit;text-underline-offset:2px}
nav ol{columns:2 18rem;padding-left:1.5rem}
footer{margin-top:3rem;padding-top:1rem;border-top:2px solid var(--rule)}
details{margin:1rem 0;padding:.75rem 1rem;background:var(--panel);border:1px solid var(--rule)}
summary{cursor:pointer;font-weight:600}
"""
"""The report's only styling. It's neutral: no status looks like a pass."""

type Headings = Sequence[tuple[str, str]]
"""A kind of report's ten sections, in the order docs/contracts.md lists them, by `id` and
heading."""


def text(value: str) -> str:
    """Text Trial Folio didn't write, as HTML: control and formatting characters, apart from tabs
    and line breaks, written as escapes, and then HTML-escaped."""
    return html.escape(visible(value, keep="\t\n\r"))


def code(value: str) -> str:
    return f"<code>{text(value)}</code>"


def moment(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def table(heads: Iterable[str], rows: Iterable[str], *, caption: str | None = None) -> list[str]:
    """A table in its scrolling wrapper: a heading cell for each of `heads`, as HTML, then
    `rows`, each a whole `<tr>`, with `caption` above them when there's one."""
    return [
        '<div class="wide"><table>',
        *([] if caption is None else [f"<caption>{caption}</caption>"]),
        "<thead><tr>" + "".join(f"<th>{head}</th>" for head in heads) + "</tr></thead>",
        "<tbody>",
        *rows,
        "</tbody></table></div>",
    ]


def facts(entries: Iterable[tuple[str, str]]) -> list[str]:
    """A description list: each entry's term, with its value as HTML."""
    return ["<dl>", *(f"<dt>{term}</dt><dd>{value}</dd>" for term, value in entries), "</dl>"]


def page(
    *,
    version: str,
    title: str,
    kind: str,
    label: str,
    top: Iterable[str],
    headings: Headings,
    sections: Mapping[str, Iterable[str]],
    records: str,
) -> str:
    """A report's whole document, rendered by Trial Folio `version`.

    `title` is the report's title, as its records give it. `kind` names the kind of report, such
    as "run report", and `label` follows it in the header, such as " · Synthetic example", or is
    empty. `top` is what the header shows after the concise notice: the synthetic banner, when
    there's one, and the report's status. `sections` holds each section's parts by its `id`,
    which `headings` numbers and heads, in their order. `records` says what the report was
    rendered from, such as "the run's saved records".
    """
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<meta name="generator" content="Trial Folio {version}">',
        f"<title>{text(title)} · Trial Folio {kind}</title>",
        f"<style>\n{_CSS}</style>",
        "</head>",
        "<body>",
        '<div class="page">',
        "<header>",
        f'<p class="kind">Trial Folio {kind}{label}</p>',
        f"<h1>{text(title)}</h1>",
        _concise_notice(),
        *top,
        *_contents(headings),
        "</header>",
        "<main>",
        *_sections(headings, sections),
        "</main>",
        *_closing(version, records),
        "</div>",
        "</body>",
        "</html>",
    ]
    return "\n".join(parts) + "\n"


def _sections(headings: Headings, sections: Mapping[str, Iterable[str]]) -> list[str]:
    """Each section, numbered and headed in the order of `headings`, holding its parts."""
    return [
        line
        for number, (key, heading) in enumerate(headings, 1)
        for line in (
            f'<section id="{key}">\n<h2>{number}. {heading}</h2>',
            *sections[key],
            "</section>",
        )
    ]


def _concise_notice() -> str:
    lead = CONCISE_NOTICE.removesuffix(f"{CONCISE_NOTICE_LINK}.")
    link = f'<a href="#{FULL_NOTICE_ID}">{html.escape(CONCISE_NOTICE_LINK)}</a>'
    return f'<p class="notice" id="notice">{html.escape(lead)}{link}.</p>'


def _contents(headings: Headings) -> list[str]:
    items = [f'<li><a href="#{key}">{heading}</a></li>' for key, heading in headings]
    return [
        '<nav aria-label="Contents">',
        "<ol>",
        *items,
        '<li><a href="#closing">Portfolio123 data, notices, and license</a></li>',
        "</ol>",
        "</nav>",
    ]


def _closing(version: str, records: str) -> list[str]:
    """The closing section, by the report of `version`, rendered from `records`, such as "the
    run's saved records"."""
    statement_lead, _, statement_rest = PORTFOLIO123_DATA_STATEMENT.partition(
        PORTFOLIO123_TERMS_LINK
    )
    terms = f'<a href="{PORTFOLIO123_TERMS_URL}">{html.escape(PORTFOLIO123_TERMS_LINK)}</a>'
    notice = [f"<p>{html.escape(paragraph)}</p>" for paragraph in FULL_NOTICE]
    return [
        '<footer id="closing">',
        (
            f'<p id="portfolio123-data"><strong>{html.escape(PORTFOLIO123_DATA_LABEL)}</strong>'
            f" {html.escape(statement_lead)}{terms}{html.escape(statement_rest)}</p>"
        ),
        f'<details id="{FULL_NOTICE_ID}">',
        "<summary>Full research and financial-result notice, and license</summary>",
        *notice,
        (
            f"<p>License: {html.escape(LICENSE_NAME)}, <code>{LICENSE_ID}</code>. Notice version"
            f' {NOTICE_VERSION}. Read <a href="{license_url(version)}">the LICENSE'
            f" published with Trial Folio {version}</a>.</p>"
        ),
        "</details>",
        f'<p class="muted">Rendered by Trial Folio {version} from {records}.</p>',
        "</footer>",
    ]
