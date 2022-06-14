import os
import pickle
import socket
import struct
import sys
import threading
from multiprocessing import Process, Queue, Event
from pathlib import Path
from signal import signal, SIGINT
from sys import exit

import numpy as np
import tensorflow as tf
import torch
import torch.backends.cudnn as cudnn

from models.common import DetectMultiBackend
from utils.augmentations import letterbox
from utils.general import (check_img_size, cv2,
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
        return 'max-30km/h'
    elif classNo == 1:
        return 'max-50km/h'
    elif classNo == 2:
        return 'max-70km/h'
    elif classNo == 3:
        return 'priority-road'
    elif classNo == 4:
        return 'yield'
    elif classNo == 5:
        return 'stop'
    elif classNo == 6:
        return 'no-vehicles'
    elif classNo == 7:
        return 'no-entry'
    elif classNo == 8:
        return 'turn-right-ahead'
    elif classNo == 9:
        return 'turn-left-ahead'
    elif classNo == 10:
        return 'ahead-only'
    elif classNo == 11:
        return 'go-straight-or-right'
    elif classNo == 12:
        return 'go-straight-or-left'
    elif classNo == 13:
        return 'keep-right'
    elif classNo == 14:
        return 'keep-left'


class SocketProcess(Process):
    def __init__(self, frames_queue, commands_queue):
        super(SocketProcess, self).__init__()
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.host_ip = '192.168.0.187'
        self.port = 10050
        self.commands_queue = commands_queue
        self.frames_queue = frames_queue
        self.runSendThread = True
        self.send_thread = threading.Thread(target=self.threadToWaitForPredictionAndSend)
        self.send_thread.start()

    def run(self) -> None:
        self.client_socket.connect((self.host_ip, self.port))
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
            if self.frames_queue.full():
                # we don't care about older frames if the queue is full
                self.frames_queue.get_nowait()
            self.frames_queue.put(frame_data)

    def threadToWaitForPredictionAndSend(self):
        while self.runSendThread:
            if self.commands_queue.empty():
                pass
            else:
                command = self.commands_queue.get().encode()
                message = struct.pack("Q", len(command)) + command
                self.client_socket.sendall(message)

    def terminate(self) -> None:
        self.runSendThread = False
        self.send_thread.join()
        super(SocketProcess, self).terminate()


@torch.no_grad()
def detectAndClassifySign(frames_queue, commands_queue, img_sz=(320, 256), hide_labels=False, hide_conf=False):
    print("Inference started!")
    # Load the VGG model
    vgg_model = tf.keras.models.load_model(ROOT / 'weights/model_vgg_training_v2.h5')

    # Load the YOLO model
    device = select_device('0')
    model = DetectMultiBackend(ROOT / 'weights/best.pt', device=device, dnn=False, data=ROOT / 'config.yaml')
    stride, names, pt = model.stride, model.names, model.pt
    img_sz = check_img_size(img_sz, s=stride)  # check image size

    # Dataloader
    cudnn.benchmark = True  # set True to speed up constant image size inference

    model.warmup(imgsz=(1 if pt else 1, 3, *img_sz))  # warmup

    while True:  # Condition here!
        if not frames_queue.empty():
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
                annotator = Annotator(im0, line_width=3, example=str(names))

                if len(det):
                    # Rescale boxes from img_size to im0 size
                    det[:, :4] = scale_coords(im.shape[2:], det[:, :4], im0.shape).round()

                    # Print results
                    for c in det[:, -1].unique():
                        n = (det[:, -1] == c).sum()  # detections per class

                        # Write results
                    for *xyxy, conf, cls in reversed(det):
                        c = int(cls)  # integer class
                        label = None if hide_labels else (names[c] if hide_conf else f'{names[c]} {conf:.2f}')
                        annotator.box_label(xyxy, label, color=colors(c, True))
                        # if save_crop:
                        aux = save_one_box(xyxy, imc, BGR=True, save=False)
                        # print(aux.shape)
                        sign_img = cv2.resize(aux, (32, 32))
                        sign_img = preprocessing(sign_img)
                        # cv2.imshow("Processed Image", sign_img)

                        sign_img = sign_img.reshape(1, 32, 32, 1)
                        # PREDICT IMAGE
                        predictions = vgg_model.predict(sign_img)
                        classIndex = vgg_model.predict_classes(sign_img)
                        probabilityValue = np.amax(predictions)
                        if probabilityValue > 0.75:
                            if commands_queue.full():
                                commands_queue.get_nowait()
                            commands_queue.put(str(getClassName(classIndex)))

                        #     print('Prediction:' + str(classIndex) + " " + str(getClassName(classIndex)) + ', p='
                        #           + str(round(probabilityValue * 100, 2)) + "%")

                # Stream results
                # im0 = annotator.result()
                # cv2.imshow("Predictions", im0)
                # cv2.waitKey(1)  # 1 millisecond


event = Event()


def handler(signal_received, frame):
    event.set()


def main():
    # detectAndClassifySign()
    signal(SIGINT, handler)

    frames_q = Queue()
    commands_q = Queue()

    socketReceiver_process = SocketProcess(frames_queue=frames_q,
                                           commands_queue=commands_q)
    classifier_process = Process(target=detectAndClassifySign, args=(frames_q, commands_q))

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
