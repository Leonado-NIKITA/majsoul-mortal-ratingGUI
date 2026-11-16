import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "diff"

// 一巡一屏的差异阅读器.
// 左右划: 勾选「仅查看差异项」时是上/下一差异, 否则是上/下一巡. 按键和按钮走同一组 nav 槽.
Item {
    id: root
    readonly property var nav: app.reviewNav
    signal backToSummary()
    focus: true

    Keys.onBackPressed: function (ev) { ev.accepted = true; root.closeToc() || root.backToSummary() }
    // 按键 (需要焦点; 切到本页或关掉目录后会重新拿焦点)
    Keys.onPressed: function (ev) {
        var k = ev.key
        ev.accepted = true
        if (k === Qt.Key_Left) nav.swipePrev()
        else if (k === Qt.Key_Right) nav.swipeNext()
        else if (k === Qt.Key_PageUp) nav.prevTurn()
        else if (k === Qt.Key_PageDown) nav.nextTurn()
        else if (k === Qt.Key_BracketLeft) nav.prevDiff()
        else if (k === Qt.Key_BracketRight) nav.nextDiff()
        else if (k === Qt.Key_T) toc.opened ? toc.close() : toc.open()
        else if (k === Qt.Key_Home) nav.first()
        else if (k === Qt.Key_End) nav.last()
        else if (k === Qt.Key_Space) nav.toggleOnlyDiff()
        else if (k === Qt.Key_Escape || k === Qt.Key_Back) { toc.opened ? toc.close() : root.backToSummary() }
        else ev.accepted = false
    }

    // 翻页动画: 当前页随手指移动; 松手后滑出, 换内容, 从另一侧滑入
    property real slide: 0
    property bool animating: false
    property int pendingDir: 0

    function go(dir) {   // dir: +1 下一个 (向左划), -1 上一个
        if (animating) return
        var ok = dir > 0 ? nav.swipeNext() : nav.swipePrev()
        if (!ok) { bounce.restart(); return }
        slide = dir * page.width * 0.35
        slideIn.restart()
    }
    // 按钮用的: 指定哪一种移动
    function move(fn) {
        if (animating) return
        var before = nav.index
        var ok = nav[fn]()
        if (!ok) { bounce.restart(); return }
        slide = (nav.index > before ? 1 : -1) * page.width * 0.35
        slideIn.restart()
    }

    NumberAnimation { id: slideIn; target: root; property: "slide"; to: 0; duration: 160; easing.type: Easing.OutCubic
        onStarted: root.animating = true
        onFinished: root.animating = false }
    SequentialAnimation {
        id: bounce
        NumberAnimation { target: root; property: "slide"; to: 0; duration: 120; easing.type: Easing.OutCubic }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // 顶栏
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: topCol.implicitHeight + 8
            color: "#eef3f8"
            ColumnLayout {
                id: topCol
                anchors.fill: parent
                anchors.margins: 4
                spacing: 2
                RowLayout {
                    Layout.fillWidth: true
                    ToolButton { text: "‹ 汇总"; onClicked: root.backToSummary() }
                    Label {
                        Layout.fillWidth: true
                        text: nav.positionText
                        elide: Text.ElideRight
                        font.bold: true
                        font.pixelSize: 14
                    }
                    CheckBox {
                        text: "仅差异项"
                        checked: nav.onlyDiff
                        onToggled: nav.onlyDiff = checked
                    }
                }
                Label {
                    visible: !!nav.header.warn
                    text: nav.header.warn || ""
                    color: "#b35c00"
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
            }
        }

        // 页面
        Item {
            id: viewport
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            EntryPage {
                id: page
                width: parent.width
                height: parent.height
                x: root.slide
                opacity: 1 - Math.min(0.5, Math.abs(root.slide) / (width || 1))
                e: nav.current
                me: nav.me
                names: nav.names
                showHands: nav.showHands
                onToggleHands: nav.showHands = !nav.showHands
            }

            // 水平拖动翻页; 垂直滚动留给 EntryPage 里的 Flickable
            DragHandler {
                id: drag
                target: null
                xAxis.enabled: true
                yAxis.enabled: false
                dragThreshold: 14
                property real lastDx: 0
                onTranslationChanged: if (active && !root.animating) { lastDx = translation.x; root.slide = translation.x * 0.8 }
                onActiveChanged: {
                    if (active) { lastDx = 0; return }
                    var dx = lastDx
                    var thr = viewport.width * 0.2
                    if (Math.abs(dx) > thr) root.go(dx < 0 ? 1 : -1)
                    else bounce.restart()
                }
            }

            // 到头提示
            Rectangle {
                id: toastBox
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 16
                radius: 14
                color: "#cc333333"
                opacity: 0
                width: toastText.implicitWidth + 28
                height: toastText.implicitHeight + 14
                Text { id: toastText; anchors.centerIn: parent; color: "white"; font.pixelSize: 13 }
                SequentialAnimation {
                    id: toastAnim
                    NumberAnimation { target: toastBox; property: "opacity"; to: 1; duration: 80 }
                    PauseAnimation { duration: 1100 }
                    NumberAnimation { target: toastBox; property: "opacity"; to: 0; duration: 250 }
                }
            }
        }

        // 底栏
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 52
            color: "#eef3f8"
            RowLayout {
                anchors.fill: parent
                anchors.margins: 4
                spacing: 4
                Button { text: "上一差异"; Layout.fillWidth: true; enabled: nav.canPrevDiff
                    onClicked: { root.move("prevDiff"); root.forceActiveFocus() } }
                Button { text: "上一巡"; Layout.fillWidth: true; enabled: nav.canPrevTurn
                    onClicked: { root.move("prevTurn"); root.forceActiveFocus() } }
                Button { text: "目录"; Layout.fillWidth: true; highlighted: true; onClicked: toc.open() }
                Button { text: "下一巡"; Layout.fillWidth: true; enabled: nav.canNextTurn
                    onClicked: { root.move("nextTurn"); root.forceActiveFocus() } }
                Button { text: "下一差异"; Layout.fillWidth: true; enabled: nav.canNextDiff
                    onClicked: { root.move("nextDiff"); root.forceActiveFocus() } }
            }
        }
    }

    Connections {
        target: nav
        function onToast(msg) { toastText.text = msg; toastAnim.restart() }
    }

    TocDrawer {
        id: toc
        onPicked: function (i) { nav.jumpTo(i); close() }
        onPickedKyoku: function (k) { nav.jumpToKyoku(k); close() }
        onClosed: root.forceActiveFocus()
    }

    function activate() { forceActiveFocus() }
    function closeToc() { if (toc.opened) { toc.close(); return true } return false }
}

