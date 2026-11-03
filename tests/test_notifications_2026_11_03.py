"""Notifications (2026-11-03): history kept between sessions, repeats grouped, messages in app language, levels,
Windows notifications (interval, hold while driving, kinds, click action), notification center (filter, days, copy,
undo), modes under Now (no status chips), race reminders (actions, overlay, sound, timer), shared toast times"""

from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QDateTime, QEvent
from PySide6.QtWidgets import QMainWindow, QSystemTrayIcon

from neopedal import i18n, overlay_messages
from neopedal.setting import cfg


def flush():
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture(autouse=True)
def fresh_app_messages(monkeypatch):
    """App messages posted by an earlier test never skipped as repeated"""
    monkeypatch.setattr(overlay_messages, "_last_posted", {})


@pytest.fixture
def store(ui_env):
    from neopedal.ui.notification import NotificationStore

    created = NotificationStore(history=False)
    yield created
    created.deleteLater()


@pytest.fixture
def french():
    i18n.set_language("Français")
    yield
    i18n.set_language("English")


# --- Messages: text in app language, repeats grouped, clear & undo, highest unread level
def test_message_text_follows_language(french):
    from neopedal.ui.notification import message_text

    parts = (("%1 starts in %2 min", ("LMP2 Fixed", "10")), ("(%1)", ("Monza",)))
    assert message_text(parts) == "LMP2 Fixed commence dans 10 min (Monza)"
    i18n.set_language("English")
    assert message_text(parts) == "LMP2 Fixed starts in 10 min (Monza)"
    assert message_text("Unable to open game shared memory, see log for details.").startswith("Unable")
    assert message_text((("%1 and %10", tuple(str(number) for number in range(1, 11))),)) == "1 and 10"


def test_repeat_within_window_counted_and_moved_up(store):
    from neopedal.ui import notification

    store.add("Overlay crashed", "error")
    store.add("Update found", "info")
    store.add("Overlay crashed", "error")  # repeated, under another one: counted, moved to the top
    entries = store.entries()
    assert [entry["source"] for entry in entries] == ["Overlay crashed", "Update found"] and entries[0]["count"] == 2
    entries[0]["time"] = QDateTime.currentDateTime().addSecs(-notification.REPEAT_SECONDS - 5)
    store.add("Overlay crashed", "error")  # older than the window: a new message
    assert len(store.entries()) == 3 and store.entries()[0]["count"] == 1
    store.add("Overlay crashed", "warning")  # other level: a new message
    assert len(store.entries()) == 4


def test_clear_undo_and_unread_level(store):
    store.add("Saved", "info")
    store.add("Cut to screen", "warning")
    assert store.unread_severity() == "warning"
    store.add("Crashed", "error")
    assert store.unread_severity() == "error"
    store.mark_all_read()
    assert store.unread_severity() == ""
    removed = store.clear()
    assert len(removed) == 3 and not store.entries()
    store.add("New one", "info")
    store.restore(removed)
    assert [entry["source"] for entry in store.entries()] == ["New one", "Crashed", "Cut to screen", "Saved"]
    store.restore(removed)  # already back: not twice
    assert len(store.entries()) == 4


def test_history_kept_between_sessions(ui_env):
    from neopedal.ui.notification import HISTORY_FILE, NotificationStore
    from neopedal.ui.quick.page_settings import settings_path, write_settings

    first = NotificationStore()
    first.add((("%1 starts in %2 min", ("LMP2 Fixed", "10")),), "info", (("Open Upcoming Races", "tool:x"),))
    first.add("Overlay crashed", "error")
    first.mark_all_read()
    first.flush()  # app quitting: written at once
    second = NotificationStore()
    entries = second.entries()
    assert [entry["source"] for entry in entries] == [
        "Overlay crashed", (("%1 starts in %2 min", ("LMP2 Fixed", "10")),)]
    assert entries[1]["actions"] == [{"label": "Open Upcoming Races", "key": "tool:x"}] and entries[0]["read"]
    assert entries[0]["time"].toMSecsSinceEpoch() == first.entries()[0]["time"].toMSecsSinceEpoch()
    # Broken file or entries: skipped, never an error
    write_settings(HISTORY_FILE, {"messages": [{"text": 3}, {"text": "ok", "severity": "bad", "time": 1, "count": 1},
                                               {"text": [["%1", ["a"]]], "severity": "info", "time": 1, "count": 1},
                                               "junk"]})
    third = NotificationStore()
    assert [entry["source"] for entry in third.entries()] == [(("%1", ("a",)),)]
    with open(settings_path(HISTORY_FILE), "w", encoding="utf-8") as file:
        file.write("{not json")
    assert NotificationStore().entries() == []
    for made in (first, second, third):
        made.deleteLater()
    flush()


# --- Levels of background messages: toast of the level (no check mark on an error), overlay told
def test_background_message_toast_level_and_overlay(ui_env, monkeypatch):
    from neopedal.ui import app
    from neopedal.ui.notification import notification_store

    toasts = []
    monkeypatch.setattr(app, "show_toast", lambda window, text, **kwargs: toasts.append((text, kwargs)))
    shown = SimpleNamespace(isVisible=lambda: True, isMinimized=lambda: False)
    bar = SimpleNamespace(window=lambda: shown)
    serial = overlay_messages.last_serial()
    app.StatusButtonBar.show_message(bar, "Telemetry recorder: unable to save lap 3, see log for details.", "error",
                                     ())
    app.StatusButtonBar.show_message(bar, "Speedometer is too big (9 x 9), cut to 5 x 5: lower its size options "
                                          "or scale.", "warning", ())
    assert [kwargs["level"] for _, kwargs in toasts] == ["error", "warning"]
    assert not toasts[0][0].startswith("⚠")  # level told by the toast icon & border
    posted = overlay_messages.since(serial)
    assert [(message.title, message.level) for message in posted] == [("Error", "error"), ("Warning", "warning")]
    store = notification_store()
    assert store.entries()[0]["severity"] == "warning" and store.entries()[1]["severity"] == "error"
    store.clear()


def test_warning_signal_sources():
    import inspect

    from neopedal import api_connector, thread_guard, vr_overlay
    from neopedal.widget import _base

    assert "app_signal.warning.emit(f\"{name} crashed and was restarted" in inspect.getsource(thread_guard)
    assert "app_signal.warning.emit(f\"Replay not compatible" in inspect.getsource(api_connector)
    assert "app_signal.warning.emit(\"VR overlay: restart the VR game" in inspect.getsource(vr_overlay)
    assert "app_signal.warning.emit(\n" in inspect.getsource(_base)


# --- Windows notifications
@pytest.fixture
def relay(ui_env, monkeypatch):
    from neopedal.ui import notification

    messages = []
    monkeypatch.setattr(QSystemTrayIcon, "showMessage",
                        lambda self, title, text, icon, duration: messages.append((text, icon)))
    monkeypatch.setattr(QSystemTrayIcon, "isVisible", lambda self: True)
    monkeypatch.setattr(QSystemTrayIcon, "supportsMessages", staticmethod(lambda: True))
    window = QMainWindow()  # hidden: errors told by tray messages
    QSystemTrayIcon(window)
    made = notification.TrayRelay(window)
    store = notification.notification_store()
    store.clear()
    yield made, messages, store
    store.added.disconnect(made.message_added)
    store.clear()
    window.deleteLater()
    flush()


def test_tray_messages_counted_meanwhile_told_at_end_of_interval(relay):
    made, messages, store = relay
    store.add("First error", "error")
    store.add("Second error", "warning")
    store.add("Third error", "error")
    assert [text for text, _ in messages] == ["First error"] and made._flush_timer.isActive()
    made.flush()  # end of the interval
    assert messages[-1][0] == "2 new messages, last one: Third error"
    assert messages[-1][1] == QSystemTrayIcon.MessageIcon.Critical and not made._waiting
    made.flush()  # nothing left
    assert len(messages) == 2


def test_tray_messages_held_while_driving_and_kind_off(relay, monkeypatch):
    from neopedal import realtime_state

    made, messages, store = relay
    cfg.notification["enable_hold_notifications_while_driving"] = True
    monkeypatch.setattr(realtime_state, "active", True)
    store.add("Recorder failed", "error")
    assert messages == [] and not made._flush_timer.isActive()  # no polling: told once driving stops
    made.flush()  # still driving
    assert messages == []
    monkeypatch.setattr(realtime_state, "overriding", True)  # active state override: not driving, not held
    assert not made.holding()
    monkeypatch.setattr(realtime_state, "overriding", False)
    monkeypatch.setattr(realtime_state, "active", False)
    from neopedal import overlay_signal

    overlay_signal.driving.emit(False)  # overlay control: driving stopped
    assert [text for text, _ in messages] == ["Recorder failed"]
    cfg.notification["show_tray_messages_for_errors"] = False
    made._last -= 1000
    store.add("Other failure", "error")
    assert len(messages) == 1  # errors turned off: in the notification center only
    assert made.show("Race soon", kind="reminder") and messages[-1][0] == "Race soon"
    cfg.notification["show_tray_messages_for_race_reminders"] = False
    assert not made.show("Race soon", kind="reminder")
    assert made.show("Still running", kind="app")  # app messages always told


def test_tray_message_click_runs_its_action(relay, monkeypatch):
    from neopedal.ui import notification

    made, _messages, _store = relay
    actions = []
    monkeypatch.setattr(notification, "run_notification_action", lambda window, key: actions.append(key))
    made.show("LMP2 Fixed starts in 10 min", action="tool:race_schedule_viewer.RaceScheduleViewer")
    made.clicked()
    made.show("Update available", action="updates")
    made.clicked()
    assert actions == ["tool:race_schedule_viewer.RaceScheduleViewer", "updates"]
    # Several told while the window is hidden: Windows does not say which one was clicked, the center lists them
    made.show("LMP2 Fixed starts in 10 min", action="tool:race_schedule_viewer.RaceScheduleViewer")
    made.show("Update available", action="updates")
    made.clicked()
    assert actions[-1] == notification.CENTER_ACTION
    made.clicked()  # clicked again: nothing told since, the center
    assert actions[-1] == notification.CENTER_ACTION
    # First close to the tray told (window shown only) before a reminder: the click still opens Upcoming Races
    made.show("NeoPedal keeps running in the notification area")
    made.show("LMP2 Fixed starts in 10 min", action="tool:race_schedule_viewer.RaceScheduleViewer")
    made.clicked()
    assert actions[-1] == "tool:race_schedule_viewer.RaceScheduleViewer"


# --- Notification center: filter, days, copy, undo, translated labels
def test_center_filter_days_copy_and_undo(ui_env):
    from PySide6.QtGui import QGuiApplication

    from neopedal.ui.notification import notification_store
    from neopedal.ui.quick.notify_backend import NotificationBackend

    store = notification_store()
    store.clear()
    store.add("Saved stats", "info")
    store.add("Overlay crashed", "error", (("View Log", "log"),))
    store.entries()[1]["time"] = QDateTime.currentDateTime().addDays(-1)
    backend = NotificationBackend(None)
    try:
        assert backend.counts == {"error": 1, "warning": 0, "info": 1}
        assert [row["day"] for row in backend.model.rows] == ["Today", "Yesterday"]
        assert backend.model.rows[0]["actions"] == [{"label": "View Log", "key": "log"}]
        backend.setFilter("info")
        assert [row["text"] for row in backend.model.rows] == ["Saved stats"] and backend.filter == "info"
        backend.copyText(backend.model.rows[0]["entryId"])
        assert QGuiApplication.clipboard().text() == "Saved stats"
        backend.setFilter("bogus")
        assert backend.filter == "" and len(backend.model.rows) == 2
        backend.setFilter("info")
        store.remove(store.entries()[1]["id"])  # no message left at this level: every message shown
        assert backend.filter == "" and [row["text"] for row in backend.model.rows] == ["Overlay crashed"]
        backend.clearAll()
        assert backend.entryCount == 0 and backend.canUndoClear
        backend.undoClear()
        assert backend.entryCount == 1 and not backend.canUndoClear
    finally:
        store.clear()
        backend.deleteLater()
        flush()


def test_center_labels_in_french(ui_env, french):
    from neopedal.ui.notification import error_actions, notification_store
    from neopedal.ui.quick.notify_backend import NotificationBackend

    store = notification_store()
    store.clear()
    store.add("Telemetry recorder: unable to save lap 3, see log for details.", "error", error_actions())
    backend = NotificationBackend(None)
    try:
        row = backend.model.rows[0]
        assert [action["label"] for action in row["actions"]] == ["Voir le journal", "Créer un rapport de bug…"]
        assert row["day"] == "Aujourd'hui" and not row["text"].startswith("Telemetry recorder")
    finally:
        store.clear()
        backend.deleteLater()
        flush()


# --- Modes listed under Now, no status chips
def test_modes_listed_under_now(ui_env):
    from neopedal.ui.notification import NotifyBar, notification_store

    bar = NotifyBar(None)
    try:
        cfg.user.config["telemetry"]["enable_auto_backup_car_setup"] = True
        bar.refresh()
        listed = notification_store().active()
        assert ("Auto Backup Car Setup Enabled", "option:telemetry/enable_auto_backup_car_setup") in listed
        cfg.notification["notify_auto_backup_car_setup"] = False
        bar.refresh()
        assert not [text for text, _ in notification_store().active() if text.startswith("Auto Backup")]
        assert bar.updates.isHidden() and len(bar.children()) == 2  # layout & update chip only
    finally:
        notification_store().set_active([])
        bar.deleteLater()
        flush()


def test_option_action_opens_settings_at_option(ui_env, monkeypatch):
    from neopedal.ui import app_settings, notification

    opened = []
    monkeypatch.setattr(app_settings, "open_app_settings", lambda *args: opened.append(args))
    window = SimpleNamespace(show_app=lambda: None)
    notification.run_notification_action(window, "option:telemetry/enable_auto_backup_car_setup")
    assert opened == [(window, "telemetry", "enable_auto_backup_car_setup")]
    shown = []
    window.centralWidget = lambda: SimpleNamespace(show_notification_center=lambda: shown.append(1))
    notification.run_notification_action(window, notification.CENTER_ACTION)
    assert shown == [1]


# --- Race reminders
def test_reminder_told_everywhere_and_timer_only_while_set(ui_env, monkeypatch):
    from neopedal.ui import notification
    from neopedal.ui.quick import schedule_reminders as sr

    now = [1_000_000.0]
    tray, sounds = [], []
    monkeypatch.setattr(notification, "tray_message", lambda *args, **kwargs: tray.append((args, kwargs)) or True)
    monkeypatch.setattr(sr, "play_reminder_sound", lambda: sounds.append(1))
    monkeypatch.setattr(sr, "windows_hides_notifications", lambda: False)  # CI runners have no desktop: hidden
    store = notification.notification_store()
    store.clear()
    reminders = sr.RaceReminders(clock=lambda: now[0])
    try:
        assert not reminders._timer.isActive()  # nothing to check
        reminders.set("race@1", "LMP2 Fixed", "Monza", now[0] + 1200, 10)
        assert reminders._timer.isActive()
        serial = overlay_messages.last_serial()
        now[0] += 600
        reminders.check()
        assert not reminders._timer.isActive() and sounds == []  # Windows shows notifications: no sound
        entry = store.entries()[0]
        assert notification.message_text(entry["source"]) == "LMP2 Fixed starts in 10 min (Monza)"
        assert entry["actions"][0] == {"label": "Open Upcoming Races", "key": sr.SCHEDULE_ACTION}
        assert entry["actions"][1]["label"] == "Remind Me in 2 Min"
        assert tray[0][0] == ("LMP2 Fixed starts in 10 min (Monza)", "info", sr.SCHEDULE_ACTION, "reminder")
        assert [(message.title, message.detail) for message in overlay_messages.since(serial)] == [
            ("Reminder", "LMP2 Fixed · 10 min")]
        cfg.notification["race_reminder_sound"] = sr.SOUND_ALWAYS
        reminders.set("race@2", "GT3", "", now[0] + 120, 5)
        reminders.check()
        assert sounds == [1]
        assert store.entries()[0]["actions"] == [{"label": "Open Upcoming Races", "key": sr.SCHEDULE_ACTION}]
        # no Remind Me in 2 Min: starts too soon
    finally:
        store.clear()
        reminders.deleteLater()
        flush()


def test_default_reminder_minutes_option(ui_env):
    from neopedal.ui.quick import schedule_reminders as sr

    assert sr.default_minutes() == 10 and sr.reminder_choices() == (5, 10, 30)
    cfg.notification["number_of_minutes_before_race_reminder"] = 15
    assert sr.default_minutes() == 15 and sr.reminder_choices() == (5, 10, 15, 30)
    cfg.notification["number_of_minutes_before_race_reminder"] = True  # broken value: default
    assert sr.default_minutes() == 10


# --- Race Notifications overlay: app messages while driving
@pytest.mark.parametrize("modern", [False, True])
def test_race_notifications_show_app_messages(ui_env, bundled_fonts, modern):
    from neopedal.widget._modern import create_widget as make

    cfg.user.config["overlay_style"]["overlay_theme"] = "Modern Dark" if modern else "Legacy Dark"
    overlay_messages.post("Reminder", "before start")  # posted before the overlay started: never shown
    widget = make(import_module("neopedal.widget.race_notifications"), cfg, "race_notifications")
    try:
        overlay_messages.post("Reminder", "LMP2 Fixed · 10 min")
        overlay_messages.post("Error", "Recorder failed", "error")
        shown = [(message.title, message.detail, message.kind) for message, _ in widget.read_notifications()]
        assert ("Reminder", "LMP2 Fixed · 10 min", 3) in shown and ("Error", "Recorder failed", 1) in shown
        assert not [item for item in shown if item[1] == "before start"]
        assert widget.read_notifications() and len(widget.toasts) == 2  # read once
        widget.show_app_messages = False
        overlay_messages.post("Reminder", "hidden")
        assert not [message for message, _ in widget.read_notifications() if message.detail == "hidden"]
    finally:
        widget.deleteLater()
        QCoreApplication.processEvents()


# --- Toast times: one source for widget toasts & TpToast
def test_toast_times_one_source(ui_env):
    from neopedal.ui import toast
    from neopedal.ui.quick import Theme
    from neopedal.ui.tokens import TOAST_TIMES

    theme = Theme()
    try:
        for name, value in TOAST_TIMES.items():
            assert theme.property(name) == value, name
        assert theme.property("toastErrorFactor") == toast.ERROR_FACTOR
        assert toast.toast_duration(10) == TOAST_TIMES["toastMinimumTime"]
    finally:
        theme.deleteLater()


# --- Information level in blue (never the accent, red in the Modern themes)
def test_information_level_blue(ui_env):
    from PySide6.QtGui import QColor

    from neopedal.ui import status_color
    from neopedal.ui.quick import Theme

    theme = Theme()
    try:
        info = theme.property("info")
        assert info == QColor(status_color("info")) and info != theme.property("accent")
        assert info.blue() > info.red()
    finally:
        theme.deleteLater()


# --- 2026-11-03 second list: update once, actions gone, read marks, search, mute, overlay repeats, reminders, phone
def test_update_message_once_across_starts_and_button_dropped(store):
    store.add("Update available: v9.9.9", "info", (("What's New", "updates"),))
    assert store.has("Update available: v9.9.9") and not store.has("Other")
    store.drop_action("updates")
    assert store.entries()[0]["actions"] == []
    store.drop_action("updates")  # nothing left: no change told
    assert len(store.entries()) == 1


def test_update_action_when_up_to_date_opens_running_version(ui_env, monkeypatch):
    from neopedal.lazy_service import update_checker
    from neopedal.ui import notification, release_notes

    opened = []
    monkeypatch.setattr(update_checker, "is_updates", lambda: False)
    monkeypatch.setattr(release_notes, "running_version_dialog",
                        lambda window: SimpleNamespace(open=lambda: opened.append(window)))
    window = SimpleNamespace(show_app=lambda: None)
    notification.run_notification_action(window, "updates")
    assert opened == [window]


def test_read_marks_search_and_mute(ui_env):
    from neopedal.ui.notification import NotificationStore, notification_store
    from neopedal.ui.quick.notify_backend import NotificationBackend

    store = notification_store()
    store.clear()
    store.unmute_all()
    store.add("Overlay crashed", "error")
    store.add("Speedometer is too big (900 x 900), cut to 500 x 500.", "warning")
    store.add("Saved stats", "info")
    backend = NotificationBackend(None)
    try:
        backend.markRead(store.entries()[0]["id"])  # clicked
        assert backend.unreadCount == 2
        backend.setFilter("warning")
        backend.popup_closed()  # only the warning was shown
        assert [entry["read"] for entry in store.entries()] == [True, True, False]
        backend.deleteLater()  # closed: no longer follows the store, opened again
        backend = NotificationBackend(None)
        backend.setFilter("")
        backend.setSearch("  OVERLAY  ")
        assert backend.search == "overlay" and [row["text"] for row in backend.model.rows] == ["Overlay crashed"]
        backend.setSearch("")
        warning = store.entries()[1]
        backend.mute(store.entries()[0]["id"])  # info: never muted
        assert len(store.entries()) == 3 and backend.mutedCount == 0
        backend.mute(warning["id"])
        assert backend.mutedCount == 1 and len(store.entries()) == 2
        assert store.add("Speedometer is too big (700 x 700), cut to 500 x 500.", "warning") is None  # other numbers
        store.flush()
        store.save()
        again = NotificationStore()  # muted kept after a restart
        assert again.muted_count() == 1
        again.deleteLater()
        backend.unmuteAll()
        assert backend.mutedCount == 0 and store.add("Speedometer is too big (1 x 1), cut to 500 x 500.", "warning")
    finally:
        store.clear()
        store.unmute_all()
        backend.deleteLater()
        flush()


def test_muted_or_held_messages_not_toasted_or_posted(ui_env, monkeypatch):
    from neopedal import realtime_state
    from neopedal.ui import app
    from neopedal.ui.notification import notification_store

    toasts = []
    monkeypatch.setattr(app, "show_toast", lambda window, text, **kwargs: toasts.append(text))
    shown = SimpleNamespace(isVisible=lambda: True, isMinimized=lambda: False)
    bar = SimpleNamespace(window=lambda: shown)
    store = notification_store()
    store.clear()
    store.add("Recorder failed lap 3", "error")
    store.mute(store.entries()[0]["id"])
    serial = overlay_messages.last_serial()
    app.StatusButtonBar.show_message(bar, "Recorder failed lap 4", "error", ())
    assert toasts == [] and overlay_messages.since(serial) == []  # muted: only logged
    store.unmute_all()
    cfg.notification["enable_hold_notifications_while_driving"] = True
    monkeypatch.setattr(realtime_state, "active", True)
    app.StatusButtonBar.show_message(bar, "Recorder failed lap 5", "error", ())
    assert len(toasts) == 1 and overlay_messages.since(serial) == []  # held while driving: not in the overlay
    store.clear()


def test_app_message_repeat_skipped(monkeypatch):
    serial = overlay_messages.last_serial()
    assert overlay_messages.post("Error", "Module crashed", "error")
    assert not overlay_messages.post("Error", "Module crashed", "error")  # crashing in a loop
    assert overlay_messages.post("Error", "Other module crashed", "error")
    assert len(overlay_messages.since(serial)) == 2
    monkeypatch.setattr(overlay_messages, "REPEAT_SECONDS", 0.0)
    assert overlay_messages.post("Error", "Module crashed", "error")  # long ago: told again


def test_last_reminder_and_snooze(ui_env, monkeypatch):
    from neopedal.ui import notification, toast
    from neopedal.ui.quick import schedule_reminders as sr

    now = [2_000_000.0]
    told = []
    monkeypatch.setattr(sr.RaceReminders, "tell", staticmethod(
        lambda message, *args, **kwargs: told.append((notification.message_text(message), kwargs.get("snooze", "")))))
    monkeypatch.setattr(sr, "_reminders", sr.RaceReminders(clock=lambda: now[0]))
    reminders = sr.reminders()
    try:
        cfg.notification["number_of_minutes_before_last_race_reminder"] = 2
        assert sr.reminder_steps(30) == [30, 2] and sr.reminder_steps(2) == [2]
        start = now[0] + 3600
        reminders.set("race@1", "GT3 Fixed", "Spa", start, 30)
        now[0] = start - 30 * 60
        reminders.check()
        assert told[-1][0] == "GT3 Fixed starts in 30 min (Spa)" and reminders.keys() == {"race@1": 30}
        snooze = told[-1][1]
        assert snooze.startswith(sr.SNOOZE_PREFIX)
        toasts = []
        monkeypatch.setattr(toast, "show_toast", lambda window, text, **kwargs: toasts.append(text))
        notification.run_notification_action(SimpleNamespace(show_app=lambda: None), snooze)
        assert toasts == ["Reminder in 2 min"]
        now[0] += 120
        reminders.check()
        assert told[-1][0] == "GT3 Fixed starts in 28 min (Spa)"
        now[0] = start - 2 * 60
        reminders.check()
        assert told[-1][0] == "GT3 Fixed starts in 2 min (Spa)" and reminders.keys() == {}  # last one
        assert not sr.snooze(snooze)  # starts in 2 min: too soon
        assert not sr.snooze("snooze:not json")
    finally:
        reminders.deleteLater()
        flush()


def test_reminder_sound_modes_and_taskbar_flash(ui_env, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from neopedal.ui import notification
    from neopedal.ui.quick import schedule_reminders as sr

    assert isinstance(sr.windows_hides_notifications(), bool)  # read only, never an error
    hidden = [False]
    monkeypatch.setattr(sr, "windows_hides_notifications", lambda: hidden[0])
    assert cfg.notification["race_reminder_sound"] == sr.SOUND_HIDDEN and not sr.sound_wanted()
    hidden[0] = True
    assert sr.sound_wanted()
    cfg.notification["race_reminder_sound"] = sr.SOUND_NEVER
    assert not sr.sound_wanted()
    cfg.notification["race_reminder_sound"] = sr.SOUND_ALWAYS
    hidden[0] = False
    assert sr.sound_wanted()
    alerts = []
    window = QMainWindow()
    window.show()
    monkeypatch.setattr(notification, "main_window", lambda: window)
    monkeypatch.setattr(QApplication, "alert", staticmethod(lambda widget, duration=0: alerts.append(widget)))
    monkeypatch.setattr(sr, "play_reminder_sound", lambda: None)
    try:
        sr.RaceReminders.tell((("Server ready: %1 (%2). Join it from the game (Join Event).", ("GT3", "15:00")),),
                              "Server ready", "GT3", sound=True)
        assert alerts == [window]
    finally:
        notification.notification_store().clear()
        window.close()
        window.deleteLater()
        flush()


def test_sound_file_played_else_windows_sound(ui_env, monkeypatch, tmp_path):
    from neopedal.ui.quick import schedule_reminders as sr

    played = []
    monkeypatch.setattr(sr, "_player", SimpleNamespace(setSource=lambda url: played.append(url.toLocalFile()),
                                                         play=lambda: played.append("play")))
    sound = tmp_path / "bell.wav"
    sound.write_bytes(b"RIFF")
    cfg.notification["race_reminder_sound_file_name"] = str(sound)
    sr.play_reminder_sound()
    assert played == [sound.as_posix(), "play"]
    cfg.notification["race_reminder_sound_file_name"] = str(tmp_path / "gone.wav")  # missing: Windows sound
    beeps = []
    import sys

    if sys.platform == "win32":
        import winsound

        monkeypatch.setattr(winsound, "MessageBeep", lambda kind: beeps.append(kind))
    else:
        from PySide6.QtWidgets import QApplication

        monkeypatch.setattr(QApplication, "beep", staticmethod(lambda: beeps.append(1)))
    sr.play_reminder_sound()
    assert len(played) == 2 and len(beeps) == 1


def test_phone_dashboard_gets_app_messages(ui_env):
    from neopedal import web_dashboard

    overlay_messages.post("Reminder", "GT3 Fixed · 10 min")
    overlay_messages.post("Server ready", "GT3 Fixed")
    sent = web_dashboard.app_messages()
    assert len(sent) <= web_dashboard.MESSAGES_SENT
    assert sent[-1]["title"] == "Server ready" and sent[-1]["detail"] == "GT3 Fixed" and sent[-1]["level"] == "info"
    assert sent[-1]["serial"] == overlay_messages.last_serial()
    page = web_dashboard.DASHBOARD_HTML
    assert 'id="note"' in page and "notes(d.messages)" in page and "navigator.vibrate" in page
