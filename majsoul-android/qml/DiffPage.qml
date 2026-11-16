import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// 差异报告选局: 玩家 -> 本地有报告的对局 (可勾选) -> 生成并在「报告」页打开
ColumnLayout {
    id: root
    spacing: 4

    readonly property var rankColors: ["#ffffff", "#e8f5e9", "#f3f8fd", "#fffbe6", "#fdecea"]

    Flow {
        Layout.fillWidth: true
        Layout.margins: 6
        spacing: 6
        ComboBox {
            width: win.narrow ? root.width - 12 : 280
            model: app.playerLabels
            currentIndex: app.playerIndex
            onActivated: function (i) { app.selectPlayer(i) }
        }
        Button { text: "刷新"; onClicked: app.refreshPlayers(true) }
        Button { text: "选新增"; onClicked: app.selectNew() }
        Button { text: "全选"; onClicked: app.selectAll() }
        Button { text: "全不选"; onClicked: app.selectNone() }
        Button {
            text: "生成报告"
            highlighted: true
            enabled: app.selectedCount > 0
            onClicked: app.generateReport()
        }
        Button { text: "打开上次报告"; onClicked: app.openLastReport() }
    }

    Label {
        Layout.fillWidth: true
        Layout.leftMargin: 8
        Layout.rightMargin: 8
        text: app.diffInfo
        color: "#555"
        wrapMode: Text.Wrap
    }

    // 桌面: 表头 + 一行一局
    Rectangle {
        visible: !win.narrow
        Layout.fillWidth: true
        Layout.leftMargin: 6
        Layout.rightMargin: 6
        height: 28
        color: "#e4e4e4"
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 4
            spacing: 6
            Label { text: "选"; Layout.preferredWidth: 30; horizontalAlignment: Text.AlignHCenter }
            Label { text: "时间"; Layout.preferredWidth: 120 }
            Label { text: "场次"; Layout.preferredWidth: 50 }
            Label { text: "顺位"; Layout.preferredWidth: 40 }
            Label { text: "点数"; Layout.preferredWidth: 56 }
            Label { text: "pt"; Layout.preferredWidth: 44 }
            Label { text: "终局四家 (按顺位)"; Layout.fillWidth: true }
            Label { text: "Rating"; Layout.preferredWidth: 54 }
            Label { text: "AI 一致率"; Layout.preferredWidth: 110 }
            Label { text: "差异"; Layout.preferredWidth: 40 }
            Label { text: ""; Layout.preferredWidth: 40 }
        }
    }

    ListView {
        id: list
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.leftMargin: 6
        Layout.rightMargin: 6
        clip: true
        model: app.gameModel
        reuseItems: true
        ScrollBar.vertical: ScrollBar {}
        delegate: win.narrow ? cardDelegate : rowDelegate

        Label {
            anchors.centerIn: parent
            visible: list.count === 0
            text: "没有本地报告的对局"
            color: "#888"
        }
    }

    Component {
        id: rowDelegate
        Rectangle {
            required property int index
            required property bool checked
            required property string when
            required property string mode
            required property int rank
            required property string score
            required property string pt
            required property string table
            required property string rating
            required property string acc
            required property string diffs
            required property bool isNew
            width: ListView.view.width
            height: 30
            color: root.rankColors[rank] || "#fff"
            border.color: "#ddd"
            border.width: 0.5
            MouseArea { anchors.fill: parent; onClicked: app.toggleGame(index) }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 4
                spacing: 6
                CheckBox {
                    checked: parent.parent.checked
                    Layout.preferredWidth: 30
                    padding: 0
                    onClicked: app.toggleGame(index)
                }
                Label { text: when; Layout.preferredWidth: 120 }
                Label { text: mode; Layout.preferredWidth: 50 }
                Label { text: rank + "位"; Layout.preferredWidth: 40 }
                Label { text: score; Layout.preferredWidth: 56 }
                Label { text: pt; Layout.preferredWidth: 44 }
                Label { text: table; Layout.fillWidth: true; elide: Text.ElideRight }
                Label { text: rating; Layout.preferredWidth: 54 }
                Label { text: acc; Layout.preferredWidth: 110; elide: Text.ElideRight }
                Label { text: diffs; Layout.preferredWidth: 40 }
                Label { text: isNew ? "新增" : ""; color: "#c60"; Layout.preferredWidth: 40 }
            }
        }
    }

    // 手机: 两行卡片, 点整张卡片切换勾选
    Component {
        id: cardDelegate
        Rectangle {
            required property int index
            required property bool checked
            required property string when
            required property string mode
            required property int rank
            required property string score
            required property string pt
            required property string table
            required property string rating
            required property string acc
            required property string diffs
            required property bool isNew
            width: ListView.view.width
            height: card.implicitHeight + 12
            color: root.rankColors[rank] || "#fff"
            border.color: "#ccc"
            border.width: 0.5
            MouseArea { anchors.fill: parent; onClicked: app.toggleGame(index) }
            RowLayout {
                id: card
                anchors.fill: parent
                anchors.margins: 6
                CheckBox {
                    checked: parent.parent.checked
                    onClicked: app.toggleGame(index)
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    RowLayout {
                        Label { text: when; font.bold: true }
                        Label { text: mode }
                        Label { text: rank + "位 " + score + " (" + pt + ")" }
                        Label { text: isNew ? "新增" : ""; color: "#c60" }
                    }
                    Label {
                        text: "Rating " + rating + "　一致率 " + acc + "　差异 " + diffs
                        color: "#444"
                        font.pixelSize: 13
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                    Label {
                        text: table
                        color: "#666"
                        font.pixelSize: 12
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                }
            }
        }
    }
}
