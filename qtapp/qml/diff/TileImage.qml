import QtQuick
import "Tiles.js" as Tiles

// 一张牌: 从精灵图裁一格. 精灵图 pai-up.png 每格 64x89, pai-side.png 每格 89x64;
// 行 0 明牌, 行 1 牌背 (只有第 0 列), 行 2 灰牌 (摸切).
Item {
    id: t
    property string pai: ""
    property bool side: false
    property bool grey: false
    readonly property bool isBack: pai === "back"
    width: side ? 31 : 22
    height: side ? 22 : 31

    Image {
        anchors.fill: parent
        source: app.assetUrl + (t.side ? "pai-side.png" : "pai-up.png")
        sourceClipRect: {
            var c = t.isBack ? 0 : Tiles.col(t.pai)
            var r = t.isBack ? 1 : (t.grey ? 2 : 0)
            return t.side ? Qt.rect(c * 89, r * 64, 89, 64) : Qt.rect(c * 64, r * 89, 64, 89)
        }
        smooth: true
        mipmap: true
        cache: true
    }
}
