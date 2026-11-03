# Flaky tests

Tests known to fail now and then on shared CI runners, what is supposed to cause it, and since when.
Policy (post-mortem 0.28.0, P1 #8):

- A test that fails on runners only is marked, never skipped there and never loosened case by case:
  `@pytest.mark.runner_flaky(reason="...", issue="...")` (both keywords required).
- On CI (env `CI` set) `tests/conftest.py` turns the marker into `flaky(reruns=2)` (pytest-rerunfailures):
  a flake never blocks a release, the rerun shows in the log. Locally it runs once: a failure here is red.
- Every marked test is listed below (`tests/test_test_rules.py` checks it). Once the cause is found and fixed,
  remove the marker and move the entry to "Fixed" with the cause.
- Time budgets scale with the machine speed (`tests/_speed.py`), not with the marker.

## Marked `runner_flaky`

| Test | Supposed cause | Seen | Since |
|---|---|---|---|
| (none) | | | |

## Fixed

| Test | Cause | Fix | Date |
|---|---|---|---|
| 6 menu & focus tests of `test_ui_audit_2026_10_29_*` (`test_source_control_switches_between_file_and_game_session`, `test_header_toolbar_actions`, `test_menu_closed_by_second_click`, `test_number_input_keys_step_enter_and_escape`, `test_compare_and_checked_laps_menus`, `test_menu_toggle_below_closes_on_second_click`) | Not the runner: Windows "Animation effects" are off there (`SPI_GETCLIENTAREAANIMATION`), so motion tokens are 0 and popups have no transitions. `TpMenu.toggleBelow` read `toggleSource` after `close()`, whose `onClosed` (synchronous without exit transition) had reset it: the second click opened the menu again. `TpDialogHost` focused its field in `onOpened`, synchronous without enter transition, before `kind` & `visible` followed the request. A real bug for users with animation effects off. | `TpMenu` keeps the source before `close()`; `TpDialogHost` focuses in `Qt.callLater`. Skips removed; `tests/test_animations_off.py` runs both with motion off on every OS. | 2026-11-02 |
| `test_login_body_size_bounded` (tests/test_web_dashboard.py) | The dashboard closed the connection with the request body unread: the socket sent a reset, which dropped the response before the client read it (Windows drops received data on a reset). About 1 in 200 locally, the hook now and then. | Lingering close: `DashboardHandler.finish` drains a body left unread (1 s, 64 KB at most) before closing. The test reads the response 0.2 s late, so it failed every time without the fix. | 2026-11-02 |
| `test_page_engine_loads_nothing_from_network` (tests/test_security_lot_a.py) | The control half waits for a plain network manager's first request, which sets up Qt networking (system proxy lookup on Windows): 5 s and more on a busy machine. | Wait up to 30 s (only the slow case waits longer). | 2026-11-02 |
| `test_ui_thread_budget*`, `test_stats_results_perf` budgets | Bounds in ms written on a fast desktop; runners are slower. | `tests/_speed.py`: bounds x speed factor of the machine (1 to 6). | 2026-11-02 |
| `test_lap_viewer_settings_within_budget` (tests/test_ui_thread_budget.py) | One setting change took 70 ms once on Python 3.11 (5 ms the other times): a pause of the machine (full garbage collection over the long laps), not the slot. | Each setting changed 3 times, best time asserted. | 2026-11-02 |
| `test_groups_not_synced_while_hidden` (tests/test_audit_i_f.py) | 1 or 2 syncs depending on runner timing. | Accepts 1-2 syncs (`4b9f5c2`). | 2026-10-31 |
| `test_delta_best_lap` (tests/test_module_replay.py) | File written by the data saver thread, read before it was done. | `run_delta` waits for the saver (`63626cc`). | 2026-10-31 |

## Open, not marked

| Test | Supposed cause | Seen | Since |
|---|---|---|---|
| `test_display_orders_move_items[modern]` (tests/test_option_probes.py) | **Order dependence, not the runner**: fails every time after `tests/test_widget_text_fit.py::test_modern_text_fits_cells` (any parameter) in the same process: the modern Trailing and Black box pictures no longer change when display orders are swapped (the pairs listed are those of the classic design). Not caused by the shape, background or lru caches, deferred deletes, the language, `OverlayStyle`, black box memory or the paint counter (each reset tried). A rerun in the same process fails again, so not marked. Reproduce: `pytest "tests/test_widget_text_fit.py::test_modern_text_fits_cells[English-metric]" "tests/test_option_probes.py::test_display_orders_move_items[modern]"` | Linux 3.11 runner (0.28.0 CI run 5), local random order | 2026-10-31 |
| `test_local_server_short_poll_interval` (tests/test_audit_g_runtime_widgets.py), `test_hidden_page_updated_once_shown` (tests/test_lap_viewer_fix_backend.py) | Busy machine: full 3.11 run with `-n auto` while other suites ran (stop in 0.1 s, a page refresh) | local 3.11, once | 2026-11-02 |
| `test_concurrent_reads_and_appends` (tests/test_driver_stats_background.py) | One record of 200 lost by the cached history read, Linux only (post-mortem P2 #13, being instrumented) | Linux 3.11 / 3.13 runners, 2 runs of 10 | 2026-10-31 |
