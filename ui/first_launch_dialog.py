"""
首次启动/更新提示对话框
"""
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt, QTimer

from ui.i18n import i18n

# 当 NOTICE_VERSION 变更时，即便用户此前确认过，也会再次提示
NOTICE_VERSION = "2026-03-12"


class FirstLaunchDialog(QDialog):
    """首次启动时显示的免责声明与使用提示。"""

    COUNTDOWN_SECONDS = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(520)

        self._seconds_left = self.COUNTDOWN_SECONDS

        self.lbl_content = QLabel()
        self.lbl_content.setWordWrap(True)
        self.lbl_content.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.lbl_content.setOpenExternalLinks(True)

        self.lbl_hint = QLabel()
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("color: #666;")

        self.btn_confirm = QPushButton()
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self.lbl_content)
        layout.addWidget(self.lbl_hint)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.btn_confirm)
        layout.addLayout(btn_row)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._update_confirm_text()

        i18n.language_changed.connect(self._retranslate)
        self._retranslate()

    def _tick(self):
        self._seconds_left -= 1
        if self._seconds_left <= 0:
            self._timer.stop()
            self.btn_confirm.setEnabled(True)
        self._update_confirm_text()

    def _retranslate(self, _lang=None):
        self.setWindowTitle(i18n.t("welcome_title"))
        self.lbl_content.setText(i18n.t("welcome_message"))
        self.lbl_hint.setText(i18n.t("welcome_hint"))

        self._update_confirm_text()

    def _update_confirm_text(self):
        if self.btn_confirm.isEnabled():
            self.btn_confirm.setText(i18n.t("welcome_confirm"))
        else:
            self.btn_confirm.setText(i18n.t("welcome_confirm_countdown", self._seconds_left))
