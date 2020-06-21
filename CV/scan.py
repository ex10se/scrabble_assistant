from pathlib import Path

import cv2
import numpy as np
from imutils import grab_contours, resize
from skimage import img_as_ubyte
from skimage.exposure import adjust_sigmoid
from skimage.filters import threshold_isodata

from skimage.restoration import denoise_tv_bregman

from CV.exceptions import CutException
from CV.transform import four_point_transform


# Размер изображений для тренировки и предсказаний модели
IMG_SIZE = 64


# Авторы: Миша, Матвей
def get_coordinates(img: np.ndarray) -> ([int], [int], int, int):
    """Считает координаты для разрезов, по Х, У и высоту, ширину
    :param img: изображение
    :return: 2 массива с координатами по Х, У и высоту, ширину.
    """
    # Получение высоты и ширины изображения
    (h, w) = img.shape[:2]

    # Заполнение массивов координат X для вертикальных и
    # Y для горизонтальных линий
    x = [0, 0.96 / 15 * w + 1, 1.96 / 15 * w, 2.96 / 15 * w, 3.96 / 15 * w,
         4.96 / 15 * w, 5.96 / 15 * w, 6.98 / 15 * w, 7.98 / 15 * w, 9 / 15 * w,
         10 / 15 * w, 11.01 / 15 * w, 12.01 / 15 * w, 13.03 / 15 * w,
         14.04 / 15 * w, 14.99 / 15 * w]
    x = [round(x[m]) for m in range(16)]
    y = [round(h / 15 * n) for n in range(16)]

    return x, y, h, w


# authors - Pavel, Mikhail, Sergei, Matvey
def cut_by_external_contour(img: np.ndarray) -> np.ndarray:
    """
    Обрезает внешний контур объекта на изображении
    Подходит для игральной доски
    :param img: Изображение на вход
    :return: Обрезанное изображение
    """

    try:
        ratio = img.shape[0] / 750.0
        orig = img.copy()
        img = resize(img, height=750)

        # Черно-белое изображение
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Размытие по Гауссу, оптимальные параметры: (5, 5)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        # Изображение с границами
        edged = cv2.Canny(gray, 75, 150)

        # Получение некого параметра для морфологического преобразования
        # Оптимальные параметры: (7, 7)
        # Затем само морфологическое преобразование (закрытие контуров)
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (7, 7))
        edged = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, kernel)

        # Массив всех контуров
        contours = cv2.findContours(edged.copy(), cv2.RETR_LIST,
                                    cv2.CHAIN_APPROX_SIMPLE)
        contours = grab_contours(contours)

        # Сортировка контуров по убыванию площади
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

        screen_cnt = None  # самый большой контур с 4 точками
        # идем по циклу контуров от самого большого до
        # самого маленького (они уже отсортированы)
        for c in contours:
            peri = cv2.arcLength(c, True)  # периметр контура

            # аппроксимация: если точки слишком рядом - сливаем их в одну
            # это позволяет выдержать небольшую погрешность на изображении
            # оптимальный параметр от 0.02 * периметр до 0.06 * периметр
            approx = cv2.approxPolyDP(c, 0.04 * peri, True)

            # берем самый большой контур с 4 точками
            if len(approx) == 4:
                screen_cnt = approx
                break
                # меняем перспективу на вид сверху
        cropped = four_point_transform(orig, screen_cnt.reshape(4, 2) * ratio)

    except AttributeError:
        raise CutException
    except cv2.error:
        raise CutException('Ошибка обрезки внутреннего контура: '
                           'Ожидается форма массива == (..., 3)), '
                           f'получено {img.shape}')

    return cropped


# author - Mikhail, Pavel
def cut_by_internal_contour(img: np.ndarray,
                            left=3.95, top=4.0,
                            right=1.5, bot=1.2) -> np.ndarray:
    """
    Обрезает изображение с разных сторон
    :param img: Изображение на вход
    :param left: Сколько процентов обрезать слева
    :param top: Сколько процентов обрезать сверху
    :param right: Сколько процентов обрезать справа
    :param bot: Сколько процентов обрезать снизу
    :return: Обрезанное изображение
    """

    try:
        (h, w) = img.shape[:2]  # получение размеров игровой доски
        # обрезка
        cropped = img[round(top * w / 100):round(h * (1 - bot / 100)),
                  round(left * h / 100):round(w * (1 - right / 100))]

        (h, w) = cropped.shape[:2]  # получение размеров игрового поля

        allowable_error = 0.03  # погрешность при проверке на квадратность
        # если cropped не квадрат (допускается погрешность)

        # границы отношения ширины к высоте в пределах заданной погрешности
        top_line = 1 * (1 + allowable_error)  # верхняя граница
        bot_line = 1 / (1 + allowable_error)  # нижняя граница
        # if not (bot_line <= w / h <= top_line):
        #     raise CutException('Not a square')

    except AttributeError:
        raise

    return cropped


# author - Mikhail
def draw_the_grid(img: np.ndarray) -> np.ndarray:
    """
    Рисует сетку, по которой можно производить разбивку на 15x15 ячеек
    :param img: Изображение на вход
    :return: Изображение с сеткой
    """

    # Получение координат, высоты и ширины изображения
    x, y, h, w = get_coordinates(img)

    # Вертикальные линии
    for n in x:
        start_point = (n, 0)
        end_point = (n, h)
        cv2.line(img, start_point, end_point, color=(0, 255, 0), thickness=2)
    # Горизонтальные линии
    for n in y:
        start_point = (0, n)
        end_point = (w, n)
        cv2.line(img, start_point, end_point, color=(0, 255, 0), thickness=2)

    return img


# author - Mikhail
def cut_board_on_cells(img: np.ndarray) -> [np.ndarray]:
    """
    Делит изображение на квадраты-ячейки, создавая двухмерный массив из них
    :param img: Изображение на вход
    :return: Массив ячеек длиной 15x15
    """

    # Получение координат, высоты и ширины изображения
    x, y, h, w = get_coordinates(img)

    # Заполнение массива
    squares = []
    for n in range(1, 16):
        squares.append([])  # todo: переписать на numpy
        for m in range(1, 16):
            cropped = img[y[n - 1]:y[n], x[m - 1]:x[m]]
            cropped = cv2.resize(cropped, (IMG_SIZE, IMG_SIZE))
            squares[n - 1].append(cropped)

    return np.array(squares, dtype='uint8')


# Автор: Матвей
def rgb_to_gray(rgb: np.ndarray, coefficients: [float], force_copy=False) -> np.ndarray:
    """
    Т.к фишки на нашей доске синего цвета, результат будет лучше, если мы будем использовать
    не стандартные коэффициенты для перевода в оттенки серого, а те, которые будут подавлять
    синие оттенки.

    Это создаст более сильный контраст буквы. И мы сможем эффективнее
    использовать порогование.

    :param rgb: изображение в RGB формате.
    :param coefficients: коэффициенты для в перевода в оттенки серого
    :param force_copy:
    :return: изображение в оттенках серого
    """

    # Проверяем форму массива
    rgb = np.asanyarray(rgb)
    if rgb.shape[-1] != 3:
        raise ValueError('Ожидается форма массива == (..., 3)), '
                         f'получено {rgb.shape}')

    rgb = img_as_ubyte(rgb, force_copy=force_copy)
    if len(coefficients) != 3:
        raise ValueError(f"Ожидается 3 коэффициента, получено {len(coefficients)}")
    coeffs = np.array(coefficients, dtype=rgb.dtype)

    return rgb @ coeffs


# Авторы: Матвей, Михаил
def gray_to_binary(image_gray: np.ndarray) -> np.ndarray:
    """
    Переводит изображение из оттенокв серого в черно-белое.
    :param image_gray: изображение в оттенках серого
    :return: изображение в ЧБ формате
    """
    img_denoised = denoise_tv_bregman(image_gray, weight=33)  # денойз
    # img_denoised = denoise_nl_means(image_gray)  # денойз
    img_adj = adjust_sigmoid(img_denoised, cutoff=0.4)
    # Регулируем контраст (сигмовидная коррекция)

    # Находим порог для изображения и возвращаем изображение в ЧБ
    return img_as_ubyte(img_adj > threshold_isodata(img_adj))


# author - Sergei, Mikhail
def crop_letter(img_bin: np.ndarray) -> np.ndarray:
    """
    Вырезает из клетки букву
    :param img_bin: Пороговое изображение на вход
    :return: Пороговое обрезанное изображение
    """
    # Поиск контуров
    cropped = img_bin.copy()
    cropped = img_as_ubyte(cropped)
    # cropped = cv2.fastNlMeansDenoising(cropped)
    contours, _ = cv2.findContours(cropped, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_NONE)

    # Перебор контуров. Если периметр достаточно большой,
    # решаем, что это буква и обрезаем картинку по
    # её левому нижнему углу
    for idx, contour in enumerate(contours):
        (x, y, w, h) = cv2.boundingRect(contour)
        contour_perimeter = cv2.arcLength(contour, True)
        contour_square = w * h
        # # Рисовалка контуров
        # cv2.rectangle(cropped, (x, y), (x + w, y + h), (255, 0, 0), 1)
        min_letter_square = np.square(IMG_SIZE) / 9.3
        if contour_square > min_letter_square:
            desired_cropped = cropped[0:y + h, x:x + y + h]
            h_desired = int(desired_cropped.shape[1])
            w_desired = int(desired_cropped.shape[0])
            cropped = cropped[0 + abs(h_desired-w_desired):y + h, x:x + y + h]
            break

    return cv2.resize(cropped, (IMG_SIZE, IMG_SIZE))


if __name__ == "__main__":
    '''image = img_as_ubyte(imread('test2.jpg'))
    # image = img_as_ubyte(cv2.imread('../resources/app_images/test.jpg'))
    img_external_crop = cut_by_external_contour(image)
    img_internal_crop = cut_by_internal_contour(img_external_crop)

    # img_internal_crop = img_as_ubyte(imread('test2.jpg'))

    img_bw = gray_to_binary(rgb_to_gray(img_internal_crop, [1, 0, 0]))
    # plt.imshow(img_bw)
    # plt.show()

    board_squares = img_as_ubyte(cut_board_on_cells(img_bw))

    for i in range(len(board_squares)):
        for j in range(len(board_squares[0])):
            board_squares[i][j] = crop_letter(board_squares[i][j])  # todo check types

    print('тест распознавания изображений:')
    clf_path = Path.cwd().parent / CLASSIFIER_DUMP_PATH
    sc_path = Path.cwd().parent / SCALER_DUMP_PATH
    predicted_letters, pred_probas = classify_images(board_squares,
                                                     clf_path,
                                                     scaler_path=None,
                                                     probability=True)

    pred_board = nums_to_letters(predicted_letters, pred_probas)
    for row in pred_board:
        print(row)
'''