.pragma library
// Clock.js — содержимое табло остановки (stateless, поэтому pragma library).
//
// Три размера цифр — по свободной высоте табло:
//   >=5 строк: пиксельный шрифт 3x5, пиксель = "##" (2 столбца x 1 строка = квадрат в ячейках 1:2)
//   >=3 строк: сегментный 3x3
//   иначе:     обычный текст

var PX = {
    "0": ["###", "# #", "# #", "# #", "###"],
    "1": [" # ", "## ", " # ", " # ", "###"],
    "2": ["###", "  #", "###", "#  ", "###"],
    "3": ["###", "  #", "###", "  #", "###"],
    "4": ["# #", "# #", "###", "  #", "  #"],
    "5": ["###", "#  ", "###", "  #", "###"],
    "6": ["###", "#  ", "###", "# #", "###"],
    "7": ["###", "  #", "  #", "  #", "  #"],
    "8": ["###", "# #", "###", "# #", "###"],
    "9": ["###", "# #", "###", "  #", "###"]
};
var COLON_PX = ["  ", "##", "  ", "##", "  "];
var COLON_OFF = ["  ", "  ", "  ", "  ", "  "];

var SEG = {
    "0": [" _ ", "| |", "|_|"], "1": ["   ", "  |", "  |"], "2": [" _ ", " _|", "|_ "],
    "3": [" _ ", " _|", " _|"], "4": ["   ", "|_|", "  |"], "5": [" _ ", "|_ ", " _|"],
    "6": [" _ ", "|_ ", "|_|"], "7": [" _ ", "  |", "  |"], "8": [" _ ", "|_|", "|_|"],
    "9": [" _ ", "|_|", " _|"]
};

function pixelDigits(str, colonOn) {
    var rows = ["", "", "", "", ""];
    for (var i = 0; i < str.length; i++) {
        var c = str.charAt(i), cols;
        if (c === ":") cols = colonOn ? COLON_PX : COLON_OFF;
        else {
            var g = PX[c] || ["   ", "   ", "   ", "   ", "   "];
            cols = g.map(function (line) {
                var o = "";
                for (var k = 0; k < line.length; k++) o += line.charAt(k) === "#" ? "##" : "  ";
                return o;
            });
        }
        for (var r = 0; r < 5; r++) rows[r] += cols[r] + (i < str.length - 1 ? "  " : "");
    }
    return rows;
}

function segDigits(str, colonOn) {
    var rows = ["", "", ""];
    for (var i = 0; i < str.length; i++) {
        var c = str.charAt(i), g;
        if (c === ":") g = colonOn ? [" ", ".", "."] : [" ", " ", " "];
        else g = SEG[c] || ["   ", "   ", "   "];
        for (var r = 0; r < 3; r++) rows[r] += g[r] + (i < str.length - 1 ? " " : "");
    }
    return rows;
}

// Возвращает массив строк для времени под доступную высоту.
function timeLines(timeStr, colonOn, avail) {
    if (avail >= 5) return pixelDigits(timeStr, colonOn);
    if (avail >= 3) return segDigits(timeStr, colonOn);
    return [colonOn ? timeStr : timeStr.replace(":", " ")];
}
