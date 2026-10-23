import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.FormLayout {
    id: page
    twinFormLayouts: parentLayout

    property alias cfg_RainDensity: density.value
    property alias cfg_Wind: wind.value
    property alias cfg_Fps: fps.value
    property alias cfg_Brightness: brightness.value
    property alias cfg_Lightning: lightning.checked
    property alias cfg_Locale: locale.text
    property alias cfg_FontFamily: family.text
    // значения по умолчанию, которые подставляет Plasma
    property double cfg_RainDensityDefault: 1.0
    property double cfg_WindDefault: -0.10
    property int cfg_FpsDefault: 20
    property double cfg_BrightnessDefault: 1.0
    property bool cfg_LightningDefault: true
    property string cfg_LocaleDefault: "en_US"
    property string cfg_FontFamilyDefault: "monospace"

    QQC2.Slider { id: density;    Kirigami.FormData.label: "Rain density:"; from: 0.2; to: 2.0; stepSize: 0.1 }
    QQC2.Slider { id: wind;       Kirigami.FormData.label: "Wind:";         from: -1.0; to: 1.0; stepSize: 0.05 }
    QQC2.Slider { id: brightness; Kirigami.FormData.label: "Brightness:";   from: 0.4; to: 1.3; stepSize: 0.05 }
    QQC2.SpinBox { id: fps;       Kirigami.FormData.label: "Frame rate:";   from: 5; to: 60 }
    QQC2.CheckBox { id: lightning; Kirigami.FormData.label: "Effects:"; text: "Occasional lightning" }
    QQC2.TextField { id: locale;  Kirigami.FormData.label: "Board locale:"; placeholderText: "en_US, ru_RU, ka_GE" }
    QQC2.TextField { id: family;  Kirigami.FormData.label: "Font family:";  placeholderText: "monospace" }
}
