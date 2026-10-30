# Configure navigation order — 30 October 2026

Configure now lists Questions, Actions, Automations, Cameras, Engines, Settings,
Diagnostics, in that order. View-mode navigation and mode-switch behaviour are
unchanged. Updated `src/vop/dashboard.py`, the existing order assertions in
`tests/test_ui_modes.py` and README navigation documentation. No version, dependency,
storage, capture or inference change was needed.

`.venv\Scripts\python.exe -m pytest -q tests/test_ui_modes.py`: **4 passed in 6.32
seconds**, using offline TestClient markup. Authenticated managed restart returned
**HTTP 202** and a new **ready** instance. `git diff --check` passed. Full CI status
is available on the PR; no passing CI is claimed without its result.

No manual browser visual, camera, model/GPU or physical-action tests were run;
model revision and hardware measurements are unchanged. Remain in Phase 5 and
confirm the requested order after refreshing the owner browser. No Phase 6 work
or auto-merge.
