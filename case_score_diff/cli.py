import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path
import sys


class InputError(ValueError):
    pass


def reject_constant(value: str) -> None:
    raise InputError(f"{value} is not a JSON number")


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate JSON field {json.dumps(key)}")
        result[key] = value
    return result


def checked_number(value: object) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise InputError("expected a finite JSON number")
    parts = value.as_tuple()
    if len(parts.digits) > 1000 or not -1000 <= parts.exponent <= 1000:
        raise InputError("number exceeds the supported precision or exponent")
    return value


def read_scores(path: Path) -> dict[str, Decimal]:
    scores = {}
    with path.open(encoding="utf-8-sig") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(
                    line, parse_float=Decimal, parse_int=Decimal,
                    parse_constant=reject_constant, object_pairs_hook=unique_object,
                )
                if not isinstance(record, dict):
                    raise InputError("expected an object with id and score fields")
                case_id = record.get("id")
                if not isinstance(case_id, str) or not case_id.strip():
                    raise InputError("id must be a non-blank string")
                if case_id in scores:
                    raise InputError(f"duplicate case id {json.dumps(case_id)}")
                scores[case_id] = checked_number(record.get("score"))
            except (ValueError, InvalidOperation, RecursionError) as error:
                raise InputError(f"{path}:{line_number}: {error}") from None
    return scores


def checked_tolerance(text: str) -> Decimal:
    try:
        value = checked_number(Decimal(text))
    except (InvalidOperation, InputError) as error:
        raise argparse.ArgumentTypeError("tolerance must be a supported finite decimal") from error
    if value < 0:
        raise argparse.ArgumentTypeError("tolerance must be nonnegative")
    return value


def compare(
    baseline: dict[str, Decimal],
    candidate: dict[str, Decimal],
    direction: str,
    tolerance: Decimal,
) -> dict:
    counts = Counter(dict.fromkeys(
        ("missing", "regressed", "within_tolerance", "improved", "added"), 0
    ))
    cases = []
    with localcontext() as context:
        # Enough digits for the difference of two supported numbers to be exact.
        context.prec = 3001
        for case_id in sorted(baseline.keys() | candidate.keys()):
            old = baseline.get(case_id)
            new = candidate.get(case_id)
            delta = None
            if new is None:
                status = "missing"
            elif old is None:
                status = "added"
            else:
                delta = new - old
                gain = delta if direction == "higher" else -delta
                if gain < -tolerance:
                    status = "regressed"
                elif gain > tolerance:
                    status = "improved"
                else:
                    status = "within_tolerance"
            counts[status] += 1
            cases.append({
                "id": case_id,
                "baseline": str(old) if old is not None else None,
                "candidate": str(new) if new is not None else None,
                "delta": str(delta) if delta is not None else None,
                "status": status,
            })
    return {
        "direction": direction,
        "tolerance": str(tolerance),
        "passed": counts["missing"] == counts["regressed"] == 0,
        "counts": dict(counts),
        "cases": cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="case-score-diff",
        description="Compare two JSONL evaluation runs by case ID.",
    )
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--direction", choices=("higher", "lower"), default="higher")
    parser.add_argument("--tolerance", type=checked_tolerance, default=Decimal(0))
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    args = parser.parse_args(argv)

    try:
        baseline = read_scores(args.baseline)
        if not baseline:
            raise InputError(f"{args.baseline}: baseline has no cases")
        candidate = read_scores(args.candidate)
    except (OSError, ValueError) as error:
        print(f"case-score-diff: {error}", file=sys.stderr)
        return 2

    report = compare(baseline, candidate, args.direction, args.tolerance)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for case in report["cases"]:
            print(
                case["status"], json.dumps(case["id"]),
                f'baseline={case["baseline"] if case["baseline"] is not None else "absent"}',
                f'candidate={case["candidate"] if case["candidate"] is not None else "absent"}',
            )
        print("PASS" if report["passed"] else "FAIL")
        print("  ".join(f"{label}={count}" for label, count in report["counts"].items()))
    return 0 if report["passed"] else 1
