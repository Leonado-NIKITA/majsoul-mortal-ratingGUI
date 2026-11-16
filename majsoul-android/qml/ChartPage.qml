import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebView

// 结果图: PNG 用 Image 显示 (可缩放拖动); 没有 matplotlib 时是网页版图, 用 WebView
Item {
    id: root
    readonly property bool isHtml: app.chartUrl.indexOf("http") === 0

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 6
            visible: app.chartUrl !== "" && !root.isHtml
            Button { text: "适应窗口"; onClicked: flick.fit() }
            Button { text: "100%"; onClicked: flick.zoomTo(1) }
            Item { Layout.fillWidth: true }
            Button {
                text: app.mobileUi ? "分享/打开" : "用系统查看器打开"
                onClicked: app.openChartExternally()
            }
        }

        Label {
            visible: app.chartUrl === ""
            Layout.fillWidth: true
            Layout.fillHeight: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            text: "跑完后在这里显示图表"
            color: "#888"
        }

        Flickable {
            id: flick
            visible: app.chartUrl !== "" && !root.isHtml
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: img.width
            contentHeight: img.height
            boundsBehavior: Flickable.StopAtBounds
            property real fitScale: img.implicitWidth > 0
                ? Math.min(width / img.implicitWidth, height / img.implicitHeight) : 1
            property real zoom: fitScale
            property bool fitted: true
            function fit() { fitted = true; zoom = fitScale; contentX = 0; contentY = 0 }
            function zoomTo(z) { fitted = false; zoom = Math.max(fitScale * 0.5, Math.min(z, 4)) }
            onFitScaleChanged: if (fitted) zoom = fitScale

            Image {
                id: img
                source: root.isHtml ? "" : app.chartUrl
                asynchronous: true
                cache: false
                smooth: true
                mipmap: true
                width: implicitWidth * flick.zoom
                height: implicitHeight * flick.zoom
                onStatusChanged: if (status === Image.Ready) flick.fit()
            }

            PinchHandler {
                target: null
                property real startZoom: 1
                onActiveChanged: if (active) startZoom = flick.zoom
                onActiveScaleChanged: flick.zoomTo(startZoom * activeScale)
            }
            WheelHandler {
                acceptedModifiers: Qt.ControlModifier
                onWheel: function (ev) { flick.zoomTo(flick.zoom * (ev.angleDelta.y > 0 ? 1.15 : 1 / 1.15)) }
            }
            TapHandler {
                onDoubleTapped: flick.fitted ? flick.zoomTo(1) : flick.fit()
            }
            ScrollBar.vertical: ScrollBar {}
            ScrollBar.horizontal: ScrollBar {}
        }

        Loader {
            active: root.isHtml
            visible: active
            Layout.fillWidth: true
            Layout.fillHeight: true
            sourceComponent: WebView { url: app.chartUrl }
        }
    }
}
