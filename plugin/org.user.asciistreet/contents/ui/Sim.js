// Sim.js — симуляция дождя поверх сетки символов.
// НЕ .pragma library: у каждого экрана свой экземпляр и своё состояние.
//
// Слои (разреженные: хранятся только затронутые клетки, строка собирается только из них):
//   far    дальние капли: короткие, медленные, тусклые
//   near   ближние капли: длинные, быстрые, яркие
//   splash брызги на кромках (крыши, карнизы, лавка) + стекающие капли
//   water  круги на лужах + ручейки в водостоках
//   refl   мерцающие блики фонарей на мокрой дороге

var PIPE = 124, DOT = 46, COLON = 58, QUOTE = 39, O = 111, LP = 40, RP = 41,
    TILDE = 126, DASH = 45, BANG = 33, SLASH = 47, BSLASH = 92, SP = 32;
var REFL_CHARS = [PIPE, PIPE, PIPE, BANG, COLON, PIPE, SP];

var TBL = [];
for (var _c = 0; _c < 128; _c++) TBL.push(String.fromCharCode(_c));
function numCmp(a, b) { return a - b; }

function Sim(scene, opts) {
    var C = scene.cols, R = scene.rows, N = C * R;
    var density = opts.density, windBase = opts.wind;
    var rs = R / 67, cs = C / 240;        // масштаб относительно сетки, под которую подобраны скорости
    var surf = scene.surfaces, ground = scene.ground, gutters = scene.gutters, refl = scene.reflect;
    var drp = scene.drips || [], pud = scene.puddles || [], shel = scene.sheltered || [];
    var nSurf = surf.length / 2, nGr = ground.length / 2, nRefl = refl.length / 2;
    var nDrp = drp.length / 2, nPud = pud.length / 2;
    var SPACES = new Array(C + 1).join(" ");

    // --- индексы по столбцам: где в колонке есть "полки" и земля ---
    var surfByCol = [], groundTop = [], x, i;
    for (x = 0; x < C; x++) { surfByCol.push([]); groundTop.push(-1); }
    for (i = 0; i < nSurf; i++) surfByCol[surf[2 * i]].push(surf[2 * i + 1]);
    for (x = 0; x < C; x++) surfByCol[x].sort(numCmp);
    for (i = 0; i < nGr; i++) {
        var gx = ground[2 * i], gy = ground[2 * i + 1];
        if (groundTop[gx] < 0 || gy < groundTop[gx]) groundTop[gx] = gy;
    }

    // зона без дождя: табло стоит под крышей остановки (рамка + 1 клетка запаса)
    var blocked = new Array(N), bd = scene.board;
    for (i = 0; i < N; i++) blocked[i] = 0;
    for (i = 0; i < shel.length; i += 2) blocked[shel[i + 1] * C + shel[i]] = 1;   // зона под крышей из маски
    for (var by = bd.y - 1; by <= bd.y + bd.h; by++)
        for (var bx = bd.x - 1; bx <= bd.x + bd.w; bx++)
            if (bx >= 0 && bx < C && by >= 0 && by < R) blocked[by * C + bx] = 1;

    // --- разреженный слой: a[] — коды, rows[y] — какие x в строке заняты ---
    function mkLayer() {
        var a = new Array(N), rows = new Array(R), k;
        for (k = 0; k < N; k++) a[k] = SP;
        for (k = 0; k < R; k++) rows[k] = [];
        return { a: a, rows: rows };
    }
    function clearLayer(Ly) {
        var a = Ly.a, rows = Ly.rows;
        for (var y = 0; y < R; y++) {
            var xs = rows[y], base = y * C;
            for (var k = 0; k < xs.length; k++) a[base + xs[k]] = SP;
            xs.length = 0;
        }
    }
    function put(Ly, px, py, c) {
        px = Math.round(px);
        if (px >= 0 && px < C && py >= 0 && py < R && !blocked[py * C + px]) {
            Ly.a[py * C + px] = c;
            Ly.rows[py].push(px);
        }
    }
    function build(Ly, presorted) {
        var lines = new Array(R), a = Ly.a;
        for (var y = 0; y < R; y++) {
            var xs = Ly.rows[y], n = xs.length;
            if (n === 0) { lines[y] = ""; continue; }
            if (n > 1 && !presorted) xs.sort(numCmp);
            var s = "", prev = 0, last = -1, base = y * C;
            for (var k = 0; k < n; k++) {
                var px = xs[k];
                if (px === last) continue;
                last = px;
                s += (px > prev ? SPACES.substring(0, px - prev) : "") + TBL[a[base + px] & 127];
                prev = px + 1;
            }
            lines[y] = s;
        }
        return lines.join("\n");
    }

    var L = { far: mkLayer(), near: mkLayer(), splash: mkLayer(), water: mkLayer(), refl: mkLayer() };

    // --- капли ---
    var nNear = Math.round(C * 0.62 * density), nFar = Math.round(C * 1.5 * density);
    var drops = [];

    function spawn(d, near, initial) {
        var k;
        if ((Math.random() < 0.5 && nGr > 0) || nSurf === 0) {
            if (nPud > 0 && Math.random() < 0.45) {                      // лужи принимают больше капель
                k = Math.floor(Math.random() * nPud);
                d.tx = pud[2 * k]; d.ty = pud[2 * k + 1]; d.ground = true;
            } else if (nGr > 0) {
                k = Math.floor(Math.random() * nGr);
                d.tx = ground[2 * k]; d.ty = ground[2 * k + 1]; d.ground = true;
            } else {
                d.tx = Math.floor(Math.random() * C); d.ty = R - 1; d.ground = true;
            }
        } else {
            k = Math.floor(Math.random() * nSurf);
            d.tx = surf[2 * k]; d.ty = surf[2 * k + 1]; d.ground = false;
        }
        d.near = near;
        d.v = (near ? 42 + Math.random() * 28 : 20 + Math.random() * 14) * rs;   // строк/сек
        d.len = Math.max(1, Math.round((near ? 3 + Math.random() * 3 : 1 + Math.random() * 2) * rs));
        d.y = initial ? -d.len + Math.random() * (d.ty + d.len)
                      : -d.len - Math.random() * 12;
    }
    for (i = 0; i < nNear; i++) { var dn = {}; spawn(dn, true, true); drops.push(dn); }
    for (i = 0; i < nFar; i++) { var df = {}; spawn(df, false, true); drops.push(df); }

    // --- брызги / круги ---
    var splashes = [];
    function addSplash(sx, sy, isGround) {
        if (splashes.length > 700) return;
        splashes.push({ x: sx, y: sy, g: isGround, age: 0, life: isGround ? 0.5 : 0.3 });
    }

    // --- стекающие капли (с карнизов вниз, до следующей "полки" или земли) ---
    var drips = [], dripAcc = 0;
    function spawnDrip() {
        var k, src = surf;
        if (nDrp > 0 && Math.random() < 0.85) { k = Math.floor(Math.random() * nDrp); src = drp; }   // точки капели из маски
        else k = Math.floor(Math.random() * nSurf);
        var dx = src[2 * k], y0 = src[2 * k + 1] + 1, col = surfByCol[dx], ty = -1, g = false, real = true, j;
        for (j = 0; j < col.length; j++)
            if (col[j] > y0 + 1 && col[j] < y0 + 16) { ty = col[j]; break; }
        if (ty < 0 && groundTop[dx] >= y0 && groundTop[dx] - y0 < 30) { ty = groundTop[dx]; g = true; }
        if (ty < 0) { ty = y0 + 5; real = false; }
        drips.push({ x: dx, y: y0, v: 0, ty: ty, g: g, real: real });
    }

    var frame = 0;

    function step(dt, t) {
        frame++;
        var wind = windBase + 0.06 * Math.sin(t * 0.35);           // лёгкие порывы
        var rainCh = wind > 0.5 ? BSLASH : (wind < -0.5 ? SLASH : PIPE);
        clearLayer(L.far); clearLayer(L.near); clearLayer(L.splash); clearLayer(L.water);

        // капли
        for (var n = 0; n < drops.length; n++) {
            var d = drops[n];
            d.y += d.v * dt;
            if (d.y >= d.ty) {
                if (Math.random() < (d.near ? 0.9 : 0.2)) addSplash(d.tx, d.ty, d.ground);
                spawn(d, d.near, false);
                continue;
            }
            var arr = d.near ? L.near : L.far, hy = Math.floor(d.y);
            for (var k = 0; k < d.len; k++) {
                var yy = hy - k;
                if (yy < 0) break;
                if (yy > d.ty) continue;
                put(arr, d.tx + wind * (yy - d.ty), yy, rainCh);
            }
        }

        // брызги
        for (n = splashes.length - 1; n >= 0; n--) {
            var s = splashes[n];
            s.age += dt;
            if (s.age >= s.life) { splashes[n] = splashes[splashes.length - 1]; splashes.pop(); continue; }
            var f = s.age / s.life;
            if (s.g) {                                  // круги на воде; ближе к зрителю — шире
                var stages = s.y > R * 0.9 ? 4 : (s.y > R * 0.82 ? 3 : 2);
                var st = Math.min(stages - 1, Math.floor(f * stages));
                if (st === 0) put(L.water, s.x, s.y, DOT);
                else if (st === 1) put(L.water, s.x, s.y, O);
                else { put(L.water, s.x - (st - 1), s.y, LP); put(L.water, s.x + (st - 1), s.y, RP); }
            } else {                                    // брызги на кромке
                var sk = Math.min(2, Math.floor(f * 3));
                if (sk === 0) put(L.splash, s.x, s.y - 1, QUOTE);
                else if (sk === 1) { put(L.splash, s.x - 1, s.y - 1, QUOTE); put(L.splash, s.x + 1, s.y - 1, QUOTE); }
                else { put(L.splash, s.x - 1, s.y, DOT); put(L.splash, s.x + 1, s.y, DOT); }
            }
        }

        // стекающие капли
        if (nSurf > 0 || nDrp > 0) {
            dripAcc += dt * 26 * cs * density;
            while (dripAcc >= 1) { dripAcc -= 1; if (drips.length < 140) spawnDrip(); }
        }
        for (n = drips.length - 1; n >= 0; n--) {
            var p = drips[n];
            p.v += 55 * rs * dt;
            p.y += p.v * dt;
            if (p.y >= p.ty) {
                if (p.real) addSplash(p.x, p.ty, p.g);
                drips[n] = drips[drips.length - 1]; drips.pop();
                continue;
            }
            put(L.splash, p.x, Math.floor(p.y), p.v > 20 * rs ? COLON : DOT);
        }

        // ручьи: бегущий узор вдоль координаты s (из маски water.flow). s растёт по течению и уже
        // учитывает перспективу, поэтому вдали узор мельче и медленнее, а вблизи крупнее и быстрее.
        var phase = t * 11 * cs;
        for (var g = 0; g < gutters.length; g++) {
            var gt = gutters[g], cnt = gt.length / 3;
            for (i = 0; i < cnt; i++) {
                var j = ((Math.floor(gt[3 * i + 2] / 10 - phase) % 8) + 8) % 8;
                if (j < 3) put(L.water, gt[3 * i], gt[3 * i + 1], TILDE);
                else if (j === 5) put(L.water, gt[3 * i], gt[3 * i + 1], DASH);
            }
        }

        // блики на дороге (8 Гц хватает); клетки в refl уже идут по строкам слева направо
        var reflStr;
        if (frame % 3 === 0 && nRefl > 0) {
            clearLayer(L.refl);
            var tick = Math.floor(t * 6);
            for (i = 0; i < nRefl; i++) {
                var rx = refl[2 * i], ry = refl[2 * i + 1];
                var h = ((rx * 73856093) ^ (ry * 19349663) ^ (tick * 83492791)) >>> 0;
                put(L.refl, rx, ry, REFL_CHARS[h % 7]);
            }
            reflStr = build(L.refl, true);
        }

        return { far: build(L.far, false), near: build(L.near, false), splash: build(L.splash, false),
                 water: build(L.water, false), refl: reflStr };
    }

    return { step: step };
}
