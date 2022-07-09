import os
from PIL import Image


def ppmToJpgFormat(full_path_to_images_dir, full_path_to_save_dir, full_txt_about_filename):
    names = os.listdir(full_path_to_images_dir)

    with open(full_txt_about_filename, 'w') as txt:
        for img_name in names:
            if not img_name.endswith('.ppm'):
                continue
            img = Image.open(full_path_to_images_dir + os.path.sep + img_name)
            new_name = full_path_to_save_dir + os.path.sep + img_name[:-4] + '.jpg'
            img.save(new_name)

            # build train.txt && test.txt with paths to images
            txt.write(os.path.abspath(new_name) + os.linesep)


def findImgSize(full_path_to_imag):  # In the dataset all images have same dimensions, this way it is enough to read the
    return Image.open(full_path_to_imag).size  # size for just an image


def chooseClassType(signType):
    if signType in prohibitory:
        return 0
    elif signType in mandatory:
        return 1
    elif signType in danger:
        return 2
    else:
        return 3


def GTSDBToYoloFormat(full_path_to_gt_file, full_path_to_save_dir, imgSize):
    lines = None
    x_center_scaling = imgSize[0] * 2  # width of image div by 2 to find x coordinate of the center of bounding box
    y_center_scaling = imgSize[1] * 2  # height of image div by 2 to find y coordinate of the center of bounding box

    with open(full_path_to_gt_file) as file:
        lines = file.readlines()

    if lines is None:
        raise Exception("Couldn't read the gt.txt file!")

    for line in lines:
        line = line.rstrip().split(';')
        with open(full_path_to_save_dir + os.path.sep + line[0][:-4] + '.txt', 'a') as bb_data:  # bounding box data
            # we calculate the center of the bounding box, the width and the height of it
            x_center = (int(line[1]) + int(line[3])) / x_center_scaling
            y_center = (int(line[2]) + int(line[4])) / y_center_scaling
            width = (int(line[3]) - int(line[1])) / imgSize[0]
            height = (int(line[4]) - int(line[2])) / imgSize[1]
            bb_data.write(f'{chooseClassType(int(line[5]))} {x_center} {y_center} {width} {height}{os.linesep}')

    names = os.listdir(full_path_to_save_dir)
    txt_files = []
    for file in names:
        if file.endswith('.txt'):
            txt_files.append(int(file[:-4]))
    for i in range(600):
        if i not in txt_files:
            number = "{:05d}".format(i)
            with open(full_path_to_save_dir + os.path.sep + number + '.txt', 'w'):
                pass


def writeClassesFile(full_path_to_save_dir, list_of_classes):
    with open(full_path_to_save_dir + os.path.sep + 'classes.txt', 'w') as file:
        for i in list_of_classes:
            file.write(f'{i}{os.linesep}')


def removeFilesFromFolder(full_path_to_folder, ends_with=''):
    f_names = os.listdir(full_path_to_folder)
    for f in f_names:
        if ends_with != '' and not f.endswith(ends_with):
            continue
        os.remove(full_path_to_folder + os.path.sep + f)


def writeToTest():
    names = os.listdir(PATH_TO_YOLO_TEST_SAVE_DIR)
    with open(PATH_TO_TXT_FILE + os.path.sep + 'test.txt', 'w') as txt:
        for file in names:
            if file.endswith('.jpg'):
                new_name = PATH_TO_YOLO_TEST_SAVE_DIR + os.path.sep + file
                # build train.txt && test.txt with paths to images
                txt.write(os.path.abspath(new_name) + os.linesep)


PATH_TO_TRAIN_DOWNLOADED_DATASET = './Dataset/train'
PATH_TO_TEST_DOWNLOADED_DATASET = './Dataset/test'
PATH_TO_YOLO_TRAIN_SAVE_DIR = './Dataset/train_yolo_format_data'
PATH_TO_YOLO_TEST_SAVE_DIR = './Dataset/test_yolo_format_data'
PATH_TO_TXT_FILE = './Dataset/ts_about'
classes = ['Prohibitory', 'Mandatory', 'Danger', 'Other']

prohibitory = [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 15, 16]  # (circular, white ground with red border)
mandatory = [33, 34, 35, 36, 37, 38, 39, 40]  # (circular, blue ground)
danger = [11, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31]  # (triangular, white ground with red border)
# other = the rest of signs like STOP, PRIORITY ROAD

if __name__ == '__main__':
    removeFilesFromFolder(PATH_TO_YOLO_TRAIN_SAVE_DIR)
    removeFilesFromFolder(PATH_TO_YOLO_TEST_SAVE_DIR)
    img_sz = findImgSize(PATH_TO_TRAIN_DOWNLOADED_DATASET + os.path.sep + '00000.ppm')  # we choose the first image

    # Generate YOLO format training data
    GTSDBToYoloFormat(PATH_TO_TRAIN_DOWNLOADED_DATASET + os.path.sep + 'gt.txt', PATH_TO_YOLO_TRAIN_SAVE_DIR, img_sz)
    ppmToJpgFormat(PATH_TO_TRAIN_DOWNLOADED_DATASET, PATH_TO_YOLO_TRAIN_SAVE_DIR,
                   PATH_TO_TXT_FILE + os.path.sep + 'train.txt')

    # Generate YOLO format testing data
    ppmToJpgFormat(PATH_TO_TEST_DOWNLOADED_DATASET, PATH_TO_YOLO_TEST_SAVE_DIR,
                   PATH_TO_TXT_FILE + os.path.sep + 'test.txt')

    # Save classes to file
    writeClassesFile(PATH_TO_TXT_FILE, list_of_classes=classes)
    writeToTest()
