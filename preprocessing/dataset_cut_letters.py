import time
from pathlib import Path
from shutil import rmtree

import numpy as np

from skimage.io import imread, imsave
from skimage.transform import resize

from CV.scan import IMG_RES
from CV.scan import cut_board_on_cells
from CV.scan import cut_by_external_contour
from CV.scan import cut_by_internal_contour
from preprocessing.model_preprocessing import to_gray, to_binary

IMAGES_TO_CUT_PATH = Path(Path.cwd().parent / '!raw_images_to_cut/1')
DATASET_PATH = Path(Path.cwd().parent / 'ML/dataset')

# authors - Misha, Matvey
if __name__ == "__main__":

    # Массив одномерных координат клеток с буквами и пустых
    coordinates = np.arange(33)
    coordinates = np.append(coordinates, (50, 52, 48, 76, 105, 112))
    coordinates = np.reshape(coordinates, (len(coordinates), 1))
    # Массив категорий для классификации
    categories = np.arange(1, 34)
    categories = np.append(categories,
                           ('Empty', 'Green', 'Blue', 'Yellow', 'Red', 'White'))
    # Объединение их в массив, состоящий из [координата, категория]
    crd_ctg = []
    for i in range(len(categories)):
        crd_ctg = np.append(crd_ctg, (coordinates[i][0], categories[i]))
    crd_ctg = np.reshape(crd_ctg, (len(coordinates), 2))

    # (Пере-)создание папок-категорий будущего датасета
    for folder in DATASET_PATH.glob('*'):
        rmtree(DATASET_PATH / Path(folder), True)
    time.sleep(1)
    for category in categories:
        (DATASET_PATH / Path(category)).mkdir(mode=0o777)

    # Создаем генератор путей исходных изображений
    path_gen = IMAGES_TO_CUT_PATH.glob('*.jpg')
    # Записываем пути
    paths = [path for path in path_gen if path.is_file()]

    for k, file_img in enumerate(paths, 1):
        image = imread(str(file_img))
        external_crop = cut_by_external_contour(image)
        internal_crop = cut_by_internal_contour(external_crop)
        board_squares = cut_board_on_cells(internal_crop)

        # Решейп из двухмерного в одномерный массив изображений
        flat_board = board_squares.reshape(
            (board_squares.shape[0] * board_squares.shape[1], IMG_RES,
             IMG_RES, 3))  # если нет фильтра то добавляется форма 3

        # Обработка и запись клеток
        for c in crd_ctg:
            cell = flat_board[int(c[0])]
            # cell = to_binary(to_gray(cell, [1, 0, 0]))  # фильтр для BGR
            imsave(str(DATASET_PATH / Path(c[1]) / Path(str(k) + '.jpg')), cell)

        # Вывод процента выполнения
        print(k, 'файл,', str(round(k / len(paths) * 100, 1)) + "%")
    print('Готово!')
