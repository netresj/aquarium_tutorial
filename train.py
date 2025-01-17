# -*- coding:utf-8 -*-

import argparse
import datetime
import glob
import os
import pathlib
import zipfile

import numpy as np
import pandas as pd
import tensorflow as tf
import matplotlib.pyplot as plt
from skimage import io, transform
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix
from tensorflow.keras.backend import clear_session
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, TensorBoard
from tensorflow.keras.layers import Conv2D, Dense, Dropout, Flatten, MaxPool2D
from tensorflow.keras.metrics import categorical_accuracy, categorical_crossentropy
from tensorflow.keras.models import Sequential
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tqdm import tqdm


def build_model(num_class) -> Sequential:
    # モデルの構築
    model = Sequential()
    model.add(Conv2D(32, (3, 3), input_shape=(28, 28, 1), activation="relu"))
    model.add(Conv2D(32, (3, 3), activation="relu"))
    model.add(MaxPool2D(pool_size=(2, 2)))
    model.add(Dropout(0.25))
    model.add(Conv2D(32, (3, 3), activation="relu"))
    model.add(Conv2D(32, (3, 3), activation="relu"))
    model.add(MaxPool2D(2, 2))
    model.add(Dropout(0.25))
    model.add(Flatten())
    model.add(Dense(64, activation="relu"))
    model.add(Dropout(0.5))
    model.add(Dense(num_class, activation="softmax"))

    # オプティマイザーと評価指標の設定
    adam = Adam(learning_rate=1e-3)
    model.compile(
        loss="sparse_categorical_crossentropy",
        optimizer=adam,
        metrics=["accuracy"],
    )

    return model


def train(args):
    # 乱数の固定
    tf.random.set_seed(0)

    # データ読み込み
    path = pathlib.Path(f"{args.input_path}")
    all_image_paths = [
        item.resolve()
        for item in path.glob("**/*")
        if item.is_file()
    ]
    all_images = np.array(
        [
            transform.resize(
                io.imread(path, as_gray=True), (28, 28), anti_aliasing=False
            )
            for path in tqdm(all_image_paths)
        ]
    )
    all_images = np.reshape(all_images, (-1, 28, 28, 1))
    
    if args.input_type == "mnist":
        all_labels = [pathlib.Path(path).parent.name for path in all_image_paths]
    elif args.input_type == "chinese":
        all_labels = [
            pathlib.Path(path).name.split(".")[0].split("_")[-1] for path in all_image_paths
        ]
    labels = list(set(all_labels))
    label_index = {label: idx for idx, label in enumerate(labels)}
    all_labels = np.array([label_index[label] for label in all_labels])

    # data generator の宣言
    train_datagen = ImageDataGenerator(
        rotation_range=20,
        width_shift_range=0.1,
        height_shift_range=0.1,
        data_format="channels_last",
    )

    X_train, X_test, y_train, y_test = train_test_split(
        all_images, all_labels, test_size=0.33, random_state=0
    )

    # コールバックの設定
    es = EarlyStopping(monitor="val_loss", patience=10)
    log_dir = f"{args.log_path}"
    tb = TensorBoard(log_dir=log_dir, histogram_freq=1, write_graph=True)
    cp = ModelCheckpoint(
        f"{args.output_path}/params.hdf5",
        monitor="val_loss",
        save_best_only=True,
    )

    # データ
    train_generator = train_datagen.flow(X_train, y_train, batch_size=32)

    # model をビルド
    model = build_model(len(label_index))

    # 学習実行
    model.fit_generator(
        train_generator,
        steps_per_epoch=X_train.shape[0] // 32,
        verbose=2,
        epochs=100,
        validation_data=(X_test, y_test),
        callbacks=[es, tb, cp],
    )

    # confusion matrixの作成
    y_pred = np.argmax(model.predict(X_test), axis=-1)
    cm = confusion_matrix(y_test, y_pred, labels=list(label_index.values()))
    cm = pd.DataFrame(cm, columns=label_index.keys(), index=label_index.keys())
    cm.to_csv(f"{args.output_path}/confusion_matrix.csv")

    # tensorboard への画像の出力
    writer = tf.summary.create_file_writer(f"{args.log_path}/images")

    # 各クラスについて間違えた画像のみを10枚ずつ収集してtensorboardで表示する
    wrong_pictures_idx = [
        idx for idx in range(len(y_pred)) if y_pred[idx] != y_test[idx]
    ]

    for image_idx in wrong_pictures_idx[:20]:
        true_label = [
            key for key, val in label_index.items() if val == y_test[image_idx]
        ]
        predicted_label = [
            key for key, val in label_index.items() if val == y_pred[image_idx]
        ]
        title = f"true {true_label}: predicted {predicted_label}"

        with writer.as_default():
            tf.summary.image(title, X_test[image_idx : image_idx + 1], step=100, max_outputs=1)


if __name__ == "__main__":
    # コマンドライン引数の設定
    parser = argparse.ArgumentParser(description="aqualium demo")
    parser.add_argument("--input_path", default="/kqi/input/images")
    parser.add_argument("--output_path", default="/kqi/output/demo")
    parser.add_argument("--log_path", default="/kqi/output/logs")
    parser.add_argument("--input_type", default="mnist")
    args = parser.parse_args()

    os.makedirs(args.output_path, exist_ok=True)
    os.makedirs(args.log_path, exist_ok=True)

    train(args)
