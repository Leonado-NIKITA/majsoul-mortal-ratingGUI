import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: win
    visible: true
    width: app.mobileUi ? 420 : 1100
    height: app.mobileUi ? 820 : 720
    minimumWidth: app.mobileUi ? 320 : 760
    minimumHeight: 480
    title: "雀魂 Rating 跑谱工具 v" + app.version + " (Mortal " + app.modelTag + ")"

    readonly property bool narrow: width < 760
    property int page: 0
    readonly property var pageNames: app.inAppWeb
        ? ["参数", "日志", "结果图", "差异报告", "报告", "网页"]
        : ["参数", "日志", "结果图", "差异报告", "报告"]
    readonly property int reportPage: 4
    readonly property int webPage: 5
    property string lastLine: ""

    function openReport(url) {
        reportView.open(url)
        page = reportPage
    }

    Component {
        id: tabsComp
        TabBar {
            id: bar
            currentIndex: win.page
            onCurrentIndexChanged: win.page = currentIndex
            Connections {
                target: win
                function onPageChanged() { bar.currentIndex = win.page }
            }
            Repeater {
                model: win.pageNames
                TabButton {
                    text: modelData
                    // 手机上不设宽度, 由 TabBar 均分 (按 bar.width 算会形成绑定环)
                    width: app.mobileUi ? undefined : implicitWidth + 16
                }
            }
        }
    }

    Component {
        id: statusComp
        ToolBar {
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                Label {
                    text: app.status
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Button {
                    text: "停止"
                    visible: app.running
                    onClicked: app.stop()
                }
            }
        }
    }

    header: Loader { sourceComponent: app.mobileUi ? statusComp : tabsComp }
    footer: Loader { sourceComponent: app.mobileUi ? tabsComp : statusComp }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // 运行进度: 有总数时显示 x/y, 没有时显示来回滚动的条; 文字里带已等时间, 能看出没卡死
        Pane {
            visible: app.running
            Layout.fillWidth: true
            padding: 6
            leftPadding: 10
            rightPadding: 10
            ColumnLayout {
                anchors.fill: parent
                spacing: 2
                Label {
                    text: app.progressText
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                    font.pixelSize: app.mobileUi ? 12 : 13
                }
                // 局数进度; 一局都还没完成时显示滚动动画, 免得一直停在 0 看着像卡死
                ProgressBar {
                    Layout.fillWidth: true
                    from: 0
                    to: Math.max(1, app.progressTotal)
                    value: app.progressDone
                    indeterminate: app.progressTotal <= 0 || app.progressDone === 0
                }
                // 已等时间 / 单局上限, 每秒走一点
                ProgressBar {
                    visible: app.progressTime >= 0
                    Layout.fillWidth: true
                    from: 0
                    to: 1
                    value: Math.max(0, app.progressTime)
                }
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: win.page

            RunPage {}
            LogPage { id: logPage }
            ChartPage {}
            DiffPage {}
            ReportPage { id: reportView }
            Loader {
                active: app.inAppWeb
                sourceComponent: SessionWebPage {}
            }
        }
    }

    Connections {
        target: app
        function onLogAppended(s) {
            logPage.append(s)
            var lines = s.split("\n").filter(function (x) { return x.trim() !== "" })
            if (lines.length)
                win.lastLine = lines[lines.length - 1].trim()
        }
        function onLogCleared() { logPage.clear(); win.lastLine = "" }
        function onOpenReport(url) { win.openReport(url) }
        function onMessage(text) { msg.text = text; msg.open() }
        function onRunningChanged() {
            if (app.running)
                win.page = app.inAppWeb ? win.webPage : 1
            else if (app.status === "完成" && app.chartUrl !== "")
                win.page = 2
        }
    }

    Dialog {
        id: msg
        property alias text: msgLabel.text
        title: "提示"
        modal: true
        anchors.centerIn: parent
        width: Math.min(win.width - 40, 460)
        standardButtons: Dialog.Ok
        Label {
            id: msgLabel
            width: parent.width
            wrapMode: Text.Wrap
        }
    }

    onClosing: app.saveSettings()
}
