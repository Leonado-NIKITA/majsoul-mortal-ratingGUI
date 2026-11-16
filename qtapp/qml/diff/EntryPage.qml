import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// 一个决策点的一整屏内容: 牌桌, 自己 vs Mortal, 手牌, 牌效, 候选动作. 竖向滚动.
Flickable {
    id: root
    property var e: ({})
    property int me: 0
    property var names: []
    property bool showHands: true
    signal toggleHands()

    clip: true
    contentWidth: width
    contentHeight: col.implicitHeight + 16
    flickableDirection: Flickable.VerticalFlick
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar {}
    onEChanged: contentY = 0

    readonly property bool wide: width >= 900
    readonly property real boardW: wide ? Math.min(600, width * 0.45) : Math.min(600, width - 16)
    readonly property real tw: width < 400 ? 19 : 22

    Rectangle {
        anchors.fill: col
        anchors.margins: -4
        visible: e.isDiff === false
        color: "#eef6ff"
    }

    GridLayout {
        id: col
        x: 8; y: 8
        width: root.width - 16
        columns: root.wide ? 2 : 1
        columnSpacing: 14
        rowSpacing: 8

        // 牌桌
        Item {
            Layout.alignment: Qt.AlignTop | Qt.AlignHCenter
            Layout.preferredWidth: root.boardW
            Layout.preferredHeight: root.boardW
            visible: !!root.e.board
            BoardView {
                anchors.fill: parent
                snap: root.e.board
                me: root.me
                names: root.names
                showHands: root.showHands
                onToggleHands: root.toggleHands()
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            spacing: 8

            Label {
                visible: !root.e.board
                text: "这一处没能在 mjai_log 里定位到对应事件，只显示手牌。"
                color: "#b35c00"
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            Label {
                text: root.e.info || ""
                color: "#555"
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            // 手牌
            Flow {
                Layout.fillWidth: true
                spacing: 2
                Repeater {
                    model: root.e.tehai ? root.e.tehai.tiles : []
                    delegate: Row {
                        spacing: 0
                        leftPadding: modelData.before ? 8 : 0
                        Text {
                            visible: !!modelData.before
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.before; font.pixelSize: 13; color: "#444"
                        }
                        TileImage { pai: modelData.pai; width: root.tw; height: root.tw * 31 / 22 }
                        Text {
                            visible: !!modelData.after
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.after; font.pixelSize: 13; color: "#444"
                        }
                    }
                }
                Repeater {
                    model: root.e.tehai ? root.e.tehai.fuuros : []
                    delegate: MeldView {
                        items: modelData
                        tw: root.tw; th: root.tw * 31 / 22
                        leftPadding: 8
                    }
                }
            }

            // 自己 vs Mortal
            GridLayout {
                columns: 4
                columnSpacing: 6
                rowSpacing: 4
                Layout.fillWidth: true
                Text { text: "自己"; font.bold: true; font.pixelSize: 14 }
                Rectangle {
                    color: "#ffd5d5"; radius: 3
                    implicitWidth: ma.implicitWidth + 12; implicitHeight: ma.implicitHeight + 6
                    ActionView { id: ma; anchors.centerIn: parent; act: root.e.actual || ({}) }
                }
                Text { text: root.e.pA !== null && root.e.pA !== undefined ? (root.e.pA * 100).toFixed(1) + "%" : ""; color: "#666"; font.pixelSize: 12 }
                Text { text: root.e.briefA || ""; color: "#345"; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
                Text { text: "Mortal"; font.bold: true; font.pixelSize: 14 }
                Rectangle {
                    color: "#d7f2dc"; radius: 3
                    implicitWidth: mb.implicitWidth + 12; implicitHeight: mb.implicitHeight + 6
                    ActionView { id: mb; anchors.centerIn: parent; act: root.e.expected || ({}) }
                }
                Text { text: root.e.pE !== null && root.e.pE !== undefined ? (root.e.pE * 100).toFixed(1) + "%" : ""; color: "#666"; font.pixelSize: 12 }
                Text { text: root.e.briefE || ""; color: "#345"; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.Wrap }
            }
            Label {
                visible: root.e.isDiff === false
                text: "与 Mortal 一致"
                color: "#1a6"
                font.bold: true
            }

            EffView { Layout.fillWidth: true; eff: root.e.eff; tw: root.tw - 2 }

            // 候选动作
            Label { text: "候选动作"; font.bold: true; visible: !!(root.e.cands && root.e.cands.length) }
            Repeater {
                model: root.e.cands || []
                delegate: Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 34
                    color: modelData.cls === "actual" ? "#ffd5d5" : modelData.cls === "expected" ? "#d7f2dc" : (index % 2 ? "#f7f7f7" : "#fff")
                    border.color: "#ddd"
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 8; anchors.rightMargin: 8
                        ActionView { act: modelData.act; tw: 19; Layout.fillWidth: true }
                        Text { text: modelData.q.toFixed(4); font.pixelSize: 12; color: "#333"; Layout.preferredWidth: 60; horizontalAlignment: Text.AlignRight }
                        Text { text: (modelData.prob * 100).toFixed(2) + "%"; font.pixelSize: 12; color: "#666"; Layout.preferredWidth: 56; horizontalAlignment: Text.AlignRight }
                    }
                }
            }
        }
    }
}
