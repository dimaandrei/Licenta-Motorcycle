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
        return b'\x02\x50'
    elif commandNo == 1:  # 50km/h - speed = 0
        return b'\x02\x70'
    elif commandNo == 2:  # 70km/h - speed = 0
        return b'\x02\x80'
    elif commandNo == 8:  # turn right ahead
        return b'\x03\x4E'
    elif commandNo == 9:  # turn left ahead 
        return b'\x03\x8A'
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
    def __init__(self, frames_queue, commands_queue, detector_started_event, host='192.168.0.187', port=10050):
        super(SocketProcess, self).__init__()
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.host_ip = host
        self.port = port
        self.commands_queue = commands_queue
        self.frames_queue = frames_queue
        self.detector_started_event = detector_started_event
        self.runSendThread = True
        self.send_thread = threading.Thread(target=self.threadToWaitForPredictionAndSend)

    def run(self) -> None:
        try:
            self.client_socket.connect((self.host_ip, self.port))
            self.send_thread.start()
            data = b''
            # Q: unsigned long long integer(8 bytes)
            payload_size = struct.calcsize("Q")

            while True:  # shared condition here!!

                while len(data) < payload_size:
                    packet = self.client_socket.recv(4 * 1024)
                    if not packet:
                        break
                    data += packet
                    # print(f'{len(data)}-{payload_size}')

                packed_msg_size = data[:payload_size]
                data = data[payload_size:]
                msg_size = struct.unpack("Q", packed_msg_size)[0]

                while len(data) < msg_size:
                    data += self.client_socket.recv(4 * 1024)
                frame_data = data[:msg_size]
                data = data[msg_size:]
                if not self.detector_started_event.is_set():
                    # we drop the frame if signs detector is not activated
                    continue
                # print("Processing frame..")
                try:
                    if self.frames_queue.full():
                        # we don't care about older frames if the queue is full
                        self.frames_queue.get_nowait()
                    self.frames_queue.put(frame_data)
                except queue.Empty as e:
                    pass
                    # print("Queue is empty!")
        except socket.error as e:
            print(f'Socket exception: {e}')
        except struct.error as e:
            print(f'Struct exception: {e}')
        finally:
            self.runSendThread = False
            if self.send_thread.is_alive():
                self.send_thread.join()

    def threadToWaitForPredictionAndSend(self):
        try:
            while self.runSendThread:
                if self.commands_queue.empty():
                    pass
                else:
                    command = self.commands_queue.get()
                    # print(command)
                    message = struct.pack("B", len(command)) + command
                    self.client_socket.sendall(message)
        except socket.error as e:
            print(f'Socket exception: {e}')

    def terminate(self) -> None:
        self.runSendThread = False
        if self.send_thread.is_alive():
            self.send_thread.join()
        super(SocketProcess, self).terminate()


@torch.no_grad()
def detectAndClassifySign(frames_queue, commands_bin_queue, commands_str_queue,
                          detector_started_event, show_processed_frames, condition, arr,
                          img_sz=(160, 128)):
    print("Inference started!")
    # Load the VGG model
    vgg_model = tf.keras.models.load_model(ROOT / 'weights/model_vgg_training_v2.h5')
    vgg_model.trainable = False
    # Load the YOLO model
    device = select_device('0')
    model = DetectMultiBackend(ROOT / 'weights/best.pt', device=device, dnn=False, data=ROOT / 'config.yaml')
    stride, names, pt = model.stride, model.names, model.pt
    img_sz = check_img_size(img_sz, s=stride)  # check image size

    # Dataloader
    cudnn.benchmark = True  # set True to speed up constant image size inference

    model.warmup(imgsz=(1 if pt else 1, 3, *img_sz))  # warmup
    old_pred = None
    while True:  # Condition here!
        startTime = time.time()
        if detector_started_event.is_set() and not frames_queue.empty():
            # print("Detecting signs from frame..")
            frame_data = frames_queue.get()
            frame = pickle.loads(frame_data)
            np_arr = np.frombuffer(frame, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            im0 = frame.copy()

            frame = letterbox(frame, img_sz, stride=stride, auto=pt)[0]
            frame = frame.transpose((2, 0, 1))[::-1]  # HWC to CHW, BGR to RGB
            frame = np.ascontiguousarray(frame)

            seen = 0
            im = torch.from_numpy(frame).to(device)
            im = im.float()  # uint8 to fp16/32
            im /= 255  # 0 - 255 to 0.0 - 1.0
            if len(im.shape) == 3:
                im = im[None]  # expand for batch dim
            pred = model(im, augment=False,
                         visualize=False)  # We don't want to augment inference or visualize features at this moment

            # NMS
            pred = non_max_suppression(pred, conf_thres=0.25, iou_thres=0.45, max_det=10)

            # Process predictions
            for i, det in enumerate(pred):  # per image
                seen += 1

                imc = im0.copy()  # for save_crop
                annotator = Annotator(im0, line_width=1, example=str(names))

                if len(det):
                    # Rescale boxes from img_size to im0 size
                    det[:, :4] = scale_coords(im.shape[2:], det[:, :4], im0.shape).round()

                    # Write results
                    for *xyxy, conf, cls in reversed(det):
                        c = int(cls)  # integer class
                        label = f'{names[c]} {conf:.2f}'
                        annotator.box_label(xyxy, label, color=colors(c, True))

                        aux = save_one_box(xyxy, imc, BGR=True, save=False)

                        sign_img = cv2.resize(aux, (32, 32))
                        sign_img = preprocessing(sign_img)

                        sign_img = sign_img.reshape(1, 32, 32, 1)
                        # PREDICT IMAGE
                        predictions = vgg_model.predict(sign_img)
                        classIndex = vgg_model.predict_classes(sign_img)
                        probabilityValue = np.amax(predictions)
                        if probabilityValue > 0.85:
                            if old_pred is None or old_pred != classIndex:  # add in queue different detections
                                old_pred = classIndex
                                aux = getCommandEncoding(classIndex, 0)
                                if aux != b'\x00\x00':
                                    if commands_bin_queue.full():
                                        commands_bin_queue.get_nowait()
                                    commands_bin_queue.put(getCommandEncoding(classIndex, 0))
                                if commands_str_queue.full():
                                    commands_str_queue.get_nowait()
                                commands_str_queue.put(getClassName(classIndex))

                else:
                    old_pred = None

                if show_processed_frames.is_set():
                    with condition:
                        # Stream results
                        im0 = annotator.result()
                        X_np = np.frombuffer(buffer=arr, dtype=np.ubyte, count=61440).reshape((128, 160, 3))
                        np.copyto(X_np, im0)
                        condition.notify_all()
                        # try:
                        #     if processed_frame_queue.full():
                        #         processed_frame_queue.get_nowait()
                        #     processed_frame_queue.put(im0)
                        # except queue.Empty as e:
                        #     pass
            # print(f'FPS:{ 1.0 / (time.time() - startTime)}  SIZE: {frames_queue.qsize()}')  # FPS = 1 / time to process loop


event = Event()


def handler(signal_received, frame):
    event.set()


def main():
    print("Test started!")
    # detectAndClassifySign()
    signal(SIGINT, handler)

    frames_q = Queue(50)
    commands_q = Queue()
    processed_frame_q = Queue()
    commands_str_q = Queue()
    detector_started_event = Event()
    show_processed_frames = Event()
    detector_event = Event()
    socketReceiver_process = SocketProcess(frames_queue=frames_q,
                                           commands_queue=commands_q, detector_started_event=detector_event)
    classifier_process = Process(target=detectAndClassifySign, args=(frames_q, commands_q, processed_frame_q,
                                                                     commands_str_q, detector_started_event,
                                                                     show_processed_frames))

    socketReceiver_process.start()
    classifier_process.start()

    print('Running. Press CTRL-C to exit.')

    while True:
        if event.is_set():
            print("Exiting all child processes..")
            classifier_process.terminate()
            socketReceiver_process.terminate()

            frames_q.close()
            commands_q.close()
            frames_q.join_thread()
            commands_q.join_thread()
            # Terminating main process
            exit(0)


if __name__ == '__main__':
    main()
