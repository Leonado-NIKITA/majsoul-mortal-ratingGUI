"""雀魂 Rating 跑谱工具 - 图形界面入口 (PySide6 + QML, 桌面和安卓共用)."""
from __future__ import annotations

import os
import sys


def _android_ca_bundle() -> None:
    """安卓上的 Python 没有 CA 证书包, 直连 HTTPS 会证书校验失败.
    把系统根证书拼成一个 PEM 文件, 用 SSL_CERT_FILE 指给 OpenSSL.
    (系统证书目录的文件名是旧式哈希, 不能直接当 SSL_CERT_DIR 用.)"""
    if os.environ.get("SSL_CERT_FILE"):
        return
    import pathlib
    import store

    out = store.app_dir() / "cacert.pem"
    for d in ("/apex/com.android.conscrypt/cacerts", "/system/etc/security/cacerts"):
        src = pathlib.Path(d)
        try:
            files = sorted(src.iterdir())
        except OSError:
            continue
        pems = []
        for f in files:
            try:
                t = f.read_text(encoding="ascii", errors="ignore")
            except OSError:
                continue
            a = t.find("-----BEGIN CERTIFICATE-----")
            b = t.find("-----END CERTIFICATE-----", a)
            if a >= 0 and b > a:
                pems.append(t[a:b + len("-----END CERTIFICATE-----")])
        if pems:
            try:
                out.write_text("\n".join(pems) + "\n", encoding="ascii")
                os.environ["SSL_CERT_FILE"] = str(out)
            except OSError:
                pass
            return


def main() -> int:
    import store

    if store.IS_ANDROID:
        _android_ca_bundle()
    if not store.IS_ANDROID:
        # Windows 上用系统自带的 WebView2 (Edge) 显示网页, 不用打包 QtWebEngine
        os.environ.setdefault("QT_WEBVIEW_PLUGIN", "webview2")
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle
    from PySide6.QtWebView import QtWebView

    QtWebView.initialize()  # 必须在 QGuiApplication 之前
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

    from app_backend import Backend

    web = None
    if store.IS_ANDROID or os.environ.get("MJR_INAPP_WEB") == "1":
        from webbackend import WebBridge  # 程序内网页提交跑谱 (安卓; 桌面可设环境变量调试)
        web = WebBridge()
    backend = Backend(web)
    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    ctx.setContextProperty("app", backend)
    ctx.setContextProperty("web", web)
    engine.load(QUrl.fromLocalFile(str(res / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 1
    app.aboutToQuit.connect(backend.shutdown)
    code = app.exec()
    del engine  # 先拆界面再释放后端, 免得 QML 退出时读到已经没了的 app
    return code


if __name__ == "__main__":
    sys.exit(main())
