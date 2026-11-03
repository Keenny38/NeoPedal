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
Upcoming Races: online races of Le Mans Ultimate to come (daily, weekly & special races, championships, co-op
events, servers hosted by players)

Qt Quick page (ui/qml/analysis/RaceSchedule.qml), state & actions in quick/schedule_backend.py.
"""

from PySide6.QtCore import QSize
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QVBoxLayout

from ..i18n import tr
from ._common import BaseDialog, UIScaler


class RaceScheduleViewer(BaseDialog):
    """Upcoming online races"""

    def __init__(self, parent):
        from .quick import create_quick_view
        from .quick.schedule_backend import RaceScheduleBackend

        super().__init__(parent)
        self.set_utility_title(tr("Upcoming Races"))
        self.setMinimumSize(UIScaler.size(64), UIScaler.size(34))
        self.backend = RaceScheduleBackend(self)
        self.view = create_quick_view(self, "RaceSchedule.qml", {"backend": self.backend})
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.resize(UIScaler.size(90), UIScaler.size(56))
        QShortcut(QKeySequence(QKeySequence.StandardKey.Refresh), self, self.backend.readAgain)  # F5

    @staticmethod
    def page_minimum_size() -> QSize:
        """Page area minimum while shown in app window (see app.DialogPage): tabs & race cards text whole,
        French included"""
        return QSize(UIScaler.size(64), UIScaler.size(34))

    def showEvent(self, event):
        self.backend.page_shown()
        super().showEvent(event)

    def hideEvent(self, event):
        self.backend.page_hidden()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.release_page()
        super().closeEvent(event)
