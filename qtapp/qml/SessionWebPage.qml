import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebView

// 程序内网页: 跑谱时 Python 侧 (webbackend.WebBridge, QML 里叫 web) 用它抓牌谱屋、提交 mjai.
// 安卓上 runJavaScript 的回调在安卓 UI 线程执行, 在里面跑 QML JS 会段错误;
// 所以不用回调: 脚本把结果写进 document.title = "MJR<序号>:<结果>", 在 onTitleChanged 里读回.
ColumnLayout {
    id: root
    spacing: 0
    property string notice: ""

    Rectangle {
        Layout.fillWidth: true
        implicitHeight: bar.implicitHeight + 12
        color: root.notice !== "" ? "#fff3cd" : "#eef3f8"
        ColumnLayout {
            id: bar
            anchors.fill: parent
            anchors.margins: 6
            spacing: 2
            Label {
                visible: root.notice !== ""
                text: root.notice
                font.bold: true
                color: "#8a5a00"
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            Label {
                text: app.running ? (win.lastLine || "运行中 ...") : "空闲（点「开始」后这里自动操作网页）"
                color: "#444"
                font.pixelSize: 12
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
        }
    }

    WebView {
        id: view
        Layout.fillWidth: true
        Layout.fillHeight: true
        url: "about:blank"

        onTitleChanged: {
            var m = /^MJR(\d+):([\s\S]*)$/.exec(title)
            if (m)
                web.jsDone(parseInt(m[1]), m[2])
        }
        onUrlChanged: web.urlSeen(url.toString())
        onLoadingChanged: function (req) {
            if (req.status === WebView.LoadSucceededStatus)
                web.loaded(req.url.toString(), true)
            else if (req.status === WebView.LoadFailedStatus)
                web.loaded(req.url.toString(), false)
            if (req.status !== WebView.LoadStartedStatus && String(req.url).indexOf("task=") >= 0)
                root.notice = ""
        }
    }

    Connections {
        target: web
        function onJsRequested(seq, script) { view.runJavaScript(script) }
        function onNavRequested(url) {
            if (view.url.toString() === url)
                view.reload()
            else
                view.url = url
        }
        function onAttention(text) {
            root.notice = text
            win.page = win.webPage
        }
    }
    Connections {
        target: app
        function onRunningChanged() { if (!app.running) root.notice = "" }
    }
}
