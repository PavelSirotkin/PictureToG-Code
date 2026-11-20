/**
 * ImageProcessor — Обработка изображений
 *
 * Улучшения контурного режима:
 * 1. Marching Squares с суб-пиксельной интерполяцией границы
 * 2. Правильный порядок: Chaikin-сглаживание ПЕРЕД RDP-прореживанием
 * 3. Равномерный ре-сэмплинг по длине дуги как альтернатива RDP
 */

class ImageProcessor {
    constructor() {
        this.originalImage = null;
        this.grayscaleData = null;
        this.width = 0;
        this.height = 0;
    }

    loadImage(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => {
                const img = new Image();
                img.onload = () => {
                    this.originalImage = img;
                    this.width = img.width;
                    this.height = img.height;
                    const canvas = document.createElement('canvas');
                    canvas.width = this.width; canvas.height = this.height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0);
                    const imageData = ctx.getImageData(0, 0, this.width, this.height);
                    this.grayscaleData = this._toGrayscale(imageData);
                    resolve({ imageData, width: this.width, height: this.height });
                };
                img.onerror = () => reject(new Error('Не удалось загрузить изображение'));
                img.src = e.target.result;
            };
            reader.onerror = () => reject(new Error('Не удалось прочитать файл'));
            reader.readAsDataURL(file);
        });
    }

    _toGrayscale(imageData) {
        const data = imageData.data;
        const gray = new Uint8Array(data.length / 4);
        for (let i = 0; i < data.length; i += 4)
            gray[i / 4] = Math.round(0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]);
        return gray;
    }

    gaussianBlur(data, width, height, kernelSize) {
        if (kernelSize <= 0) return new Uint8Array(data);
        if (kernelSize % 2 === 0) kernelSize++;
        const sigma = kernelSize / 3.0;
        const kernel = this._gaussianKernel1D(kernelSize, sigma);
        const half = Math.floor(kernelSize / 2);
        const temp = new Uint8Array(data.length);
        const result = new Uint8Array(data.length);
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                let sum = 0, wsum = 0;
                for (let k = -half; k <= half; k++) {
                    const sx = Math.min(Math.max(x + k, 0), width - 1);
                    const w = kernel[k + half];
                    sum += data[y * width + sx] * w; wsum += w;
                }
                temp[y * width + x] = Math.round(sum / wsum);
            }
        }
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                let sum = 0, wsum = 0;
                for (let k = -half; k <= half; k++) {
                    const sy = Math.min(Math.max(y + k, 0), height - 1);
                    const w = kernel[k + half];
                    sum += temp[sy * width + x] * w; wsum += w;
                }
                result[y * width + x] = Math.round(sum / wsum);
            }
        }
        return result;
    }

    _gaussianKernel1D(size, sigma) {
        const kernel = new Float32Array(size);
        const half = Math.floor(size / 2);
        let sum = 0;
        for (let i = 0; i < size; i++) {
            const x = i - half;
            kernel[i] = Math.exp(-(x * x) / (2 * sigma * sigma));
            sum += kernel[i];
        }
        for (let i = 0; i < size; i++) kernel[i] /= sum;
        return kernel;
    }

    threshold(data, threshold, invert) {
        const result = new Uint8Array(data.length);
        for (let i = 0; i < data.length; i++) {
            let val = data[i] >= threshold ? 255 : 0;
            if (invert) val = 255 - val;
            result[i] = val;
        }
        return result;
    }

    /**
     * Извлечение контуров.
     *
     * Конвейер:
     *   1. Marching Squares с суб-пиксельной интерполяцией
     *   2. Сборка контуров
     *   3. Фильтрация по площади
     *   4. Chaikin-сглаживание (smoothPasses проходов)
     *   5a. Равномерный ре-сэмплинг (если resampleStep > 0)  ← рекомендуется
     *   5b. RDP-прореживание (если epsilonFactor > 0)
     *
     * @param {Uint8Array} binaryData
     * @param {number} width
     * @param {number} height
     * @param {number} minArea        — мин. площадь контура (пикс²)
     * @param {number} epsilonFactor  — RDP: epsilon = factor × периметр (0 = выкл.)
     * @param {number} smoothPasses   — проходов Chaikin (0 = выкл., рек. 3-4)
     * @param {number} resampleStep   — шаг точек в пикс. (0 = выкл.; если задан — заменяет RDP)
     */
    extractContours(binaryData, width, height,
                    minArea = 10, epsilonFactor = 0.001,
                    smoothPasses = 3, resampleStep = 0) {
        return this._marchingSquares(
            binaryData, width, height,
            minArea, epsilonFactor, smoothPasses, resampleStep
        );
    }

    // ─── Marching Squares ────────────────────────────────────────────────────

    /**
     * Marching Squares с линейной суб-пиксельной интерполяцией.
     *
     * Стандартный MS ставит точку ровно на середине ребра (0.5px).
     * Улучшение: для бинарного изображения граница всё равно посередине,
     * но при использовании с предварительным размытием (blurSize > 0)
     * интерполяция даёт более точное положение изолинии.
     *
     *   t = (127 - val_A) / (val_B - val_A)
     *   точка = A + t * (B - A)
     */
    _marchingSquares(binary, width, height, minArea, epsilonFactor, smoothPasses, resampleStep) {
        const segments = [];

        const lerp = (v0, v1, x0, x1) => {
            if (Math.abs(v1 - v0) < 1) return (x0 + x1) / 2;
            const t = (127 - v0) / (v1 - v0);
            return x0 + Math.max(0, Math.min(1, t)) * (x1 - x0);
        };

        for (let y = 0; y < height - 1; y++) {
            for (let x = 0; x < width - 1; x++) {
                const v00 = binary[y * width + x];
                const v10 = binary[y * width + (x + 1)];
                const v01 = binary[(y + 1) * width + x];
                const v11 = binary[(y + 1) * width + (x + 1)];

                let ci = 0;
                if (v00 > 127) ci |= 1;
                if (v10 > 127) ci |= 2;
                if (v11 > 127) ci |= 4;
                if (v01 > 127) ci |= 8;
                if (ci === 0 || ci === 15) continue;

                // Суб-пиксельные координаты точек на рёбрах
                // Формат ключа: "X.XXX,Y.YYY" — используем точку как разделитель
                const top   = `${lerp(v00, v10, x, x+1).toFixed(3)}_${y.toFixed(3)}`;
                const bot   = `${lerp(v01, v11, x, x+1).toFixed(3)}_${(y+1).toFixed(3)}`;
                const left  = `${x.toFixed(3)}_${lerp(v00, v01, y, y+1).toFixed(3)}`;
                const right = `${(x+1).toFixed(3)}_${lerp(v10, v11, y, y+1).toFixed(3)}`;

                const pts = [];
                if (this._edgeCrossed(ci, 0)) pts.push(left);
                if (this._edgeCrossed(ci, 1)) pts.push(top);
                if (this._edgeCrossed(ci, 2)) pts.push(right);
                if (this._edgeCrossed(ci, 3)) pts.push(bot);

                for (let k = 0; k + 1 < pts.length; k += 2)
                    segments.push([pts[k], pts[k + 1]]);
            }
        }

        const contours = this._assembleContours(segments);
        const result = [];

        for (const chain of contours) {
            if (chain.length < 3) continue;
            if (this._polygonArea(chain) < minArea) continue;

            let pts = chain;

            // ── 1. Chaikin ПЕРЕД прореживанием ──────────────────────────
            // Сначала сглаживаем исходную плотную пиксельную сетку.
            // Это правильно: сглаживаем фактическую форму, а не уже упрощённую.
            if (smoothPasses > 0) {
                pts = this._chaikinSmooth(pts, smoothPasses, true);
            }

            // ── 2. Прореживание ──────────────────────────────────────────
            if (resampleStep > 0) {
                // Равномерный ре-сэмплинг: все точки через resampleStep пикс.
                // Плотность G1 одинакова по всему контуру.
                pts = this._resampleByLength(pts, resampleStep, true);
            } else if (epsilonFactor > 0) {
                // RDP: убирает лишние точки на почти-прямолинейных участках
                const perim = this._chainPerimeter(pts);
                pts = this._ramerDouglasPeucker(pts, epsilonFactor * perim);
            }

            if (pts.length < 3) continue;

            // ── 3. Перевод Y и замыкание ─────────────────────────────────
            const flipped = pts.map(([px, py]) => [px, height - py]);
            if (Math.abs(flipped[0][0] - flipped[flipped.length - 1][0]) > 0.001 ||
                Math.abs(flipped[0][1] - flipped[flipped.length - 1][1]) > 0.001) {
                flipped.push([...flipped[0]]);
            }

            result.push(flipped);
        }

        return result;
    }

    // ─── Chaikin ─────────────────────────────────────────────────────────────

    /**
     * Алгоритм Chaikin — итеративное срезание углов.
     * Каждый проход: Q = ¾·P[i] + ¼·P[i+1],  R = ¼·P[i] + ¾·P[i+1]
     * Сходится к B-сплайну 2-го порядка.
     *
     * Рекомендации:
     *   1–2 прохода — лёгкое сглаживание, форма почти не меняется
     *   3–4 прохода — хороший результат для большинства изображений
     *   5–6 проходов — очень гладко, мелкие детали округляются
     */
    _chaikinSmooth(pts, passes, closed = true) {
        let p = [...pts];
        // Убираем явное замыкание перед обработкой
        if (closed && p.length > 1) {
            const f = p[0], l = p[p.length - 1];
            if (Math.abs(f[0] - l[0]) < 0.001 && Math.abs(f[1] - l[1]) < 0.001)
                p = p.slice(0, -1);
        }
        for (let i = 0; i < passes; i++) {
            const n = p.length;
            if (n < 2) break;
            const next = [];
            if (closed) {
                for (let j = 0; j < n; j++) {
                    const a = p[j], b = p[(j + 1) % n];
                    next.push([0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]]);
                    next.push([0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]]);
                }
            } else {
                // Открытая полилиния: концы остаются неподвижными
                next.push([...p[0]]);
                for (let j = 0; j < n - 1; j++) {
                    const a = p[j], b = p[j + 1];
                    next.push([0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]]);
                    next.push([0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]]);
                }
                next.push([...p[n - 1]]);
            }
            p = next;
        }
        if (closed) p.push([...p[0]]);
        return p;
    }

    // ─── Равномерный ре-сэмплинг ─────────────────────────────────────────────

    /**
     * Расставляет точки вдоль контура с равным шагом stepLen (пикс.).
     *
     * Преимущество перед RDP: плотность точек (и G1-сегментов) одинакова
     * везде — на прямых и на кривых. RDP оставляет много точек только там
     * где есть изломы, пропуская детали кривых.
     *
     * Практический выбор stepLen: 0.5–1.5 пикс. для хорошего разрешения.
     * В мм: stepLen × (outputMM / imagePX).
     */
    _resampleByLength(pts, stepLen, closed = true) {
        if (pts.length < 2 || stepLen <= 0) return pts;

        let src = [...pts];
        if (closed && src.length > 1) {
            const f = src[0], l = src[src.length - 1];
            if (Math.abs(f[0] - l[0]) < 0.001 && Math.abs(f[1] - l[1]) < 0.001)
                src = src.slice(0, -1);
        }
        if (closed) src.push([...src[0]]);

        const result = [[...src[0]]];
        let acc = 0; // накопленное расстояние с последней поставленной точки

        for (let i = 1; i < src.length; i++) {
            const dx = src[i][0] - src[i - 1][0];
            const dy = src[i][1] - src[i - 1][1];
            const segLen = Math.hypot(dx, dy);
            if (segLen < 1e-9) continue;

            let traveled = 0;
            while (acc + (segLen - traveled) >= stepLen) {
                const move = stepLen - acc;
                traveled += move;
                const t = traveled / segLen;
                result.push([src[i - 1][0] + t * dx, src[i - 1][1] + t * dy]);
                acc = 0;
            }
            acc += segLen - traveled;
        }

        if (closed) {
            result.push([...result[0]]);
        } else {
            // Для открытой полилинии гарантируем сохранение конечной точки
            const last = src[src.length - 1];
            const r = result[result.length - 1];
            if (Math.hypot(last[0] - r[0], last[1] - r[1]) > 1e-6) {
                result.push([...last]);
            }
        }
        return result;
    }

    // ─── Вспомогательные ─────────────────────────────────────────────────────

    _edgeCrossed(ci, edge) {
        const pairs = [[0, 3], [0, 1], [1, 2], [2, 3]];
        const [a, b] = pairs[edge];
        return ((ci >> a) & 1) !== ((ci >> b) & 1);
    }

    _assembleContours(segments) {
        const adj = new Map();
        for (const [a, b] of segments) {
            if (!adj.has(a)) adj.set(a, []);
            if (!adj.has(b)) adj.set(b, []);
            adj.get(a).push(b);
            adj.get(b).push(a);
        }

        const contours = [];
        const used = new Set();

        for (const [startKey, nbrs] of adj) {
            if (used.has(startKey) || nbrs.length < 2) continue;

            const contour = [];
            let cur = startKey, prev = null;
            while (cur) {
                used.add(cur);
                const parts = cur.split('_');
                contour.push([parseFloat(parts[0]), parseFloat(parts[1])]);
                const neighbors = adj.get(cur) || [];
                let nxt = null;
                for (const n of neighbors) {
                    if (n !== prev && !used.has(n)) { nxt = n; break; }
                }
                if (!nxt) break;
                prev = cur; cur = nxt;
            }
            if (contour.length >= 3) contours.push(contour);
        }
        return contours;
    }

    _polygonArea(points) {
        let area = 0;
        const n = points.length;
        for (let i = 0; i < n; i++) {
            const j = (i + 1) % n;
            area += points[i][0] * points[j][1] - points[j][0] * points[i][1];
        }
        return Math.abs(area) / 2;
    }

    _chainPerimeter(points) {
        let total = 0;
        for (let i = 0; i < points.length - 1; i++)
            total += Math.hypot(points[i+1][0] - points[i][0], points[i+1][1] - points[i][1]);
        return total;
    }

    _ramerDouglasPeucker(points, epsilon) {
        if (points.length < 3) return points;
        let maxD = 0, maxI = 0;
        const s = points[0], e = points[points.length - 1];
        const dx = e[0] - s[0], dy = e[1] - s[1];
        const len2 = dx * dx + dy * dy;
        for (let i = 1; i < points.length - 1; i++) {
            const px = points[i][0] - s[0], py = points[i][1] - s[1];
            let d;
            if (len2 < 1e-12) {
                d = Math.hypot(px, py);
            } else {
                const t = Math.max(0, Math.min(1, (px * dx + py * dy) / len2));
                d = Math.hypot(px - t * dx, py - t * dy);
            }
            if (d > maxD) { maxD = d; maxI = i; }
        }
        if (maxD > epsilon) {
            const L = this._ramerDouglasPeucker(points.slice(0, maxI + 1), epsilon);
            const R = this._ramerDouglasPeucker(points.slice(maxI), epsilon);
            return [...L.slice(0, -1), ...R];
        }
        return [s, e];
    }

    // ─── Средняя линия (скелет / медиальная ось) ─────────────────────────────

    /**
     * Извлекает «среднюю линию» фигур — скелет бинарного изображения.
     *
     * В отличие от extractContours (обводка фигуры снаружи), здесь
     * генерируется одиночная линия по центру штриха. Подходит для
     * гравировки рукописного/каллиграфического текста, где толстый штрих
     * нужно пройти фрезой один раз посередине.
     *
     * Конвейер:
     *   1. Утончение Чжана-Суэня → скелет толщиной 1 пиксель
     *   2. Трассировка скелета в сегменты (между узлами)
     *   3. Сшивка сегментов в длинные непрерывные линии по углу продолжения
     *   4. Отсев коротких отростков (шумовых веточек)
     *   5. Chaikin-сглаживание + равномерный ре-сэмплинг (открытые линии)
     *
     * @param {Uint8Array} binaryData  — бинарное изображение (255 = фигура)
     * @param {number} width
     * @param {number} height
     * @param {number} smoothPasses    — проходов Chaikin (0 = выкл.)
     * @param {number} resampleStep    — шаг точек в пикс. (0 = выкл.)
     * @param {number} minBranchLen    — мин. длина линии в пикс. (отсев отростков)
     * @returns {Array<Array<[number, number]>>}  открытые полилинии, Y уже перевёрнут
     */
    extractCenterlines(binaryData, width, height,
                       smoothPasses = 3, resampleStep = 0, minBranchLen = 8) {
        const skeleton = this._zhangSuenThinning(binaryData, width, height);
        // Утончение Чжана-Суэня оставляет диагональные «лесенки» шириной 2 px.
        // В графе пикселей это даёт массу ложных узлов, дробящих линию.
        // Чистка схлопывает такие участки до настоящей ширины 1 px.
        this._cleanSkeleton(skeleton, width, height);
        // Убираем короткие «заусенцы» — они создают ложные точки ветвления,
        // из-за которых ровный штрих рассыпается на множество кусков.
        this._pruneSkeletonSpurs(skeleton, width, height, 14);
        let chains = this._traceSkeleton(skeleton, width, height);
        // Сшиваем сегменты, разрезанные в точках ветвления, обратно
        // в длинные непрерывные линии — иначе один штрих распадается на куски.
        chains = this._stitchChains(chains);
        const result = [];

        for (const chain of chains) {
            if (chain.length < 2) continue;
            if (this._chainPerimeter(chain) < minBranchLen) continue;

            let pts = chain;
            if (smoothPasses > 0) pts = this._chaikinSmooth(pts, smoothPasses, false);
            if (resampleStep > 0) pts = this._resampleByLength(pts, resampleStep, false);
            if (pts.length < 2) continue;

            result.push(pts.map(([px, py]) => [px, height - py]));
        }

        return result;
    }

    /**
     * Утончение бинарного изображения алгоритмом Чжана-Суэня (Zhang-Suen).
     * Итеративно «обгрызает» границу фигуры, пока не останется скелет
     * толщиной в 1 пиксель, сохраняя связность.
     *
     * @returns {Uint8Array}  1 = пиксель скелета, 0 = фон
     */
    _zhangSuenThinning(binary, width, height) {
        const img = new Uint8Array(width * height);
        for (let i = 0; i < img.length; i++) img[i] = binary[i] > 127 ? 1 : 0;

        const idx = (x, y) => y * width + x;
        const toClear = [];

        // pass: 0 — первый подитерация, 1 — второй
        const step = (pass) => {
            toClear.length = 0;
            for (let y = 1; y < height - 1; y++) {
                for (let x = 1; x < width - 1; x++) {
                    if (img[idx(x, y)] !== 1) continue;

                    const p2 = img[idx(x,     y - 1)];
                    const p3 = img[idx(x + 1, y - 1)];
                    const p4 = img[idx(x + 1, y    )];
                    const p5 = img[idx(x + 1, y + 1)];
                    const p6 = img[idx(x,     y + 1)];
                    const p7 = img[idx(x - 1, y + 1)];
                    const p8 = img[idx(x - 1, y    )];
                    const p9 = img[idx(x - 1, y - 1)];

                    const B = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9;
                    if (B < 2 || B > 6) continue;

                    // A — число переходов 0→1 в обходе p2..p9..p2
                    const seq = [p2, p3, p4, p5, p6, p7, p8, p9, p2];
                    let A = 0;
                    for (let k = 0; k < 8; k++)
                        if (seq[k] === 0 && seq[k + 1] === 1) A++;
                    if (A !== 1) continue;

                    if (pass === 0) {
                        if (p2 * p4 * p6 !== 0) continue;
                        if (p4 * p6 * p8 !== 0) continue;
                    } else {
                        if (p2 * p4 * p8 !== 0) continue;
                        if (p2 * p6 * p8 !== 0) continue;
                    }

                    toClear.push(idx(x, y));
                }
            }
            for (const i of toClear) img[i] = 0;
            return toClear.length > 0;
        };

        let changed = true;
        let iterations = 0;
        while (changed && iterations < 500) {
            changed = false;
            if (step(0)) changed = true;
            if (step(1)) changed = true;
            iterations++;
        }
        return img;
    }

    /**
     * Трассировка скелета в набор полилиний.
     * Идёт от «узлов» (концы — степень 1, развилки — степень ≥3) вдоль
     * цепочек пикселей степени 2; оставшиеся замкнутые петли обходятся отдельно.
     *
     * @returns {Array<Array<[number, number]>>}  полилинии в пиксельных коорд.
     */
    _traceSkeleton(skel, width, height) {
        const idx = (x, y) => y * width + x;
        const nbrOff = [
            [-1, -1], [0, -1], [1, -1],
            [-1,  0],          [1,  0],
            [-1,  1], [0,  1], [1,  1],
        ];

        const getNbrs = (x, y) => {
            const r = [];
            for (const [dx, dy] of nbrOff) {
                const nx = x + dx, ny = y + dy;
                if (nx >= 0 && ny >= 0 && nx < width && ny < height &&
                    skel[idx(nx, ny)]) {
                    r.push([nx, ny]);
                }
            }
            return r;
        };

        const degree = new Int32Array(width * height);
        const pix = [];
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                if (skel[idx(x, y)]) {
                    degree[idx(x, y)] = getNbrs(x, y).length;
                    pix.push([x, y]);
                }
            }
        }

        const usedEdge = new Set();
        const eKey = (a, b) => {
            const ka = a[1] * width + a[0];
            const kb = b[1] * width + b[0];
            return ka < kb ? ka + '_' + kb : kb + '_' + ka;
        };

        // Проход вдоль цепочки пикселей степени 2 от (a → b) до следующего узла
        const walk = (a, b) => {
            const path = [a, b];
            usedEdge.add(eKey(a, b));
            let prev = a, cur = b;
            while (degree[idx(cur[0], cur[1])] === 2) {
                let next = null;
                for (const n of getNbrs(cur[0], cur[1])) {
                    if (n[0] === prev[0] && n[1] === prev[1]) continue;
                    next = n;
                }
                if (!next) break;
                const k = eKey(cur, next);
                if (usedEdge.has(k)) break;
                usedEdge.add(k);
                path.push(next);
                prev = cur;
                cur = next;
            }
            return path;
        };

        const chains = [];

        // 1. Ветви, начинающиеся в узлах (концы и развилки)
        for (const [x, y] of pix) {
            if (degree[idx(x, y)] === 2) continue;
            for (const n of getNbrs(x, y)) {
                if (usedEdge.has(eKey([x, y], n))) continue;
                chains.push(walk([x, y], n));
            }
        }

        // 2. Оставшиеся замкнутые петли (все пиксели степени 2)
        for (const [x, y] of pix) {
            for (const n of getNbrs(x, y)) {
                if (usedEdge.has(eKey([x, y], n))) continue;
                const path = walk([x, y], n);
                if (path.length > 2) path.push([x, y]); // замыкаем петлю
                chains.push(path);
            }
        }

        return chains;
    }

    /**
     * Чистка скелета: схлопывает диагональные «лесенки» шириной 2 px
     * до настоящей ширины 1 px.
     *
     * Пиксель P считается избыточным, если среди его соседей-пикселей
     * есть такой N, к которому примыкают все остальные соседи P. Тогда N
     * полностью берёт на себя связность P, и P можно удалить, не нарушив
     * топологию. Концевые пиксели (1 сосед) не трогаются. Удаление —
     * последовательное (по одному), иначе можно разорвать линию.
     *
     * @param {Uint8Array} skel  — карта скелета (мутируется на месте)
     */
    _cleanSkeleton(skel, width, height) {
        const idx = (x, y) => y * width + x;
        const nbrOff = [
            [-1, -1], [0, -1], [1, -1],
            [-1,  0],          [1,  0],
            [-1,  1], [0,  1], [1,  1],
        ];
        const fgNbrs = (x, y) => {
            const r = [];
            for (const [dx, dy] of nbrOff) {
                const nx = x + dx, ny = y + dy;
                if (nx >= 0 && ny >= 0 && nx < width && ny < height &&
                    skel[idx(nx, ny)]) r.push([nx, ny]);
            }
            return r;
        };
        const adjacent = (a, b) =>
            (a[0] !== b[0] || a[1] !== b[1]) &&
            Math.abs(a[0] - b[0]) <= 1 && Math.abs(a[1] - b[1]) <= 1;

        let changed = true;
        let guard = 0;
        while (changed && guard++ < 60) {
            changed = false;
            for (let y = 0; y < height; y++) {
                for (let x = 0; x < width; x++) {
                    if (!skel[idx(x, y)]) continue;
                    const nb = fgNbrs(x, y);
                    if (nb.length < 2) continue; // концевой пиксель — не трогаем

                    for (const N of nb) {
                        let dominated = true;
                        for (const M of nb) {
                            if (M[0] === N[0] && M[1] === N[1]) continue;
                            if (!adjacent(M, N)) { dominated = false; break; }
                        }
                        if (dominated) {
                            skel[idx(x, y)] = 0;
                            changed = true;
                            break;
                        }
                    }
                }
            }
        }
    }

    /**
     * Удаляет короткие «заусенцы» (spurs) скелета — тупиковые веточки,
     * висящие на точке ветвления. Они возникают как артефакты утончения
     * толстых штрихов и создают ложные узлы, дробящие линию.
     *
     * Заусенец = сегмент с одним концом-тупиком (степень 1) и одним
     * концом-развилкой (степень ≥3), короче maxSpurLen. Настоящие штрихи
     * (оба конца — тупики) и длинные ветви не трогаются.
     *
     * @param {Uint8Array} skel    — карта скелета (мутируется на месте)
     * @param {number} width
     * @param {number} height
     * @param {number} maxSpurLen  — макс. длина заусенца в пикселях
     */
    _pruneSkeletonSpurs(skel, width, height, maxSpurLen) {
        const idx = (x, y) => y * width + x;
        const nbrOff = [
            [-1, -1], [0, -1], [1, -1],
            [-1,  0],          [1,  0],
            [-1,  1], [0,  1], [1,  1],
        ];
        const degAt = (x, y) => {
            let c = 0;
            for (const [dx, dy] of nbrOff) {
                const nx = x + dx, ny = y + dy;
                if (nx >= 0 && ny >= 0 && nx < width && ny < height &&
                    skel[idx(nx, ny)]) c++;
            }
            return c;
        };

        for (let iter = 0; iter < 30; iter++) {
            // Степени всех пикселей на начало итерации
            const degMap = new Int32Array(width * height);
            for (let y = 0; y < height; y++)
                for (let x = 0; x < width; x++)
                    if (skel[idx(x, y)]) degMap[idx(x, y)] = degAt(x, y);

            const chains = this._traceSkeleton(skel, width, height);
            const toRemove = [];

            for (const ch of chains) {
                if (ch.length < 2) continue;
                const a = ch[0], b = ch[ch.length - 1];
                const da = degMap[idx(a[0], a[1])];
                const db = degMap[idx(b[0], b[1])];
                const isSpur = (da === 1 && db >= 3) || (db === 1 && da >= 3);
                if (!isSpur) continue;
                if (this._chainPerimeter(ch) >= maxSpurLen) continue;
                // удаляем пиксели заусенца, кроме самой развилки
                for (const p of ch) {
                    if (degMap[idx(p[0], p[1])] >= 3) continue;
                    toRemove.push(idx(p[0], p[1]));
                }
            }

            if (toRemove.length === 0) break;
            for (const i of toRemove) skel[i] = 0;
        }
    }

    /**
     * Сшивка сегментов скелета в длинные непрерывные линии.
     *
     * Трассировка разрезает линию в каждой точке ветвления. В результате
     * один штрих буквы распадается на множество коротких отрезков (а узлы
     * часто ложные — от мелких «заусенцев» скелета). Здесь в каждом узле
     * сегменты попарно соединяются по принципу «наиболее прямого
     * продолжения»: пара сегментов, идущих почти навстречу друг другу,
     * объединяется в сквозную линию; лишние ветви остаются отдельными.
     *
     * @param {Array<Array<[number, number]>>} chains
     * @returns {Array<Array<[number, number]>>}
     */
    _stitchChains(chains) {
        const n = chains.length;
        if (n < 2) return chains;

        const key = (p) => Math.round(p[0]) + '_' + Math.round(p[1]);
        const sid = (ci, end) => ci * 2 + end;

        // Единичный вектор, направленный от конца сегмента внутрь него
        const dirAway = (chain, end) => {
            const m = chain.length;
            const span = Math.min(m - 1, 5);
            const a = end === 0 ? chain[0] : chain[m - 1];
            const b = end === 0 ? chain[span] : chain[m - 1 - span];
            const dx = b[0] - a[0], dy = b[1] - a[1];
            const L = Math.hypot(dx, dy) || 1;
            return [dx / L, dy / L];
        };

        // Группируем концы сегментов по узлам (общим точкам)
        const nodes = new Map();
        for (let ci = 0; ci < n; ci++) {
            const ch = chains[ci];
            if (ch.length < 2) continue;
            for (const end of [0, 1]) {
                const p = end === 0 ? ch[0] : ch[ch.length - 1];
                const k = key(p);
                if (!nodes.has(k)) nodes.set(k, []);
                nodes.get(k).push({ ci, end });
            }
        }

        // partner[sid] — с каким концом какого сегмента соединён данный конец
        const partner = new Int32Array(n * 2).fill(-1);

        for (const stubs of nodes.values()) {
            if (stubs.length < 2) continue;
            const dirs = stubs.map(s => dirAway(chains[s.ci], s.end));

            // Все возможные пары концов в этом узле
            const pairs = [];
            for (let i = 0; i < stubs.length; i++) {
                for (let j = i + 1; j < stubs.length; j++) {
                    if (stubs[i].ci === stubs[j].ci) continue; // не сшивать сегмент сам с собой
                    const dot = dirs[i][0] * dirs[j][0] + dirs[i][1] * dirs[j][1];
                    pairs.push({ i, j, dot });
                }
            }
            // dot ≈ -1 → сегменты идут навстречу (прямое продолжение); сортируем по возрастанию
            pairs.sort((a, b) => a.dot - b.dot);

            const taken = new Set();
            for (const pr of pairs) {
                if (taken.has(pr.i) || taken.has(pr.j)) continue;
                if (pr.dot > 0.5) continue; // слишком резкий загиб (шпилька) — не сшивать
                const si = stubs[pr.i], sj = stubs[pr.j];
                if (partner[sid(si.ci, si.end)] !== -1) continue;
                if (partner[sid(sj.ci, sj.end)] !== -1) continue;
                partner[sid(si.ci, si.end)] = sid(sj.ci, sj.end);
                partner[sid(sj.ci, sj.end)] = sid(si.ci, si.end);
                taken.add(pr.i);
                taken.add(pr.j);
            }
        }

        // Собираем сегменты в объединённые полилинии по связям partner
        const visited = new Array(n).fill(false);
        const result = [];

        const buildFrom = (ci, entryEnd) => {
            const poly = [];
            let first = true;
            while (!visited[ci]) {
                visited[ci] = true;
                const ch = chains[ci];
                const ordered = entryEnd === 0 ? ch : ch.slice().reverse();
                if (first) {
                    for (const p of ordered) poly.push(p);
                    first = false;
                } else {
                    // первая точка совпадает с узлом стыка — пропускаем дубликат
                    for (let i = 1; i < ordered.length; i++) poly.push(ordered[i]);
                }
                const exitEnd = 1 - entryEnd;
                const np = partner[sid(ci, exitEnd)];
                if (np === -1) break;
                ci = np >> 1;
                entryEnd = np & 1;
            }
            return poly;
        };

        // 1. Начинаем с «свободных» концов (без партнёра)
        for (let ci = 0; ci < n; ci++) {
            if (visited[ci] || chains[ci].length < 2) continue;
            for (const end of [0, 1]) {
                if (partner[sid(ci, end)] === -1) {
                    result.push(buildFrom(ci, end));
                    break;
                }
            }
        }
        // 2. Оставшиеся — замкнутые петли (все концы соединены)
        for (let ci = 0; ci < n; ci++) {
            if (visited[ci] || chains[ci].length < 2) continue;
            result.push(buildFrom(ci, 0));
        }

        return result;
    }

    getBinaryPreview(threshold, invert, blurSize) {
        if (!this.grayscaleData) return null;
        let data = this.grayscaleData;
        if (blurSize > 0) data = this.gaussianBlur(data, this.width, this.height, blurSize);
        const binary = this.threshold(data, threshold, invert);
        const canvas = document.createElement('canvas');
        canvas.width = this.width; canvas.height = this.height;
        const ctx = canvas.getContext('2d');
        const id = ctx.createImageData(this.width, this.height);
        for (let i = 0; i < binary.length; i++) {
            const idx = i * 4;
            id.data[idx] = id.data[idx+1] = id.data[idx+2] = binary[i];
            id.data[idx+3] = 255;
        }
        return id;
    }

    getHeightmap(blurSize) {
        if (!this.grayscaleData) return null;
        if (blurSize > 0) return this.gaussianBlur(this.grayscaleData, this.width, this.height, blurSize);
        return new Uint8Array(this.grayscaleData);
    }
}