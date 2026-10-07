# Live exercise of release 0.2.0

At the owner's request, Trial Folio 0.2.0 reviewed real runs that `trialfolio run` wrote from Portfolio123's responses. This exercise isn't one of the release's [verification commands](../../docs/releases/0.2.0-review.md#verification-commands-and-expected-evidence), and it isn't the owner's private use, which the owner does on their own. It adds evidence that a review reads real runs as it reads the runs the tests build over the fake server.

This run record and the configurations beside it are committed. The runs and the reviews hold Portfolio123's data, so they stay in `payloads/`, which is git-ignored and never committed ([REQ-11](../../docs/spec.md#enduring-requirements)). Nothing here comes from a response except the credits used. The review configurations name their runs by paths relative to themselves, in `payloads/runs/`, as the [user guide](../../docs/user-guide.md#10-compare-runs-with-a-review) recommends.

## Settings

On 2026-10-07 the owner approved two live runs with a budget of 10 credits, and was present for them. Each is [`formula.yaml`](../../tests/fixtures/screen-configs/formula.yaml), the documented example, with one setting changed, and its own title and purpose:

- [`holdings-50.yaml`](holdings-50.yaml): `max_holdings: 50`
- [`benchmark-iwm.yaml`](benchmark-iwm.yaml): `benchmark: 'IWM'`

Each ranks by a single formula, so nothing in the account was created or changed. Two runs already in the owner's reference data were reviewed too, at no cost, as copies in `payloads/runs/`: the [live check](../p123api-live-check/README.md)'s run of `formula.yaml` (`live-check`), the baseline of both reviews, and the [user guide walk-through](../user-guide-walkthrough/README.md)'s run of the starter `screen.yaml` (`walkthrough`), which has the same settings.

## Run record

Date: 2026-10-07, 07:59 to 08:01 UTC. Trial Folio 0.2.0, from `main` at 7cb317e; macOS 26.6.2, Python 3.14.8, and the verified versions: `p123api` 3.1.0, `requests` 2.34.2, and `urllib3` 2.8.0. Each command ran with `TRIALFOLIO_ACCEPT_LICENSE` set, and only the two runs had the credentials, injected as [AGENTS.md](../../AGENTS.md#credentials-and-reference-data) describes.

| Step | Outcome |
|---|---|
| `trialfolio review review-existing.yaml --out payloads/reviews/existing --json`: [`review-existing.yaml`](review-existing.yaml), the live check's run against the walk-through's | Exit 0, no warning. All 23 settings are `same`, and all 20 metrics are differenced, each with a difference of zero: two real runs of the same settings, made hours apart on 2026-10-04, agree. Their saved responses differ in bytes, so no row is flagged `identical_source`. |
| `trialfolio run holdings-50.yaml --out payloads/runs/holdings-50 --approve <plan hash> --json` | Exit 0, outcome `completed`, with the plan hash `sha256:4272909945d0baa7a2d2d71c16b17760a8495fd292449bc19c7ec8bf161c151b`. One attempt, `succeeded`, possibly charged, and one provider request. 5 credits, as Portfolio123 reported. All 20 metrics available. |
| `trialfolio run benchmark-iwm.yaml --out payloads/runs/benchmark-iwm --approve <plan hash> --json` | Exit 0, outcome `completed`, with the plan hash `sha256:67c23077a4f9c0a0f568c7708c509388c459978c5efa65fbb9b23fd843be05f3`. One attempt, `succeeded`, possibly charged, and one provider request. 5 credits, as Portfolio123 reported. All 20 metrics available. |
| `trialfolio review review-changes.yaml --out payloads/reviews/changes --json`: [`review-changes.yaml`](review-changes.yaml), both new runs against the live check's, `max_holdings` declared and the benchmark not | Exit 0, no warning, and `settings_flagged` 1. For `holdings-50`, `max_holdings` is an `intended_change`, with its reason, and isn't flagged. The other 22 settings are `same`, and all 20 metrics are differenced: 10 moved, and the 10 that the holdings don't change, the coverage, the risk samples, and the benchmark's own metrics, are zero. For `benchmark-iwm`, `benchmark` is an `unexplained_mismatch`, flagged `critical_unexplained_mismatch`. The 10 metrics that depend on the benchmark, rows 10 to 13 and 15 to 20, are `not_comparable`, with `different_benchmark`, and the strategy's other 10 are differenced, each with a difference of zero. |

**Credits:** 10, as Portfolio123 reported, within the budget of 10. Authentication's cost wasn't measured.

**The reports.** Each review's report carries the concise notice and the Portfolio123 data statement, reads "Not assessed", and shows each result's benchmark. Its only outside links are the LICENSE at `v0.2.0` and Portfolio123's terms, every other link is a file the review lists, and it has no script, event handler, or `src` attribute. It shows no `run` path, and no synthetic banner.

**The copies and the logs.** Each review's copies are byte-identical to their runs' files: 8 of 8, and 12 of 12. The logs hold no label, `run` path, description, reason, title, or purpose from the review configurations, and no metric value from the copied tables.

**The credentials.** A scan after the runs found the API key in no file of the new runs, and nowhere in the commands' stderr. The API ID matched inside one saved response, Portfolio123's own data. Neither appears in the logs, the reports, the normalized tables, the plans, the configurations, or the attempts' records.

Every result matched what [release 0.2.0](../../docs/releases/0.2.0-review.md) specifies.
