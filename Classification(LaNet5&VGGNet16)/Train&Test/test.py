import cv2
import numpy as np
import tensorflow as tf

'''###########Constants###########'''

frameWidth = 640  # CAMERA RESOLUTION
frameHeight = 480
brightness = 180
threshold = 0.75  # PROBABILITY THRESHOLD
font = cv2.FONT_HERSHEY_SIMPLEX

######################################


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


if __name__ == '__main__':

    # SET UP THE VIDEO CAMERA
    cap = cv2.VideoCapture(0)
    cap.set(3, frameWidth)
    cap.set(4, frameHeight)
    cap.set(10, brightness)

    # tf.device('/gpu:0')
    model = tf.keras.models.load_model('./Models/model_vgg_training_v2.h5')

    # model.summary()

    while True:
        # READ IMAGE
        success, imgOriginal = cap.read()

        # PROCESS IMAGE
        img = np.asarray(imgOriginal)
        img = cv2.resize(img, (32, 32))
        img = preprocessing(img)
        cv2.imshow("Processed Image", img)
        img = img.reshape(1, 32, 32, 1)
        cv2.putText(imgOriginal, "CLASS: ", (20, 35), font, 0.75, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.putText(imgOriginal, "PROBABILITY: ", (20, 75), font, 0.75, (0, 0, 255), 2, cv2.LINE_AA)

        # PREDICT IMAGE
        predictions = model.predict(img)
        classIndex = model.predict_classes(img)
        probabilityValue = np.amax(predictions)
        if probabilityValue > threshold:
            cv2.putText(imgOriginal, str(classIndex) + " " + str(getClassName(classIndex)), (120, 35), font, 0.75,
                        (0, 0, 255), 2, cv2.LINE_AA)
            cv2.putText(imgOriginal, str(round(probabilityValue * 100, 2)) + "%", (180, 75), font, 0.75, (0, 0, 255), 2,
                        cv2.LINE_AA)
        cv2.imshow("Classification", imgOriginal)

        if cv2.waitKey(1) and 0xFF == ord('q'):
            break
