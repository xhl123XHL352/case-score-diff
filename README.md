# case-score-diff

Compare two saved evaluation runs by case ID. Use this CLI to catch individual
score regressions or missing cases before an aggregate score hides them. It
runs offline and works with exported scores from any evaluator.

## Install

Requires Python 3.10+. The CLI has no Python runtime dependencies.

~~~sh
pipx install git+https://github.com/xhl123XHL352/case-score-diff.git
~~~

## Try it

~~~sh
printf '%s\n' '{"id":"checkout","score":0.9}' '{"id":"search","score":0.7}' > before.jsonl
printf '%s\n' '{"id":"search","score":0.9}' '{"id":"checkout","score":0.8}' > after.jsonl
case-score-diff before.jsonl after.jsonl --tolerance 0.02
~~~

`search` improved. `checkout` dropped by 0.1, so the comparison exits `1`
even though the combined score went up.

Use `--direction lower` for metrics such as latency. Use `--json` for a
CI artifact with counts and every case in ID order. JSON preserves scores,
deltas, and tolerance as decimal strings.

## Input and result

Use one UTF-8 JSON object per line with a non-blank string `id` and a finite
numeric `score`. IDs must be unique within each file. Blank lines are
skipped and extra fields are accepted. Keep the same metric and scoring
configuration on both sides. The baseline must contain at least one case.

The tolerance is inclusive: a drop equal to the tolerance counts as within
tolerance. New cases are reported without affecting the result. Missing
baseline cases always fail the comparison.

- **0** All baseline cases are present and within tolerance or improved.
- **1** At least one baseline case is missing or regressed.
- **2** An input or command-line error prevented comparison.

## Tests

~~~sh
python -m unittest discover -s tests -v
~~~
