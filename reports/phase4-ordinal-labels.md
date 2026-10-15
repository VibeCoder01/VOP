# Ordinal answer labels — 15 October 2026

Changed `src/vop/dashboard.py`, `tests/test_ordinal_labels.py`, `README.md`,
`CHANGELOG.md` and this report. Implements QRY-003/QRY-004 and preserves INF-004/MET-008.

Capture results, latest answers, recent observations, the observation list and inspection
show configured ordinal level descriptions. Fractional expected positions are described as
between adjacent levels. Historical observations load their immutable question version.
Stored numeric values, provider fields, probabilities and trend calculations are unchanged.
Level text is escaped by FastHTML. Failed/missing answers remain Unknown.

Commands and actual results:

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_ordinal_labels.py`: 9 passed.
- `.\.venv\Scripts\python.exe -m pytest -q`: 281 passed, 4 skipped in 41.00 s.
  The skips are Linux-only helper tests on Windows.
- `.\.venv\Scripts\python.exe tools\phase4_smoke.py`: PASS; explicit mock worker over
  actual loopback HTTP; restart persistence 3 observations; browser form and Windows DPAPI
  protection passed; weights not loaded, cameras not connected.
- `git diff --check`: passed.

No camera, GPU or model tests were run for this presentation change. No new measurements,
dependencies, schema or model revisions. Existing approved Liquid revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`.

An expected level is not the most probable category and is not a calibrated probability.
Raw probabilities remain in technical details. Trends retain numeric positions with a named
level legend and an explanation. Existing camera connectivity issues are outside this fix.

Recommendation: review the named ordinal results in the current Phase 4 pilot. Phase 5
remains unauthorised.
