import QtQuick

// Один слой сетки символов. Параметры метрик берёт у элемента-сетки `g`.
Text {
    required property Item g

    width: g.width
    height: g.height
    wrapMode: Text.NoWrap
    textFormat: Text.PlainText
    renderType: Text.NativeRendering
    lineHeightMode: Text.FixedHeight
    lineHeight: g.cellH
    font.family: g.family
    font.pixelSize: g.fontPx
    font.letterSpacing: g.spacing
    font.kerning: false
}
