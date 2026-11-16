import QtQuick

// 一组副露 (items: [{t, rot, add}]), 底部对齐. tw/th 是竖牌的宽高; 横置牌是 th x tw.
Row {
    id: m
    property var items: []
    property real tw: 22
    property real th: 31
    readonly property real cellH: items.some(function (x) { return !!x.add }) ? 2 * tw : th

    Repeater {
        model: m.items
        delegate: Item {
            width: (modelData.rot || modelData.add) ? m.th : m.tw
            height: m.cellH
            Column {
                visible: !!modelData.add
                anchors.bottom: parent.bottom
                TileImage { side: true; pai: modelData.t; width: m.th; height: m.tw }
                TileImage { side: true; pai: modelData.add; width: m.th; height: m.tw }
            }
            TileImage {
                visible: !modelData.add
                anchors.bottom: parent.bottom
                side: !!modelData.rot
                pai: modelData.t
                width: modelData.rot ? m.th : m.tw
                height: modelData.rot ? m.tw : m.th
            }
        }
    }
}
