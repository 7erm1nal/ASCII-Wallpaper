import QtQuick
import org.kde.plasma.plasmoid

// Тонкая обёртка для Plasma 6: вся логика — в AsciiStreet.qml
WallpaperItem {
    id: wallpaper

    function cfg(name, def) {
        var v = wallpaper.configuration[name];
        return v === undefined ? def : v;
    }

    AsciiStreet {
        anchors.fill: parent
        running: wallpaper.visible
        rainDensity: wallpaper.cfg("RainDensity", 1.0)
        wind: wallpaper.cfg("Wind", -0.10)
        fps: wallpaper.cfg("Fps", 20)
        brightness: wallpaper.cfg("Brightness", 1.0)
        lightning: wallpaper.cfg("Lightning", true)
        localeName: wallpaper.cfg("Locale", "en_US")
        fontFamily: wallpaper.cfg("FontFamily", "monospace")
    }
}
