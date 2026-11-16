import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// 牌效: 当前手牌的进张, 或打出每张牌后的向听与进张
Column {
    id: v
    property var eff: null
    property real tw: 18
    visible: !!eff
    spacing: 4

    Component {
        id: waitsComp
        Flow {
            property var waits: []
            property real tw: 18
            spacing: 6
            Repeater {
                model: waits
                Row {
                    opacity: modelData.n === 0 ? 0.45 : 1
                    TileImage { pai: modelData.tile; width: tw; height: tw * 31 / 22 }
                    Text { text: "*" + modelData.n; font.pixelSize: 12; color: modelData.n === 0 ? "#c00" : "#333"; anchors.verticalCenter: parent.verticalCenter }
                }
            }
        }
    }

    Label {
        text: !v.eff ? "" : v.eff.kind === "wait" ? "牌效（当前手牌）" : "牌效：打出后的向听与进张"
        font.bold: true
    }
    Label {
        visible: !!v.eff && v.eff.kind === "wait"
        width: v.width
        wrapMode: Text.Wrap
        text: v.eff ? v.eff.shText + "，进张 " + v.eff.total + " 枚 / " + v.eff.kinds + " 种" : ""
    }
    Loader {
        active: !!v.eff && v.eff.kind === "wait"
        width: v.width
        sourceComponent: waitsComp
        onLoaded: { item.waits = v.eff.waits; item.tw = v.tw }
    }
    Label {
        visible: !!v.eff && v.eff.kind === "discard"
        width: v.width
        wrapMode: Text.Wrap
        color: "#777"
        font.pixelSize: 12
        text: v.eff ? "打牌前 " + v.eff.shText + "。" + v.eff.note : ""
    }
    Repeater {
        model: v.eff && v.eff.kind === "discard" ? v.eff.rows : []
        delegate: Rectangle {
            width: v.width
            height: rowCol.implicitHeight + 8
            color: modelData.isActual ? "#ffd5d5" : modelData.isExpected ? "#d7f2dc" : "#fff"
            border.color: "#ddd"
            Column {
                id: rowCol
                x: 6; y: 4
                width: parent.width - 12
                spacing: 2
                Row {
                    spacing: 8
                    TileImage { pai: modelData.tile; width: v.tw + 2; height: (v.tw + 2) * 31 / 22; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.shText + (modelData.back ? "（退向）" : "") + "　进张 " + modelData.total + "/" + modelData.kinds + "种"
                        color: modelData.back ? "#c33" : "#222"
                        font.pixelSize: 13
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.marks.join(" ")
                        color: modelData.best ? "#1a6" : "#444"
                        font.pixelSize: 11
                    }
                }
                Loader {
                    width: parent.width
                    sourceComponent: waitsComp
                    onLoaded: { item.waits = modelData.waits; item.tw = v.tw - 2 }
                }
            }
        }
    }
}
