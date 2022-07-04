import tensorflow
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.layers import Dropout, Flatten
from tensorflow.keras.layers import Conv2D, MaxPooling2D
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from keras.utils.np_utils import to_categorical
from sklearn.model_selection import train_test_split
import collections
import matplotlib
import time
import numpy as np
import matplotlib.pyplot as plt
import cv2
import os
import pandas as pd
import seaborn as sns

matplotlib.use('TkAgg')


class DataInitializer:
    def __init__(self, pathToData, pathToLabels):
        self.images = []
        self.classNo = []
        self.labels = self.loadLabels(pathToLabels)
        self.loadImages(pathToData)

    @staticmethod
    def loadLabels(pathToLabelsFile):
        return pd.read_csv(pathToLabelsFile)

    def loadImages(self, pathToData):
        imagesDirs = os.listdir(pathToData)
        if len(imagesDirs) != len(self.labels):
            raise Exception('Number of labels different from number of folders with images!')
        print(F'[{time.ctime()}] -> Loading dataset...')

        count = 0
        for i in range(len(imagesDirs)):
            classDir = os.listdir(pathToData + '/' + str(i))
            for imageName in classDir:
                img = cv2.imread(pathToData + '/' + str(i) + '/' + imageName)
                self.images.append(img)
                self.classNo.append(count)
            count += 1
        print(F'[{time.ctime()}] -> Finished to load the dataset!')


class Network:
    def __init__(self, data, testRatio, validationRatio, useVGG=True):
        self.useVGG = useVGG
        self.model = None
        self.history = None
        self.dataGen = None
        self.data = data
        self.dataset_train, self.dataset_test, self.labels_train, self.labels_test \
            = train_test_split(data.images, data.classNo, test_size=testRatio)
        self.dataset_train, self.dataset_valid, self.labels_train, self.labels_valid \
            = train_test_split(self.dataset_train, self.labels_train, test_size=validationRatio)

    def pipeline(self):
        # import keras.backend.tensorflow_backend as tb
        # tb._SYMBOLIC_SCOPE.value = True

        self.dataset_train = np.array(list(map(self.preprocessing, self.dataset_train)))
        self.dataset_test = np.array(list(map(self.preprocessing, self.dataset_test)))
        self.dataset_valid = np.array(list(map(self.preprocessing, self.dataset_valid)))
        self.reshaping()
        self.augmentation()
        self.labels_train = to_categorical(self.labels_train, len(self.data.labels))
        self.labels_valid = to_categorical(self.labels_valid, len(self.data.labels))
        self.labels_test = to_categorical(self.labels_test, len(self.data.labels))
        # if self.useVGG:
        #     self.model = self.VGG_Model()
        # else:
        #     self.model = self.LaNet_Model()
        # self.train2()
        # self.storeTheModel()
        #
        # score = self.model.evaluate(self.dataset_test, self.labels_test, verbose=0)
        # print('Test Score:', score[0])
        # print('Test Accuracy:', score[1])
        self.confMatrix()

    @staticmethod
    def preprocessing(img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        equalisedHist = cv2.equalizeHist(gray)
        normalizedImg = equalisedHist / 255
        return normalizedImg

    def reshaping(self):
        self.dataset_train = self.dataset_train.reshape(self.dataset_train.shape[0], self.dataset_train.shape[1],
                                                        self.dataset_train.shape[2], 1)
        self.dataset_test = self.dataset_test.reshape(self.dataset_test.shape[0], self.dataset_test.shape[1],
                                                      self.dataset_test.shape[2], 1)
        self.dataset_valid = self.dataset_valid.reshape(self.dataset_valid.shape[0], self.dataset_valid.shape[1],
                                                        self.dataset_valid.shape[2], 1)

    def augmentation(self):
        self.dataGen = ImageDataGenerator(width_shift_range=0.3,
                                          # 0.1 = 10%     IF MORE THAN 1 E.G 10 THEN IT REFFERS TO NO. OF  PIXELS EG
                                          # 10 PIXELS
                                          height_shift_range=0.3,
                                          zoom_range=0.4,  # 0.2 MEANS CAN GO FROM 0.8 TO 1.2
                                          shear_range=0.2,  # MAGNITUDE OF SHEAR ANGLE
                                          rotation_range=30)  # DEGREES
        self.dataGen.fit(self.dataset_train)

    def LaNet_Model(self):
        size_of_Filter = (5, 5)  # THIS IS THE KERNEL THAT MOVE AROUND THE IMAGE TO GET THE FEATURES.

        size_of_pool = (2, 2)  # SCALE DOWN ALL FEATURE MAP TO GENERALIZE MORE, TO REDUCE OVERFFITING

        model = Sequential()

        # Layer 1 (Convolutional): Input = 32x32x1. Output = 28x28x6.
        model.add(Conv2D(6, size_of_Filter, input_shape=(32, 32, 1), activation='relu'))

        # Pooling: Input = 28x28x6. Output = 14x14x6.
        model.add(MaxPooling2D(pool_size=size_of_pool))

        # Layer 2 (Convolutional): Output = 10x10x16.
        model.add((Conv2D(16, size_of_Filter, activation='relu')))

        # Pooling: Input = 10x10x16. Output = 5x5x6.
        model.add(MaxPooling2D(pool_size=size_of_pool))

        # Flattening: Input = 5x5x16. Output = 400.
        model.add(Flatten())
        model.add(Dropout(0.25))

        # Layer 3 (Fully Connected): Input = 400. Output = 120.
        model.add(Dense(120, activation='relu'))
        model.add(Dropout(0.25))

        # Layer 3 (Fully Connected): Input = 120. Output = 84.
        model.add(Dense(84, activation='relu'))
        model.add(Dropout(0.2))

        # Layer 5 (Fully Connected): Input = 84. Output = 43.
        model.add(Dense(len(self.data.labels), activation='softmax'))  # OUTPUT LAYER
        # COMPILE MODEL
        model.compile(Adam(learning_rate=0.001), loss='categorical_crossentropy', metrics=['accuracy'])
        return model

    def VGG_Model(self):
        size_of_pool = (2, 2)  # SCALE DOWN ALL FEATURE MAP TO GENERALIZE MORE, TO REDUCE OVERFITTING

        model = Sequential()

        # Layer 1 (Convolutional): Input = 32x32x1. Output = 32x32x32.
        model.add(Conv2D(32, (3, 3), input_shape=(32, 32, 1), padding='same', activation='relu'))

        # Layer 2 (Convolutional): Input = 32x32x32. Output = 32x32x32.
        model.add(Conv2D(32, (3, 3), input_shape=(32, 32, 32), padding='same', activation='relu'))

        # Pooling: Input = 32x32x32. Output = 16x16x32.
        model.add(MaxPooling2D(pool_size=size_of_pool, padding='valid'))
        model.add(Dropout(0.3))

        # Layer 3 (Convolutional):Input = 16x16x32. Output = 16x16x64.
        model.add((Conv2D(64, (3, 3), input_shape=(16, 16, 32), padding='same', activation='relu')))

        # Layer 4 (Convolutional): Input = 16x16x64. Output = 16x16x64.
        model.add((Conv2D(64, (3, 3), input_shape=(16, 16, 64), padding='same', activation='relu')))

        # Pooling: Input = 16x16x64. Output = 8x8x64.
        model.add(MaxPooling2D(pool_size=size_of_pool, padding='valid'))
        model.add(Dropout(0.3))

        # Layer 5 (Convolutional): Input = 8x8x64. Output = 8x8x128.
        model.add((Conv2D(128, (3, 3), input_shape=(8, 8, 64), padding='same', activation='relu')))

        # Layer 6 (Convolutional): Input = 8x8x128. Output = 8x8x128
        model.add((Conv2D(128, (3, 3), input_shape=(8, 8, 128), padding='same', activation='relu')))

        # Layer 7 (Convolutional): Input = 8x8x128. Output = 8x8x128
        model.add((Conv2D(128, (3, 3), input_shape=(8, 8, 128), padding='same', activation='relu')))

        # Pooling: Input = 8x8x128. Output = 4x4x128.
        model.add(MaxPooling2D(pool_size=size_of_pool, padding='valid'))
        model.add(Dropout(0.3))

        # Flatten. Input = 4x4x128. Output = 2048.
        model.add(Flatten())

        # Layer 8 (Fully Connected): Input = 2048. Output = 128.
        model.add(Dense(128, activation='relu'))
        model.add(Dropout(0.5))

        # Layer 9 (Fully Connected): Input = 128. Output = 128.
        model.add(Dense(128, activation='relu'))
        model.add(Dropout(0.5))

        # Layer 10 (Fully Connected): Input = 128. Output = no_of_labels.
        model.add(Dense(len(self.data.labels), activation='softmax'))  # OUTPUT LAYER

        # Compile the model
        model.compile(Adam(learning_rate=0.001), loss='categorical_crossentropy', metrics=['accuracy'])
        return model

    def train2(self):
        print(self.model.summary())
        self.history = self.model.fit(self.dataset_train, self.labels_train, batch_size=64, epochs=30,
                                      validation_data=(self.dataset_valid, self.labels_valid), shuffle=1)
        plt.figure(1)
        plt.plot(self.history.history['loss'])
        plt.plot(self.history.history['val_loss'])
        plt.legend(['training', 'validation'])
        plt.title('loss')
        plt.xlabel('epoch')
        plt.figure(2)
        plt.plot(self.history.history['accuracy'])
        plt.plot(self.history.history['val_accuracy'])
        plt.legend(['training', 'validation'])
        plt.title('Accuracy')
        plt.xlabel('epoch')
        plt.show()
        plt.show(block=True)
        plt.interactive(False)

    def confMatrix(self):
        model = tensorflow.keras.models.load_model('Models/model_vgg_training_v2.h5')
        y_pred = model.predict(self.dataset_valid)
        y_pred = np.argmax(y_pred, axis=1)

        cm = tensorflow.math.confusion_matrix(np.argmax(self.labels_valid, axis=1), y_pred).numpy()
        cm = np.around(cm.astype('float') / cm.sum(axis=1)[:, np.newaxis], decimals=2)
        cm = pd.DataFrame(cm, index=self.data.labels, columns=self.data.labels)
        plt.figure(figsize=(8, 8))
        sns.heatmap(cm.astype('float'), annot=True, cmap=plt.cm.Blues)  # font size
        # plt.show()
        # con_mat = tensorflow.math.confusion_matrix(labels=self.labels_valid, predictions=y_pred).numpy()

        con_mat_norm = np.around(cm.astype('float') / cm.sum(axis=1)[:, np.newaxis], decimals=2)
        #
        # con_mat_df = pd.DataFrame(con_mat_norm,
        #                           index=self.data.labels,
        #                           columns=self.data.labels)
        # figure = plt.figure(figsize=(8, 8))
        # sns.heatmap(con_mat_df, annot=True, cmap=plt.cm.Blues)
        plt.tight_layout()
        plt.ylabel('True label')
        plt.xlabel('Predicted label')
        plt.xticks(rotation=45)
        plt.show()

    def train(self):
        print(self.model.summary())
        self.history = self.model.fit_generator(self.dataGen.flow(self.dataset_train,
                                                                  self.labels_train,
                                                                  batch_size=64),
                                                steps_per_epoch=2000, epochs=10,
                                                validation_data=(self.dataset_valid,
                                                                 self.labels_valid),
                                                shuffle=1)
        plt.figure(1)
        plt.plot(self.history.history['loss'])
        plt.plot(self.history.history['val_loss'])
        plt.legend(['training', 'validation'])
        plt.title('loss')
        plt.xlabel('epoch')
        plt.figure(2)
        plt.plot(self.history.history['accuracy'])
        plt.plot(self.history.history['val_accuracy'])
        plt.legend(['training', 'validation'])
        plt.title('Accuracy')
        plt.xlabel('epoch')
        plt.show()
        plt.show(block=True)
        plt.interactive(False)
        # plt.savefig()

    def storeTheModel(self):
        self.model.save('./Models/new_model.h5')

    def plotNetworkClassesDistribution(self):
        elements_count = collections.Counter(self.data.classNo)
        print(list(elements_count.values()))
        plt.figure(figsize=(8, 4))
        plt.bar(range(0, len(self.data.labels)), list(elements_count.values()))
        plt.title("Distribution of the training dataset")
        plt.xlabel("Class number")
        plt.ylabel("Number of images")
        plt.show()
        plt.show(block=True)
        plt.interactive(False)


def main():
    labelsPath = '../labels.csv'
    imagesPath = '../Dataset'
    data = DataInitializer(imagesPath, labelsPath)
    network = Network(data, testRatio=0.2, validationRatio=0.2)
    # network.plotNetworkClassesDistribution()
    network.pipeline()


if __name__ == '__main__':
    main()
