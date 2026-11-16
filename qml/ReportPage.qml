import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebView

// 报告浏览: 本机 http 服务提供的差异报告. 外链 (雀魂牌谱 / mjai 原报告) 交给系统浏览器
ColumnLayout {
    id: root
    spacing: 0
    property string home: ""

    function open(url) {
        home = url
        view.url = url
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.margins: 4
        Button { text: "后退"; enabled: view.canGoBack; onClicked: view.goBack() }
        Button { text: "汇总"; enabled: root.home !== ""; onClicked: view.url = root.home }
        Button { text: "刷新"; enabled: root.home !== ""; onClicked: view.reload() }
        Label {
            Layout.fillWidth: true
            text: view.loading ? "加载中 ..." : view.title
            elide: Text.ElideRight
            color: "#555"
        }
        Button {
            text: "用浏览器打开"
            visible: !app.mobileUi
            enabled: root.home !== ""
            onClicked: app.openExternal(view.url.toString())
        }
    }

    Item {
        Layout.fillWidth: true
        Layout.fillHeight: true

        Label {
            anchors.centerIn: parent
            visible: root.home === ""
            text: "在「差异报告」页勾选对局后点「生成报告」"
            color: "#888"
        }

        WebView {
            id: view
            anchors.fill: parent
            visible: root.home !== ""
            onLoadingChanged: function (req) {
                var u = req.url.toString()
                if (req.status === WebView.LoadStartedStatus && u.indexOf("http") === 0
                        && !app.isLocalUrl(u)) {
                    view.stop()
                    app.openExternal(u)
                    if (view.canGoBack)
                        view.goBack()
                }
            }
        }
    }
}
