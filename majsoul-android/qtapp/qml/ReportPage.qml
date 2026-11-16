import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// 「报告」页: 汇总 <-> 阅读器 两层
Item {
    id: root
    property bool reading: false

    function showSummary() { reading = false }
    function showReader() { reading = true; if (reader.item) reader.item.activate() }
    function back() {   // 安卓返回键: 先关目录, 再回汇总. 返回 true 表示已处理
        if (!reading) return false
        if (reader.item && reader.item.closeToc()) return true
        app.closeReader()
        return true
    }

    Label {
        anchors.centerIn: parent
        visible: !app.hasSummary
        text: "在「差异报告」页勾选对局后点「生成报告」"
        color: "#888"
    }
    DiffSummaryPage {
        anchors.fill: parent
        visible: app.hasSummary && !root.reading
    }
    Loader {
        id: reader
        anchors.fill: parent
        active: root.reading
        visible: root.reading
        sourceComponent: DiffReaderPage {
            onBackToSummary: app.closeReader()
            Component.onCompleted: activate()
        }
    }
    Connections {
        target: app
        function onShowReader() { root.showReader() }
        function onShowSummary() { root.showSummary() }
    }
}

