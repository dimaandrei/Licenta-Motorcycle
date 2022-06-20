from __future__ import print_function

import json
import sys

from PyQt5 import QtCore
from PyQt5 import uic
# from PyQt5.QtWebEngineWidgets import (QWebEngineView)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QSizePolicy
)
from main import *


class Window(QMainWindow):
    def __init__(self, parent=None, ):
        super().__init__(parent)
        uic.loadUi('./ui/MainWindow.ui', self)  # Load the .ui file
        self.darkTheme2 = self.loadColorJSON("./ui/themes/darkTheme")
        self.lightTheme = self.loadColorJSON("./ui/themes/lightTheme")
        self.connectSignalsSlots()
        self.setTheme("lightTheme")

        # WebEngine
        # self.webView = QWebEngineView(self.verticalWidget)
        # self.webView.setUrl(QtCore.QUrl("http:www.google.com"))
        # self.webView.setObjectName("webView")
        # # self.verticalLayout_2.insertWidget(0, self.webView)
        # self.webView.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        # self.autoControlMenu.layout().insertWidget(0, self.webView)
        # self.webView.show()

        self.frames_q = Queue()
        self.commands_q = Queue()

        self.socketReceiver_process = SocketProcess(frames_queue=self.frames_q, commands_queue=self.commands_q)
        self.classifier_process = Process(target=detectAndClassifySign, args=(self.frames_q, self.commands_q))

        self.socketReceiver_process.start()
        self.classifier_process.start()

    def connectSignalsSlots(self):
        self.aboutButton.clicked.connect(self.about)
        self.manualControlButton.clicked.connect(self.manualControlCallback)
        self.autoControlButton.clicked.connect(self.autoControlCallback)
        self.backToMainMenu.clicked.connect(self.backToMainMenuCallback)
        self.actionDark_Theme.triggered.connect(self.changeToDarkThemeCallback)
        self.actionLight_Theme.triggered.connect(self.changeToLightThemeCallback)
        self.startVideoFeedButton.clicked.connect(self.videoCallback)
        self.backToMainFM.clicked.connect(self.backToMainMenuCallback)
        # Pressed && Released

        self.goForward.pressed.connect(self.goForward_pressed)
        self.goForward.released.connect(self.goForward_released)
        self.goBackwards.pressed.connect(self.goBackwards_pressed)
        self.goBackwards.released.connect(self.goBackwards_released)
        self.goToTheLeft.pressed.connect(self.goToTheLeft_pressed)
        self.goToTheLeft.released.connect(self.goToTheLeft_released)
        self.goToTheRight.pressed.connect(self.goToTheRight_pressed)
        self.goToTheRight.released.connect(self.goToTheRight_released)

        self.activatePID_c.toggled.connect(self.pidStatusChanged)
        self.avoidCollision_c.toggled.connect(self.obstaclesDetectorStatusChanged)

    def goForward_pressed(self):
        aux = getCommandEncoding(22, 80)
        self.addUserCommand(aux)

    def goForward_released(self):
        aux = getCommandEncoding(22, 0)
        self.addUserCommand(aux)

    def goBackwards_pressed(self):
        aux = getCommandEncoding(23, 80)
        self.addUserCommand(aux)

    def goBackwards_released(self):
        aux = getCommandEncoding(23, 0)
        self.addUserCommand(aux)

    def goToTheRight_pressed(self):
        for i in reversed(range(80, 106, 2)):
            aux = getCommandEncoding(24, i)
            self.addUserCommand(aux)
            from time import sleep
            sleep(0.1)

    def goToTheRight_released(self):
        for i in range(82, 108, 2):
            aux = getCommandEncoding(24, i)
            self.addUserCommand(aux)
            from time import sleep
            sleep(0.1)

    def goToTheLeft_pressed(self):
        for i in range(110, 136, 2):
            aux = getCommandEncoding(24, i)
            self.addUserCommand(aux)
            from time import sleep
            sleep(0.1)

    def goToTheLeft_released(self):
        for i in reversed(range(108, 134, 2)):
            aux = getCommandEncoding(24, i)
            self.addUserCommand(aux)
            from time import sleep
            sleep(0.1)

    def addUserCommand(self, command):
        if self.commands_q.full():
            self.commands_q.get_nowait()
        if command != b'\x00\x00':
            self.commands_q.put(command)

    def pidStatusChanged(self):
        aux = None
        if self.activatePID_c.isChecked():
            aux = getCommandEncoding(20, 0)
        else:
            aux = getCommandEncoding(21, 0)
        self.addUserCommand(aux)

    def obstaclesDetectorStatusChanged(self):
        aux = None
        if self.avoidCollision_c.isChecked():
            aux = getCommandEncoding(25, 0)
        else:
            aux = getCommandEncoding(26, 0)
        self.addUserCommand(aux)

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
        print("Exiting all child processes..")
        self.classifier_process.terminate()
        self.socketReceiver_process.terminate()
        # user_comm_process.terminate()
        self.frames_q.close()
        self.commands_q.close()
        self.frames_q.join_thread()
        self.commands_q.join_thread()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Window(None)
    win.show()
    sys.exit(app.exec())
