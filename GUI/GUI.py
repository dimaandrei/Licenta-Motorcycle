from __future__ import print_function

import json
import sys

from PyQt5 import QtCore
from PyQt5 import uic
from PyQt5.QtWebEngineWidgets import (QWebEngineView)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QSizePolicy
)


class Window(QMainWindow):
    def __init__(self, parent=None, ):
        super().__init__(parent)
        uic.loadUi('./ui/MainWindow.ui', self)  # Load the .ui file
        self.darkTheme2 = self.loadColorJSON("./ui/themes/darkTheme")
        self.lightTheme = self.loadColorJSON("./ui/themes/lightTheme")
        self.connectSignalsSlots()
        self.setTheme("darkTheme")

        # WebEngine
        self.webView = QWebEngineView(self.verticalWidget)
        self.webView.setUrl(QtCore.QUrl("http:www.google.com"))
        self.webView.setObjectName("webView")
        # self.verticalLayout_2.insertWidget(0, self.webView)
        self.webView.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        self.autoControlMenu.layout().insertWidget(0, self.webView)
        self.webView.show()

    def connectSignalsSlots(self):
        self.aboutButton.clicked.connect(self.about)
        self.manualControlButton.clicked.connect(self.manualControlCallback)
        self.autoControlButton.clicked.connect(self.autoControlCallback)
        self.backToMainMenu.clicked.connect(self.backToMainMenuCallback)
        self.actionDark_Theme.triggered.connect(self.changeToDarkThemeCallback)
        self.actionLight_Theme.triggered.connect(self.changeToLightThemeCallback)
        self.startVideoFeedButton.clicked.connect(self.videoCallback)

    def about(self):
        QMessageBox.about(
            self,
            "About 'Moto-App'",
            "<p>A sample app built with:</p>"
            "<p>- PyQt</p>"
            "<p>- Qt Designer</p>"
            "<p>- Python</p>",
        )

    def manualControlCallback(self):
        self.stackedWidget.setCurrentIndex(1)

    def autoControlCallback(self):
        self.stackedWidget.setCurrentIndex(2)

    def backToMainMenuCallback(self):
        self.stackedWidget.setCurrentIndex(0)

    def changeToDarkThemeCallback(self):
        self.setTheme("darkTheme")

    def changeToLightThemeCallback(self):
        self.setTheme("lightTheme")

    def videoCallback(self):
        pass

    def setTheme(self, themeName):
        theme = self.loadColorJSON(f'./ui/themes/{themeName}')
        self.menubar.setStyleSheet(f'background-color: {theme["menuBar"]}')
        self.setStyleSheet(f'background-color: {theme["background"]}')
        self.autoControlButton.setStyleSheet(f'background-color: {theme["buttons"]}')
        self.manualControlButton.setStyleSheet(f'background-color: {theme["buttons"]}')
        self.aboutButton.setStyleSheet(f'background-color: {theme["buttons"]}')
        self.startVideoFeedButton.setStyleSheet(f'background-color: {theme["buttons"]}')
        self.backToMainMenu.setStyleSheet(f'background-color: {theme["buttons"]}')
        self.speakBotton.setStyleSheet(f'background-color: {theme["buttons"]}')

    @staticmethod
    def loadColorJSON(filePath):
        f = open(f'{filePath}.json')
        theme = json.load(f)
        f.close()
        return theme

    def closeEvent(self, event):
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Window(None)
    win.show()
    sys.exit(app.exec())
