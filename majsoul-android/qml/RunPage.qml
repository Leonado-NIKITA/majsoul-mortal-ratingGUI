import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

ScrollView {
    id: root
    contentWidth: availableWidth
    clip: true

    function startRun() { app.start(identBox.editText, freshBox.checked); freshBox.checked = false }

    ColumnLayout {
        width: root.availableWidth
        spacing: 10

        GroupBox {
            title: "玩家"
            Layout.fillWidth: true
            Layout.margins: 8
            ColumnLayout {
                anchors.fill: parent
                RowLayout {
                    RadioButton {
                        text: "UID"
                        checked: app.by === "id"
                        onClicked: app.by = "id"
                    }
                    RadioButton {
                        text: "昵称"
                        checked: app.by === "name"
                        onClicked: app.by = "name"
                    }
                }
                ComboBox {
                    id: identBox
                    Layout.fillWidth: true
                    editable: true
                    model: app.historyModel
                    textRole: "label"
                    editText: app.ident
                    Component.onCompleted: { currentIndex = -1; editText = app.ident }
                    // 输入时立刻写回 app.ident, 否则改别的选项触发 formChanged 会把旧 UID 填回来
                    onEditTextChanged: if (activeFocus && editText !== app.ident) app.ident = editText
                    Connections {
                        target: app
                        function onFormChanged() {
                            if (identBox.editText !== app.ident && !identBox.activeFocus)
                                identBox.editText = app.ident
                        }
                    }
                    onActivated: function (i) { app.pickHistory(i); editText = app.ident }
                    onAccepted: root.startRun()
                    Keys.onDeletePressed: function (ev) {
                        if (popup.visible && highlightedIndex >= 0) {
                            app.forgetHistory(highlightedIndex)
                            ev.accepted = true
                        } else {
                            ev.accepted = false
                        }
                    }
                    delegate: ItemDelegate {
                        required property int index
                        required property string label
                        width: identBox.width
                        text: label
                        highlighted: identBox.highlightedIndex === index
                        onPressAndHold: forget.ask(index, label)
                    }
                }
                Label {
                    text: app.mobileUi ? "长按历史项可删除" : "下拉中按 Delete 删除历史项"
                    color: "#888"
                    font.pixelSize: 12
                }
            }
        }

        GroupBox {
            title: "场次"
            Layout.fillWidth: true
            Layout.leftMargin: 8
            Layout.rightMargin: 8
            Flow {
                anchors.fill: parent
                spacing: 4
                Repeater {
                    model: app.modeNames
                    CheckBox {
                        text: modelData
                        checked: app.modes.indexOf(modelData) >= 0
                        onToggled: app.setMode(modelData, checked)
                    }
                }
            }
        }

        GroupBox {
            title: "选项"
            Layout.fillWidth: true
            Layout.leftMargin: 8
            Layout.rightMargin: 8
            GridLayout {
                anchors.fill: parent
                columns: win.narrow ? 2 : 4
                columnSpacing: 12

                Label { text: "局数" }
                SpinBox {
                    from: 1; to: 500; editable: true
                    value: app.gameCount
                    onValueModified: app.gameCount = value
                }
                Label { text: "并发"; visible: !app.inAppWeb }
                SpinBox {
                    visible: !app.inAppWeb
                    from: 1; to: 8; editable: true
                    value: app.concurrency
                    onValueModified: app.concurrency = value
                }
                Label { text: "超时倍数" }
                RowLayout {
                    SpinBox {
                        id: ts
                        from: 5; to: 100; stepSize: 5; editable: true
                        value: Math.round(app.timeoutScale * 10)
                        textFromValue: function (v) { return (v / 10).toFixed(1) }
                        valueFromText: function (t) { return Math.round(parseFloat(t) * 10) }
                        onValueModified: app.timeoutScale = value / 10
                    }
                    Label { text: app.timeoutHint; color: "#888"; font.pixelSize: 12 }
                }
                CheckBox {
                    id: freshBox
                    text: "清缓存重跑"
                    Layout.columnSpan: 2
                }
            }
        }

        GroupBox {
            title: "输出目录"
            visible: !app.mobileUi
            Layout.fillWidth: true
            Layout.leftMargin: 8
            Layout.rightMargin: 8
            RowLayout {
                anchors.fill: parent
                TextField {
                    Layout.fillWidth: true
                    text: app.outDir
                    onEditingFinished: app.outDir = text
                }
                Button { text: "浏览..."; onClicked: folderDlg.open() }
            }
        }

        RowLayout {
            Layout.margins: 8
            Layout.fillWidth: true
            Button {
                text: "开始"
                highlighted: true
                enabled: !app.running
                Layout.fillWidth: app.mobileUi
                onClicked: root.startRun()
            }
            Button {
                text: "停止"
                enabled: app.running
                Layout.fillWidth: app.mobileUi
                onClicked: app.stop()
            }
            Item { Layout.fillWidth: true; visible: !app.mobileUi }
            Button { text: "打开输出目录"; visible: !app.mobileUi; onClicked: app.openOutDir() }
            Button { text: "玩家数据"; visible: !app.mobileUi; onClicked: app.openPlayersDir() }
        }

        Label {
            visible: app.inAppWeb
            Layout.margins: 8
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            color: "#666"
            text: "跑谱时会切到「网页」页自动填表提交；出现人机验证时请在网页上点一下。"
                  + "跑的过程中请不要切到别的应用，中途被打断再点开始会自动续跑。"
        }
    }

    FolderDialog {
        id: folderDlg
        onAccepted: app.setOutDirUrl(selectedFolder.toString())
    }

    Dialog {
        id: forget
        property int idx: -1
        property string label: ""
        function ask(i, l) { idx = i; label = l; open() }
        title: "删除历史"
        modal: true
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Yes | Dialog.No
        Label { text: "从历史中删除「" + forget.label + "」？" }
        onAccepted: { identBox.popup.close(); app.forgetHistory(idx) }
    }
}
