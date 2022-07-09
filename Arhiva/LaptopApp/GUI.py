from __future__ import print_function

import ctypes
import json
from time import sleep

from PyQt5 import uic
from PyQt5.QtCore import QThread, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QMessageBox
)
from multiprocessing import Condition, RawArray

from main import *


class ProcessedFrameRecvThread(QThread):
    changePixmapSignal = pyqtSignal(QImage)

    def __init__(self, sharedByteArray, condition, parent=None):
        super(ProcessedFrameRecvThread, self).__init__(parent)
        self.sharedByteArray = sharedByteArray
        self.condition = condition
        self.runFlag = True

    def run(self):
        while self.runFlag:
            try:
                with self.condition:
                    self.condition.wait()
                    frame = np.frombuffer(self.sharedByteArray, dtype=np.ubyte,
                                          count=YOLO_FRAME_BYTES_NO).reshape(YOLO_FRAME_SHAPE)
                    rgbImage = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgbImage.shape
                    bytesPerLine = ch * w
                    convertToQtFormat = QImage(rgbImage.data, w, h, bytesPerLine, QImage.Format_RGB888)
                    qFrame = convertToQtFormat.scaled(320, 256, Qt.KeepAspectRatio)

                    self.changePixmapSignal.emit(qFrame)
            except Exception as e:
                print(e)

    def terminate(self) -> None:
        self.runFlag = False
        with self.condition:
            self.condition.notify()


class ExtractedSignRecvThread(QThread):
    changePixmapSignal = pyqtSignal(QImage)

    def __init__(self, sharedByteArraySign, condition, parent=None):
        super(ExtractedSignRecvThread, self).__init__(parent)
        self.sharedByteArraySign = sharedByteArraySign
        self.condition = condition
        self.runFlag = True

    def run(self):
        while self.runFlag:
            try:
                with self.condition:
                    self.condition.wait()
                    frame = np.frombuffer(self.sharedByteArraySign,
                                          dtype=np.ubyte, count=SIGN_EXTRACTED_BYTES_NO).reshape(SIGN_EXTRACTED_SHAPE)
                    rgbImage = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgbImage.shape
                    bytesPerLine = ch * w
                    convertToQtFormat = QImage(rgbImage.data, w, h, bytesPerLine, QImage.Format_RGB888)
                    qFrame = convertToQtFormat.scaled(100, 100, Qt.KeepAspectRatio)

                    self.changePixmapSignal.emit(qFrame)
            except Exception as e:
                print(e)

    def terminate(self) -> None:
        self.runFlag = False
        with self.condition:
            self.condition.notify()


class SignNameRecvThread(QThread):
    changeLabelSignal = pyqtSignal(str)

    def __init__(self, strCommandsQ, parent=None):
        super(SignNameRecvThread, self).__init__(parent)
        self.strCommandsQ = strCommandsQ
        self.runFlag = True

    def run(self):
        while self.runFlag:
            try:
                if not self.strCommandsQ.empty():
                    self.changeLabelSignal.emit(self.strCommandsQ.get())
            except Exception as e:
                print(e)

    def terminate(self) -> None:
        self.runFlag = False


class Window(QMainWindow):
    def __init__(self, parent=None, ):
        super().__init__(parent)
        self.extractedSignRecvThread = None
        self.processedFrameRecvThread = None
        self.signNameRecvThread = None
        uic.loadUi('./ui/MainWindow.ui', self)  # Load the .ui file
        self.darkTheme = self.loadColorJSON("./ui/themes/darkTheme")
        self.lightTheme = self.loadColorJSON("./ui/themes/lightTheme")
        self.connectSignalsSlots()
        self.setTheme("lightTheme")
        self.angleSliderValue = 108  # Middle

        self.piFramesQ = Queue(25)
        self.binCommandsQ = Queue()
        self.strCommandsQ = Queue()

        self.availableProcessedFrameCond = Condition()
        self.availableExtractedSignCond = Condition()

        self.yoloAnnotatedFrameBArr = RawArray(ctypes.c_ubyte, YOLO_FRAME_BYTES_NO)
        self.yoloExtractedSignBArr = RawArray(ctypes.c_ubyte, SIGN_EXTRACTED_BYTES_NO)

        self.signDetectorStartedEvent = Event()
        self.showProcessedFrameEvent = Event()

        self.piSocketReceiverProcess = SocketProcess(framesQueue=self.piFramesQ, commandsQueue=self.binCommandsQ,
                                                     detectorStartedEvent=self.signDetectorStartedEvent)
        self.classifierProcess = Process(target=detectAndClassifySign, args=(self.piFramesQ, self.binCommandsQ,
                                                                             self.strCommandsQ,
                                                                             self.signDetectorStartedEvent,
                                                                             self.showProcessedFrameEvent,
                                                                             self.availableProcessedFrameCond,
                                                                             self.availableExtractedSignCond,
                                                                             self.yoloAnnotatedFrameBArr,
                                                                             self.yoloExtractedSignBArr))

        self.piSocketReceiverProcess.start()
        self.classifierProcess.start()

    def connectSignalsSlots(self):
        self.aboutButton.clicked.connect(self.about)
        self.manualControlButton.clicked.connect(self.manualControlCallback)
        self.autoControlButton.clicked.connect(self.autoControlCallback)
        self.backToMainMenu.clicked.connect(self.backToMainMenuCallback)
        self.actionDark_Theme.triggered.connect(self.changeToDarkThemeCallback)
        self.actionLight_Theme.triggered.connect(self.changeToLightThemeCallback)
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
        self.signsDetector_c.toggled.connect(self.signsDetectorCheckboxCallback)
        self.showCamera_c.toggled.connect(self.showYoloFramesCheckboxCallback)

        self.angleSlider.sliderPressed.connect(self.sliderPressedCallback)
        self.angleSlider.sliderReleased.connect(self.sliderReleasedCallback)

    def goForward_pressed(self):
        aux = getCommandEncoding(24, 108)
        self.addUserCommand(aux)
        aux = getCommandEncoding(22, self.speedSlider.value())
        self.addUserCommand(aux)

    def goForward_released(self):
        aux = getCommandEncoding(22, 0)
        self.addUserCommand(aux)

    def goBackwards_pressed(self):
        aux = getCommandEncoding(24, 108)
        self.addUserCommand(aux)
        aux = getCommandEncoding(23, self.speedSlider.value())
        self.addUserCommand(aux)

    def goBackwards_released(self):
        aux = getCommandEncoding(23, 0)
        self.addUserCommand(aux)

    def goToTheRight_pressed(self):
        if not self.backwardsTurn_c.isChecked():
            self.goForward_pressed()
        else:
            self.goBackwards_pressed()
        self.backwardsTurn_c.setEnabled(False)
        for i in reversed(range(108 - self.rateOfTurnSlider.value(), self.angleSlider.value() - 2, 2)):  # 106
            aux = getCommandEncoding(24, i)
            self.addUserCommand(aux)
            sleep(0.1)

    def goToTheRight_released(self):
        if not self.backwardsTurn_c.isChecked():
            self.goForward_released()
        else:
            self.goBackwards_released()
        self.backwardsTurn_c.setEnabled(True)
        for i in range(108 - self.rateOfTurnSlider.value() + 2, self.angleSlider.value(), 2):  # 82 && 108
            aux = getCommandEncoding(24, i)
            self.addUserCommand(aux)
            sleep(0.1)

    def goToTheLeft_pressed(self):
        if not self.backwardsTurn_c.isChecked():
            self.goForward_pressed()
        else:
            self.goBackwards_pressed()
        self.backwardsTurn_c.setEnabled(False)
        for i in range(self.angleSlider.value() + 2, 108 + self.rateOfTurnSlider.value(), 2):  # 110 && 136
            aux = getCommandEncoding(24, i)
            self.addUserCommand(aux)
            sleep(0.1)

    def goToTheLeft_released(self):
        if not self.backwardsTurn_c.isChecked():
            self.goForward_released()
        else:
            self.goBackwards_released()
        self.backwardsTurn_c.setEnabled(True)
        for i in reversed(range(self.angleSlider.value(), 108 + self.rateOfTurnSlider.value() - 2, 2)):  # 108 && 134
            aux = getCommandEncoding(24, i)
            self.addUserCommand(aux)
            sleep(0.1)

    def addUserCommand(self, command):
        if self.binCommandsQ.full():
            self.binCommandsQ.get_nowait()
        if command != b'\x00\x00':
            self.binCommandsQ.put(command)

    def pidStatusChanged(self):
        if self.activatePID_c.isChecked():
            aux = getCommandEncoding(20, 0)
        else:
            aux = getCommandEncoding(21, 0)
        self.addUserCommand(aux)

    def obstaclesDetectorStatusChanged(self):
        if self.avoidCollision_c.isChecked():
            aux = getCommandEncoding(25, 0)
        else:
            aux = getCommandEncoding(26, 0)
        self.addUserCommand(aux)

    def signsDetectorCheckboxCallback(self):
        if self.signsDetector_c.isChecked():
            self.signDetectorStartedEvent.set()
            self.showCamera_c.setEnabled(True)
            self.signNameRecvThread = SignNameRecvThread(self.strCommandsQ, self)
            self.signNameRecvThread.setObjectName("Sign name receiver THREAD")
            self.signNameRecvThread.changeLabelSignal.connect(self.setSignNameLabelSlot)
            self.signNameRecvThread.start()
            self.signDetectedLine.setText("Sign detector activated..")
        else:
            self.signDetectorStartedEvent.clear()
            if self.showCamera_c.isChecked():
                self.showCamera_c.toggle()
            self.showCamera_c.setEnabled(False)
            self.signNameRecvThread.changeLabelSignal.disconnect(self.setSignNameLabelSlot)
            self.signNameRecvThread.terminate()
            self.signDetectedLine.setText("Sign detector not activated!")

    def showYoloFramesCheckboxCallback(self):
        if self.showCamera_c.isChecked() and self.signsDetector_c.isChecked():
            self.showProcessedFrameEvent.set()
            self.processedFrameRecvThread = ProcessedFrameRecvThread(self.yoloAnnotatedFrameBArr,
                                                                     self.availableProcessedFrameCond, self)
            self.processedFrameRecvThread.setObjectName("Processed YOLO frame receiver THREAD")
            self.processedFrameRecvThread.changePixmapSignal.connect(self.setYoloProcessedFrameSlot)
            self.processedFrameRecvThread.start()

            self.extractedSignRecvThread = ExtractedSignRecvThread(self.yoloExtractedSignBArr,
                                                                   self.availableExtractedSignCond, self)
            self.extractedSignRecvThread.setObjectName("Extracted sign frame receiver THREAD")
            self.extractedSignRecvThread.changePixmapSignal.connect(self.setExtractedSignFrameSlot)
            self.extractedSignRecvThread.start()
        elif not self.showCamera_c.isChecked():
            self.showProcessedFrameEvent.clear()

            self.processedFrameRecvThread.changePixmapSignal.disconnect(self.setYoloProcessedFrameSlot)
            self.processedFrameRecvThread.terminate()
            self.frameViewerLabel.setText("\tImage preview not selected")

            self.extractedSignRecvThread.changePixmapSignal.disconnect(self.setExtractedSignFrameSlot)
            self.extractedSignRecvThread.terminate()
            self.signDetectedLabel.setText("       Sign")

    def sliderPressedCallback(self):
        self.angleSliderValue = self.angleSlider.value()

    def sliderReleasedCallback(self):
        if self.angleSlider.value() != self.angleSliderValue:
            self.angleSliderChangedCallback()

    def angleSliderChangedCallback(self):
        if self.angleSlider.value() < self.angleSliderValue:  # to the right
            for i in reversed(range(self.angleSlider.value(), self.angleSliderValue - 1, 1)):  # 106
                aux = getCommandEncoding(24, i)
                self.addUserCommand(aux)
                sleep(0.1)
        elif self.angleSlider.value() > self.angleSliderValue:  # to the left
            for i in range(self.angleSliderValue + 1, self.angleSlider.value(), 1):  # 110
                aux = getCommandEncoding(24, i)
                self.addUserCommand(aux)
                sleep(0.1)

    @pyqtSlot(QImage)
    def setYoloProcessedFrameSlot(self, image):
        self.frameViewerLabel.setPixmap(QPixmap.fromImage(image))

    @pyqtSlot(QImage)
    def setExtractedSignFrameSlot(self, image):
        self.signDetectedLabel.setPixmap(QPixmap.fromImage(image))

    @pyqtSlot(str)
    def setSignNameLabelSlot(self, string):
        self.signDetectedLine.setText(string)

    def about(self):
        QMessageBox.about(
            self,
            "About 'Moto-App'",
            "<p>GUI built with:</p>"
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
        self.signDetectedLabel.setStyleSheet(f'background-color: {theme["menuBar"]}')
        self.goForward.setStyleSheet(f'background-color: {theme["menuBar"]}')
        self.goToTheLeft.setStyleSheet(f'background-color: {theme["menuBar"]}')
        self.goToTheRight.setStyleSheet(f'background-color: {theme["menuBar"]}')
        self.goBackwards.setStyleSheet(f'background-color: {theme["menuBar"]}')

    @staticmethod
    def loadColorJSON(filePath):
        f = open(f'{filePath}.json')
        theme = json.load(f)
        f.close()
        return theme

    def closeEvent(self, close_event):
        print("Exiting all child processes..")

        self.classifierProcess.terminate()
        self.piSocketReceiverProcess.terminate()

        if self.processedFrameRecvThread is not None and self.processedFrameRecvThread.isRunning():
            self.processedFrameRecvThread.terminate()
        if self.signNameRecvThread is not None and self.signNameRecvThread.isRunning():
            self.signNameRecvThread.terminate()
        if self.extractedSignRecvThread is not None and self.extractedSignRecvThread.isRunning():
            self.extractedSignRecvThread.terminate()

        self.piFramesQ.close()
        self.binCommandsQ.close()
        self.strCommandsQ.close()

        self.piFramesQ.join_thread()
        self.binCommandsQ.join_thread()
        self.strCommandsQ.join_thread()
        close_event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Window(None)
    win.show()
    sys.exit(app.exec())
