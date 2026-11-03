#  NeoPedal is an open-source overlay application for racing simulation.
#  Copyright (C) 2022-2026 TinyPedal developers, see contributors.md file
#
#  This file is part of NeoPedal.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Notification
"""

from __future__ import annotations

import logging
import re
import sys
import threading
import weakref
from collections.abc import Callable
from functools import partial
from time import monotonic
from typing import Any

import shiboken6
from PySide6.QtCore import QCoreApplication, QDateTime, QLocale, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QWidget,
)

from ..const_app import APP_NAME
from ..i18n import current_language, tr, trm
from ..jobs import Job, WorkerPool, get_courier, weak_callback
from ..lazy_service import update_checker
from ..setting import cfg
from ._common import UIScaler, confirm_action, find_dialog_host

logger = logging.getLogger(__name__)

DOWNLOAD_CANCELLED = "cancelled"  # error message of cancelled download, see UpdateInstaller


def main_window() -> QWidget | None:
    """Main application window (has quit_app), None if not created"""
    for widget in QApplication.topLevelWidgets():
        if callable(getattr(widget, "quit_app", None)):
            return widget
    return None


# Update module (http.client, urllib, zipfile...) imported once used: not at start, see lazy_service
def can_auto_update() -> bool:
    """See update.can_auto_update"""
    from ..update import can_auto_update as found

    return found()


def is_portable_copy() -> bool:
    """See update.is_portable_copy"""
    from ..update import is_portable_copy as found

    return found()


def release_url() -> str:
    """See update.release_url"""
    from ..update import release_url as found

    return found()


def skip_version(version_tuple: tuple[int, int, int]):
    """See update.skip_version"""
    from ..update import skip_version as found

    found(version_tuple)


def discard_installer(path: str) -> None:
    """See update.discard_installer"""
    from ..update import discard_installer as found

    found(path)


def download_installer(asset, **kwargs) -> str:
    """See update.download_installer"""
    from ..update import download_installer as found

    return found(asset, **kwargs)


def run_installer(path: str, folder: str | None = None, repository: str | None = None,
                  signer: str | None = None) -> None:
    """See update.run_installer"""
    from ..update import run_installer as found

    found(path, folder, repository, signer)


def installer_signer(path: str, repository: str | None = None) -> str:
    """See update.installer_signer"""
    from ..update import installer_signer as found

    return found(path, repository)


def is_official_repository(repo: str) -> bool:
    """See update.is_official_repository"""
    from ..update import is_official_repository as found

    return found(repo)


def update_repository() -> str:
    """See update.update_repository"""
    from ..update import update_repository as found

    return found()


def install_error_text(error: Exception) -> str:
    """Message of installer refused or not started (run_installer, installer_signer errors)"""
    from ..update import InstallerChangedError, RevocationUnknownError, UnsignedInstallerError

    if isinstance(error, UnsignedInstallerError):
        return tr("Installer of custom update repository is not signed, update was not installed.")
    if isinstance(error, RevocationUnknownError):
        return tr("Revocation of the installer signing certificate could not be checked (server unreachable), "
                  "update was not installed. Try again later.")
    if isinstance(error, InstallerChangedError):
        return tr("Installer changed after it was downloaded, update was not installed.")
    if isinstance(error, ValueError):
        return tr("Installer signature is not valid, update was not installed.")
    return trm(f"Unable to install update: {error}")


def display_signer(signer: str) -> str:
    """Signer name shown in a message (certificate text: no markup, no control character, bounded)"""
    return "".join(char for char in signer if char not in "<>&" and char.isprintable())[:200]


def install_update(window: QWidget | None, path: str, repository: str | None = None,
                   signer: str | None = None) -> bool:
    """Run downloaded installer then quit, False if cancelled or installer not started

    Open pages are closed first (each may ask to save changes): cancelling keeps app as is,
    installer is only started once app can quit. Installer not started: removed (downloaded again next time).

    Args:
        repository: update repository the installer was downloaded from, None for current setting.
        signer: signer shown to user (custom repository), installer refused if signed by another one.
    """
    close_pages = getattr(window, "close_pages_for_quit", None)
    if callable(close_pages) and not close_pages():
        discard_installer(path)
        return False
    try:
        run_installer(path, repository=repository, signer=signer)
    except (OSError, ValueError) as error:
        logger.error("UPDATES: unable to run installer: %s", error)
        cancel_quit = getattr(window, "cancel_quit", None)
        if callable(cancel_quit):
            cancel_quit()
        discard_installer(path)  # broken signature never kept, unstartable one never left in temp folder
        QMessageBox.warning(window, tr("Error"), install_error_text(error))
        return False
    quit_app = getattr(window, "quit_app", None)
    if callable(quit_app):
        quit_app()
    return True


def format_megabytes(size: int) -> str:
    """Size in MB, one decimal, in current language"""
    return QLocale(current_language()).toString(size / 1_000_000, "f", 1)


def _download(asset, report: Callable[[int, int], None], cancel: threading.Event) -> tuple[str, str, str | None]:
    """Installer downloaded (download thread): path, error message ("" if downloaded) & signer

    Installer of a custom update repository: signature verified (revocation checked online, off the UI
    thread), its signer shown before installing; refused one removed, error is then the full message.
    Signer None: official release (signed manifest verified at check time).
    """
    from ..update import DownloadCancelled

    try:
        path = download_installer(asset, progress=report, cancelled=cancel)
    except DownloadCancelled:
        logger.info("UPDATES: download cancelled")
        return "", DOWNLOAD_CANCELLED, None
    except Exception as error:  # OSError, ValueError, or unexpected: never left busy
        logger.error("UPDATES: download failed: %s", error)
        return "", trm(f"Unable to download update: {error}"), None
    repository = asset.repository or update_repository()
    if is_official_repository(repository):
        return path, "", None
    try:
        return path, "", installer_signer(path, repository)
    except Exception as error:  # refused (ValueError), unreadable (OSError) or unexpected: never left busy
        logger.error("UPDATES: installer refused: %s", error)
        discard_installer(path)
        return "", install_error_text(error), None


_download_workers: WorkerPool | None = None


def _download_pool() -> WorkerPool:
    """Worker thread of update downloads, created when first needed (UI thread)"""
    global _download_workers
    if _download_workers is None:
        _download_workers = WorkerPool(1, "Update download")
    return _download_workers


def download_progress_text(received: int, total: int) -> str:
    """Downloaded part: percent & size, or size only if total is unknown"""
    if total > 0:
        percent = min(round(received * 100 / total), 100)
        return trm(f"{percent}% ({format_megabytes(received)} / {format_megabytes(total)} MB)")
    return trm(f"{format_megabytes(received)} MB")


class UpdateInstaller(QObject):
    """Download & install of update: one download at a time, whatever button or page asked it

    Notify buttons are rebuilt on language change and what's new pages can be reopened,
    so download state (busy, progress) is kept here, not in them.
    """

    busy_changed = Signal(bool)
    progress = Signal(int, int)  # received, total bytes (0 if unknown), from download thread
    PROGRESS_INTERVAL = 0.1  # seconds between progress signals

    def __init__(self):
        super().__init__()
        self.busy = False
        self.received = 0
        self.total = 0
        self._auto_install = False
        self._repository: str | None = None  # update repository of downloading installer
        self._cancel = threading.Event()
        self._serial = 0
        self._ref = weakref.ref(self)
        get_courier()  # created on the UI thread (hands the download result over)
        self.progress.connect(self.store_progress)

    def download(self, auto_install: bool = False) -> bool:
        """Download installer in background thread, False if none or already downloading"""
        asset = update_checker.installer
        if asset is None or self.busy:
            return False
        self.busy = True
        self.received = self.total = 0
        self._auto_install = auto_install
        # Repository of release found at check time: setting may change before installing
        self._repository = asset.repository or None
        self._cancel = cancel = threading.Event()
        self.busy_changed.emit(True)
        last_report = [0.0]

        def report(received: int, total: int):  # download thread: progress signal of this app-lifetime object
            now = monotonic()
            if now - last_report[0] >= self.PROGRESS_INTERVAL or received >= total > 0:
                last_report[0] = now
                self.progress.emit(received, total)

        # Job of its own worker thread (a download of minutes never holds back page jobs), handed over on the UI
        # thread by the jobs courier (deliver_job)
        self._serial += 1
        _download_pool().submit(Job(self._serial, None, "download", "Update", partial(_download, asset, report, cancel),
                                    weak_callback(None), weak_callback(None), False, self._ref))
        return True

    def deliver_job(self, job: Job):
        """Download over (UI thread): installer run, or error shown"""
        ok, value = job.outcome or (False, None)
        job.release()
        if not ok:  # unexpected error of the download thread: never left busy
            logger.error("UPDATES: download failed: %s", value)
        path, message, signer = value if ok else ("", trm(f"Unable to download update: {value}"), None)
        self.install_downloaded(path, message, signer)

    def cancel(self) -> bool:
        """Stop download (partial file removed), False if not downloading"""
        if not self.busy:
            return False
        self._cancel.set()
        return True

    @Slot(int, int)  # type: ignore[operator]
    def store_progress(self, received: int, total: int):
        """Progress kept for buttons & pages shown later"""
        self.received, self.total = received, total

    def install_downloaded(self, path: str, error: str, signer: str | None = None):
        """Run installer and quit, installer restarts NeoPedal when done

        Args:
            error: full message of failed download (empty if downloaded).
            signer: signer of installer of a custom update repository (see _download): always asked first,
                with update repository & signer shown. None: official release.
        """
        self.busy = False
        self.busy_changed.emit(False)
        auto_install, self._auto_install = self._auto_install, False
        window = main_window()
        if error == DOWNLOAD_CANCELLED:
            return
        if not path:
            QMessageBox.warning(window, tr("Error"), error)
            return
        if signer is not None:  # custom update repository: publisher shown, never installed without asking
            repository = self._repository or update_repository()
            publisher = display_signer(signer) or tr("unknown publisher")
            question = trm(f"Update downloaded from {repository}, installer signed by {publisher}. "
                           "Install it only if you trust this publisher. Close NeoPedal and install it now?")
        elif not auto_install:
            question = tr("Update downloaded. Close NeoPedal and install it now?")
        else:
            question = ""
        if question and not confirm_action(window, tr("Download And Install"), question, tr("Install Now"),
                                           default_action=signer is None):
            discard_installer(path)  # declined: never left in temp folder
            return
        if signer is None:
            install_update(window, path, self._repository)
        else:
            install_update(window, path, self._repository, signer=signer)


_update_installer: UpdateInstaller | None = None


def update_installer() -> UpdateInstaller:
    """Update download & install (created once, after QApplication)"""
    global _update_installer
    if _update_installer is None:
        _update_installer = UpdateInstaller()
    return _update_installer


# Modes on, listed under "Now" in the notification center: (name of notify_<name> option, text, center action)
MODE_NOTICES = (
    ("locked_preset", "Preset Locked", "page:preset"),
    ("spectate_mode", "Spectate Mode Enabled", "tool:spectate_view.SpectateList"),  # Spectate tab of Director
    ("pace_notes_playback", "Pace Notes Playback Enabled", "tool:track_notes_editor.TrackNotesEditor"),  # Notes tab
    ("auto_backup_car_setup", "Auto Backup Car Setup Enabled", "option:telemetry/enable_auto_backup_car_setup"),
    ("broadcast_director", "Broadcast Director On", "tool:broadcast_director.BroadcastDirector"),
)


def director_running() -> bool:
    """Broadcast Director page open with the director on (it asks the game while hidden too)"""
    module = sys.modules.get("neopedal.ui.quick.director_backend")  # imported only by the page
    return module is not None and module.director_status() == "on"


class NotifyBar(QWidget):
    """Update chip of the window status band (title bar drawn by the app, or status bar). Modes on (preset locked,
    spectate, pace notes, global hotkey, car setup backup, Broadcast Director on) are listed under "Now" in the
    notification center, never as chips."""

    def __init__(self, parent):
        super().__init__(parent)
        layout = QHBoxLayout()
        layout.setSpacing(UIScaler.pixel(4))
        layout.setContentsMargins(0, 0, 0, 0)
        self.updates = UpdatesNotifyButton("")
        self.updates.setVisible(False)
        self.updates.setStyleSheet(self.chip_style())
        layout.addWidget(self.updates)
        layout.addStretch(1)
        self.setLayout(layout)
        self._modes: dict[str, bool] = {}  # mode name: on (and its notice enabled)

    @staticmethod
    def chip_style() -> str:
        """Style sheet of the update chip: rounded, compact"""
        return (f"QPushButton {{ border: none; border-radius: {UIScaler.pixel(9)}px; "
                f"padding: {UIScaler.pixel(1)}px {UIScaler.pixel(9)}px; margin: {UIScaler.pixel(2)}px 0; }}")

    @Slot(bool)  # type: ignore[operator]
    def refresh(self):
        """Modes read again (setting refreshed)"""
        self.set_modes(
            locked_preset=cfg.filename.setting in cfg.user.filelock,
            spectate_mode=cfg.api["enable_player_index_override"],
            pace_notes_playback=cfg.user.setting["pace_notes_playback"]["enable"],
            auto_backup_car_setup=cfg.telemetry["enable_auto_backup_car_setup"],
            broadcast_director=director_running(),
        )

    def refresh_director(self):
        """Broadcast Director on or off, each second"""
        self.set_modes(broadcast_director=director_running())

    def set_modes(self, **modes: Any):
        """Modes on or off, notification center told only when one changes"""
        notification = cfg.notification
        shown = {name: bool(on) and bool(notification[f"notify_{name}"]) for name, on in modes.items()}
        if any(self._modes.get(name) != on for name, on in shown.items()):
            self._modes.update(shown)
            self.publish_active()

    def active_notices(self) -> list[tuple[str, str]]:
        """Modes on: (text, notification center action)"""
        return [(tr(text), action) for name, text, action in MODE_NOTICES if self._modes.get(name)]

    def publish_active(self):
        """Modes on listed in the notification center"""
        notification_store().set_active(self.active_notices())


class UpdatesNotifyButton(QPushButton):
    """Updates notify button

    Prompted version & dismissed message are shared by buttons (rebuilt on language change).
    """

    prompted_version = ""  # update already proposed, see prompt_update
    dismissed_message = ""  # update message hidden by user, see dismiss
    logged_message = ""  # update message added to the notification center (once)

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        version_menu = QMenu(self)

        self.install_update = version_menu.addAction(tr("Download And Install"))
        self.install_update.triggered.connect(self.download_update)
        self.install_update.setVisible(False)
        self._auto_install = False
        installer = update_installer()
        installer.busy_changed.connect(self.download_state)
        installer.progress.connect(self.download_progress)

        self.cancel_download = version_menu.addAction(tr("Cancel Download"))
        self.cancel_download.triggered.connect(lambda: update_installer().cancel())
        self.cancel_download.setVisible(False)

        self.view_notes = version_menu.addAction(tr("What's New"))
        self.view_notes.triggered.connect(lambda: self.show_release_notes())
        self.view_notes.setVisible(False)

        view_update = version_menu.addAction(tr("View Updates On GitHub"))
        view_update.triggered.connect(self.open_release)
        version_menu.addSeparator()

        self.skip_update = version_menu.addAction(tr("Skip This Version"))
        self.skip_update.setToolTip(tr("Not shown again for this version, shown again for a newer one"))
        self.skip_update.triggered.connect(self.skip)
        self.skip_update.setVisible(False)

        dismiss_msg = version_menu.addAction(tr("Dismiss"))
        dismiss_msg.triggered.connect(self.dismiss)

        self.setMenu(version_menu)

    def open_release(self):
        """Open release link"""
        QDesktopServices.openUrl(release_url())

    def dismiss(self):
        """Hide message, kept hidden when button is rebuilt (language change)"""
        UpdatesNotifyButton.dismissed_message = update_checker.message()
        self.hide()

    def skip(self):
        """Skip version of available update: notice not shown again (a newer version is), saved"""
        skip_update_version()
        self.hide()

    def can_install(self) -> bool:
        """Update available & app can download and run its installer"""
        return can_auto_update() and update_checker.is_updates() and update_checker.installer is not None

    @Slot(bool)  # type: ignore[operator]
    def checking(self, checking: bool):
        """Checking updates"""
        if checking:
            # Show checking message only with manual checking, notice shown kept while checking automatically
            if not update_checker.is_manual():
                return
            self.setText(tr("Checking for updates…"))
            self.setVisible(True)
        else:
            # Hide message if no updates (or version skipped, or dismissed) and not manual checking.
            # Release refused (signed manifest not verified): shown like an update, without install
            skipped = update_checker.is_skipped()
            dismissed = update_checker.message() == self.dismissed_message
            noticed = (update_checker.is_updates() and not skipped) or update_checker.is_refused()
            self.setText(trm(update_checker.message()))
            self.setVisible(update_checker.is_manual() or (noticed and not dismissed))
            store = notification_store()
            if noticed and UpdatesNotifyButton.logged_message != update_checker.message():
                UpdatesNotifyButton.logged_message = update_checker.message()  # once per version
                updates = update_checker.is_updates()
                if not store.has(update_checker.message()):  # told at an earlier start: kept in history
                    store.add(update_checker.message(), "info" if updates else "warning",
                              (("What's New", "updates"),) if updates else ())
            if not update_checker.is_updates():  # up to date: What's New of updates found before leads nowhere
                store.drop_action("updates")
            self.view_notes.setVisible(update_checker.is_updates() and bool(update_checker.notes(current_language())))
            self.skip_update.setVisible(update_checker.is_updates())
            self.install_update.setVisible(self.can_install())
            if self.install_update.isVisible() and not skipped:
                self.prompt_update()
            self.download_state(update_installer().busy)

    def restore(self):
        """Show result of last check again (button rebuilt on language change), unless dismissed"""
        if not update_checker.imported:  # never checked (window built at start): nothing to show
            return
        if update_checker.is_checking():
            self.checking(True)
        elif (((update_checker.is_updates() and not update_checker.is_skipped()) or update_checker.is_refused())
                and update_checker.message() != self.dismissed_message):
            self.checking(False)

    @Slot(bool)  # type: ignore[operator]
    def download_state(self, busy: bool):
        """Downloading update: shown on button (with progress), install entry disabled, cancel shown"""
        self.install_update.setEnabled(not busy)
        self.cancel_download.setVisible(busy)
        if busy:
            installer = update_installer()
            self.download_progress(installer.received, installer.total)
        elif update_checker.is_updates():
            self.setText(trm(update_checker.message()))

    @Slot(int, int)  # type: ignore[operator]
    def download_progress(self, received: int, total: int):
        """Downloaded part shown on button"""
        if not update_installer().busy:
            return
        text = tr("Downloading Update…")
        if received:
            text = f"{text} {download_progress_text(received, total)}"
        self.setText(text)

    def prompt_update(self):
        """Ask once per version to install available update (what's new shown), install downloads it

        Window hidden (tray) or minimized, game likely running: never popped up, what's new page
        waits inside app and a tray message tells about the update. Found by automatic check while app
        runs: popped up only if window is the active one (not over the game on another screen).
        """
        version_text = update_checker.message()
        if self.prompted_version == version_text:
            return
        UpdatesNotifyButton.prompted_version = version_text
        window = self.window()
        if (window.isVisible() and not window.isMinimized()
                and (not update_checker.is_scheduled() or window.isActiveWindow())):
            self.show_release_notes(prompt=True)
            return
        self.show_release_notes(prompt=True, bring_to_front=False)
        version = ".".join(str(number) for number in update_checker.latest_version())
        tray_message(trm(f"Update available: v{version}. Open {APP_NAME} to see what's new and install it."),
                     action="updates", kind=KIND_UPDATE, window=window)

    def release_notes_dialog(self, prompt: bool = False):
        """What's new page of available update, install button when it can install"""
        from .release_notes import ReleaseNotesDialog

        portable = is_portable_copy()
        installer = update_checker.installer
        dialog = ReleaseNotesDialog(
            self, update_checker.notes(current_language()), update_checker.latest_version(), update_checker.latest_date(),
            can_install=self.can_install(), prompt=prompt,
            download_url=installer.url if installer is not None and not portable else "", portable=portable,
            installer=update_installer(), can_skip=update_checker.is_updates(),
            earlier=update_checker.earlier_notes(current_language()))
        # Page may outlive this button (kept when view is rebuilt in new language): not only bound to it
        dialog.install_requested.connect(
            lambda button=self: button.install_from_notes() if shiboken6.isValid(button) else install_from_notes())
        dialog.skip_requested.connect(skip_from_notes)
        dialog.skip_requested.connect(self.hide)
        return dialog

    def show_release_notes(self, prompt: bool = False, bring_to_front: bool = True):
        """Show release notes (changelog) of available update

        Not brought to front: shown as page of hidden window, seen once window is opened.
        """
        from .release_notes import open_notes_page

        shown = open_notes_page(self, tr("Update Available") if prompt else tr("What's New"),
                                update_checker.latest_version())
        if shown is not None:  # notes of this update already open: shown again, no second page built
            if bring_to_front:
                shown.open()
            return
        dialog = self.release_notes_dialog(prompt)
        if bring_to_front:
            dialog.open()
            return
        host = find_dialog_host(self)
        if host is None or not host.show_dialog_page(dialog, bring_to_front=False):
            dialog.deleteLater()  # no page to wait in: tray message only

    def install_from_notes(self):
        """Install asked from what's new page: installs once downloaded, no second question"""
        self._auto_install = True
        self.download_update()

    def download_update(self):
        """Download installer in background thread (once, while not already downloading)"""
        auto_install, self._auto_install = self._auto_install, False
        update_installer().download(auto_install)


def install_from_notes():
    """Install asked from what's new page: installs once downloaded, no second question"""
    update_installer().download(auto_install=True)


def skip_update_version():
    """Version of available update skipped (saved): notice not shown again, a newer version is"""
    skip_version(update_checker.latest_version())
    UpdatesNotifyButton.dismissed_message = update_checker.message()


def skip_from_notes():
    """Skip asked from what's new page: version skipped, update notices of main window hidden"""
    skip_update_version()
    window = main_window()
    if window is not None:
        for button in window.findChildren(UpdatesNotifyButton):
            button.hide()


# Notification center: messages of the app kept with their time & level (errors of background work, saving
# failures, updates found, race reminders), modes on, read from the bell of the navigation rail. Kept between
# sessions in the user config folder (HISTORY_FILE), told by Windows notifications while the window is hidden
SEVERITIES = ("error", "warning", "info")
MAX_NOTIFICATIONS = 100
TRAY_MESSAGE_INTERVAL = 60.0  # seconds: at most one tray message this often (more messages: count told)
REPEAT_SECONDS = 600  # same message within this time: counted on the first one (moved to the top)
HISTORY_FILE = "notifications.json"
SAVE_DELAY_MS = 1000  # history written once changes pause
# Kinds of tray messages, each with its option (notification section of config.json); KIND_APP always told
KIND_ERROR = "error"
KIND_REMINDER = "reminder"
KIND_UPDATE = "update"
KIND_APP = "app"
TRAY_OPTIONS = {
    KIND_ERROR: "show_tray_messages_for_errors",
    KIND_REMINDER: "show_tray_messages_for_race_reminders",
    KIND_UPDATE: "show_tray_messages_for_updates",
}
CENTER_ACTION = "center"  # notification center opened

# Text of a message: English text (translated when shown, trm), or parts joined by a space, each an English
# template with %1, %2... filled with its arguments (translated when shown, tr): shown in the language of the app
# even after a language change or a restart
MessageText = str | tuple[tuple[str, tuple[str, ...]], ...]


def mute_key(source: MessageText) -> str:
    """Same message whatever its numbers (sizes, lap, seconds): English text with numbers as #, templates of parts"""
    if isinstance(source, str):
        return re.sub(r"\d+", "#", source)
    return "|".join(template for template, _args in source)


def message_text(source: MessageText) -> str:
    """Text of a message in app language"""
    if isinstance(source, str):
        return trm(source)
    parts = []
    for template, args in source:
        text = tr(template)
        for number, value in reversed(list(enumerate(args, 1))):  # %10 before %1
            text = text.replace(f"%{number}", value)
        parts.append(text)
    return " ".join(parts)


def _source_value(value: Any) -> MessageText | None:
    """Message text read from history file, None if invalid"""
    if isinstance(value, str):
        return value
    if not isinstance(value, list) or not value:
        return None
    parts = []
    for part in value:
        if (not isinstance(part, list) or len(part) != 2 or not isinstance(part[0], str)
                or not isinstance(part[1], list) or not all(isinstance(arg, str) for arg in part[1])):
            return None
        parts.append((part[0], tuple(part[1])))
    return tuple(parts)


def _entry_value(value: Any) -> dict | None:
    """Message read from history file, None if invalid"""
    if not isinstance(value, dict):
        return None
    source = _source_value(value.get("text"))
    severity, stamp, count = value.get("severity"), value.get("time"), value.get("count")
    if (source is None or severity not in SEVERITIES or isinstance(stamp, bool) or not isinstance(stamp, int)
            or isinstance(count, bool) or not isinstance(count, int) or count < 1):
        return None
    actions = value.get("actions")
    actions = [{"label": action["label"], "key": action["key"]} for action in actions
               if isinstance(action, dict) and isinstance(action.get("label"), str)
               and isinstance(action.get("key"), str)] if isinstance(actions, list) else []
    return {"source": source, "severity": severity, "time": QDateTime.fromMSecsSinceEpoch(stamp), "count": count,
            "read": value.get("read") is True, "actions": actions}


class NotificationStore(QObject):
    """Messages of the notification center (newest first) & modes on (listed under "Now")

    Emits changed when messages, their read state or the modes on change, added with each new message.
    A message repeating one of the last REPEAT_SECONDS is counted on it (moved to the top, time updated) instead of
    added again. Messages are read from HISTORY_FILE when first used, written once changes pause & at quit.
    """

    changed = Signal()
    added = Signal(dict)

    def __init__(self, history: bool = True):
        super().__init__()
        self._entries: list[dict] = []
        self._active: list[tuple[str, str]] = []
        self._muted: set[str] = set()  # mute keys of messages not shown again (see mute_key)
        self._next_id = 1
        self._history = history
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DELAY_MS)
        self._save_timer.timeout.connect(self.save)
        if history:
            self.load()
            app = QCoreApplication.instance()
            if app is not None:
                app.aboutToQuit.connect(self.flush)

    def _new_id(self) -> int:
        number = self._next_id
        self._next_id += 1
        return number

    def add(self, text: MessageText, severity: str = "error",
            actions: tuple[tuple[str, str], ...] = ()) -> dict | None:
        """Message added (severity: "error", "warning" or "info"); text in English, see MessageText; actions:
        (English label, action key) of its buttons, see run_notification_action. None: muted (Don't Show Again),
        only logged"""
        if severity not in SEVERITIES:
            severity = "error"
        if severity != "info" and mute_key(text) in self._muted:
            logger.info("NOTIFICATIONS: muted: %s", message_text(text))
            return None
        now = QDateTime.currentDateTime()
        oldest = now.addSecs(-REPEAT_SECONDS)
        repeated = next((entry for entry in self._entries if entry["time"] >= oldest
                         and entry["source"] == text and entry["severity"] == severity), None)
        if repeated is not None:
            self._entries.remove(repeated)
            repeated["count"] += 1
            repeated["time"] = now
            repeated["read"] = False
            entry = repeated
        else:
            entry = {"id": self._new_id(), "source": text, "severity": severity, "time": now, "count": 1,
                     "read": False, "actions": [{"label": label, "key": key} for label, key in actions]}
        self._entries.insert(0, entry)
        del self._entries[MAX_NOTIFICATIONS:]
        self.notify_changed()
        self.added.emit(entry)
        return entry

    def entries(self) -> list[dict]:
        """Messages, newest first"""
        return list(self._entries)

    def has(self, text: MessageText) -> bool:
        """Message with this text kept (any time)"""
        return any(entry["source"] == text for entry in self._entries)

    def drop_action(self, key: str):
        """Buttons of this action removed from every message (action no longer possible)"""
        changed = False
        for entry in self._entries:
            actions = [action for action in entry["actions"] if action["key"] != key]
            if len(actions) != len(entry["actions"]):
                entry["actions"] = actions
                changed = True
        if changed:
            self.notify_changed()

    def unread_count(self) -> int:
        return sum(not entry["read"] for entry in self._entries)

    def unread_severity(self) -> str:
        """Highest level of unread messages ("error", "warning", "info"), "" if all read"""
        unread = {entry["severity"] for entry in self._entries if not entry["read"]}
        return next((severity for severity in SEVERITIES if severity in unread), "")

    def mark_all_read(self):
        self.mark_read({entry["id"] for entry in self._entries})

    def mark_read(self, entry_ids: set[int]):
        """Messages seen (clicked, or shown in the notification center when it closes)"""
        unread = [entry for entry in self._entries if entry["id"] in entry_ids and not entry["read"]]
        for entry in unread:
            entry["read"] = True
        if unread:
            self.notify_changed()

    def mute(self, entry_id: int):
        """Message not shown again (Don't Show Again): removed, same message (any numbers) only logged from now"""
        entry = next((entry for entry in self._entries if entry["id"] == entry_id), None)
        if entry is None or entry["severity"] == "info":
            return
        key = mute_key(entry["source"])
        self._muted.add(key)
        self._entries = [other for other in self._entries if mute_key(other["source"]) != key]
        self.notify_changed()

    def muted_count(self) -> int:
        return len(self._muted)

    def unmute_all(self):
        """Muted messages shown again"""
        if self._muted:
            self._muted.clear()
            self.notify_changed()

    def remove(self, entry_id: int):
        entries = [entry for entry in self._entries if entry["id"] != entry_id]
        if len(entries) != len(self._entries):
            self._entries = entries
            self.notify_changed()

    def clear(self) -> list[dict]:
        """Every message removed: removed messages (see restore)"""
        removed, self._entries = self._entries, []
        if removed:
            self.notify_changed()
        return removed

    def restore(self, entries: list[dict]):
        """Messages removed by clear put back (Undo), under those added since, newest first"""
        kept = {entry["id"] for entry in self._entries}
        restored = [entry for entry in entries if entry["id"] not in kept]
        if restored:
            self._entries = sorted(self._entries + restored, key=lambda entry: entry["time"], reverse=True)
            del self._entries[MAX_NOTIFICATIONS:]
            self.notify_changed()

    def active(self) -> list[tuple[str, str]]:
        """Modes on, listed under "Now": (text, action key)"""
        return list(self._active)

    def set_active(self, notices: list[tuple[str, str]]):
        if notices != self._active:
            self._active = list(notices)
            self.changed.emit()

    def notify_changed(self):
        """Messages changed: told, history written once changes pause"""
        self.changed.emit()
        if self._history:
            self._save_timer.start()

    def load(self):
        """Messages of history file, newest first (invalid ones skipped)"""
        from .quick.page_settings import load_settings

        settings = load_settings(HISTORY_FILE)
        data = settings.get("messages")
        entries = [entry for entry in map(_entry_value, data if isinstance(data, list) else ()) if entry]
        for entry in entries[:MAX_NOTIFICATIONS]:
            entry["id"] = self._new_id()
            self._entries.append(entry)
        muted = settings.get("muted")
        self._muted = {key for key in muted if isinstance(key, str)} if isinstance(muted, list) else set()

    def save(self):
        """History file written now (errors logged: never a message of its own, see write_settings)"""
        from .quick.page_settings import write_settings

        self._save_timer.stop()
        messages = [{
            "text": entry["source"], "severity": entry["severity"], "time": entry["time"].toMSecsSinceEpoch(),
            "count": entry["count"], "read": entry["read"], "actions": entry["actions"],
        } for entry in self._entries]
        try:
            write_settings(HISTORY_FILE, {"messages": messages, "muted": sorted(self._muted)})
        except Exception as error:  # history never breaks the app
            logger.warning("NOTIFICATIONS: history not saved: %s", error)

    def flush(self):
        """Changes not written yet written now (app quitting)"""
        if self._save_timer.isActive():
            self.save()


_notification_store: NotificationStore | None = None


def notification_store() -> NotificationStore:
    """Notification center messages (created once, after QApplication)"""
    global _notification_store
    if _notification_store is None:
        _notification_store = NotificationStore()
    return _notification_store


def error_actions() -> tuple[tuple[str, str], ...]:
    """Buttons of an error message: log & bug report (English labels, translated when shown)"""
    return (("View Log", "log"), ("Create Bug Report…", "bug_report"))


def run_notification_action(window: QWidget | None, key: str):
    """Action of a notification center button or Windows notification: "log", "bug_report", "updates" (what's new of
    available update), "center" (notification center), "page:<page key>" (main window page),
    "tool:<module.DialogClass>" (tool page), "option:<section>/<key>" (Settings page at that option, or category if
    no key), "snooze:..." (race reminder told again in 2 min, see schedule_reminders.snooze_action), "" (window shown
    only)"""
    if window is None:
        return
    show_app = getattr(window, "show_app", None)
    if callable(show_app):
        show_app()
    if key == "log":
        from .log_info import LogInfo

        LogInfo(window).show()
    elif key == "bug_report":
        from .bug_report_view import BugReport

        BugReport(window).show()
    elif key == "updates":
        if not update_checker.is_updates():  # installed since: what's new in the running version
            from .release_notes import running_version_dialog

            running_version_dialog(window).open()
            return
        for button in window.findChildren(UpdatesNotifyButton):
            button.show_release_notes()
            break
    elif key == CENTER_ACTION:
        view = getattr(window, "centralWidget", lambda: None)()
        show_center = getattr(view, "show_notification_center", None)
        if callable(show_center):
            show_center()
    elif key.startswith("snooze:"):
        from .quick.schedule_reminders import snooze
        from .toast import show_toast

        if snooze(key):
            show_toast(window, tr("Reminder in 2 min"), level="info")
        else:
            show_toast(window, tr("The race starts too soon to remind you again."), level="warning")
    elif key.startswith("page:"):
        from .nav_rail import PAGE_INDEX

        view = getattr(window, "centralWidget", lambda: None)()
        index = PAGE_INDEX.get(key.removeprefix("page:"))
        select_page = getattr(view, "select_page", None)
        if index is not None and callable(select_page):
            select_page(index)
    elif key.startswith("tool:"):
        from .tools_view import open_tool

        open_tool(key.removeprefix("tool:"), window)
    elif key.startswith("option:"):
        from .app_settings import open_app_settings

        section, _, option = key.removeprefix("option:").partition("/")
        open_app_settings(window, section, option)


def tray_shown(window: QWidget | None) -> QSystemTrayIcon | None:
    """Tray icon of window able to show messages, None if hidden or none"""
    tray_icon = window.findChild(QSystemTrayIcon) if window is not None else None
    if tray_icon is None or not tray_icon.isVisible() or not QSystemTrayIcon.supportsMessages():
        return None
    return tray_icon


def tray_message(text: str, level: str = "info", action: str = "", kind: str = KIND_APP,
                 window: QWidget | None = None) -> bool:
    """Windows notification (message of the tray icon, shown over the game), True if shown

    Args:
        text: message in app language.
        level: "info", "warning" or "error" (icon).
        action: run when the notification is clicked (see run_notification_action), "" shows the window.
        kind: KIND_ERROR, KIND_REMINDER or KIND_UPDATE (each turned off by its option, see TRAY_OPTIONS), KIND_APP.
        window: main window, found if None.
    """
    window = window if window is not None else main_window()
    relay = window.findChild(TrayRelay) if window is not None else None
    return relay is not None and relay.show(text, level, action, kind)


class TrayRelay(QObject):
    """Windows notifications of the main window: what each one opens once clicked, kinds turned off in settings

    New error or warning while the main window is hidden in tray or minimized (racing): a tray message (system
    notification, never a window over the game), at most one per TRAY_MESSAGE_INTERVAL; messages meanwhile told by
    one more at the end of the interval (how many, the last one). Held while driving with Hold Notifications While
    Driving, told once driving stops (overlay_signal.driving: overlay control runs without any overlay too). Only
    with the tray icon shown.

    Windows keeps former notifications (notification center of Windows) and does not say which one was clicked:
    one notification since the window was last shown runs its action, several open the notification center (it
    lists them all).
    """

    def __init__(self, window: QWidget):
        super().__init__(window)
        self._window = window
        self._last = -TRAY_MESSAGE_INTERVAL
        self._waiting = 0  # messages not told since last tray message
        self._waiting_entry: dict | None = None  # last of them
        self._actions: list[str] = []  # actions of the notifications shown since the window was last shown
        self._icon: QSystemTrayIcon | None = None  # tray icon whose clicks are followed
        self._flush_timer = QTimer(self)  # messages counted meanwhile told at end of interval, or once driving stops
        self._flush_timer.setSingleShot(True)
        self._flush_timer.timeout.connect(self.flush)
        notification_store().added.connect(self.message_added)
        from .. import overlay_signal

        overlay_signal.driving.connect(self.driving_changed)

    def show(self, text: str, level: str = "info", action: str = "", kind: str = KIND_APP) -> bool:
        """Tray message shown (see tray_message), its action run when clicked"""
        option = TRAY_OPTIONS.get(kind)
        if option is not None and not cfg.notification.get(option, True):
            return False
        tray_icon = tray_shown(self._window)
        if tray_icon is None:
            return False
        if tray_icon is not self._icon:
            self._icon = tray_icon
            tray_icon.messageClicked.connect(self.clicked)
        if self.window_hidden():
            self._actions.append(action)
        else:
            self._actions = [action]
        icon = (QSystemTrayIcon.MessageIcon.Critical if level == "error" else QSystemTrayIcon.MessageIcon.Warning
                if level == "warning" else QSystemTrayIcon.MessageIcon.Information)
        tray_icon.showMessage(APP_NAME, text, icon, 15000 if kind == KIND_REMINDER else 10000)
        return True

    @Slot()
    def clicked(self):
        """Tray message clicked: window shown, its action run (several told meanwhile: notification center)"""
        actions, self._actions = self._actions, []
        run_notification_action(self._window, actions[0] if len(set(actions)) == 1 else CENTER_ACTION)

    @Slot(bool)
    def driving_changed(self, driving: bool):
        """Driving stopped: messages held told"""
        if not driving:
            self.flush()

    def window_hidden(self) -> bool:
        window = self._window
        return not window.isVisible() or window.isMinimized()

    @staticmethod
    def holding() -> bool:
        """Messages held: driving (not the active state override), with Hold Notifications While Driving"""
        from .. import realtime_state

        return (bool(cfg.notification.get("enable_hold_notifications_while_driving")) and realtime_state.active
                and not realtime_state.overriding)

    def message_added(self, entry: dict):
        if entry["severity"] == "info" or not self.window_hidden() or tray_shown(self._window) is None:
            return
        self._waiting += 1
        self._waiting_entry = entry
        if self.holding():  # told once driving stops (driving_changed)
            return
        left = TRAY_MESSAGE_INTERVAL - (monotonic() - self._last)
        if left > 0:
            if not self._flush_timer.isActive():
                self._flush_timer.start(max(round(left * 1000), 1))
            return
        self.flush()

    def flush(self):
        """Messages counted since the last tray message told by one (still driving: checked again later)"""
        if not self._waiting or self._waiting_entry is None or self.holding():
            return
        entry, count = self._waiting_entry, self._waiting
        self._waiting, self._waiting_entry = 0, None
        if not self.window_hidden():  # window shown meanwhile: messages seen in the app (bell)
            return
        self._flush_timer.stop()
        self._last = monotonic()
        text = message_text(entry["source"])
        if count > 1:
            text = trm(f"{count} new messages, last one: {text}")
        self.show(text, entry["severity"], CENTER_ACTION, KIND_ERROR)


def open_notification_center(window: QWidget, anchor: QWidget):
    """Notification center popup next to anchor (bell of the rail)"""
    from .quick.notify_backend import NotificationCenter

    NotificationCenter.open_at(window, anchor)
