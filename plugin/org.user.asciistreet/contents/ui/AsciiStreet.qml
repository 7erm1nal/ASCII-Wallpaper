import QtQuick
import "Sim.js" as SimLib
import "Clock.js" as ClockLib
import "scene.js" as Scene

// Чистая Qt Quick сцена — без импортов Plasma, поэтому запускается и отдельно:
//   qml6 dev/preview.qml
Item {
    id: root

    // --- настройки (main.qml пробрасывает их из конфигурации обоев) ---
    property real rainDensity: 1.0
    property real wind: -0.10
    property int fps: 20
    property real brightness: 1.0
    property bool lightning: true
    property string localeName: "en_US"
    property string fontFamily: "monospace"
    property bool running: true
    property var fakeNow: null          // для тестов: фиксированное время вместо текущего

    clip: true

    // Сетка держится на моноширинном шрифте. "monospace" не везде резолвится в настоящий моноширинный,
    // поэтому выбираем первый установленный из проверенных (или тот, что задан в настройках).
    readonly property var monoCandidates: ["DejaVu Sans Mono", "Noto Sans Mono", "JetBrains Mono", "Hack",
                                           "Liberation Mono", "Ubuntu Mono", "Fira Mono", "Source Code Pro"]
    readonly property string resolvedFont: {
        var fams = Qt.fontFamilies();
        if (fontFamily !== "" && fontFamily !== "monospace" && fams.indexOf(fontFamily) >= 0)
            return fontFamily;
        for (var i = 0; i < monoCandidates.length; i++)
            if (fams.indexOf(monoCandidates[i]) >= 0) return monoCandidates[i];
        return "monospace";
    }

    // ячейка 1:2, сцена масштабируется "cover" (лишнее обрезается по краям)
    readonly property real cellW: Math.max(width / Scene.cols, height / (Scene.rows * 2))
    readonly property real cellH: cellW * 2

    property real flash: 0          // вспышка молнии 0..1
    property real lampLevel: 1
    property real glowLevel: 1
    property real t: 0
    property double lastMs: 0
    property var sim: null

    function rebuildSim() {
        sim = new SimLib.Sim(Scene, { density: rainDensity, wind: wind });
    }
    onRainDensityChanged: if (sim) rebuildSim()
    onWindChanged: if (sim) rebuildSim()

    Component.onCompleted: { rebuildSim(); updateClock(); tick(); }

    // ---------- кадр ----------
    function tick() {
        if (!sim) return;
        var now = Date.now();
        var dt = lastMs ? Math.min((now - lastMs) / 1000, 0.1) : 0.05;
        lastMs = now;
        t += dt;
        var s = sim.step(dt, t);
        farL.text = s.far;
        nearL.text = s.near;
        splashL.text = s.splash;
        waterL.text = s.water;
        if (s.refl !== undefined) reflL.text = s.refl;
    }

    // ---------- табло ----------
    function updateClock() {
        var d = root.fakeNow ? root.fakeNow : new Date();
        var qtDay = d.getDay() === 0 ? 7 : d.getDay();
        var dayName = Qt.locale(localeName).dayName(qtDay, Locale.LongFormat);
        var inner = Scene.board.h - 2;
        var innerW = Scene.board.w - 2;
        var dateLine = dayName + " " + Qt.formatDate(d, "dd.MM.yyyy");
        var lines = ClockLib.timeLines(Qt.formatTime(d, "HH:mm"), d.getSeconds() % 2 === 0, inner - 1);
        // Text.AlignHCenter не учитывает хвостовые пробелы строки, из-за чего ряды цифр "съезжали".
        // Поэтому выравниваем строки до одной ширины и центрируем сами: левое выравнивание + отступ в клетках.
        var tw = 0, i;
        for (i = 0; i < lines.length; i++) tw = Math.max(tw, lines[i].length);
        for (i = 0; i < lines.length; i++) while (lines[i].length < tw) lines[i] += " ";
        dateT.text = dateLine;
        dateT.colOffset = Math.max(0, Math.floor((innerW - dateLine.length) / 2));
        timeT.text = lines.join("\n");
        timeT.colOffset = Math.max(0, Math.floor((innerW - tw) / 2));
        timeT.rowOffset = 1 + Math.floor((inner - 1 - lines.length) / 2);
        timeT.rows = lines.length;
    }

    onRunningChanged: if (running) { lastMs = 0; updateClock(); }

    Timer {
        interval: Math.round(1000 / Math.max(5, root.fps))
        repeat: true
        running: root.running && root.visible
        onTriggered: root.tick()
    }
    Timer {
        interval: 500
        repeat: true
        running: root.running && root.visible
        onTriggered: root.updateClock()
    }
    // мерцание фонарей и дыхание ореолов
    Timer {
        interval: 110
        repeat: true
        running: root.running && root.visible
        onTriggered: {
            var r = Math.random();
            root.lampLevel = r < 0.03 ? 0.45 : 0.86 + Math.random() * 0.14;
            root.glowLevel = 0.8 + 0.2 * Math.sin(root.t * 1.3) + (Math.random() - 0.5) * 0.1;
        }
    }
    // редкие молнии: общая вспышка неба
    Timer {
        id: lightningTimer
        interval: 30000
        repeat: true
        running: root.running && root.visible && root.lightning
        onTriggered: { interval = 20000 + Math.random() * 45000; flashAnim.restart(); }
    }
    SequentialAnimation {
        id: flashAnim
        NumberAnimation { target: root; property: "flash"; to: 1.0; duration: 60 }
        NumberAnimation { target: root; property: "flash"; to: 0.2; duration: 90 }
        NumberAnimation { target: root; property: "flash"; to: 0.9; duration: 50 }
        NumberAnimation { target: root; property: "flash"; to: 0.0; duration: 600; easing.type: Easing.OutQuad }
    }

    // ---------- визуал ----------
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {                       // не чистый чёрный: ночное небо чуть светлее низа
            GradientStop { position: 0.0; color: "#0d1119" }
            GradientStop { position: 1.0; color: "#07090e" }
        }
    }
    Rectangle {
        anchors.fill: parent
        opacity: root.flash * 0.28
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#a9c2e6" }
            GradientStop { position: 1.0; color: "#243044" }
        }
    }

    TextMetrics {
        id: tm
        text: "M"
        font.family: root.resolvedFont
        font.pixelSize: Math.max(5, Math.round(root.cellW / 0.6))
        font.kerning: false
    }

    Item {
        id: grid
        width: Scene.cols * root.cellW
        height: Scene.rows * root.cellH
        x: (root.width - width) / 2
        y: (root.height - height) / 2

        readonly property real cellH: root.cellH
        readonly property string family: root.resolvedFont
        readonly property int fontPx: tm.font.pixelSize
        readonly property real spacing: root.cellW - tm.advanceWidth

        // тёплая подложка-отсвет от фонарей (генерируется конвертером из lamp.glow), мерцает вместе с ним
        Image {
            anchors.fill: parent
            source: "spill.png"
            smooth: true
            opacity: Math.min(1, root.glowLevel * 0.9 * root.brightness)
        }

        // статические слои (считаются один раз генератором)
        Repeater {
            model: Scene.layers
            GridText {
                required property var modelData
                g: grid
                text: modelData.text
                color: modelData.color
                // слои с motion (туман) медленно "дышат" по горизонтали
                SequentialAnimation on x {
                    running: modelData.motion !== undefined && root.running && root.visible
                    loops: Animation.Infinite
                    NumberAnimation {
                        from: -(modelData.motion ? modelData.motion.dx : 0) * root.cellW
                        to: (modelData.motion ? modelData.motion.dx : 0) * root.cellW
                        duration: (modelData.motion ? modelData.motion.period : 2000) / 2
                        easing.type: Easing.InOutSine
                    }
                    NumberAnimation {
                        from: (modelData.motion ? modelData.motion.dx : 0) * root.cellW
                        to: -(modelData.motion ? modelData.motion.dx : 0) * root.cellW
                        duration: (modelData.motion ? modelData.motion.period : 2000) / 2
                        easing.type: Easing.InOutSine
                    }
                }
                opacity: Math.min(1, modelData.opacity * root.brightness *
                         (modelData.name === "lamps" ? root.lampLevel :
                          modelData.name === "glow" ? root.glowLevel : 0.9))
            }
        }

        // подложка табло + живой текст
        Rectangle {
            x: (Scene.board.x + 1) * root.cellW
            y: (Scene.board.y + 1) * root.cellH
            width: (Scene.board.w - 2) * root.cellW
            height: (Scene.board.h - 2) * root.cellH
            color: "#1b1205"
            opacity: 0.8
        }
        GridText {
            id: dateT
            property int colOffset: 0
            g: grid
            x: (Scene.board.x + 1 + colOffset) * root.cellW
            y: (Scene.board.y + 1) * root.cellH
            width: (Scene.board.w - 2 - colOffset) * root.cellW
            height: root.cellH
            horizontalAlignment: Text.AlignLeft
            color: "#d9983f"
        }
        GridText {
            id: timeT
            property int rowOffset: 2
            property int rows: 5
            property int colOffset: 0
            g: grid
            x: (Scene.board.x + 1 + colOffset) * root.cellW
            y: (Scene.board.y + 1 + rowOffset) * root.cellH
            width: (Scene.board.w - 2 - colOffset) * root.cellW
            height: rows * root.cellH
            horizontalAlignment: Text.AlignLeft
            color: "#ffc45c"
        }

        // динамические слои дождя
        GridText { id: reflL;   g: grid; color: "#d98a38"; opacity: 0.8 }
        GridText { id: farL;    g: grid; color: "#42546f"; opacity: Math.min(1, 0.85 + root.flash) }
        GridText { id: waterL;  g: grid; color: "#6aa4c6"; opacity: 0.9 }
        GridText { id: nearL;   g: grid; color: "#a8c3e6"; opacity: 0.9 }
        GridText { id: splashL; g: grid; color: "#d4e6ff" }
    }
}
