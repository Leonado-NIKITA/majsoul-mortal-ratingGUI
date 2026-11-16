import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// 差异汇总: 对局列表 (点进阅读器) + Q 损失最大的差异项 (点进对应那一手)
Flickable {
    id: root
    clip: true
    contentWidth: width
    contentHeight: mainCol.implicitHeight + 16
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar {}
    readonly property var s: app.summary
    readonly property var rankColors: ["#ffffff", "#e8f5e9", "#f3f8fd", "#fffbe6", "#fdecea"]

    ColumnLayout {
        id: mainCol
        width: root.width
        spacing: 6

        Label {
            Layout.margins: 8
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            font.bold: true
            font.pixelSize: 16
            text: "差异项汇总　共 " + (s.games ? s.games.length : 0) + " 局，差异项 " + (s.diffs || 0) + " 处"
        }

        Label { text: "对局列表（点一局开始阅读）"; Layout.leftMargin: 8; font.bold: true }
        Repeater {
            model: s.games || []
            delegate: Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: 6; Layout.rightMargin: 6
                implicitHeight: gcol.implicitHeight + 12
                color: modelData.ok ? (root.rankColors[modelData.rank] || "#fff") : "#f0f0f0"
                border.color: "#ccc"; border.width: 0.5
                ColumnLayout {
                    id: gcol
                    anchors.fill: parent; anchors.margins: 6
                    spacing: 2
                    RowLayout {
                        Label { text: modelData.when; font.bold: true }
                        Label { text: modelData.mode }
                        Label { text: modelData.rank + "位 " + modelData.score }
                        Item { Layout.fillWidth: true }
                        Label {
                            visible: modelData.ok
                            text: modelData.diffs + " 处差异  ›"
                            color: "#1f5fa8"; font.bold: true
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        font.pixelSize: 12
                        color: "#555"
                        text: modelData.ok
                              ? "Rating " + (modelData.rating === null || modelData.rating === undefined ? "-" : modelData.rating)
                                + "　一致 " + modelData.matches + "/" + modelData.total
                                + (modelData.note ? "　" + modelData.note : "")
                              : modelData.note
                    }
                }
                TapHandler { enabled: modelData.ok; onTapped: app.openGame(modelData.uuid, -1) }
            }
        }

        Label { text: "Q 值损失最大的差异项"; Layout.leftMargin: 8; Layout.topMargin: 8; font.bold: true }
        Label {
            Layout.leftMargin: 8; Layout.rightMargin: 8; Layout.fillWidth: true
            wrapMode: Text.Wrap; font.pixelSize: 12; color: "#777"
            text: "Q 损失 = Mortal 首选的 Q 值 − 自己选择的 Q 值，越大说明偏离越多。"
        }
        Repeater {
            model: s.top || []
            delegate: Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: 6; Layout.rightMargin: 6
                implicitHeight: tc.implicitHeight + 10
                color: "#fff"; border.color: "#ddd"
                ColumnLayout {
                    id: tc
                    anchors.fill: parent; anchors.margins: 5
                    spacing: 1
                    RowLayout {
                        Label { text: modelData.when + "　" + modelData.kyoku + " 第" + modelData.junme + "巡"; font.pixelSize: 12; color: "#555" }
                        Item { Layout.fillWidth: true }
                        Label { text: modelData.loss.toFixed(3); color: "#c33"; font.bold: true }
                    }
                    Label {
                        text: modelData.actual + "  →  " + modelData.expected
                        font.pixelSize: 14
                    }
                    Label {
                        visible: !!(modelData.briefA || modelData.briefE)
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        font.pixelSize: 11; color: "#777"
                        text: modelData.briefA + (modelData.briefA && modelData.briefE ? "  →  " : "") + modelData.briefE
                    }
                }
                TapHandler { onTapped: app.openGame(modelData.uuid, modelData.idx) }
            }
        }
    }
}


