from __future__ import annotations

import base64
import binascii
import sqlite3
import uuid
from pathlib import Path

import cv2
import numpy as np

from database import find_employee, load_training_samples, save_employee_and_samples


class ImageInputError(ValueError):
    pass


class FaceRecognitionService:
    def __init__(self, database_path: str, face_dir: str, threshold: float = 75.0):
        self.database_path = database_path
        self.face_dir = Path(face_dir)
        self.threshold = threshold
        self._recognizer = cv2.face.LBPHFaceRecognizer_create()
        self._trained = False
        self._labels: set[int] = set()
        self._cascade = cv2.CascadeClassifier(
            str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        )
        if self._cascade.empty():
            raise RuntimeError("OpenCV could not load its face detection model.")

    @staticmethod
    def _decode_frame(value: str) -> np.ndarray:
        if not isinstance(value, str):
            raise ImageInputError("A camera image is required.")
        encoded = value.split(",", 1)[-1] if value.startswith("data:image/") else value
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImageInputError("The camera image could not be decoded.") from exc
        if not raw or len(raw) > 5 * 1024 * 1024:
            raise ImageInputError("Each image must be smaller than 5 MB.")
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ImageInputError("The uploaded file is not a readable image.")
        return image

    def _face_crop(self, value: str) -> np.ndarray:
        image = self._decode_frame(value)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = self._cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
        if len(faces) == 0:
            raise ImageInputError("No face detected. Face the camera in good, even lighting.")
        x, y, width, height = max(faces, key=lambda box: box[2] * box[3])
        crop = gray[y : y + height, x : x + width]
        crop = cv2.equalizeHist(crop)
        return cv2.resize(crop, (160, 160), interpolation=cv2.INTER_AREA)

    def enroll(self, employee_code: str, name: str, frames: list[str]) -> int:
        crops: list[np.ndarray] = []
        for frame in frames:
            try:
                crops.append(self._face_crop(frame))
            except ImageInputError:
                continue
        if len(crops) < 3:
            raise ImageInputError("At least 3 clear samples must contain a detectable face. Adjust lighting and try again.")

        filenames: list[str] = []
        try:
            for crop in crops:
                path = self.face_dir / f"{employee_code}_{uuid.uuid4().hex}.png"
                if not cv2.imwrite(str(path), crop):
                    raise RuntimeError("Could not save a face sample to disk.")
                filenames.append(str(path))
            old_paths = save_employee_and_samples(employee_code, name, filenames)
        except Exception:
            for filename in filenames:
                Path(filename).unlink(missing_ok=True)
            raise
        for old_path in old_paths:
            if old_path not in filenames:
                Path(old_path).unlink(missing_ok=True)

        self._trained = False
        return len(crops)

    def _train_if_needed(self) -> None:
        if self._trained:
            return
        images: list[np.ndarray] = []
        labels: list[int] = []
        for employee_id, filename in load_training_samples():
            image = cv2.imread(filename, cv2.IMREAD_GRAYSCALE)
            if image is not None:
                images.append(image)
                labels.append(employee_id)
        self._labels = set(labels)
        if images:
            self._recognizer.train(images, np.asarray(labels, dtype=np.int32))
        self._trained = True

    def recognize(self, frame: str) -> tuple[int, str, str] | None:
        crop = self._face_crop(frame)
        self._train_if_needed()
        if not self._labels:
            return None
        label, distance = self._recognizer.predict(crop)
        if distance > self.threshold:
            return None
        employee = find_employee(int(label))
        if employee is None:
            return None
        employee_code, name = employee
        return int(label), employee_code, name
