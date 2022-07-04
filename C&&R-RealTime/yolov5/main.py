import ctypes
import os
import pickle
import queue
import socket
import struct
import sys
import threading
import time
from multiprocessing import Process, Queue, Event, Condition, RawArray
from pathlib import Path
from signal import signal, SIGINT
from sys import exit

import cv2
import numpy as np
import tensorflow as tf
import torch
import torch.backends.cudnn as cudnn

from models.common import DetectMultiBackend
from utils.augmentations import letterbox
from utils.general import (check_img_size,
                           non_max_suppression, scale_coords)
from utils.plots import Annotator, colors, save_one_box
from utils.torch_utils import select_device

FILE = Path(__file__).resolve()
ROOT = FILE.parents[0]  # YOLOv5 root directory
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH
ROOT = Path(os.path.relpath(ROOT, Path.cwd()))  # relative

YOLO_FRAME_SHAPE = (128, 160, 3)
SIGN_EXTRACTED_SHAPE = (32, 32, 3)
YOLO_FRAME_BYTES_NO = YOLO_FRAME_SHAPE[0] * YOLO_FRAME_SHAPE[1] * YOLO_FRAME_SHAPE[2]
SIGN_EXTRACTED_BYTES_NO = SIGN_EXTRACTED_SHAPE[0] * SIGN_EXTRACTED_SHAPE[1] * SIGN_EXTRACTED_SHAPE[2]


def grayscale(in_img):
    return cv2.cvtColor(in_img, cv2.COLOR_BGR2GRAY)


def equalize(in_img):
    return cv2.equalizeHist(in_img)


def preprocessing(in_img):
    out_img = grayscale(in_img)
    out_img = equalize(out_img)
    out_img = out_img / 255
    return out_img


def getClassName(classNo):
    if classNo == 0:
        return 'Speed Limit 30 km/h'
    elif classNo == 1:
        return 'Speed Limit 50 km/h'
    elif classNo == 2:
        return 'Speed Limit 70 km/h'
    elif classNo == 3:
        return 'Priority road'
    elif classNo == 4:
        return 'Yield'
    elif classNo == 5:
        return 'Stop'
    elif classNo == 6:
        return 'No vehicles'
    elif classNo == 7:
        return 'No entry'
    elif classNo == 8:
        return 'Turn right ahead'
    elif classNo == 9:
        return 'Turn left ahead'
    elif classNo == 10:
        return 'Ahead only'
    elif classNo == 11:
        return 'Go straight or right'
    elif classNo == 12:
        return 'Go straight or left'
    elif classNo == 13:
        return 'Keep right'
    elif classNo == 14:
        return 'Keep left'


def getCommandEncoding(commandNo, execValue):
    if commandNo == 5:  # STOP sign - speed = 0
        return b'\x02\x00'
    elif commandNo == 7:  # No entry - speed = 0
        return b'\x02\x00'
    elif commandNo == 0:  # 30km/h - speed = 0
        return b'\x02\x30'
    elif commandNo == 1:  # 50km/h - speed = 0
        return b'\x02\x40'
    elif commandNo == 2:  # 70km/h - speed = 0
        return b'\x02\x50'
    elif commandNo == 8:  # turn right ahead
        return b'\x03\x5C'
    elif commandNo == 9:  # turn left ahead 
        return b'\x03\x7C'
    elif commandNo == 10:  # go straight ahead
        return b'\x03\x6C'

    # Starting with this value these are `admin-manual` commands
    elif commandNo == 20:  # Turn on PID algorithm
        return b'\x01\x01'

    elif commandNo == 21:  # Turn off PID algorithm
        return b'\x01\x00'

    elif commandNo == 22:  # Go forward
        if execValue < 0:
            return b'\x02\x00'
        elif execValue > 255:
            return b'\x02\xFF'
        else:
            aux = 0x0200 | execValue
            return aux.to_bytes(2, 'big')

    elif commandNo == 23:  # Go backwards
        if execValue < 0:
            return b'\x12\x00'
        elif execValue > 255:
            return b'\x12\xFF'
        else:
            aux = 0x1200 | execValue
            return aux.to_bytes(2, 'big')

    elif commandNo == 24:  # Turn
        if execValue < 78:
            return b'\x03\x4E'
        elif execValue > 138:
            return b'\x03\x8A'
        else:
            aux = 0x0300 | execValue
            return aux.to_bytes(2, 'big')

    elif commandNo == 25:  # Turn on front objects detection
        return b'\x04\x01'
    elif commandNo == 26:  # Turn off front objects detection
        return b'\x04\x00'
    else:
        return b'\x00\x00'


# address = ('192.168.32.161', 10050)

class SocketProcess(Process):
    def __init__(self, framesQueue, commandsQueue, detectorStartedEvent, host='192.168.0.187', port=10050):
        super(SocketProcess, self).__init__()
        self.clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.hostIp = host
        self.port = port
        self.commandsQueue = commandsQueue
        self.framesQueue = framesQueue
        self.detectorStartedEvent = detectorStartedEvent
        self.runSendThread = True
        self.sendSocketCommandsThread = threading.Thread(target=self.threadToWaitForPredictionAndSend)

    def run(self) -> None:
        try:
            self.clientSocket.connect((self.hostIp, self.port))
            self.sendSocketCommandsThread.start()
            data = b''
            # Q: unsigned long long integer(8 bytes)
            payloadSize = struct.calcsize("Q")

            while True:  # shared condition here!!

                while len(data) < payloadSize:
                    packet = self.clientSocket.recv(4 * 1024)
                    if not packet:
                        break
                    data += packet
                    # print(f'{len(data)}-{payload_size}')

                packedMsgSize = data[:payloadSize]
                data = data[payloadSize:]
                msgSize = struct.unpack("Q", packedMsgSize)[0]

                while len(data) < msgSize:
                    data += self.clientSocket.recv(4 * 1024)
                frame_data = data[:msgSize]
                data = data[msgSize:]

                if not self.detectorStartedEvent.is_set():
                    # we drop the frame if signs detector is not activated
                    continue

                # print("Processing frame..")
                try:
                    if self.framesQueue.full():
                        # we don't care about older frames if the queue is full
                        self.framesQueue.get_nowait()
                    self.framesQueue.put(frame_data)
                except queue.Empty as e:
                    pass
                    # print("Queue is empty!")
        except socket.error as e:
            print(f'Socket exception: {e}')
        except struct.error as e:
            print(f'Struct exception: {e}')
        finally:
            self.runSendThread = False
            if self.sendSocketCommandsThread.is_alive():
                self.sendSocketCommandsThread.join()

    def threadToWaitForPredictionAndSend(self):
        try:
            while self.runSendThread:
                if self.commandsQueue.empty():
                    pass
                else:
                    command = self.commandsQueue.get()
                    # print(command)
                    message = struct.pack("B", len(command)) + command
                    self.clientSocket.sendall(message)
        except socket.error as e:
            print(f'Socket exception: {e}')

    def terminate(self) -> None:
        self.runSendThread = False
        if self.sendSocketCommandsThread.is_alive():
            self.sendSocketCommandsThread.join()
        super(SocketProcess, self).terminate()


@torch.no_grad()
def detectAndClassifySign(framesQueue, byteCommandsQueue, strCommandsQueue,
                          detectorStartedEvent, showProcessedFrameEvent, writeYoloFrameCondition,
                          writeExtractedSignCondition, processedFrameSharedArray, extractedSignSharedArray,
                          imgSize=(160, 128)):
    print("Inference started!")
    # Load the VGG model
    vggTrainedModel = tf.keras.models.load_model(ROOT / 'weights/model_vgg_training_v2.h5')
    vggTrainedModel.trainable = False
    # Load the YOLO model
    device = select_device('0')
    model = DetectMultiBackend(ROOT / 'weights/best.pt', device=device, dnn=False, data=ROOT / 'config.yaml')
    stride, names, pt = model.stride, model.names, model.pt
    imgSize = check_img_size(imgSize, s=stride)  # check image size

    # Dataloader
    cudnn.benchmark = True  # set True to speed up constant image size inference

    model.warmup(imgsz=(1 if pt else 1, 3, *imgSize))  # warmup
    lastPrediction = None
    while True:  # Condition here!
        startTime = time.time()
        if detectorStartedEvent.is_set() and not framesQueue.empty():
            # print("Detecting signs from frame..")
            framePickle = framesQueue.get()
            frame = pickle.loads(framePickle)
            npFrameArray = np.frombuffer(frame, np.uint8)
            frame = cv2.imdecode(npFrameArray, cv2.IMREAD_COLOR)
            originalImg = frame.copy()

            frame = letterbox(frame, imgSize, stride=stride, auto=pt)[0]
            frame = frame.transpose((2, 0, 1))[::-1]  # HWC to CHW, BGR to RGB
            frame = np.ascontiguousarray(frame)

            seen = 0
            im = torch.from_numpy(frame).to(device)
            im = im.float()  # uint8 to fp16/32
            im /= 255  # 0 - 255 to 0.0 - 1.0
            if len(im.shape) == 3:
                im = im[None]  # expand for batch dim
            predictions = model(im, augment=False,
                                visualize=False)  # We don't want to augment inference or visualize features at this moment

            # NMS
            predictions = non_max_suppression(predictions, conf_thres=0.25, iou_thres=0.45, max_det=10)

            # Process predictions
            for i, det in enumerate(predictions):  # per image
                seen += 1

                auxImgForCropping = originalImg.copy()  # for save_crop
                annotator = Annotator(originalImg, line_width=1, example=str(names))
                if len(det):
                    # Rescale boxes from img_size to im0 size
                    det[:, :4] = scale_coords(im.shape[2:], det[:, :4], originalImg.shape).round()

                    # Write results
                    for *xyxy, conf, cls in reversed(det):
                        c = int(cls)  # integer class
                        label = f'{names[c]} {conf:.2f}'
                        annotator.box_label(xyxy, label, color=colors(c, True))

                        signExtracted = save_one_box(xyxy, auxImgForCropping, BGR=True, save=False)

                        signExtracted = cv2.resize(signExtracted, (32, 32))

                        if showProcessedFrameEvent.is_set():
                            with writeExtractedSignCondition:
                                temp2 = np.frombuffer(buffer=extractedSignSharedArray, dtype=np.ubyte,
                                                      count=SIGN_EXTRACTED_BYTES_NO).reshape(
                                    (32, 32, 3))
                                np.copyto(temp2, signExtracted)
                                writeExtractedSignCondition.notify_all()

                        signPreprocessed = preprocessing(signExtracted)

                        signPreprocessed = signPreprocessed.reshape(1, 32, 32, 1)
                        # PREDICT IMAGE
                        vggPredictions = vggTrainedModel.predict(signPreprocessed)
                        classIndex = vggTrainedModel.predict_classes(signPreprocessed)
                        probabilityValue = np.amax(vggPredictions)
                        if probabilityValue > 0.85:
                            if lastPrediction is None or lastPrediction != classIndex:  # add in queue different detections
                                lastPrediction = classIndex
                                aux = getCommandEncoding(classIndex, 0)
                                if aux != b'\x00\x00':
                                    if byteCommandsQueue.full():
                                        byteCommandsQueue.get_nowait()
                                    byteCommandsQueue.put(getCommandEncoding(classIndex, 0))
                                if strCommandsQueue.full():
                                    strCommandsQueue.get_nowait()
                                strCommandsQueue.put(getClassName(classIndex))

                else:
                    lastPrediction = None

                if showProcessedFrameEvent.is_set():
                    with writeYoloFrameCondition:
                        # Stream results
                        originalImg = annotator.result()
                        temp1 = np.frombuffer(buffer=processedFrameSharedArray, dtype=np.ubyte, count=61440).reshape(
                            (128, 160, 3))
                        np.copyto(temp1, originalImg)
                        writeYoloFrameCondition.notify_all()
                        # try:
                        #     if processed_frame_queue.full():
                        #         processed_frame_queue.get_nowait()
                        #     processed_frame_queue.put(im0)
                        # except queue.Empty as e:
                        #     pass
            # print(f'FPS:{ 1.0 / (time.time() - startTime)}  SIZE: {frames_queue.qsize()}')  # FPS = 1 / time to
            # process loop


event = Event()


def handler(signal_received, frame):
    event.set()


def main():
    print("Test started!")
    # detectAndClassifySign()
    signal(SIGINT, handler)

    framesQ = Queue(50)
    commandsQ = Queue()
    strCommandsQ = Queue()
    detectorStartedEvent = Event()
    showProcessedFrameEvent = Event()
    socketReceiverProcess = SocketProcess(framesQueue=framesQ,
                                          commandsQueue=commandsQ, detectorStartedEvent=detectorStartedEvent)

    # Declare RawArray for testing this!!
    classifierProcess = Process(target=detectAndClassifySign, args=(framesQ, commandsQ, strCommandsQ,
                                                                    detectorStartedEvent,
                                                                    showProcessedFrameEvent))

    socketReceiverProcess.start()
    classifierProcess.start()

    print('Running. Press CTRL-C to exit.')

    while True:
        if event.is_set():
            print("Exiting all child processes..")
            classifierProcess.terminate()
            socketReceiverProcess.terminate()

            framesQ.close()
            commandsQ.close()
            strCommandsQ.close()
            framesQ.join_thread()
            commandsQ.join_thread()
            strCommandsQ.join_thread()
            # Terminating main process
            exit(0)


if __name__ == '__main__':
    main()
