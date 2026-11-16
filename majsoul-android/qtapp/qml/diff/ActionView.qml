import QtQuick
import QtQuick.Controls

// 一个动作: 前缀文字 + 牌 + 后缀文字. act = {pre, tiles, post}
Row {
    id: r
    property var act: ({pre: "", tiles: [], post: ""})
    property real tw: 21
    property color textColor: "#222"
    spacing: 2
    Text {
        visible: !!r.act.pre
        anchors.verticalCenter: parent.verticalCenter
        text: r.act.pre || ""
        color: r.textColor
        font.pixelSize: 15
    }
    Repeater {
        model: r.act.tiles || []
        TileImage {
            anchors.verticalCenter: parent.verticalCenter
            pai: modelData
            width: r.tw; height: r.tw * 31 / 22
        }
    }
    Text {
        visible: !!r.act.post
        anchors.verticalCenter: parent.verticalCenter
        text: r.act.post || ""
        color: r.textColor
        font.pixelSize: 15
    }
}
