# Readability refactor

**Status:** Draft. **Don't refactor from it yet.** The owner decided each of its [open questions](#open-questions) on 2026-10-13, and sets it to Ready.
**Decided by:** [D-39](spec.md#decisions), on 2026-10-12 and 2026-10-13
**Depends on:** the code on `main` at 8a4c475, the merge of [D-38](spec.md#decisions)'s fixes (#80), against which the findings below were checked. Each task also depends on the `v0.3.0` tag, which is met: `v0.3.0` was tagged on 2026-10-13, on 6da0c3f, the merge commit of the pull request that set [0.3.0](releases/0.3.0-experiments.md) to Implemented.

This is the plan for refactoring `src/trialfolio` for readability. It isn't a release: it has no version or tag, and adds nothing to what Trial Folio does. It changes how the code is arranged, never what the code does, so every output, message, and committed file stays as it was.

The findings come from the owner's scope of the work, written on 2026-10-12 against 4a3bd93, and checked again against 8a4c475 for this plan. Each site is named by its module and function, not by line, since lines move. Module paths are relative to `src/trialfolio/`.

## The owner's decisions

1. **A track of its own (2026-10-12).** The refactor runs as a separate track, with this plan and its own task IDs, as the [user manual](user-manual.md) did. It isn't part of release [0.4.0](releases/0.4.0-ranking-weights.md), and it isn't done in pull requests outside a plan.
2. **After D-38's fixes merge (2026-10-12).** The track starts once the pull request with D-38's fixes, #80, has merged, because it changed six of the modules the track splits: `attempts.py`, `cli.py`, `experiment_approval.py`, `experiment_execution.py`, `logs.py`, and `provider.py`.
3. **Plan now, change `src/` after the tag (2026-10-13).** #80 merged on 2026-10-13, as 8a4c475. The owner decided that this plan's pull request starts then, and that every pull request that changes `src/` waits until `v0.3.0` is tagged, so the tag marks exactly the code the owner used privately.
4. **No ADR (2026-10-13).** The owner decided the track needs no ADR, rather than one for its design ([question 9](#open-questions)). By the owner's decision on question 8, `ArtifactStore` stays the interface that REQ-05 and [ADR 0003](adrs/0003-versioned-research-artifacts.md) name.

On 2026-10-13 the owner also decided each of the plan's [open questions](#open-questions):

5. **When the track runs (2026-10-13).** RF-T01 and RF-T02 run first, now that `v0.3.0` is tagged, alongside 0.4.0's remaining specification tasks. The other tasks run between 0.4.0's implementation tasks, each when no open pull request changes the modules it changes, and 0.4.0's implementation doesn't wait for the track. The alternative was to refactor first, so that 0.4.0's implementation is written in the new structure, but waits for the track.
6. **The top-level contract models stay where they are (2026-10-13),** so no committed schema changes. The alternative was to move them, which changes committed schemas' bytes.
7. **The "1 metrics" wording is fixed outside the track (2026-10-13),** in a change of its own, so each task of the track can show byte-identical reports. The alternative was to fix it within a task.
8. **The tests get a second pass (2026-10-13),** after RF-T11, so they follow the new structure. The alternative was to include them now, which doubles the review effort.
9. **Ruff's limits are decided after RF-T05 (2026-10-13).** Whether `scripts/check` enables Ruff's `C901` and `PLR0915` is decided once RF-T05 ends the scope's third step. The alternative was to decide it now.
10. **The provider's failure messages come from tables (2026-10-13):** a function that classifies the exchange, and a table of messages for each call, with every message recorded before and after the change. The alternative was to extract only the shared opening branches, a smaller change.
11. **Every logger name stays (2026-10-13).** Every module that logs at 8a4c475 keeps its logger's name, so no log event's `component` changes: code moved out of such a module logs under its name. The first task that moves code that logs rewords contracts.md's rule that core modules log through `logging.getLogger(__name__)`. The alternative was to keep only `trialfolio.cli`, `trialfolio.report`, and `trialfolio.storage`.
12. **`ArtifactStore` combines narrower Protocols (2026-10-13).** The platform's primitives move out of `storage.py`, and a reader's, a writer's, the claim's, and the lock's Protocols are added, which `ArtifactStore` combines, so it stays the interface that REQ-05, ADR 0003, and contracts.md's [protocols](contracts.md#protocols) name. The readers take the reader's Protocol. The alternatives were to replace `ArtifactStore` with the four Protocols, which would need an ADR, or only to move the primitives.

## Goal

The owner set four criteria for readability:

- **Long functions.** A function over about 50 lines has room to extract its steps.
- **Repeated logic.** Logic written in more than one place is extracted once, for reuse.
- **Large classes.** A class or Protocol with many methods composes better as smaller ones.
- **Mixed modules.** A module that holds logically distinct things is separated.

The [findings](#findings) apply them to the code at 8a4c475. The track is done when each finding is resolved as its task gives, or declined with a reason recorded in this file.

## What it doesn't change

Nothing a user, a saved file, or a test can observe:

- **Behavior:** each command's steps, exit codes, and outputs, the JSON summary, and the files each command writes.
- **Messages:** every error, log, and terminal message, word for word.
- **The committed schemas** under `schemas/`, byte for byte.
- **The committed fixtures,** and the reports rendered from them, byte for byte.
- **The logger names,** and so each log event's `component`.
- **The CLI's options and help,** and so the user manual's generated reference pages.
- **What the tests check.** A task changes a test only to import a name from where it moved, or to name a moved module in a docstring.

The run report says "1 metrics are unavailable" for a single unavailable metric. Fixing that changes a report's bytes, so the owner decided it's fixed in a change of its own, outside the track ([question 3](#open-questions)).

## Constraints

Every task respects these:

- **The committed schemas.** A schema's `$comment` names the module and class of its top-level model (`render`, in `contracts/schema_files.py`). So moving a top-level contract model, such as `DifferencesRow` or `AttemptRecordV1_1`, changes a committed schema's bytes, so the top-level models stay where they are, as the owner decided ([question 2](#open-questions)). Moving helpers and nested models doesn't. A model's field order and field docstrings shape its schema too.
- **Logger names.** Each module that logs does so through `logging.getLogger(__name__)`, and each log event's `component` is its logger's name ([logging](contracts.md#logging-and-local-diagnostics)). So code moved into a new module logs under a new name, unless the move keeps the old one.
  - `tests/core/test_review_report.py` and `tests/core/test_experiment_report.py` assert `trialfolio.report`, and `tests/core/test_artifact_store.py` captures `trialfolio.storage`.
  - The committed fixture logs record `trialfolio.cli`, `trialfolio.report`, `trialfolio.attempts`, `trialfolio.execution`, `trialfolio.review`, and `trialfolio.review_inputs`.
  - The CLI's `component` is `trialfolio.cli`.

  The owner decided that every module that logs at 8a4c475 keeps its logger's name ([question 7](#open-questions)). So a split of `report.py` or `cli.py` into a package keeps `trialfolio.report` and `trialfolio.cli` explicitly, and code moved out of any module that logs logs under that module's name. The first task that moves such code rewords contracts.md's rule to say so, and the module docstring of `logs.py`, which states the same rule.
- **Entry points and imports.** These keep working:
  - `trialfolio.cli:run_installed`, the installed command (`pyproject.toml`), and `python -m trialfolio`;
  - `trialfolio.cli.main`, the entry function ([CLI behavior](contracts.md#cli-behavior));
  - `trialfolio.cli._parser`, from which `scripts/manual_reference.py` generates the manual's reference pages, and `EXIT_CODES`, in `errors.py`, against which it checks contracts.md's errors;
  - `python -m trialfolio.contracts.schema_files`, which `scripts/schemas` runs;
  - `trialfolio.cli._Invocation.claimed`, which `tests/interface/test_review_storage.py` replaces by name;
  - every name the tests and `scripts/` import, from the module they import it from, unless the importer changes with it.
- **Lazy imports.** `cli.py`'s functions import the modules that import `p123api`, `requests`, or `urllib3` only once `installed_versions` has checked them, as its module docstring says. They stay lazy, so importing `trialfolio.cli` imports none of the three. The core never imports `trialfolio.cli`, as `tests/core/test_experiment_core.py` checks.
- **Documents.** Code, documents, and tests change together ([rules](../AGENTS.md#rules)). A task that moves a module or a name updates the documents that describe the code as it is: contracts.md names source paths on 21 lines, [user-manual.md](user-manual.md) names `_parser` in `src/trialfolio/cli.py`, [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)'s PyYAML row names `src/trialfolio/configuration.py` as the module that builds values from its parse events, and module and test docstrings name modules. The records of past work keep the paths they give: the release files and verification records, the ADRs, and AGENTS.md's account of past tasks.
- **Proving nothing changed.** The tests go through public entry points, so private helpers can move freely. But the tests check error codes, not every message's wording, and a report's content, not its every byte. So each task also shows what the [acceptance criteria](#acceptance-criteria) ask: the schemas' drift check, the bytes of the fixtures written again, and the messages it touches, before and after.
- **No live calls.** No task sends anything to Portfolio123, or needs credentials.
- **Other open pull requests.** A task doesn't start while an open pull request changes the modules it changes, such as one of 0.4.0's implementation tasks, between which the owner decided the later tasks run ([question 1](#open-questions)).

## The size of the work

At 8a4c475, measured as the scope measured 4a3bd93, with a function's lines counted from its `def` to its last line:

- **Functions:** 38 are over 50 lines, and another 26 are 41 to 50 lines. Ruff's complexity rules, which the project doesn't enable, flag 38 places: `C901` 13, `PLR0913` 11, `PLR0912` 6, `PLR0911` 6, and `PLR0915` 2.
- **Modules:** five are over 1,000 lines: `report.py` (4,024), `experiment_execution.py` (1,721), `cli.py` (1,562), `experiment_records.py` (1,452), and `attempts.py` (1,071).
- **Classes:** four have 30 or more methods, and each is over 750 lines: `ExperimentExecution` (62 methods), `_ReviewReport` (49), `_ExperimentReport` (38), and `_Report` (30).

Most of the length comes from two parallel paths, written separately. The screen run and the experiment repeat each other's execution, attempts, records, and approval, and the three kinds of report repeat each other. Extracting the shared logic also shortens most of the long functions.

## Findings

These are the track's scope. Each names the task that covers it.

### Repeated logic

Highest payoff first.

1. **The report's HTML scaffolding** (`report.py`; RF-T02):
   - `_Report.document`, `_ReviewReport.document`, and `_ExperimentReport.document` each build the same page. They differ only in the title's suffix, the kind's label, the sections, the closing phrase, and the method of section 5.
   - The table wrapper, `<div class="wide"><table>`, is written out 30 times, and `<dt>` 89 times. The pair of "Statistical validation" and "Trading readiness", each `NOT_ASSESSED`, appears 6 times.
   - `_settings_of` and `_case_settings` are the same apart from what they read. `ComparedRun.of`, in `differences.py`, repeats their fallback, from `settings.csv` to the plan, for its own type.
   - The settings table: `_Report._settings_table` and `_ExperimentReport._baseline_table` have the same 8 columns, and `_ReviewReport._baseline_settings` has 6 of them.
   - The metric definitions: the review's table, in `_ReviewReport._definitions`, and the experiment's, in `_ExperimentReport._definitions`, are the same. The run's, in `_Report._definitions`, is the same without overrides.
   - The limitations: the items on reproducibility and on inferred defaults are word for word the same in `_Report._limitations` and `_ExperimentReport._limitations`.
   - The facts of section 5: the budget, the attempt counts, the cost phrase (three times), and the entries "Plan built by", "Provider wrapper", "Transport", and "Run written by".
   - The data section: the parser and layout line (three times), the vendor and point-in-time entries, and the provenance list (three times).
   - The artifacts table, in each class's `_artifacts`, and `_link`, three times each, with a different path prefix each time.
   - The review's synthetic mix: `len(self._synthetic) == len(self._review.inputs)` appears 6 times.
   - The review's four tables of setting changes, `_intended_changes`, `_mismatches`, `_unknown`, and `_same`, have the same shape.
   - **The change:** the helpers `_table`, `_facts`, `_section`, and `_page`, and a module of shared fragments. It removes the most lines of any item.
2. **The screen run and the experiment build their manifest and their ending the same way** (`execution.py` and `experiment_execution.py`; RF-T03):
   - The provider's source record: `Execution._source` and `ExperimentExecution._attempt_file` have the same body and comment, with different inputs for `acquired_at`.
   - The configuration's source record, in `Execution._source` and `ExperimentExecution._listed`; the capabilities; the reproducibility; the parser list; and the artifact entry.
   - Writing the manifest, and discarding it when the write fails: `Execution._write_manifest`, `ExperimentExecution._write_ending`, and a third copy, `Review._write_manifest`, in `review.py`.
   - Mapping an ending to an error, where an interrupt becomes `command.interrupted`, any failure but `storage.write_failed` is raised again, and the detail is appended: `Execution.run`, `ExperimentExecution.run` (twice), and `Review.write`.
   - Whether an attempt ends the session: the same test in `Execution.run` and `ExperimentExecution._run_cases`, apart from the screen run's check that its configuration was written.
   - The message that an attempt's start record reads as running: in `Execution._request_detail`, and twice in `ExperimentExecution._attempt_detail`.
   - The manifest's detail: `Execution._manifest_detail` and `ExperimentExecution._manifest_detail` have the same three branches, with different nouns.
   - `_model_json` and `_utc` are each defined three times: in `execution.py`, `experiment_execution.py`, and `attempts.py`.
   - **The change:** a shared `manifests` module.
3. **Small helpers for errors and files** (RF-T01):
   - Appending one sentence to both an error's `message` and its `log_message` is written at 8 sites: `attempts._with_detail`, `cli._Invocation.execute`, `cli._init`, `Execution.run`, `Review.write`, and `ExperimentExecution._before_cases`, `_unrecorded`, and `_incomplete`. **The change:** `TrialFolioError.with_detail()`. `cli._with_repeat_options`, and `cli._with_report`, which #80 added, append other text, and keep their own.
   - `command.interrupted`, "Trial Folio was interrupted.", is built at 7 sites, in three forms: with a detail, in `attempts._interrupted`, `cli._Invocation._interrupted`, `cli._init`, and `Review.write`; with "after the attempt ended", in `Execution.run`; and alone, twice in `ExperimentExecution.run`. **The change:** a function in `errors.py` that builds it.
   - `_reason(error)` is the same in `storage.py`, `runs.py`, and `experiment_records.py`, and written inline 3 more times: twice in `cli.py`, and once in `logs.py`.
   - Resolving a path that exists is copied, comment included, in `cli._resolved` and in `review_inputs.local_run_stores`. The path containment in `logs.py`, `_within` and `_existing`, could share the new module.
   - Reading a file back, to know whether it was published whole: in `_AttemptFiles.published`, `ExperimentExecution._published`, and `ExperimentExecution._before_cases`. Building a `StoredFile` from bytes: in `_AttemptFiles.published`, `ExperimentExecution._published`, `experiment_records._stored`, and `storage._stored`. **The change:** `StoredFile.of(path, data)`, and `published(store, path, data)` in `storage.py`.
   - Listing items in a sentence, "a, b, and c": `report._series`, and `experiment_execution._and`, which #80 added, are the same, and `review._series` does it for positions. **The change:** one helper.
4. **The readers of a run's and an experiment's records** (`runs.py` and `experiment_records.py`; RF-T04):
   - Each has its own `_json_object`, `_validated`, `_named`, `_reason`, and `_METRIC_ROWS`, the four checks of the tables, the plan hash computed again, and the match of each listed artifact.
   - They differ only in the function that makes the error. **The change:** one `record_checks.py`, which takes that function as a parameter.
   - `_check_version` differs on purpose: the run's reader accepts a listed file without a version, skips unknown kinds, and names the run later. Those differences become parameters.
5. **`Attempt` and `ExperimentAttempt`** (`attempts.py`; RF-T06). The module's docstring says both kinds write their files, and end, the same way.
   - The same in both: `_write_start`, `_log_fields`, and five properties: `attempt_id`, `case_id`, `directory`, `files`, and `start_record`.
   - The same shape: the guard that ends an attempt once, the wrapper in `run` that records every ending, and the result's assembly in `_end`.
   - **The change:** an `_AttemptBase` class, with each subclass giving only its record and result builders.
   - Also repeated: the provider's metadata, `_metadata` and `_count`, in both `attempts.py` and `experiment_records.py`; and the count of authentication calls, in `experiment_execution._recorded` and `experiment_records._authentications`.
6. **The CLI counts an experiment a second time** (RF-T05). `_Invocation._experiment_counts`, in `cli.py`, computes from the records again what `ExperimentExecution` counts in `_counts` and `metrics_unavailable`, and its docstring says they're the counts the manifest gives. That's a risk to their consistency, not just repetition. **The change:** `SavedExperiment.counts(plan)` in the core, so the CLI only flattens them.
7. **The rules of a case's state are written twice** (RF-T05). `ExperimentExecution._awaiting_repeat` matches `SavedCase.state`; `ExperimentExecution._described` is close to `experiment_approval._code`; `ExperimentExecution._outcome` is close to `SavedCase.outcome` and `experiment_approval._retired_outcome`; and `ExperimentExecution.repeat_attempts`, and `ExperimentExecution._giving`, which #80 added, are close to `SavedCase.latest_charged`. The cause is that `experiment_execution._Attempt` and `SavedExperimentAttempt` both model an attempt. **The change:** a `case_state.py` module, with functions over a minimal Protocol.
8. **The provider's two failure functions** (`provider.py`; RF-T07). `_authentication_failure` (74 lines) and `_request_failure` (78) have the same skeleton: no exchange, not connected, no status, a 5xx status, a branch for each status, and a fallback. **The change:** `_recorded_exchange(call)`, a function that classifies the exchange, and a table of messages for each call, which removes about 100 lines, as the owner decided ([question 6](#open-questions)).
9. **Repeated annotations in the contracts** (RF-T01):
   - `Annotated[X | None, BeforeValidator(present), Field(json_schema_extra=optional_key)]` appears 13 times, in `contracts/experiment_configuration.py`, `contracts/review_configuration.py`, and `contracts/screen_configuration.py`.
   - `Annotated[tuple[X, ...], Strict(False), BeforeValidator(ordered)]` appears 6 times, 5 of them with `Field(min_length=n)`.
   - **The change:** the generic aliases `OptionalKey[T]`, `OrderedList[T]`, and `NonEmptyOrderedList[T]`, in `contracts/common.py`. A scratch script showed identical validation and serialization schemas, and identical errors.
   - Two catches: the minimum length has to sit inside the alias, because a `Field(min_length=1)` around it gives `minLength` instead of `minItems`; and a PEP 695 `type` alias would add `$defs` entries.
10. **Smaller repeats,** each in the task that changes its module:
    - The rules of a variant's change exist twice: `_rules_of` and `_value_of`, in `contracts/experiment_configuration.py`, and `_changed_value`, in `contracts/experiment_plan.py`. The rule is extracted, and each caller keeps its wording (RF-T10).
    - The three configuration readers, `read_screen_configuration`, `read_review_configuration`, and `read_experiment_configuration`, differ only in the kind, the versions, the model, and the quoting check (RF-T09).
    - The approval's prompt and messages are word for word the same in `approval.obtain_approval`, and in `experiment_approval.approve_experiment` and `experiment_approval._approval_problem`. So is the text that gives what's "Counted so far" and what it leaves of the budget, in `experiment_approval._counted_lines` and `experiment_approval.format_experiment_summary` (RF-T10).
    - `ExperimentExecution._write_plan` and `ExperimentExecution._write_revision` take the same five steps, and `_Tables(...)` is built four times (RF-T11).
    - Small validators repeated across the contracts: of the baseline, the variants, and the description; the credits check; "doesn't revise itself"; the case totals; and the review's checks in `JsonSummaryV1_1` and `JsonSummaryV1_2` (RF-T10).
    - `DifferencesRow._check_setting` repeats the checks and messages of `check_row`, in `contracts/screen_settings.py`, and `_METRIC_UNIT` repeats `MetricUnit`'s pattern (RF-T10).
    - `normalization._metrics` repeats the first half of `normalization._write`, and `write_case_tables` builds a path that `case_tables_path` already builds (RF-T09).
    - The CLI's handlers end the same way, and `_run`, `_demo`, and `_review` open the same way: the acknowledgment, `_started`, `store_factory`, and `check_empty` (RF-T08).

**Deliberate duplication, which stays.** Only the shared mechanics are extracted here:

- Each kind of report's wording ([DSC-04](disclaimers.md#dsc-04-actual-simulated-and-hypothetical-results)), including each class's `_nature`, the synthetic banners, and the approval texts.
- The privacy comment repeated at each record in `cli.py`.
- The versioned models of the JSON summary and the attempt records, whose field descriptions and field order differ between versions.
- The manifests' artifact models: a generic base would rename schema definitions.
- `_setting_row` and `_metric_row`, in `differences.py`, which list all 18 columns to mirror the contract.
- The repeat check in the CLI and again in the core, and, in both, the check of a reason given without a revision.
- The budget's preview, `ExperimentRun.uncovered` in `experiment_approval.py`, and its enforcement, `ExperimentExecution._stop_before`.
- The order of the steps in `_run` and `_demo`, which follows the contract's order.

### Classes that are too large

| Class | The change | Task |
|---|---|---|
| `ExperimentExecution` (62 methods) | An authorization function, a read-only ledger, the writer of the session's records, a case runner, a manifest builder, and the ending messages. **The hardest item:** its state must stay readable after any interrupt, `_attempts` changes in three places, and several methods depend on the order of the writes: `_retired` on `_write_revision`, and `_before_cases` on the `_record_data` that `_write_plan` sets. | RF-T11 |
| The three report classes | Not inheritance. Module functions for the shared pieces, and a small context object for each kind of report. The review's comparison of settings (about 265 lines) and the experiment's case ledger (about 300 lines) become section modules. | RF-T02 |
| `_Invocation` (16 methods, 21 fields), in `cli.py` | Six methods check which command ran: `_output_dir`, `_ids`, `_outputs`, `_counts`, `_execution_detail`, and `_write_result`. `_Invocation` stays, with `execute`, `claimed`, and `resuming`, and the state every command shares, such as its logs, IDs, output directory, and result, so `trialfolio.cli._Invocation.claimed` keeps working ([constraints](#constraints)). It holds a frozen `_Context`, with the 11 inputs, and an `_Outcome` Protocol, with one implementation for each command, which holds what that command did, such as its execution, review, or experiment, and takes over the six methods' work for it. | RF-T08 |
| The `ArtifactStore` Protocol (8 methods) and `LocalArtifactStore` (20), in `storage.py` | The readers use only `read` and `entries`, apart from `open_experiment`, in `experiment_records.py`, which takes the lock before it reads. The platform's primitives move into a module of their own: `_publish`, `_take_lock`, `_release_lock`, `_defer_sigint`, and the method `LocalArtifactStore._sync`. Narrower Protocols, a reader's, a writer's, the claim's, and the lock's, are added, which `ArtifactStore` combines, and the readers take the reader's, `open_experiment` the reader's and the lock's ([question 8](#open-questions)). | RF-T09 |
| `_AttemptFiles` (12), in `attempts.py` | A file writer (`write`, `write_request`, `save`, and `published`) and an ending policy (`end`, `ending_fields`, `_write_record`, and `_write_again`) | RF-T06 |
| The `_Ending` Protocol (8 members), in `contracts/attempt.py` | Deleted, with its argument typed as `AttemptRecord \| AttemptRecordV1_1`. The schemas don't change. | RF-T06 |
| `P123ScreenBacktestClient` (9), in `provider.py` | `_provider_message` moves out, as a pure function that sanitizes, beside `provider_message_of`, which #80 added | RF-T07 |
| `_Builder` (9), in `configuration.py` | The check of key names and the policy for scalars move to module functions. The builder keeps the traversal and the source spans. | RF-T09 |
| **Left as they are** | `ScreenBacktestClient` (5), `_Wrapper`, which mirrors `p123api`, `CommandLogs` (7), and `ReportRenderer` (3). From `Review` (17 methods, cohesive), only the manifest's assembly comes out. | RF-T03, for `Review` |

### Modules to separate

| Module | The layout | Task |
|---|---|---|
| `report.py` | A `report/` package: `renderer`, `page` (the HTML primitives and the CSS), `vocabulary` (the tables from codes to text), `fragments`, `run`, `review`, and `experiment` | RF-T02 |
| `cli.py` | A `cli/` package: `arguments`, `invocation`, `summary`, `screen`, `experiment`, `offline` (`report` and `review`), `workspace` (`init`), and `license` | RF-T08 |
| `experiment_execution.py` | Modules of their own for the progress events and `Cancellation`; for `Repeat` and `_confirmed`, since `experiment_approval.py` imports the whole executor only for `Repeat`; and for the ledger, the manifest, and the ending, from [the classes](#classes-that-are-too-large) | RF-T11 |
| `experiment_records.py` | The paths, the case state, and the checks, which `runs.py` shares. `SavedExperimentAttempt.completed_record` is writer logic in the reader, so it moves to the resume's code. | RF-T04, RF-T05, and RF-T11 |
| `attempts.py` | Reading attempts, which `runs.py` uses; the ending policy, which `execution.py` uses; and the two attempt classes | RF-T06 |
| `experiment_approval.py` | The display, the approval, and the confirmation of a repeat | RF-T10 |
| `planning.py` | The version checks, the screen plans, the experiment plan's compiler, and the revisions. `_versions_of`, and the `Versions(...)` that `ExperimentExecution._check_configuration` builds, become one `Versions.of(plan)`. | RF-T10 |
| `provider.py` | A `provider/` package: `credentials`, `failures`, `adapter`, and `client`. Its users import only public names. | RF-T07 |
| `configuration.py` | `strict_yaml.py`, the YAML reader that refuses ambiguous forms, and the error messages, split out. The readers stay. | RF-T09 |
| `normalization.py` | The response layout's adapter, the row builders, and the writing of the tables | RF-T09 |
| `contracts/manifest.py` and `contracts/plan.py` | Only the shared parts move, such as `SourceRecord`, `Capabilities`, and the request models, such as `PlanRequest`. The top-level models stay, so no schema changes ([question 2](#open-questions)). | RF-T10 |

### Long functions

Most get shorter once the shared logic above is extracted. For the rest, each step below becomes a function of its own. The lines are at 8a4c475.

| Function | Lines | Steps to extract | Task |
|---|---|---|---|
| `ExperimentExecution.__init__` | 144 | The checks of the kinds, the authorization, and building the state from the saved experiment | RF-T11 |
| `cli._run_experiment` | 111 | Opening the directory, or falling back to its lock; loading the resume; the approval; building the executor; and mapping the ending | RF-T08 |
| `cli._parser` | 103 | One `_add_<command>()` function for each subcommand | RF-T08 |
| `SavedExperimentAttempt.completed_record` | 103 | One builder for each branch; it builds the common fields twice | RF-T11 |
| `_Invocation._experiment_counts` | 89 | None: it goes once the core counts ([repeated logic](#repeated-logic), item 6) | RF-T05 |
| `experiment_approval.format_experiment_plan` | 82 | One function for each section of the display | RF-T10 |
| `experiment_approval._check_repeats` | 81 | The checks of a key alone, and the checks with an attempt | RF-T10 |
| `Execution.run` | 80 | The test of the session's end, writing the report and the manifest, and mapping the error (item 2) | RF-T03 |
| `experiment_records._tables` | 80 | The metrics' checks and the settings' checks | RF-T04 |
| `_ExperimentReport._limitations`, `_ExperimentReport._case_section`, and `_Report._cases` | 78 to 79 | The shared limitation items, case cells, and facts of section 5 (item 1) | RF-T02 |
| `provider._request_failure` and `provider._authentication_failure` | 74 to 78 | The classifier and the tables of messages (item 8) | RF-T07 |
| `experiment_records._plan` and `experiment_records._attempt` | 69 to 74 | The hash check, the entry check, the history, and the declared fields; and the identity checks and the placement | RF-T04 |
| `ExperimentExecution._run_cases` | 73 | Starting the attempt, choosing the next token, and stopping after an attempt | RF-T11 |
| `ExperimentExecution._partial` | 51 | Each part of the message, which #80 made longer: Portfolio123's messages, the stop, the charge, and the revision | RF-T11 |
| `LocalArtifactStore._claim` | 59 | Creating the file, and checking the directory afterwards | RF-T09 |
| `_Builder._scalar` | 51 | One helper for each YAML tag, chosen from a table | RF-T09 |

Each other function over 50 lines is left to the task that changes its module, which extracts its steps where that reads better.

### Outside the scope

- **The tests.** 51 functions under `tests/` are over 50 lines, decorators included, and 38 of them are tests. `write_run`, in `tests/core/conftest.py`, is 124 lines. The largest test files are `tests/core/test_experiment_resume.py` (1,896 lines) and `tests/interface/test_json_summary.py` (1,807). They haven't been checked for repetition. The owner decided they get a second pass, after RF-T11 ([question 4](#open-questions)).
- **The "1 metrics" wording.** `_Report._limitations` gives "1 metrics are unavailable", where `_ExperimentReport._limitations` gives the singular. It's fixed in a change of its own, outside the track ([question 3](#open-questions)).
- **Enforcing the limits** in `scripts/check`, which the owner decides after RF-T05 ([question 5](#open-questions)).

## Acceptance criteria

RF-AC01 to RF-AC10 apply to each task, checked on its pull request. RF-AC11 applies to the track.

| ID | Criterion |
|---|---|
| RF-AC01 | `scripts/check` passes on the task's branch, and so do both jobs of the `check` workflow, on Python 3.12 and 3.14 |
| RF-AC02 | The committed schemas are unchanged: `scripts/schemas --check` is clean, and the pull request changes no file under `schemas/` |
| RF-AC03 | The user manual's generated reference pages are unchanged: `uv run python scripts/manual_reference.py --check` is clean, and the pull request changes no file under `manual/` |
| RF-AC04 | The committed fixtures are byte-identical, and so is what the code writes again from them. The pull request changes no file under `tests/fixtures/`. Each fixture is written again through the real code, as it was written, by the code before the change and by the code after it, with the fixed clock and a fixed sequence of IDs in place of `uuid.uuid4`, and the two give the same bytes in every file but those in `logs/`, whose timestamps come from the wall clock: `runs/synthetic-run-1.0.0/` by `trialfolio demo`; `reviews/synthetic-review-1.0.0/` by `trialfolio review`, over a copy of that run at the `run` path its configuration gives; and `experiments/synthetic-experiment-1.0.0/`, with both sessions' reports, by the synthetic experiment's writer, `tests/support/synthetic_experiment.py`. The run's report is also rendered again from the fixture's records, as `trialfolio report` renders it. No code renders a review's or an experiment's report from its records, and a screen run's own report is rendered from what `Execution.run` holds, so only writing them again goes through the code that builds their evidence. |
| RF-AC05 | Every name a module logs under at 8a4c475 is kept, so no log event's `component` changes ([question 7](#open-questions)): `trialfolio.attempts`, `trialfolio.cli`, `trialfolio.execution`, `trialfolio.experiment_execution`, `trialfolio.provider`, `trialfolio.report`, `trialfolio.review`, `trialfolio.review_inputs`, and `trialfolio.storage` |
| RF-AC06 | Every message keeps its wording. A task that moves or rebuilds a message's text, such as the error helpers, the endings, the approval prompts, or the provider's failures, records each such message before and after the change, and they're identical. For the provider's failures, that's every message `_request_failure` and `_authentication_failure` can give. |
| RF-AC07 | The entry points and imports in the [constraints](#constraints) keep working, and the tests check what they checked: a change under `tests/` only imports a name from where it moved, or gives a moved module's new name in a docstring, apart from RF-T01's check of the fixtures (RF-AC04) |
| RF-AC08 | The CLI's imports stay lazy: `uv run python -c "import sys, trialfolio.cli; assert not {'p123api', 'requests', 'urllib3'} & set(sys.modules)"` passes, and the test that the core doesn't import `trialfolio.cli` passes unchanged |
| RF-AC09 | Every reference test passes, and none skips. They run `trialfolio run` and `trialfolio review` over the owner's real responses and runs, so they go through planning, execution, attempts, the provider client, normalization, the reports, and the review, whichever of those modules a task changes. They're run on the owner's machine, where the reference data is, as AGENTS.md's [development commands](../AGENTS.md#development-commands) and step 9 of [doing the next item](../AGENTS.md#doing-the-next-item) give: from the task's worktree, read-only, with `TRIALFOLIO_REFERENCE_DIR` naming the main checkout's `reference/`. Whoever does the task runs them before the pull request opens, and again after any later change to `src/`, and the pull request records each result, since neither its reviewers nor the `check` workflow runs them. No reference test reads an experiment, so for an experiment's code, RF-AC04 and the default suite are the evidence. |
| RF-AC10 | Each finding the task covers is resolved as this file gives, or declined with a reason recorded in this file. The documents that describe the code as it is give its new paths and names, and `git grep` finds an old path only in the records of past work. |
| RF-AC11 | The last task, RF-T11, measures the code again, as [the size of the work](#the-size-of-the-work) does, and records both measurements in this file |

## Tasks

The owner assigns these by ID. They aren't next items: [doing the next item](../AGENTS.md#doing-the-next-item) goes through the release files only. Each task is one pull request, and follows that section's steps 4 to 11, with a branch such as `refactor/rf-t01-shared-helpers`, and a commit subject that ends with its ID, such as `refactor(report): split the report into a package (RF-T02)`. Each adds itself, with its date, to this file's status line, and records the details it settled in this file, in a section of its own, for the owner to confirm, as the user manual's tasks did.

Every task changes `src/`, so each depends on the `v0.3.0` tag, which is met, as well as on this file's status. By the owner's decision ([question 1](#open-questions)), RF-T01 and RF-T02 run first, alongside 0.4.0's remaining specification tasks, and the others between 0.4.0's implementation tasks, each when no open pull request changes the modules it changes. The order is the scope's: the small shared helpers first, then the report, the shared core modules, the provider and the CLI, and `ExperimentExecution` last. RF-T06, RF-T09, and RF-T10 cover findings the scope's order didn't place, before the executor.

| ID | Task | Depends on |
|---|---|---|
| RF-T01 | **Shared helpers, and the check of the reports.** First, write the check that RF-AC04 runs: it writes the fixtures again through the real code, and renders the run's report again from its records, as RF-AC04 gives, so that a task can run it on its base and on its branch, and compare the files. Record in this file where it lives, and how to run it. Then extract the small helpers of [repeated logic](#repeated-logic) items 3 and 9: `TrialFolioError.with_detail()`, the function that builds `command.interrupted`, one `_reason`, a module that resolves paths, `StoredFile.of` and `published`, one helper that lists items in a sentence, and the aliases `OptionalKey[T]`, `OrderedList[T]`, and `NonEmptyOrderedList[T]`. | Status Ready; `v0.3.0` tagged (met on 2026-10-13) |
| RF-T02 | **The `report/` package:** item 1, the three report classes, and the package's layout, keeping the logger `trialfolio.report`, with `_ExperimentReport._limitations`, `_ExperimentReport._case_section`, and `_Report._cases` shortened | RF-T01 |
| RF-T03 | **The shared manifests and endings:** item 2's `manifests` module, which `execution.py`, `experiment_execution.py`, and `review.py` use, with `Review`'s manifest assembly moved out, and `Execution.run` shortened | RF-T01 |
| RF-T04 | **The shared record checks:** item 4's `record_checks.py`, which `runs.py` and `experiment_records.py` use, and the paths and checks of `experiment_records.py` separated, with its `_tables`, `_plan`, and `_attempt` shortened | RF-T01 |
| RF-T05 | **Case state and the core's counts:** item 7's `case_state.py`, and item 6's `SavedExperiment.counts(plan)`, which `_Invocation._experiment_counts` then only flattens. Then ask the owner to decide whether `scripts/check` enforces Ruff's `C901` and `PLR0915` ([question 5](#open-questions)). It depends on RF-T03 too, so that it ends the scope's third step, the shared core modules, as that decision assumes. | RF-T03, RF-T04 |
| RF-T06 | **Attempts:** item 5's `_AttemptBase`, `_AttemptFiles` split into a file writer and an ending policy, the `_Ending` Protocol in `contracts/attempt.py` deleted, and `attempts.py` separated into reading, the ending policy, and the attempt classes | RF-T03 |
| RF-T07 | **The `provider/` package:** item 8's classifier and tables of messages, with every message recorded before and after (RF-AC06), `_provider_message` moved out of `P123ScreenBacktestClient`, and the package's layout, keeping the logger `trialfolio.provider` | RF-T01 |
| RF-T08 | **The `cli/` package:** `_Invocation` kept, with `claimed` and the state every command shares, holding a `_Context` and an `_Outcome` that take the rest; and the package's layout, keeping the logger `trialfolio.cli`, the lazy imports, `trialfolio.cli.main`, and `trialfolio.cli._parser`; the handlers' shared opening and ending; and `_run_experiment` and `_parser` shortened | RF-T05, RF-T07 |
| RF-T09 | **Storage, configuration, and normalization:** the platform's primitives moved out of `storage.py`, and the narrower store Protocols, which `ArtifactStore` combines, with the readers taking the reader's, and `open_experiment` the reader's and the lock's ([question 8](#open-questions)); `strict_yaml.py` and the configuration's error messages split out, with THIRD_PARTY_NOTICES.md's PyYAML row naming `strict_yaml.py`, `_Builder`'s key-name check and scalar policy moved to module functions, and the three configuration readers sharing their steps; `normalization.py` separated, with its repeats removed; and `LocalArtifactStore._claim` and `_Builder._scalar` shortened | RF-T01 |
| RF-T10 | **Plans, approval, and contracts:** `planning.py` and `experiment_approval.py` separated, with `Versions.of(plan)`, the approval prompts' shared messages, and `format_experiment_plan` and `_check_repeats` shortened; and in the contracts, the shared parts of `contracts/manifest.py` and `contracts/plan.py` moved, and the repeated validators, the setting check, the metric unit's pattern, and the rule of a variant's change each written once | RF-T05 |
| RF-T11 | **`ExperimentExecution`, last:** its split, from [the classes](#classes-that-are-too-large); the modules separated from `experiment_execution.py`; `SavedExperimentAttempt.completed_record` moved to the resume's code; `_write_plan` and `_write_revision` sharing their steps; and `__init__`, `_run_cases`, and `_partial` shortened. Then measure the code again, and record both measurements (RF-AC11), and ask the owner to plan the tests' second pass ([question 4](#open-questions)). | Every other RF task |

## Open questions

The owner decided each question on 2026-10-13, and each decision is now a requirement of this plan. Each impact keeps the alternative for the record.

| # | Question | Impact | Decided by the owner (2026-10-13) |
|---|---|---|---|
| 1 | When does the track run, against 0.4.0? | 0.4.0's remaining specification tasks change no module in `src/`: R04-T03 specifies sending and records, and R04-T04 completes the specification and sets the version. So the overlap is with 0.4.0's implementation, which will change how a case is sent, recorded, and reported, as R04-T03 specifies. Refactoring first means 0.4.0's implementation is written in the new structure, but waits for the track. Refactoring between its tasks means no wait, but more code to move later. | RF-T01 and RF-T02 first, now that `v0.3.0` is tagged, alongside 0.4.0's remaining specification tasks. Then the other tasks between 0.4.0's implementation tasks, each when no open pull request changes the modules it changes. 0.4.0's implementation doesn't wait for the track. |
| 2 | Do the top-level contract models stay where they are? | Moving one changes a committed schema's bytes, for a small gain in readability | They stay, so no committed schema changes (RF-AC02) |
| 3 | Where is the "1 metrics" wording fixed? | Fixed within a task of this track, it changes a report's bytes, so that task can't show byte-identical reports (RF-AC04) | In a change of its own, outside the track |
| 4 | Are the tests in scope? | Including them now doubles the review effort. A second pass after `src/` lets the tests follow the new structure. | A second pass, after RF-T11 |
| 5 | Are the limits enforced afterwards? | Enabling Ruff's `C901` and `PLR0915` in `scripts/check` would stop functions from growing again, but needs exemptions until the cleanup is done | Decided after RF-T05, which ends the scope's third step |
| 6 | How are the provider's failure messages rebuilt? | A classifier driven fully by tables removes about 100 lines. Extracting only the shared opening branches is a smaller change. Either way, the messages keep their wording. | Driven by tables, with every message recorded before and after (RF-AC06) |
| 7 | Does every logger name stay? | Each module logs under its own name, which is each log event's `component`, so code moved into a new module logs under a new name. Tests assert `trialfolio.report` and capture `trialfolio.storage`, and the committed fixture logs record six names. Keeping only the CLI's name and those the tests hold, `trialfolio.cli`, `trialfolio.report`, and `trialfolio.storage`, would change other events' `component` in new logs, which are diagnostics, not evidence ([REQ-06](spec.md#enduring-requirements)). Keeping every name departs from [logging](contracts.md#logging-and-local-diagnostics)'s rule that core modules log through `logging.getLogger(__name__)`. | Every module that logs at 8a4c475 keeps its logger's name, so no event's `component` changes: code moved out of it logs under that name. The first task that moves such code rewords contracts.md's rule to allow it. |
| 8 | Is the `ArtifactStore` Protocol split? | REQ-05, [ADR 0003](adrs/0003-versioned-research-artifacts.md), and contracts.md's [protocols](contracts.md#protocols) name `ArtifactStore` as the interface every artifact read and write goes through. Replacing it with four narrower Protocols would change them, which needs an ADR. Moving only the platform's primitives out of `storage.py` changes no interface. | The platform's primitives move out, and the narrower Protocols, a reader's, a writer's, the claim's, and the lock's, are added, which `ArtifactStore` combines. It stays the interface they name, so no ADR is needed. The readers take the reader's Protocol. |
| 9 | Does the track need an ADR? | An ADR records a significant decision, or a reversal of one. The refactor changes no behavior, and, by question 8's decision, no interface that REQ-05 or [ADR 0003](adrs/0003-versioned-research-artifacts.md) names. An ADR for the track's design would record its structure, such as the new packages and modules. | No ADR |
