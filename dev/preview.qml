import QtQuick
import QtQuick.Window
import "../plugin/org.user.asciistreet/contents/ui"

// Запуск без Plasma и без блокировки экрана:  qml6 dev/preview.qml
Window {
    width: 1920; height: 1080; visible: true; color: "black"
    title: "ASCII street preview"
    AsciiStreet { anchors.fill: parent }
}
