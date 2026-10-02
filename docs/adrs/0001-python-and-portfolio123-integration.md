# ADR 0001: Python and Portfolio123 integration

**Status:** Accepted. Decision 3 is superseded by [ADR 0005](0005-build-on-the-portfolio123-api-only.md): Trial Folio no longer reads DataMiner exports or configurations. Its code boundary remains in force through REQ-02. [ADR 0006](0006-observe-the-wrappers-http-exchanges.md) (proposed) extends decision 6 by recording each HTTP exchange the wrapper makes. The language and dependency constraints are owner requirements, and provider behavior is re-verified in each release.
**Date:** 2026-10-01

## Context

Trial Folio reuses Portfolio123's research engines instead of reimplementing them. It adds controlled experimentation, durable evidence, and transparent comparison around them. The owner requires Python. Portfolio123 publishes three relevant projects:

- **`p123api`**, the official Python API wrapper.
- **DataMiner**, a YAML-driven tool that runs operations such as ScreenBacktest through the API and writes CSV exports.
- **FactorMiner**, a factor-analysis tool.

Trial Folio's own material is licensed under a custom, source-available license that restricts publication ([ADR 0004](0004-custom-personal-research-license.md)). Code under GPL-3.0 cannot be combined with those restrictions, and a repository without a license grants no permission to copy its code.

These are **verified observations** from the guide's 2026-10-01 check; the [verification notes](#verification-notes) below record the details:

- `p123api` is MIT-licensed. It handles endpoint calls, authentication, and retries, and it can convert results in ways that reshape them and drop metadata. [Wrapper documentation](https://portfolio123.customerly.help/en/articles/13765-the-api-wrapper-p123api), [source](https://github.com/portfolio-123/p123api-py/blob/master/p123api/client.py)
- DataMiner is licensed under GPL-3.0. [License](https://github.com/portfolio-123/dataminer/blob/master/LICENSE)
- FactorMiner's repository declares no license.
- DataMiner's inline ranking definitions reuse a shared `APIRankingSystem` in the account, so concurrent operations can interfere with each other. [Ranking definitions](https://portfolio123.customerly.help/en/articles/13793-dataminer-ranking-definition)

## Decision

1. **Python.** Trial Folio is implemented in Python, with Python 3.12 or later and `uv` for environments and dependencies (under [D-02](../spec.md#decisions)). The project does not use Go and does not require an LLM API for 0.1.0 to 0.3.0.
2. **`p123api` is the only Portfolio123 code dependency.** Trial Folio calls it through the `ScreenBacktestClient` protocol and adds its own durable recording, plan approval, and bounded execution around it. The wrapper's version is recorded with every attempt.
3. **DataMiner and FactorMiner are integrated only through their outputs.** Trial Folio reads DataMiner exports and user-supplied configurations as data, and matching their file layouts and key names is permitted. Their code is never imported, vendored, bundled, ported, or paraphrased, including in examples, notebooks, containers, and test utilities. Upstream source may be read to confirm behavior. That behavior is then described in original words and cited by link and pinned commit.
4. **Full payloads before conversion.** Trial Folio saves the full decoded response the wrapper returns before any conversion. It does not rely on the wrapper's table conversions for evidence.
5. **Shared-state operations are serialized.** Any operation that updates a shared account object, such as an API ranking system, is locked per account across processes for the whole update–execute–capture sequence, unless verified isolated objects are used.
6. **Visible attempts.** Trial Folio sets the wrapper to a single HTTP attempt per call and applies its own bounded retry policy, so that each attempt appears in the attempt log. A charged request whose outcome is uncertain is never retried automatically. Results are always requested in decoded JSON form (`to_pandas=False`).
7. **Credential objects stay contained.** The wrapper's exception and response objects can carry the bearer token and API key. Trial Folio never logs, serializes, or saves them. It extracts only the status code and a sanitized message.

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Fork or wrap DataMiner | GPL-3.0 code would prevent distribution under Trial Folio's license. Its GUI and option surface are also not the product. |
| Call the HTTP API directly without `p123api` | This duplicates authentication and endpoint handling the official wrapper already maintains. It could be revisited if the wrapper hides evidence Trial Folio needs, but only through a new ADR. |
| Go, or a mixed-language implementation | This contradicts the owner's requirement, and `p123api` is a Python library. |
| Reuse FactorMiner's calculations | The repository has no license, and its statistical choices do not match the study methods ([METH-02, METH-04](../methodology.md)). |

## Consequences

- Trial Folio depends on `p123api`'s behavior and versions. Wrapper upgrades are tested against recorded payloads, and changes that affect evidence are noted in release notes.
- When this ADR was accepted, visibility into retries was limited to what the wrapper exposes. Now [ADR 0006](0006-observe-the-wrappers-http-exchanges.md) records each HTTP exchange below the wrapper, so attempt records show every request it sends.
- Supporting a DataMiner layout requires a real reference export ([D-09](../spec.md#decisions)). Synthetic fixtures mirror its structure, never its data.
- Portfolio123 operations cost API credits, so the default test suite blocks network access, and live checks are opt-in with a budget.

## Follow-up conditions

- Before relying on it, re-verify wrapper behavior in the version actually installed, and pin the version and source commit in the release's verification evidence.
- Any need to copy upstream code requires a recorded license review and the owner's decision first.
- If wrapper conversions or retries prevent adequate evidence capture, write a new ADR that considers direct HTTP calls.

## Verification notes

Recorded on 2026-10-01 from public sources, without account access. These are documentation and source-code observations, not integration evidence. Re-verify them against the installed version.

**`p123api`**
- Pinned source: [p123api-py](https://github.com/portfolio-123/p123api-py) at commit `7b449eeb490f00759327624376397d60d69f1681`.
- Package: [PyPI](https://pypi.org/project/p123api/) 3.1.0, released 2026-08-25, MIT license, Python 3.10 or later. It depends on `requests` and `typing_extensions`, and pandas is an optional extra.
- **Credentials.** `Client(api_id=..., api_key=...)` takes both an API ID and an API key, and reads no environment variables or files. Portfolio123 users create both on the website under "DataMiner & API".
- **Screen backtest call.** `screen_backtest(params, to_pandas=False)` sends `POST /screen/backtest` and returns the decoded JSON body. Raw bytes, the status code, and headers are not exposed on success. The body's `cost` and `quotaRemaining` are also copied to client attributes, which the next call overwrites.
- **`to_pandas=True`** drops `cost`, `quotaRemaining`, and any unrecognized top-level fields.
- **Response shape, derived from source and undocumented.** `stats`, with portfolio and benchmark summary statistics; `results`, a per-period table with averages and up- and down-market rows; and `chart`, with dates, screen and benchmark returns, turnover percentages, and position counts.
  - **Confirmed by the 0.1.0 reference response** (R01-T02), which [`p123api-screen-backtest` version 1](../contracts.md#p123api-screen-backtest-version-1) documents. There are two corrections:
    - The chart's screen and benchmark series are levels, not returns: the value of 100 invested, starting at 100.
    - The average and up- and down-market rows are one element shorter than the table's columns, and they align from its second column. `to_pandas=True` appends them without that offset, which moves each value one column to the left.
  - **The installed wrapper matches the pinned source.** The `p123api` 3.1.0 wheel's `client.py` equals `p123api/client.py` at the pinned commit, apart from line endings.
- **Retries.**
  - The wrapper retries connection errors and HTTP 5xx responses up to 5 total attempts by default, which `set_max_request_retries` configures.
  - It reissues a request once after re-authenticating on a 401 or 403.
  - `requests.ReadTimeout` is not caught; the default timeout is 300 seconds.
  - A single wrapper call can therefore send a charged request more than once, or end with an unknown outcome.
- **Errors.** `ClientException`, and `ClientItemNotFoundException` for 404. The response attached to an exception carries the `Authorization` header, and for authentication failures the request body contains the API key.

**Portfolio123 API**
- A screen backtest costs 5 API credits per call. [API: Screen](https://portfolio123.customerly.help/en/articles/43324-api-screen), [API credits](https://portfolio123.customerly.help/en/articles/13766-api-credits)
- It accepts an inline screen or a saved screen ID, and a ranking as a name, an ID, or a single formula. `startDt` is required.
- Optional settings include `endDt`, `pitMethod`, `precision`, `transPrice`, `rebalFreq`, `slippage`, `maxPosPct`, `rankTolerance`, `carryCost`, and `riskStatsPeriod`.
- No commission parameter is documented; slippage is the only trading-cost input.
- The response fields are not documented.
- Unverified: whether failed requests are charged.

**DataMiner**
- A desktop GUI application distributed as builds from a Dropbox folder, so the build may differ from its [GitHub source](https://github.com/portfolio-123/dataminer), last pushed at commit `721f3deaa8bcb564846229506e6f84e3a41f9008` on 2025-02-19. [DataMiner](https://portfolio123.customerly.help/en/articles/13764-dataminer)
- It prompts for the API ID and key. It can save them in plaintext in a local `config.ini`.
- The [ScreenBacktest operation](https://portfolio123.customerly.help/en/articles/14056-dataminer-operation-screen-backtest) documents its configuration keys and defaults. The defaults include End Date = today, Slippage = 0, Benchmark = SPY, and Precision = 2.
- The output file format is not documented. The pinned source suggests a multi-section CSV with `Stats`, `Results`, and `Time Series` sections and no configuration, version, cost, or timestamp. This is unverified until a real export is inspected.
- Ranking definitions given as nodes or XML create or overwrite `APIRankingSystem` in the account.

**Licenses:** DataMiner GPL-3.0; FactorMiner has no license, at commit `d814c5df5000dc536de65a578da6ce42c05b17bf`; `p123api` MIT.
