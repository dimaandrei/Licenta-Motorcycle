from __future__ import print_function

import json
from time import sleep

import numpy as np
from PyQt5 import uic
from PyQt5.QtCore import QThread, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QImage, QPixmap
# from PyQt5.QtWebEngineWidgets import (QWebEngineView)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QMessageBox
)

from main import *


class ProcessedFramesViewer(QThread):
    changePixmap = pyqtSignal(QImage)
    changeLabel = pyqtSignal(str)

    def __init__(self, arr, cond, parent=None):
        super(ProcessedFramesViewer, self).__init__(parent)
        self.arr = arr
        self.cond = cond
        self.run_flag = True

    def run(self):
        while self.run_flag:
            try:
                with self.cond:
                    self.cond.wait()
                    frame = np.frombuffer(self.arr, dtype=np.ubyte, count=61440).reshape((128, 160, 3))
                    rgbImage = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgbImage.shape
                    bytesPerLine = ch * w
                    convertToQtFormat = QImage(rgbImage.data, w, h, bytesPerLine, QImage.Format_RGB888)
                    p = convertToQtFormat.scaled(320, 256, Qt.KeepAspectRatio)
                    self.changePixmap.emit(p)
                # if not self.frames_q.empty():
                #     frame = self.frames_q.get()
                #     rgbImage = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                #     h, w, ch = rgbImage.shape
                #     bytesPerLine = ch * w
                #     convertToQtFormat = QImage(rgbImage.data, w, h, bytesPerLine, QImage.Format_RGB888)
                #     p = convertToQtFormat.scaled(320, 256, Qt.KeepAspectRatio)
                #     self.changePixmap.emit(p)
            except Exception as e:
                print(e)

    def terminate(self) -> None:
        self.run_flag = False
        self.exit(0)


class SignsDetectedViewerUpdater(QThread):
    changeLabel = pyqtSignal(str)

    def __init__(self, commands_str_q, parent=None):
        super(SignsDetectedViewerUpdater, self).__init__(parent)
        self.commands_str_q = commands_str_q
        self.run_flag = True

    def run(self):
        while self.run_flag:
            try:
                if not self.commands_str_q.empty():
                    self.changeLabel.emit(self.commands_str_q.get())
            except Exception as e:
                print(e)

    def terminate(self) -> None:
        self.run_flag = False
        self.exit(0)


class Window(QMainWindow):
    def __init__(self, parent=None, ):
        super().__init__(parent)
        self.framesThreadViewer = None
        self.signsDetectedThreadUpdater = None
        uic.loadUi('./ui/MainWindow.ui', self)  # Load the .ui file
        self.darkTheme2 = self.loadColorJSON("./ui/themes/darkTheme")
        self.lightTheme = self.loadColorJSON("./ui/themes/lightTheme")
        self.connectSignalsSlots()
        self.setTheme("lightTheme")
        self.angleSliderValue = 108
        # WebEngine
        # self.webView = QWebEngineView(self.verticalWidget)
        # self.webView.setUrl(QtCore.QUrl("http:www.google.com"))
        # self.webView.setObjectName("webView")
        # # self.verticalLayout_2.insertWidget(0, self.webView)
        # self.webView.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        # self.autoControlMenu.layout().insertWidget(0, self.webView)
        # self.webView.show()

        self.frames_q = Queue(25)
        self.commands_bin_q = Queue()
        self.processed_frames_q = Queue(50)
        self.commands_str_q = Queue()
        self.con = Condition()
        self.arr = RawArray(ctypes.c_ubyte, 128 * 160 * 3)

        self.signDetectorStartedEvent = Event()
        self.showProcessedFramesEvent = Event()

        self.socketReceiver_process = SocketProcess(frames_queue=self.frames_q, commands_queue=self.commands_bin_q,
                                                    detector_started_event=self.signDetectorStartedEvent)
        self.classifier_process = Process(target=detectAndClassifySign, args=(self.frames_q, self.commands_bin_q,
                                                                              self.processed_frames_q,
                                                                              self.commands_str_q,
                                                                              self.signDetectorStartedEvent,
                                                                              self.showProcessedFramesEvent, self.con, self.arr))

        self.socketReceiver_process.start()
        self.classifier_process.start()

    def connectSignalsSlots(self):
        self.aboutButton.clicked.connect(self.about)
        self.manualControlButton.clicked.connect(self.manualControlCallback)
        self.autoControlButton.clicked.connect(self.autoControlCallback)
        self.backToMainMenu.clicked.connect(self.backToMainMenuCallback)
        self.actionDark_Theme.triggered.connect(self.changeToDarkThemeCallback)
        self.actionLight_Theme.triggered.connect(self.changeToLightThemeCallback)
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
        self.signsDetector_c.toggled.connect(self.signsDetectorStatusChanged)
        self.showCamera_c.toggled.connect(self.showCameraStatusChanged)

        self.angleSlider.sliderPressed.connect(self.sliderPressed)
        self.angleSlider.sliderReleased.connect(self.sliderReleased)

    def goForward_pressed(self):
        aux = getCommandEncoding(22, self.speedSlider.value())
        self.addUserCommand(aux)

    def goForward_released(self):
        aux = getCommandEncoding(22, 0)
        self.addUserCommand(aux)

    def goBackwards_pressed(self):
        aux = getCommandEncoding(23, self.speedSlider.value())
        self.addUserCommand(aux)

    def goBackwards_released(self):
        aux = getCommandEncoding(23, 0)
        self.addUserCommand(aux)

    def goToTheRight_pressed(self):
        for i in reversed(range(80, self.angleSlider.value() - 2, 2)):  # 106
            aux = getCommandEncoding(24, i)
            self.addUserCommand(aux)
            sleep(0.1)

    def goToTheRight_released(self):
        for i in range(82, self.angleSlider.value(), 2):  # 108
            aux = getCommandEncoding(24, i)
            self.addUserCommand(aux)
            sleep(0.1)

    def goToTheLeft_pressed(self):
        for i in range(self.angleSlider.value() + 2, 136, 2):  # 110
            aux = getCommandEncoding(24, i)
            self.addUserCommand(aux)
            sleep(0.1)

    def goToTheLeft_released(self):
        for i in reversed(range(self.angleSlider.value(), 134, 2)):  # 108
            aux = getCommandEncoding(24, i)
            self.addUserCommand(aux)
            sleep(0.1)

    def addUserCommand(self, command):
        if self.commands_bin_q.full():
            self.commands_bin_q.get_nowait()
        if command != b'\x00\x00':
            self.commands_bin_q.put(command)

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

    def signsDetectorStatusChanged(self):
        if self.signsDetector_c.isChecked():
            self.signDetectorStartedEvent.set()
            self.showCamera_c.setEnabled(True)
            self.signsDetectedThreadUpdater = SignsDetectedViewerUpdater(self.commands_str_q, self)
            self.signsDetectedThreadUpdater.changeLabel.connect(self.setLabel)
            self.signsDetectedThreadUpdater.start()
        else:
            self.signDetectorStartedEvent.clear()
            if self.showCamera_c.isChecked():
                self.showCamera_c.toggle()
            self.showCamera_c.setEnabled(False)
            self.signsDetectedThreadUpdater.changeLabel.disconnect(self.setLabel)
            self.signsDetectedThreadUpdater.terminate()
            self.signDetectedLine.setText("Sign detector not activated!")

    def showCameraStatusChanged(self):
        if self.showCamera_c.isChecked() and self.signsDetector_c.isChecked():
            self.showProcessedFramesEvent.set()
            self.framesThreadViewer = ProcessedFramesViewer(self.arr, self.con, self)
            self.framesThreadViewer.changePixmap.connect(self.setFrame)
            self.framesThreadViewer.start()
        else:
            self.showProcessedFramesEvent.clear()
            self.framesThreadViewer.changePixmap.disconnect(self.setFrame)
            self.framesThreadViewer.terminate()
            self.frameViewerLabel.setText("\tImage preview not selected")

    def sliderPressed(self):
        self.angleSliderValue = self.angleSlider.value()

    def sliderReleased(self):
        if self.angleSlider.value() != self.angleSliderValue:
            self.angleSliderChanged()

    def angleSliderChanged(self):
        if self.angleSlider.value() < self.angleSliderValue:  # to the right
            for i in reversed(range(self.angleSlider.value(), self.angleSliderValue-1, 1)):  # 106
                aux = getCommandEncoding(24, i)
                self.addUserCommand(aux)
                sleep(0.1)
        elif self.angleSlider.value() > self.angleSliderValue:  # to the left
            for i in range(self.angleSliderValue+1, self.angleSlider.value(), 1):  # 110
                aux = getCommandEncoding(24, i)
                self.addUserCommand(aux)
                sleep(0.1)

    @pyqtSlot(QImage)
    def setFrame(self, image):
        self.frameViewerLabel.setPixmap(QPixmap.fromImage(image))

    @pyqtSlot(str)
    def setLabel(self, string):
        self.signDetectedLine.setText(string)

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
        self.frameViewerLabel.setStyleSheet(f'background-color: {theme["menuBar"]}')

    @staticmethod
    def loadColorJSON(filePath):
        f = open(f'{filePath}.json')
        theme = json.load(f)
        f.close()
        return theme

    def closeEvent(self, close_event):
        print("Exiting all child processes..")
        self.classifier_process.terminate()
        self.socketReceiver_process.terminate()
        if self.framesThreadViewer is not None and self.framesThreadViewer.isRunning():
            self.framesThreadViewer.terminate()
        if self.signsDetectedThreadUpdater is not None and self.signsDetectedThreadUpdater.isRunning():
            self.signsDetectedThreadUpdater.terminate()
        self.frames_q.close()
        self.commands_bin_q.close()
        self.frames_q.join_thread()
        self.commands_bin_q.join_thread()
        close_event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Window(None)
    win.show()
    sys.exit(app.exec())
