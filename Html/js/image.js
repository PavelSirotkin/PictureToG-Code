/**
 * ImageProcessor — Обработка изображений
 * Аналог core/image.py
 * 
 * Реализует:
 * - Загрузку изображения через FileReader
 * - Преобразование в градации серого
 * - Gaussian blur
 * - Бинаризацию с порогом
 * - Извлечение контуров (marching squares)
 * - Упрощение контуров
 */

class ImageProcessor {
    constructor() {
        this.originalImage = null;
        this.grayscaleData = null;
        this.width = 0;
        this.height = 0;
    }

    /**
     * Загружает изображение из File объекта
     * @param {File} file 
     * @returns {Promise<{imageData: ImageData, width: number, height: number}>}
     */
    loadImage(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => {
                const img = new Image();
                img.onload = () => {
                    this.originalImage = img;
                    this.width = img.width;
                    this.height = img.height;

                    // Создаём canvas для извлечения данных
                    const canvas = document.createElement('canvas');
                    canvas.width = this.width;
                    canvas.height = this.height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0);
                    
                    const imageData = ctx.getImageData(0, 0, this.width, this.height);
                    this.grayscaleData = this._toGrayscale(imageData);
                    
                    resolve({
                        imageData: imageData,
                        width: this.width,
                        height: this.height
                    });
                };
                img.onerror = () => reject(new Error('Не удалось загрузить изображение'));
                img.src = e.target.result;
            };
            reader.onerror = () => reject(new Error('Не удалось прочитать файл'));
            reader.readAsDataURL(file);
        });
    }

    /**
     * Преобразование в градации серого
     * @param {ImageData} imageData 
     * @returns {Uint8Array}
     */
    _toGrayscale(imageData) {
        const data = imageData.data;
        const len = data.length;
        const gray = new Uint8Array(len / 4);
        
        for (let i = 0; i < len; i += 4) {
            // Формула люминанса
            gray[i / 4] = Math.round(0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]);
        }
        
        return gray;
    }

    /**
     * Gaussian blur (упрощённая реализация с separable kernel)
     * @param {Uint8Array} data 
     * @param {number} width 
     * @param {number} height 
     * @param {number} kernelSize 
     * @returns {Uint8Array}
     */
    gaussianBlur(data, width, height, kernelSize) {
        if (kernelSize <= 0) return new Uint8Array(data);
        
        // Делаем kernelSize нечётным
        if (kernelSize % 2 === 0) kernelSize++;
        
        const sigma = kernelSize / 3.0;
        const kernel = this._gaussianKernel1D(kernelSize, sigma);
        
        // Двухпроходное размытие (horizontal + vertical)
        const temp = new Uint8Array(data.length);
        const result = new Uint8Array(data.length);
        
        // Горизонтальный проход
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                let sum = 0;
                let weightSum = 0;
                for (let k = -Math.floor(kernelSize / 2); k <= Math.floor(kernelSize / 2); k++) {
                    const sx = Math.min(Math.max(x + k, 0), width - 1);
                    const weight = kernel[k + Math.floor(kernelSize / 2)];
                    sum += data[y * width + sx] * weight;
                    weightSum += weight;
                }
                temp[y * width + x] = Math.round(sum / weightSum);
            }
        }
        
        // Вертикальный проход
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                let sum = 0;
                let weightSum = 0;
                for (let k = -Math.floor(kernelSize / 2); k <= Math.floor(kernelSize / 2); k++) {
                    const sy = Math.min(Math.max(y + k, 0), height - 1);
                    const weight = kernel[k + Math.floor(kernelSize / 2)];
                    sum += temp[sy * width + x] * weight;
                    weightSum += weight;
                }
                result[y * width + x] = Math.round(sum / weightSum);
            }
        }
        
        return result;
    }

    /**
     * 1D Gaussian kernel
     */
    _gaussianKernel1D(size, sigma) {
        const kernel = new Float32Array(size);
        const half = Math.floor(size / 2);
        let sum = 0;
        
        for (let i = 0; i < size; i++) {
            const x = i - half;
            const val = Math.exp(-(x * x) / (2 * sigma * sigma));
            kernel[i] = val;
            sum += val;
        }
        
        // Нормализация
        for (let i = 0; i < size; i++) {
            kernel[i] /= sum;
        }
        
        return kernel;
    }

    /**
     * Бинаризация изображения
     * @param {Uint8Array} data 
     * @param {number} threshold 
     * @param {boolean} invert 
     * @returns {Uint8Array}
     */
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
     * Извлечение контуров алгоритмом Marching Squares.
     * Находит именно ГРАНИЦЫ между чёрным и белым,
     * а не залитые области — идеально для контурной резки.
     *
     * @param {Uint8Array} binaryData
     * @param {number} width
     * @param {number} height
     * @param {number} minArea
     * @param {number} epsilonFactor
     * @returns {Array<Array<[number, number]>>}
     */
    extractContours(binaryData, width, height, minArea = 10, epsilonFactor = 0.001) {
        return this._marchingSquares(binaryData, width, height, minArea, epsilonFactor);
    }

    /**
     * Marching Squares — находит изолинии на бинарном изображении.
     * Для каждого 2x2 блока определяет конфигурацию (0-15)
     * и строит сегменты на рёбрах ячеек, затем собирает их в контуры.
     */
    _marchingSquares(binary, width, height, minArea, epsilonFactor) {
        // Словарь рёбер: ключ "x,y,dir" → точка [x, y]
        // dir: 0 = horizontal (ребро вниз), 1 = vertical (ребро вправо)
        const edgeMap = new Map();
        // Список сегментов: [{from: key, to: key}, ...]
        const segments = [];

        // Сканируем 2x2 ячейки
        for (let y = 0; y < height - 1; y++) {
            for (let x = 0; x < width - 1; x++) {
                // Индексы 4 углов
                const i00 = y * width + x;         // верхний левый
                const i10 = y * width + (x + 1);   // верхний правый
                const i01 = (y + 1) * width + x;   // нижний левый
                const i11 = (y + 1) * width + (x + 1); // нижний правый

                // Определяем case (битовая маска)
                let caseIndex = 0;
                if (binary[i00] > 127) caseIndex |= 1;
                if (binary[i10] > 127) caseIndex |= 2;
                if (binary[i11] > 127) caseIndex |= 4;
                if (binary[i01] > 127) caseIndex |= 8;

                // Пропускаем однородные ячейки
                if (caseIndex === 0 || caseIndex === 15) continue;

                // Находим точки пересечения на рёбрах
                // Ребро сверху: между (x,y) и (x+1,y)
                const topKey = `${x + 0.5},${y},h`;
                // Ребро снизу: между (x,y+1) и (x+1,y+1)
                const botKey = `${x + 0.5},${y + 1},h`;
                // Ребро слева: между (x,y) и (x,y+1)
                const leftKey = `${x},${y + 0.5},v`;
                // Ребро справа: между (x+1,y) и (x+1,y+1)
                const rightKey = `${x + 1},${y + 0.5},v`;

                // Определяем какие рёбра пересекаются
                const intersections = [];
                if (this._edgeCrossed(caseIndex, 0)) intersections.push(leftKey);
                if (this._edgeCrossed(caseIndex, 1)) intersections.push(topKey);
                if (this._edgeCrossed(caseIndex, 2)) intersections.push(rightKey);
                if (this._edgeCrossed(caseIndex, 3)) intersections.push(botKey);

                // Соединяем точки пересечения в сегменты
                // Для marching squares всегда 2 точки на ячейку (кроме saddle cases)
                if (intersections.length === 2) {
                    segments.push([intersections[0], intersections[1]]);
                } else if (intersections.length === 4) {
                    // Saddle case — нужно выбрать соединение
                    // Для бинарного изображения выбираем по центральному пикселю
                    const centerVal = binary[i11]; // используем нижний правый как "центр"
                    if (centerVal > 127) {
                        segments.push([intersections[0], intersections[1]]);
                        segments.push([intersections[2], intersections[3]]);
                    } else {
                        segments.push([intersections[0], intersections[3]]);
                        segments.push([intersections[1], intersections[2]]);
                    }
                }
            }
        }

        // Собираем сегменты в цепочки (контуры)
        const contours = this._assembleContours(segments, edgeMap);

        // Фильтруем, упрощаем, переворачиваем Y
        const result = [];
        for (const chain of contours) {
            if (chain.length < 3) continue;

            // Проверяем минимальную площадь
            const area = this._polygonArea(chain);
            if (area < minArea) continue;

            // Упрощаем RDP — epsilon = factor * периметр (как в оригинале)
            const perimeter = this._chainPerimeter(chain);
            const eps = epsilonFactor > 0 ? epsilonFactor * perimeter : 0;
            const simplified = eps > 0
                ? this._ramerDouglasPeucker(chain, eps)
                : chain;

            if (simplified.length < 3) continue;

            // Переводим Y (вверх)
            const flipped = simplified.map(([px, py]) => [px, height - py]);

            // Замыкаем
            if (flipped[0][0] !== flipped[flipped.length - 1][0] ||
                flipped[0][1] !== flipped[flipped.length - 1][1]) {
                flipped.push([...flipped[0]]);
            }

            result.push(flipped);
        }

        return result;
    }

    /**
     * Определяет, пересекает ли данное ребро границу для данного case.
     * Рёбра: 0=лево, 1=верх, 2=право, 3=низ
     */
    _edgeCrossed(caseIndex, edge) {
        // Таблица рёбер для marching squares
        // edge 0 (лево): биты 0 и 3 различаются
        // edge 1 (верх): биты 0 и 1 различаются
        // edge 2 (право): биты 1 и 2 различаются
        // edge 3 (низ): биты 2 и 3 различаются
        const pairs = [[0, 3], [0, 1], [1, 2], [2, 3]];
        const [a, b] = pairs[edge];
        return ((caseIndex >> a) & 1) !== ((caseIndex >> b) & 1);
    }

    /**
     * Собирает список сегментов в замкнутые контуры.
     */
    _assembleContours(segments, edgeMap) {
        // Строим adjacency map
        const adjacency = new Map();

        for (const [a, b] of segments) {
            if (!adjacency.has(a)) adjacency.set(a, []);
            if (!adjacency.has(b)) adjacency.set(b, []);
            adjacency.get(a).push(b);
            adjacency.get(b).push(a);
        }

        const contours = [];
        const used = new Set();

        // Для каждой начальной точки пытаемся построить контур
        for (const [startKey, neighbors] of adjacency) {
            if (used.has(startKey)) continue;
            if (neighbors.length < 2) continue; //孤立点

            // Обход контура
            const contour = [];
            let current = startKey;
            let prev = null;

            while (current) {
                used.add(current);

                // Парсим координаты из ключа
                const parts = current.split(',');
                contour.push([parseFloat(parts[0]), parseFloat(parts[1])]);

                // Находим следующего соседа
                const nbrs = adjacency.get(current) || [];
                let next = null;
                for (const n of nbrs) {
                    if (n !== prev && !used.has(n)) {
                        next = n;
                        break;
                    }
                }

                // Если тупик — пробуем вернуться к началу
                if (!next) {
                    // Проверяем, замкнут ли контур
                    if (contour.length > 2 && adjacency.get(current)?.includes(startKey)) {
                        break; // замкнулся
                    }
                    break; // тупик
                }

                prev = current;
                current = next;
            }

            if (contour.length >= 3) {
                contours.push(contour);
            }
        }

        return contours;
    }

    /**
     * Вычисление площади полигона (shoelace formula)
     */
    _polygonArea(points) {
        let area = 0;
        const n = points.length;
        for (let i = 0; i < n; i++) {
            const j = (i + 1) % n;
            area += points[i][0] * points[j][1];
            area -= points[j][0] * points[i][1];
        }
        return Math.abs(area) / 2;
    }

    /**
     * Вычисление периметра полилинии
     */
    _chainPerimeter(points) {
        let total = 0;
        for (let i = 0; i < points.length - 1; i++) {
            total += Math.hypot(
                points[i + 1][0] - points[i][0],
                points[i + 1][1] - points[i][1]
            );
        }
        return total;
    }

    /**
     * Алгоритм Рамера-Дугласа-Пекера для упрощения полилинии
     * Аналог _rdp в geometry.py
     */
    _ramerDouglasPeucker(points, epsilon) {
        if (points.length < 3) return points;
        
        let maxDist = 0;
        let maxIndex = 0;
        const start = points[0];
        const end = points[points.length - 1];
        
        const dx = end[0] - start[0];
        const dy = end[1] - start[1];
        const distSq = dx * dx + dy * dy;
        
        for (let i = 1; i < points.length - 1; i++) {
            const px = points[i][0];
            const py = points[i][1];
            
            let dist;
            if (distSq === 0) {
                dist = Math.hypot(px - start[0], py - start[1]);
            } else {
                let t = ((px - start[0]) * dx + (py - start[1]) * dy) / distSq;
                t = Math.max(0, Math.min(1, t));
                dist = Math.hypot(px - (start[0] + t * dx), py - (start[1] + t * dy));
            }
            
            if (dist > maxDist) {
                maxDist = dist;
                maxIndex = i;
            }
        }
        
        if (maxDist > epsilon) {
            const left = this._ramerDouglasPeucker(points.slice(0, maxIndex + 1), epsilon);
            const right = this._ramerDouglasPeucker(points.slice(maxIndex), epsilon);
            return [...left.slice(0, -1), ...right];
        }
        
        return [start, end];
    }

    /**
     * Получить бинаризованное изображение для предпросмотра
     * @param {number} threshold 
     * @param {boolean} invert 
     * @param {number} blurSize 
     * @returns {ImageData}
     */
    getBinaryPreview(threshold, invert, blurSize) {
        if (!this.grayscaleData) return null;
        
        let data = this.grayscaleData;
        if (blurSize > 0) {
            data = this.gaussianBlur(data, this.width, this.height, blurSize);
        }
        
        const binary = this.threshold(data, threshold, invert);
        
        // Создаём ImageData
        const canvas = document.createElement('canvas');
        canvas.width = this.width;
        canvas.height = this.height;
        const ctx = canvas.getContext('2d');
        const imageData = ctx.createImageData(this.width, this.height);
        
        for (let i = 0; i < binary.length; i++) {
            const idx = i * 4;
            imageData.data[idx] = binary[i];
            imageData.data[idx + 1] = binary[i];
            imageData.data[idx + 2] = binary[i];
            imageData.data[idx + 3] = 255;
        }
        
        return imageData;
    }

    /**
     * Получить карту высот для рельефа
     * @param {number} blurSize 
     * @returns {Uint8Array}
     */
    getHeightmap(blurSize) {
        if (!this.grayscaleData) return null;
        
        if (blurSize > 0) {
            return this.gaussianBlur(this.grayscaleData, this.width, this.height, blurSize);
        }
        
        return new Uint8Array(this.grayscaleData);
    }
}
