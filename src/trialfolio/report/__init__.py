"""The report: one self-contained, script-free HTML file showing a run's, a review's, or an
experiment session's evidence, with the notices (docs/contracts.md, reports; docs/disclaimers.md,
DSC-02, DSC-03, and DSC-06; REQ-08 and REQ-13).

`ReportRenderer` is the protocol, and `HtmlReportRenderer` its implementation. Rendering reads
only the `SavedRun`, the `ReviewEvidence`, or the `ExperimentEvidence` it's given, so it needs
no provider or network access.

- `write_report` writes `report.html` into the output directory of the run being written. `run`
  and `demo` do that just before the manifest.
- `rerender_report` is the core of `trialfolio report`: it reads and checks a saved run, renders
  its report, and claims a new output directory with it.
- `write_experiment_report` writes an experiment session's `sessions/<s>/report.html`, just
  before its manifest (release 0.3.0, R03-T10). The experiment report shows every planned case in
  the plan's order, with its change from the baseline, its outcome, and its attempts; each case's
  metrics side by side, without a difference; the retired cases; every plan with its reason; each
  repeat with the attempt it repeated; and each case awaiting a repeat with the option that
  repeats it. It orders, ranks, and marks no case by a value.
- `write_review_report` writes a review's `report.html`, just before its manifest (release 0.2.0,
  R02-T07). The review report compares each result with the baseline: intended changes apart from
  unexplained mismatches, and each result's metrics beside the baseline's, with the difference
  where they're comparable.

What a report holds:

- **Nothing that runs or loads.** Inline CSS only: no script, event-handler attribute, or
  external resource. Its only links are in-page fragments, relative paths to the run's artifacts,
  to the review's files, or to the experiment's, and the two outside links D-21 allows: the
  LICENSE of the version that rendered it, and Portfolio123's terms. A review report never links
  a run.
- **The notices.** The concise notice near the top, before any result, linking to the full
  notice. The Portfolio123 data statement in the closing section, and after it the full notice in
  a `<details>` element, with the license's name and identifier, the notice version, and the
  LICENSE link.
- **The ten sections docs/contracts.md lists,** in order. A section the run's evidence can't
  support says it's unavailable, or not assessed, and why. Nothing is filled in.
- **Values exactly as the normalized tables hold them,** with their units, never padded or
  rounded. An unavailable metric shows its reason. A synthetic result's values are labeled
  wherever they appear, and never called Portfolio123's (DSC-04).
- **Text Trial Folio didn't write,** such as the title, the formulas, or a provider message,
  HTML-escaped, with its control and formatting characters written as escapes such as `\\u202e`,
  so it can't add markup or reorder what's shown.
- **No account information:** `quotaRemaining` stays in the attempt record.
- **Neutral status.** No status is styled as a pass; execution success is kept apart from any
  statement about the strategy.

Rendering is deterministic: the same run, review, or session, and version give the same bytes.
Nothing here logs the report's contents.

The package's modules, each importing only those before it:

- `page`: the HTML primitives, the page every report is put together into, and the CSS.
- `vocabulary`: the tables from the codes in the records to the report's words for them.
- `fragments`: the parts more than one kind of report shows the same way, word for word.
- `evidence`: what each kind of report is rendered from, and the context its sections read.
- `run`, `review`, and `experiment`: each kind of report, section by section, with two sections
  long enough for modules of their own: `review_settings`, the review's comparison of settings,
  and `experiment_cases`, the experiment's case ledger.
- `renderer`: `ReportRenderer`, `HtmlReportRenderer`, and the functions that write each kind of
  report, which log under `trialfolio.report`.

Every name the rest of Trial Folio uses is imported from `trialfolio.report`, as before it was a
package.
"""

from trialfolio.report.evidence import (
    REPORT_PATH,
    CaseView,
    ExperimentEvidence,
    RetiredCaseView,
    ReviewEvidence,
    experiment_manifest_path,
    experiment_report_path,
)
from trialfolio.report.fragments import NOT_ASSESSED
from trialfolio.report.page import FULL_NOTICE_ID
from trialfolio.report.renderer import (
    HtmlReportRenderer,
    ReportRenderer,
    rerender_report,
    write_experiment_report,
    write_report,
    write_review_report,
)

__all__ = [
    "FULL_NOTICE_ID",
    "NOT_ASSESSED",
    "REPORT_PATH",
    "CaseView",
    "ExperimentEvidence",
    "HtmlReportRenderer",
    "ReportRenderer",
    "RetiredCaseView",
    "ReviewEvidence",
    "experiment_manifest_path",
    "experiment_report_path",
    "rerender_report",
    "write_experiment_report",
    "write_report",
    "write_review_report",
]
