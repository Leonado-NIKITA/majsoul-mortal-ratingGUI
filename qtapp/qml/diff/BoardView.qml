import QtQuick

// 牌桌: 内部按 600x600 排版, 整体缩放到 width. 四家 + 中央 (局名/供托/余牌/宝牌).
Item {
    id: root
    property var snap
    property int me: 0
    property var names: []
    property bool showHands: true
    signal toggleHands()
    height: width

    Item {
        width: 600; height: 600
        scale: root.width / 600
        transformOrigin: Item.TopLeft

        Rectangle { anchors.fill: parent; color: "#2f6b4f"; radius: 10 }

        Rectangle {
            x: 220; y: 220; width: 160; height: 160; radius: 8; color: "#24543e"
            Column {
                anchors.centerIn: parent
                spacing: 3
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: root.snap ? root.snap.name : ""
                    color: "#fff"; font.pixelSize: 16; font.bold: true
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: root.snap ? "供托 " + root.snap.kyotaku + "　余 " + root.snap.tiles_left + " 张" : ""
                    color: "#fff"; font.pixelSize: 13
                }
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 1
                    Repeater {
                        model: 5
                        TileImage {
                            width: 17; height: 24
                            pai: root.snap && index < root.snap.dora.length ? root.snap.dora[index] : "back"
                        }
                    }
                }
            }
        }

        Repeater {
            model: root.snap ? 4 : 0
            delegate: BoardLayer {
                required property int index
                seat: index
                snap: root.snap
                me: root.me
                names: root.names
                showHands: root.showHands
            }
        }

        Rectangle {
            x: 600 - 6 - width; y: 6; width: 92; height: 34; radius: 4
            color: "#40000000"; border.color: "#80ffffff"
            Text { anchors.centerIn: parent; text: root.showHands ? "隐藏他家" : "他家手牌"; color: "#eef"; font.pixelSize: 14 }
            TapHandler { onTapped: root.toggleHands() }
        }
    }
}
