import QtQuick
import "../plugin/org.user.asciistreet/contents/ui/Sim.js" as SimLib
import "../plugin/org.user.asciistreet/contents/ui/scene.js" as Scene
Item {
    Component.onCompleted: {
        var ds = [0.01, 0.5, 1.0, 2.0];
        for (var q = 0; q < ds.length; q++) {
            var sim = new SimLib.Sim(Scene, { density: ds[q], wind: -0.1 });
            for (var w = 0; w < 40; w++) sim.step(0.05, w * 0.05);   // прогрев
            var t0 = Date.now(), n = 120;
            for (var i = 0; i < n; i++) sim.step(0.05, (i + 40) * 0.05);
            console.log("BENCH density " + ds[q] + ": " + ((Date.now() - t0) / n).toFixed(2) + " ms/step");
        }
        Qt.quit();
    }
}
