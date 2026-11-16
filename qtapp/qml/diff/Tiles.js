.pragma library

// 精灵图列顺序 (与 diff_report.SPRITE_TILES 一致): 1-9m 1-9p 1-9s 5mr 5pr 5sr 东南西北白发中
var NAMES = (function () {
    var a = []
    ;["m", "p", "s"].forEach(function (s) { for (var n = 1; n <= 9; n++) a.push(n + s) })
    a.push("5mr", "5pr", "5sr")
    ;["e", "s", "w", "n", "p", "f", "c"].forEach(function (h) { a.push(h) })
    return a
})()

function col(pai) {
    var i = NAMES.indexOf(String(pai).toLowerCase())
    return i < 0 ? 0 : i
}

var WINDS = ["东", "南", "西", "北"]
