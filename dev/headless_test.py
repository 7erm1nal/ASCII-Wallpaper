#!/usr/bin/env python3
"""Безголовый прогон сцены: грузит dev/preview.qml, крутит N секунд, сохраняет кадры в PNG.
   QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software python3 dev/headless_test.py out_prefix [seconds]"""
import os, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView

prefix = sys.argv[1] if len(sys.argv) > 1 else "/tmp/frame"
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 3
app = QGuiApplication(sys.argv)
view = QQuickView()
view.setResizeMode(QQuickView.SizeRootObjectToView)
view.setSource(QUrl.fromLocalFile(os.path.join(os.path.dirname(__file__), "headless_root.qml")))
if view.status() != QQuickView.Ready:
    for e in view.errors(): print("QML ERROR:", e.toString())
    sys.exit(1)
view.resize(1920, 1080)
view.show()
t0 = time.time(); n = [0]; frames = []
def snap():
    img = view.grabWindow()
    path = f"{prefix}_{n[0]}.png"; img.save(path); frames.append(path); n[0] += 1
    print("saved", path, img.width(), img.height())
QTimer.singleShot(int(secs * 1000 * 0.5), snap)
QTimer.singleShot(int(secs * 1000), lambda: (snap(), app.quit()))
app.exec()
