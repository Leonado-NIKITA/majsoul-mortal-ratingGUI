"""雀魂 Rating 跑谱工具 - Qt 重写版入口 (桌面: python -m qtapp.main; 安卓: 构建时作为入口).

和旧 main.py 的区别只有两点: 后端换成 qtapp.backend.Backend, QML 从 qtapp/qml 加载.
旧 main.py / app_backend.py / qml/ 不动, 用于对比.
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    import store
    try:  # 安卓构建里旧入口被改名为 legacy_main (见 fast_build.sh 的 QT=1)
        from legacy_main import _android_ca_bundle
    except ImportError:
        from main import _android_ca_bundle

    if store.IS_ANDROID:
        _android_ca_bundle()
    else:
        os.environ.setdefault("QT_WEBVIEW_PLUGIN", "webview2")
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle
    from PySide6.QtWebView import QtWebView

    QtWebView.initialize()
    QQuickStyle.setStyle("Material" if store.IS_ANDROID else "Fusion")
    app = QGuiApplication(sys.argv)
    app.setApplicationName("MajsoulRating")
    app.setOrganizationName("MajsoulRating")
    res = store.resource_dir()
    ico = res / "installer" / "app.ico"
    if not ico.exists():
        ico = res / "app.ico"
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))
    os.chdir(store.app_dir())

    from qtapp.backend import Backend

    web = None
    if store.IS_ANDROID or os.environ.get("MJR_INAPP_WEB") == "1":
        from webbackend import WebBridge
        web = WebBridge()
    backend = Backend(web)
    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    ctx.setContextProperty("app", backend)
    ctx.setContextProperty("web", web)
    engine.load(QUrl.fromLocalFile(str(res / "qtapp" / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 1
    app.aboutToQuit.connect(backend.shutdown)
    code = app.exec()
    del engine
    return code


if __name__ == "__main__":
    sys.exit(main())

