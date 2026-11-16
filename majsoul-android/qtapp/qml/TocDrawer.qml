import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// 目录: 按小局分组, 差异项高亮; 点小局标题跳到该局第一个差异, 点条目跳到该手
Drawer {
    id: d
    signal picked(int idx)
    signal pickedKyoku(int ki)
    edge: Qt.LeftEdge
    width: Math.min(parent.width * 0.88, 420)
    height: parent.height
    modal: true

    onOpened: list.forceActiveFocus()
    ListView {
        id: list
        anchors.fill: parent
        clip: true
        focus: true
        Keys.onBackPressed: function (ev) { d.close(); ev.accepted = true }
        Keys.onEscapePressed: function (ev) { d.close(); ev.accepted = true }
        model: d.opened || d.visible ? app.reviewNav.toc : []
        ScrollBar.vertical: ScrollBar {}
        header: Label {
            padding: 10
            text: "目录　差异 " + app.reviewNav.diffCount + " 处 / 共 " + app.reviewNav.count + " 手"
            font.bold: true
        }
        delegate: Rectangle {
            required property var modelData
            readonly property bool isK: modelData.type === "kyoku"
            readonly property bool cur: !isK && modelData.idx === app.reviewNav.index
            width: ListView.view.width
            height: isK ? 40 : 34
            color: cur ? "#cfe3ff" : isK ? "#e4e4e4" : modelData.isDiff ? "#fff5f5" : "#fff"
            Label {
                anchors.fill: parent
                anchors.leftMargin: isK ? 10 : 22
                anchors.rightMargin: 8
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                font.bold: isK
                color: isK || modelData.isDiff ? "#222" : "#888"
                text: isK ? modelData.title + "　" + modelData.diffs + " 处　" + modelData.end : modelData.label
            }
            TapHandler {
                onTapped: isK ? d.pickedKyoku(modelData.ki) : d.picked(modelData.idx)
            }
        }
        onVisibleChanged: if (visible) positionViewAtIndex(Math.max(0, indexOfCurrent() - 3), ListView.Beginning)
        function indexOfCurrent() {
            var t = app.reviewNav.toc
            for (var i = 0; i < t.length; i++)
                if (t[i].type === "entry" && t[i].idx === app.reviewNav.index) return i
            return 0
        }
    }
}
