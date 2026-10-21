"""A live diagnostic of a stale backtest after `rank_update` (release 0.4.0, the walk-through's
finding).

On 2026-10-20, the live walk-through of 0.4.0 found an experiment's case whose backtest, sent at
once after its `rank_update` got a 200, returned exactly the response of the definition
`ApiRankingSystem` held before. This script writes two definitions, A and B, into
`ApiRankingSystem` in turn, B first, each followed at once by the same backtest, as an
experiment's attempts are, and labels each backtest by the definition whose response it returns.
With `--touch`, it sends `rank_touch` for `ApiRankingSystem` between the two, which Portfolio123's
Rank API page says "Forces a flush of all cached ranks". With `--pause`, it waits that many seconds
after the `rank_update`'s 200, or the touch's, before the backtest.

The calls go through Trial Folio's own provider client, configured as for a run (ADR 0006): one
authentication for the command, then each write's calls, each allowed one HTTP exchange, with no
retry. `rank_touch` goes through the same client, by the wrapper's `rank_touch`, and needs the
system's ID, which the `id` command reads with a `rank_get` and keeps in the payloads folder.
The credentials come from `TRIALFOLIO_P123_API_ID` and `TRIALFOLIO_P123_API_KEY`, injected for
the one command, as AGENTS.md describes. Like Trial Folio's CLI, the script removes
`SSLKEYLOGFILE` from its own environment, with a warning.

Labels. A backtest is `fresh` when it returns the response most of the writes of its own
definition return in the command, `stale` when it returns the other definition's, and `other`
when it returns neither. Responses are compared without `cost` and `quotaRemaining`. With
`--references`, the script also says whether each definition's response is the one given, such as
an earlier day's, which shows whether Portfolio123's data changed in between.

Stops. Before sending anything, the command refuses a plan whose documented cost is over
`--budget`. It stops after any call that fails, after a third distinct response, which means the
data changed during the command, and after four writes that all returned one response, which means
the two definitions can't be told apart.

What it prints is only what a run record may hold: each write's definition, each call's
exchanges, the time from the `rank_update`'s 200 to the backtest's send, the labels, the credits
Portfolio123 reports, and the fall in the remaining credits. Never a definition, a response's
values, the system's ID, the remaining credits, or Portfolio123's message on a failure, of which
it prints only Trial Folio's error code. Every response, the exchanges, and a summary of the
labels and timings are saved in the payloads folder given, which must be git-ignored.

    diagnose.py writes PAYLOADS LABEL A.xml B.xml BACKTEST.json --writes N --budget C
                [--touch] [--pause S] [--references A.json B.json]    6 credits a write, 7 with --touch
    diagnose.py id PAYLOADS [--compare A.xml B.xml] --budget C       1 credit
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from trialfolio.provider.client import (
    DecodedResponse,
    P123ScreenBacktestClient,
    ScreenBacktestResponse,
)
from trialfolio.provider.credentials import Credentials
from trialfolio.provider.failures import RANK_UPDATE, ProviderError

SYSTEM = "ApiRankingSystem"
RANKING_METHOD = 2
CREDITS = {"rank_update": 1, "rank_touch": 1, "backtest": 5, "rank_get": 1}
"""Portfolio123's documented costs: API functions: Rank, and API: Screen."""
KEY_LOG = "SSLKEYLOGFILE"
SYSTEM_ID_FILE = "api-ranking-system.json"
TOUCH_PATH = re.compile(r"/rank/\d+/touch")


@dataclass
class Write:
    number: int
    definition: str
    exchanges: list[str] = field(default_factory=list)
    gap_seconds: float | None = None
    response: str | None = None
    label: str | None = None
    credits_reported: int = 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    w = commands.add_parser("writes")
    w.add_argument("payloads", type=Path)
    w.add_argument("label")
    w.add_argument("a", type=Path)
    w.add_argument("b", type=Path)
    w.add_argument("backtest", type=Path)
    w.add_argument("--writes", type=int, required=True)
    w.add_argument("--budget", type=int, required=True)
    w.add_argument("--touch", action="store_true")
    w.add_argument("--pause", type=float, default=0.0)
    w.add_argument("--references", type=Path, nargs=2)
    i = commands.add_parser("id")
    i.add_argument("payloads", type=Path)
    i.add_argument("--compare", type=Path, nargs=2)
    i.add_argument("--budget", type=int, required=True)
    args = parser.parse_args()
    if args.command == "writes":
        writes(args)
    else:
        read_id(args.payloads, args.compare, args.budget)


# The writes


def writes(args: argparse.Namespace) -> None:
    per_write = (
        CREDITS["rank_update"] + CREDITS["backtest"] + (CREDITS["rank_touch"] if args.touch else 0)
    )
    planned = args.writes * per_write
    if args.writes < 2 or planned > args.budget:
        sys.exit(
            f"{args.writes} writes cost {planned} credits; the budget is {args.budget}. Nothing sent."
        )
    folder = args.payloads / args.label
    ignored(folder)
    folder.mkdir(parents=True, exist_ok=False)
    definitions = {"A": read_text(args.a), "B": read_text(args.b)}
    backtest = json.loads(args.backtest.read_bytes())
    system_id = saved_id(args.payloads) if args.touch else None
    print(
        f"{args.writes} writes, alternating B and A, B first{', with rank_touch' if args.touch else ''}"
        f"{f', with a pause of {args.pause:g} s' if args.pause else ''}: "
        f"at most {planned} credits at the documented costs."
    )
    done: list[Write] = []
    quota: list[tuple[int, int]] = []
    with client() as provider:
        if call(provider, provider.authenticate, folder / "authentication") is None:
            sys.exit("Stopped: authentication failed. Nothing else was sent.")
        for number in range(1, args.writes + 1):
            name = "B" if number % 2 else "A"
            write = Write(number, name)
            done.append(write)
            sent = send_write(
                provider, write, definitions[name], backtest, (system_id, args.pause), folder, quota
            )
            report(write)
            save_summary(folder, done, args)
            if not sent:
                sys.exit("Stopped: a call failed. Its exchanges are saved.")
            distinct = {w.response for w in done if w.response}
            if len(distinct) > 2:
                sys.exit(
                    "Stopped: a third distinct response, so the data changed during the command."
                )
            if number >= 4 and len(distinct) == 1:
                sys.exit(
                    "Stopped: four writes returned one response, so A and B can't be told apart."
                )
    conclude(done, args, quota)
    save_summary(folder, done, args)


def send_write(
    provider: P123ScreenBacktestClient,
    write: Write,
    definition: str,
    backtest: dict[str, object],
    between: tuple[int | None, float],
    folder: Path,
    quota: list[tuple[int, int]],
) -> bool:
    """Sends one write's calls, as an attempt sends them, and records what the summary may hold:
    between the `rank_update` and the backtest, the `rank_touch` of the system ID, when given,
    then the pause, in seconds. Returns whether every call succeeded."""
    system_id, pause = between
    stem = folder / f"write-{write.number:02d}"
    params = {
        "type": "stock",
        "nodes": definition,
        "rankingMethod": RANKING_METHOD,
        "currency": "USD",
    }
    before = len(provider.exchanges)
    updated = call(
        provider, lambda: provider.rank_update(params), stem.with_name(stem.name + "-rank-update")
    )
    ended = time.monotonic()
    if updated is None:
        write.exchanges = exchanges(provider, before)
        return False
    if system_id is not None:
        # The wrapper's rank_touch returns nothing; a 200 without a JSON body is a success too.
        # The client's private call keeps its classification of a failure.
        touch = provider._request(
            # Trial Folio's typed view of the wrapper leaves out rank_touch, which it never sends.
            lambda: provider._wrapper.rank_touch(system_id),  # pyright: ignore[reportAttributeAccessIssue]
            RANK_UPDATE,
        )
        if isinstance(touch, ProviderError):
            write.exchanges = exchanges(provider, before)
            print(f"  Write {write.number}: rank_touch failed: {touch.code}.")
            return False
    if pause:
        time.sleep(pause)
    started = time.monotonic()
    tested = call(
        provider,
        lambda: provider.screen_backtest(backtest),
        stem.with_name(stem.name + "-backtest"),
    )
    write.gap_seconds = round(started - ended, 3)
    write.exchanges = exchanges(provider, before)
    for response in (updated, tested):
        if response is not None:
            cost, left = response.get("cost"), response.get("quotaRemaining")
            write.credits_reported += cost if isinstance(cost, int) else 0
            if isinstance(cost, int) and isinstance(left, int):
                quota.append((cost, left))
    if tested is None:
        return False
    write.response = fingerprint(tested)
    return True


def call(
    provider: P123ScreenBacktestClient,
    send: Callable[[], ScreenBacktestResponse | None],
    stem: Path,
) -> dict[str, object] | None:
    """Makes one call, and saves its response as `<stem>.json`. Returns the decoded response, or
    None when the call failed, or returned a body the wrapper couldn't decode."""
    ignore_key_log()
    try:
        response = send()
    except ProviderError as error:
        print(f"  {stem.name}: failed: {error.code}.")
        return None
    if response is None:  # Authentication returns nothing.
        return {}
    if not isinstance(response, DecodedResponse) or not isinstance(response.payload, dict):
        print(f"  {stem.name}: its 200's body isn't a JSON object the wrapper decoded.")
        return None
    stem.with_suffix(".json").write_text(json.dumps(response.payload, indent=2), encoding="utf-8")
    return response.payload  # pyright: ignore[reportUnknownVariableType]


def conclude(done: list[Write], args: argparse.Namespace, quota: list[tuple[int, int]]) -> None:
    """Labels each write by the response most writes of each definition returned."""
    usual: dict[str, str | None] = {}
    for name in ("A", "B"):
        counts = Counter(w.response for w in done if w.definition == name and w.response)
        ranked = counts.most_common(2)
        if not ranked or (len(ranked) == 2 and ranked[0][1] == ranked[1][1]):
            print(f"No response is the usual one for definition {name}, so no write is labeled.")
            return
        usual[name] = ranked[0][0]
    if usual["A"] == usual["B"]:
        print("A and B usually return the same response, so no write is labeled.")
        return
    for w in done:
        other = "A" if w.definition == "B" else "B"
        w.label = (
            "fresh"
            if w.response == usual[w.definition]
            else "stale"
            if w.response == usual[other]
            else "other"
        )
    labels = Counter(w.label for w in done)
    print(f"Labels: {', '.join(f'{w.number}{w.definition} {w.label}' for w in done)}.")
    print(f"Counts: fresh {labels['fresh']}, stale {labels['stale']}, other {labels['other']}.")
    if args.references:
        for name, path in zip(("A", "B"), args.references, strict=True):
            same = fingerprint(json.loads(path.read_bytes())) == usual[name]
            print(f"Definition {name}'s response is the reference's: {'yes' if same else 'no'}.")
    reported = sum(w.credits_reported for w in done)
    print(f"Credits reported: {reported}.")
    if quota:
        # Before the first response, the remaining credits were its own plus its cost.
        fall = quota[0][1] + quota[0][0] - quota[-1][1]
        print(f"Remaining credits fell by {fall}, from before the first write to after the last.")


def report(write: Write) -> None:
    gap = f"{write.gap_seconds:.3f} s" if write.gap_seconds is not None else "not sent"
    print(
        f"  Write {write.number} ({write.definition}): {write.exchanges}; to the backtest: {gap}."
    )


def save_summary(folder: Path, done: list[Write], args: argparse.Namespace) -> None:
    summary = {
        "touch": args.touch,
        "pause_seconds": args.pause,
        "writes": [asdict(w) for w in done],
    }
    (folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


# The system's ID


def read_id(payloads: Path, compare: list[Path] | None, budget: int) -> None:
    if budget < CREDITS["rank_get"]:
        sys.exit("A rank_get costs 1 credit, over the budget. Nothing sent.")
    ignored(payloads)
    with client() as provider:
        if call(provider, provider.authenticate, payloads / "id-authentication") is None:
            sys.exit("Stopped: authentication failed. Nothing else was sent.")
        record = call(provider, lambda: provider.rank_get(SYSTEM), payloads / "id-rank-get")
    if record is None:
        sys.exit("Stopped: the rank_get failed.")
    system_id = record.get("id")
    (payloads / SYSTEM_ID_FILE).write_text(json.dumps({"id": system_id}), encoding="utf-8")
    print(
        f"rank_get of {SYSTEM}: ID present and saved: {isinstance(system_id, int)}. "
        f"Ranking method: {record.get('rankingMethod')}. Credits reported: {record.get('cost')}."
    )
    if compare is not None:
        held = str(record.get("xml") or "")
        for name, path in zip(("A", "B"), compare, strict=True):
            sent = read_text(path)
            same_tree = ET.canonicalize(sent, strip_text=True) == ET.canonicalize(
                held, strip_text=True
            )
            print(f"  Holds definition {name}: byte for byte: {sent == held}; as XML: {same_tree}.")


def saved_id(payloads: Path) -> int:
    path = payloads / SYSTEM_ID_FILE
    if not path.exists():
        sys.exit(f"--touch needs {SYSTEM}'s ID: run the id command first. Nothing sent.")
    value = json.loads(path.read_text(encoding="utf-8")).get("id")
    if not isinstance(value, int):
        sys.exit(f"{path.name} holds no ID. Nothing sent.")
    return value


# Helpers


def client() -> P123ScreenBacktestClient:
    ignore_key_log()
    credentials = Credentials(
        os.environ["TRIALFOLIO_P123_API_ID"], os.environ["TRIALFOLIO_P123_API_KEY"]
    )
    return P123ScreenBacktestClient(credentials)


def exchanges(provider: P123ScreenBacktestClient, since: int) -> list[str]:
    """Each exchange's method, path, and status, or how it ended without one, with the system's
    ID in `rank_touch`'s path written as `<id>`."""
    return [
        TOUCH_PATH.sub(
            "/rank/<id>/touch", f"{e.request} {e.status if e.status is not None else e.result}"
        )
        for e in provider.exchanges[since:]
    ]


def ignored(path: Path) -> None:
    """Stops unless Git ignores `path`, so no response can be committed by mistake."""
    found = subprocess.run(
        [
            "git",
            "-C",
            str(path.parent if path.parent.exists() else Path.cwd()),
            "check-ignore",
            "-q",
            str(path.resolve()),
        ],
        check=False,
        stderr=subprocess.DEVNULL,
    )
    if found.returncode != 0:
        sys.exit(
            f"{path} isn't ignored by Git; the responses must never be committed. Nothing sent."
        )


def fingerprint(response: dict[str, object]) -> str:
    """A hash of the response without `cost` and `quotaRemaining`, for comparing responses
    without printing them."""
    rest = {k: v for k, v in response.items() if k not in ("cost", "quotaRemaining")}
    canonical = json.dumps(rest, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def read_text(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as source:
        return source.read()


def ignore_key_log() -> None:
    """Removes `SSLKEYLOGFILE` from the process environment, with a warning, as Trial Folio's CLI
    does (docs/contracts.md, credentials)."""
    if os.environ.pop(KEY_LOG, None) is not None:
        print(
            f"Warning: {KEY_LOG} is set; diagnose.py ignores it, and removed it from its own "
            "environment. Your shell is unaffected.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
