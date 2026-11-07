"""Один снимок с веб-камеры для Кая-сторожа. Qt Multimedia (PySide6-Addons), иначе OpenCV, иначе без фото."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

log = logging.getLogger(__name__)

WARMUP_MS = 1500        # камере нужно время на экспозицию, иначе первый кадр чёрный
TIMEOUT_MS = 12000


def available() -> bool:
    try:
        from PySide6.QtMultimedia import QMediaDevices
        return bool(QMediaDevices.videoInputs())
    except ImportError:
        pass
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


class Snapshot(QObject):
    """Снимок в файл; done(путь или "") приходит в потоке интерфейса ровно один раз."""
    done = Signal(str)
    _from_thread = Signal(str)

    def __init__(self, path: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.path = path
        self._finished = False
        self._qt = None
        self._from_thread.connect(self._finish)

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self._start_qt():
            QTimer.singleShot(TIMEOUT_MS, lambda: self._finish(""))
            return
        threading.Thread(target=self._opencv, daemon=True).start()

    def _start_qt(self) -> bool:
        try:
            from PySide6.QtMultimedia import QCamera, QImageCapture, QMediaCaptureSession, QMediaDevices
        except ImportError:
            return False
        device = QMediaDevices.defaultVideoInput()
        if device.isNull():
            return False
        camera = QCamera(device, self)
        capture = QImageCapture(self)
        session = QMediaCaptureSession(self)
        session.setCamera(camera)
        session.setImageCapture(capture)
        capture.imageSaved.connect(lambda _id, name: self._finish(name))
        capture.errorOccurred.connect(lambda _id, _err, text: (log.warning("Камера: %s", text), self._finish("")))
        camera.errorOccurred.connect(lambda _err, text: (log.warning("Камера: %s", text), self._finish("")))
        self._qt = (camera, capture, session)
        camera.start()
        QTimer.singleShot(WARMUP_MS, lambda: not self._finished and capture.captureToFile(str(self.path)))
        return True

    def _opencv(self) -> None:
        try:
            import cv2
        except ImportError:
            log.info("Для фото нужен PySide6-Addons или opencv-python")
            self._from_thread.emit("")
            return
        import time
        cam = cv2.VideoCapture(0, cv2.CAP_DSHOW) if hasattr(cv2, "CAP_DSHOW") else cv2.VideoCapture(0)
        try:
            frame, deadline = None, time.monotonic() + WARMUP_MS / 1000
            while time.monotonic() < deadline or frame is None:
                ok, frame = cam.read()
                if not ok:
                    frame = None
                    if time.monotonic() > deadline + 3:
                        break
            ok = frame is not None and cv2.imwrite(str(self.path), frame)
            self._from_thread.emit(str(self.path) if ok else "")
        finally:
            cam.release()

    def _finish(self, name: str) -> None:
        if self._finished:
            return
        self._finished = True
        if self._qt:
            self._qt[0].stop()
        self.done.emit(name if name and Path(name).is_file() else "")
        self.deleteLater()


def take(path: Path, callback: Callable[[str], None], parent: QObject | None = None) -> None:
    snap = Snapshot(path, parent)
    snap.done.connect(callback)
    snap.start()
