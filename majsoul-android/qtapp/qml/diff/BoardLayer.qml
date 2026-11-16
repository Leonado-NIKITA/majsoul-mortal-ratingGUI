import QtQuick
import "Tiles.js" as Tiles

// 牌桌上一家的那一层: 先按「自家在下」摆好, 再整体旋转. 几何照搬 assets/diff_report.css 的 .board
Item {
    id: lay
    property var snap
    property int seat: 0
    property int me: 0
    property var names: []
    property bool showHands: true
    readonly property int rel: (seat + 4 - me) % 4
    readonly property bool openHand: rel === 0 || showHands
    readonly property var river: snap.rivers[seat]
    anchors.fill: parent
    rotation: [0, -90, 180, 90][rel]

    // 座位标签: 风 + 点数 + 立直
    Item {
        x: 220; y: 383; width: 160; height: 20
        Row {
            anchors.centerIn: parent
            spacing: 3
            Text {
                text: Tiles.WINDS[((lay.seat - lay.snap.oya) % 4 + 4) % 4]
                color: lay.seat === lay.snap.oya ? "#ffd666" : "#e9f5ee"
                font.pixelSize: 13
                font.bold: lay.seat === lay.snap.oya || lay.rel === 0
            }
            Text {
                text: String(lay.snap.scores[lay.seat])
                color: "#e9f5ee"
                font.pixelSize: 13
                font.bold: lay.rel === 0
            }
            Rectangle {
                visible: !!lay.snap.riichi[lay.seat]
                width: rt.implicitWidth + 6; height: 15; radius: 3; color: "#c0392b"
                Text { id: rt; anchors.centerIn: parent; text: "立直"; color: "#fff"; font.pixelSize: 11 }
            }
        }
    }

    // 牌河: 每行 6 张, 第 3 行起不换行
    Column {
        x: 234; y: 404; width: 150
        Repeater {
            model: 3
            delegate: Item {
                id: rowItem
                required property int index
                readonly property var tiles: lay.river.slice(index * 6, index === 2 ? undefined : index * 6 + 6)
                width: 150
                height: tiles.length ? 31 : 0
                Row {
                    anchors.bottom: parent.bottom
                    Repeater {
                        model: rowItem.tiles
                        delegate: Item {
                            width: modelData.side ? 31 : 22
                            height: 31
                            opacity: modelData.called ? 0.35 : 1
                            TileImage {
                                id: ti
                                anchors.bottom: parent.bottom
                                side: !!modelData.side
                                grey: !!modelData.tg
                                pai: modelData.pai
                            }
                            Rectangle {
                                visible: !!lay.snap.last_discard && lay.snap.last_discard[0] === lay.seat
                                         && lay.snap.last_discard[1] === rowItem.index * 6 + index
                                x: ti.x; y: ti.y; width: ti.width; height: ti.height
                                color: "transparent"; border.color: "#ff4d4f"; border.width: 2; radius: 3
                            }
                        }
                    }
                }
            }
        }
    }

    // 手牌 (左) 和副露 (右)
    Item {
        x: 48; y: 552; width: 504; height: 44
        Row {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            Repeater {
                model: lay.snap.hands[lay.seat]
                delegate: Item {
                    readonly property bool drawnTile: !!lay.snap.drawn[lay.seat] && index === lay.snap.hands[lay.seat].length - 1
                    width: 22 + (drawnTile ? 6 : 0)
                    height: 31
                    TileImage {
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        pai: lay.openHand ? modelData : "back"
                    }
                }
            }
        }
        Row {
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            spacing: 5
            Repeater {
                model: lay.snap.meldv[lay.seat]
                delegate: Item {
                    width: mv.width
                    height: 44
                    MeldView { id: mv; anchors.bottom: parent.bottom; items: modelData }
                }
            }
        }
    }
}

