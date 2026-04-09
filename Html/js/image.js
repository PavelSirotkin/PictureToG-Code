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
            const next = [];
            for (let j = 0; j < n; j++) {
                const a = p[j], b = p[(j + 1) % n];
                next.push([0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]]);
                next.push([0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]]);
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

        if (closed) result.push([...result[0]]);
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
