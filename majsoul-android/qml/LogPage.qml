import QtQuick
import QtQuick.Controls

ScrollView {
    id: root
    clip: true
    readonly property int maxChars: 300000

    function clear() { area.text = "" }
    function append(s) {
        var sb = root.ScrollBar.vertical
        var atEnd = !sb || sb.size >= 1 || sb.position + sb.size >= 0.98
        area.insert(area.length, s)
        if (area.length > maxChars * 1.2)   // 超长了一次砍掉前面一截, 别每次都砍
            area.remove(0, area.length - maxChars)
        if (atEnd)
            area.cursorPosition = area.length
    }

    TextArea {
        id: area
        readOnly: true
        selectByMouse: true
        wrapMode: app.mobileUi ? TextArea.WrapAnywhere : TextArea.NoWrap
        font.family: app.mobileUi ? "monospace" : "Consolas"
        font.pixelSize: app.mobileUi ? 12 : 13
        placeholderText: "点「开始」后这里显示进度"
    }
}
