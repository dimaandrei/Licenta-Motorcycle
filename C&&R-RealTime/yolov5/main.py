import os
import sys
from pathlib import Path

import numpy as np
import tensorflow as tf
import torch
import torch.backends.cudnn as cudnn

from models.common import DetectMultiBackend
from utils.dataloaders import LoadStreams
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
        return 'No vechiles'
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


@torch.no_grad()
def detectAndClassifySign(img_sz=(640, 480), hide_labels=False, hide_conf=False):
    # Load the VGG model
    vgg_model = tf.keras.models.load_model(ROOT / 'weights/model_vgg_training_v2.h5')

    # Load the YOLO model
    device = select_device('0')
    model = DetectMultiBackend(ROOT / 'weights/best.pt', device=device, dnn=False, data=ROOT / 'config.yaml')
    stride, names, pt = model.stride, model.names, model.pt
    img_sz = check_img_size(img_sz, s=stride)  # check image size

    # Dataloader
    cudnn.benchmark = True  # set True to speed up constant image size inference
    dataset = LoadStreams('0', img_size=img_sz, stride=stride, auto=pt)
    bs = len(dataset)  # batch_size

    # Run inference
    model.warmup(imgsz=(1 if pt else bs, 3, *img_sz))  # warmup

    seen = 0
    for path, im, im0s, vid_cap, s in dataset:
        im = torch.from_numpy(im).to(device)
        im = im.float()  # uint8 to fp16/32
        im /= 255  # 0 - 255 to 0.0 - 1.0
        if len(im.shape) == 3:
            im = im[None]  # expand for batch dim

        # Inference
        pred = model(im, augment=False,
                     visualize=False)  # We don't want to augment inference or visualize features at this moment

        # NMS
        pred = non_max_suppression(pred, conf_thres=0.25, iou_thres=0.45, max_det=10)

        # Process predictions
        for i, det in enumerate(pred):  # per image
            seen += 1
            p, im0, frame = path[i], im0s[i].copy(), dataset.count
            s += f'{i}: '
            p = Path(p)  # to Path
            s += '%gx%g ' % im.shape[2:]  # print string
            # gn = torch.tensor(im0.shape)[[1, 0, 1, 0]]  # normalization gain whwh
            imc = im0.copy()  # for save_crop
            annotator = Annotator(im0, line_width=3, example=str(names))

            if len(det):
                # Rescale boxes from img_size to im0 size
                det[:, :4] = scale_coords(im.shape[2:], det[:, :4], im0.shape).round()

                # Print results
                for c in det[:, -1].unique():
                    n = (det[:, -1] == c).sum()  # detections per class
                    s += f"{n} {names[int(c)]}{'s' * (n > 1)}, "  # add to string
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
                    cv2.imshow("Processed Image", sign_img)

                    sign_img = sign_img.reshape(1, 32, 32, 1)
                    # PREDICT IMAGE
                    predictions = vgg_model.predict(sign_img)
                    classIndex = vgg_model.predict_classes(sign_img)
                    probabilityValue = np.amax(predictions)
                    if probabilityValue > 0.75:
                        print('Prediction:' + str(classIndex) + " " + str(getClassName(classIndex)) + ', p='
                              + str(round(probabilityValue * 100, 2)) + "%")
                    cv2.waitKey(1)  # 1 millisecond

            # Stream results
            im0 = annotator.result()
            cv2.imshow(str(p), im0)
            cv2.waitKey(1)  # 1 millisecond


def main():
    detectAndClassifySign()


if __name__ == '__main__':
    main()
