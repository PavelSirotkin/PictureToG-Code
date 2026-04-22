/**
 * Geometry — Геометрические операции
 * Аналог core/geometry.py
 * 
 * Реализует:
 * - Упрощение контуров RDP
 * - Офсет контуров (tool compensation)
 * - Масштабирование контуров
 * - Сортировка контуров (nearest neighbor)
 * - Вставку мостиков (bridges)
 */

class Geometry {
    /**
     * Упрощает контур алгоритмом Рамера-Дугласа-Пекера
     * @param {Array<[number, number]>} chain 
     * @param {number} epsilon 
     * @returns {Array<[number, number]>}
     */
    static simplifyChain(chain, epsilon) {
        if (epsilon <= 0 || chain.length < 3) return chain;
        return Geometry._rdp(chain, epsilon);
    }

    /**
     * RDP алгоритм (рекурсивный)
     */
    static _rdp(points, epsilon) {
        if (points.length < 3) return points;
        
        const start = points[0];
        const end = points[points.length - 1];
        const dx = end[0] - start[0];
        const dy = end[1] - start[1];
        const distSq = dx * dx + dy * dy;
        
        let maxDist = 0;
        let idx = 0;
        
        for (let i = 1; i < points.length - 1; i++) {
            const px = points[i][0];
            const py = points[i][1];
            
            let d;
            if (distSq === 0) {
                d = Math.hypot(px - start[0], py - start[1]);
            } else {
                let t = ((px - start[0]) * dx + (py - start[1]) * dy) / distSq;
                t = Math.max(0, Math.min(1, t));
                d = Math.hypot(px - (start[0] + t * dx), py - (start[1] + t * dy));
            }
            
            if (d > maxDist) {
                maxDist = d;
                idx = i;
            }
        }
        
        if (maxDist > epsilon) {
            const left = Geometry._rdp(points.slice(0, idx + 1), epsilon);
            const right = Geometry._rdp(points.slice(idx), epsilon);
            return [...left.slice(0, -1), ...right];
        }
        
        return [start, end];
    }

    /**
     * Смещает контур на указанное расстояние (компенсация инструмента)
     * Упрощённая реализация без Shapely — просто масштабируем контур от центра
     * @param {Array<[number, number]>} chain 
     * @param {number} offset 
     * @returns {Array<Array<[number, number]>>}
     */
    static offsetChain(chain, offset) {
        if (offset === 0 || chain.length < 3) return [chain];
        
        // Упрощённый офсет: находим центр и масштабируем
        // Это НЕ точный офсет как у Shapely, но работает для простых контуров
        const center = Geometry._centroid(chain);
        
        const result = chain.map(([x, y]) => {
            const dx = x - center[0];
            const dy = y - center[1];
            const dist = Math.hypot(dx, dy);
            if (dist === 0) return [x, y];
            
            const scale = (dist + offset) / dist;
            return [center[0] + dx * scale, center[1] + dy * scale];
        });
        
        return [result];
    }

    /**
     * Вычисление центроида полигона
     */
    static _centroid(points) {
        let cx = 0, cy = 0;
        const n = points.length;
        for (const [x, y] of points) {
            cx += x;
            cy += y;
        }
        return [cx / n, cy / n];
    }

    /**
     * Получить bounding box контуров
     * @param {Array<Array<[number, number]>>} chains 
     * @returns {[number, number, number, number]}
     */
    static getBounds(chains) {
        const allPts = chains.flat();
        if (allPts.length === 0) return [0, 0, 0, 0];
        
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const [x, y] of allPts) {
            if (x < minX) minX = x;
            if (y < minY) minY = y;
            if (x > maxX) maxX = x;
            if (y > maxY) maxY = y;
        }
        
        return [minX, minY, maxX, maxY];
    }

    /**
     * Масштабирует контуры к целевым размерам
     * @param {Array<Array<[number, number]>>} chains 
     * @param {number|null} targetW 
     * @param {number|null} targetH 
     * @param {boolean} keepAspect 
     * @returns {Array<Array<[number, number]>>}
     */
    static scaleChains(chains, targetW = null, targetH = null, keepAspect = true) {
        if (!chains || chains.length === 0 || (targetW === null && targetH === null)) {
            return chains;
        }
        
        const [minX, minY, maxX, maxY] = Geometry.getBounds(chains);
        const srcW = maxX - minX;
        const srcH = maxY - minY;
        
        if (srcW === 0 || srcH === 0) return chains;
        
        let sx, sy;
        if (targetW !== null && targetH !== null) {
            sx = targetW / srcW;
            sy = targetH / srcH;
            if (keepAspect) sx = sy = Math.min(sx, sy);
        } else if (targetW !== null) {
            sx = sy = targetW / srcW;
        } else {
            sx = sy = targetH / srcH;
        }
        
        return chains.map(chain => 
            chain.map(([x, y]) => [(x - minX) * sx, (y - minY) * sy])
        );
    }

    /**
     * Сортировка контуров методом ближайшего соседа
     * @param {Array<Array<[number, number]>>} chains 
     * @returns {Array<Array<[number, number]>>}
     */
    static sortChainsNearest(chains) {
        if (chains.length <= 1) return chains;
        
        const remaining = Array.from({ length: chains.length }, (_, i) => i);
        const ordered = [remaining.shift()];
        
        while (remaining.length > 0) {
            const lastChain = chains[ordered[ordered.length - 1]];
            const last = lastChain[lastChain.length - 1];
            
            let bestIdx = 0;
            let bestDist = Infinity;
            
            for (let i = 0; i < remaining.length; i++) {
                const ri = remaining[i];
                const first = chains[ri][0];
                const d = (first[0] - last[0]) ** 2 + (first[1] - last[1]) ** 2;
                if (d < bestDist) {
                    bestDist = d;
                    bestIdx = i;
                }
            }
            
            ordered.push(remaining.splice(bestIdx, 1)[0]);
        }
        
        return ordered.map(i => chains[i]);
    }

    /**
     * Вычисляет длину полилинии
     * @param {Array<[number, number]>} chain 
     * @returns {number}
     */
    static chainLength(chain) {
        let total = 0;
        for (let i = 0; i < chain.length - 1; i++) {
            total += Math.hypot(chain[i + 1][0] - chain[i][0], chain[i + 1][1] - chain[i][1]);
        }
        return total;
    }

    /**
     * Вставляет мостики (perемычки) в контур
     * Аналог insert_bridges в geometry.py
     * @param {Array<[number, number]>} chain 
     * @param {number} bridgeSize 
     * @param {number} numBridges 
     * @returns {Array<{segment: Array<[number, number]>, isBridge: boolean}>}
     */
    static insertBridges(chain, bridgeSize, numBridges = 2) {
        if (chain.length < 2) return [{ segment: chain, isBridge: false }];
        
        const total = Geometry.chainLength(chain);
        if (total < bridgeSize * numBridges * 2 || bridgeSize <= 0) {
            return [{ segment: chain, isBridge: false }];
        }
        
        const interval = total / numBridges;
        const bridgeStarts = Array.from({ length: numBridges }, (_, i) => 
            interval * i + interval * 0.5
        );
        
        const segments = [];
        let curDist = 0;
        let segPts = [chain[0]];
        let bridgeIdx = 0;
        let inBridge = false;
        
        for (let i = 0; i < chain.length - 1; i++) {
            const p0 = chain[i];
            const p1 = chain[i + 1];
            const step = Math.hypot(p1[0] - p0[0], p1[1] - p0[1]);
            if (step === 0) continue;
            
            const events = [];
            if (bridgeIdx < bridgeStarts.length) {
                const bs = bridgeStarts[bridgeIdx];
                const be = bs + bridgeSize;
                
                for (const distEvent of [bs, be]) {
                    const dLocal = distEvent - curDist;
                    if (dLocal > 0 && dLocal < step) {
                        const t = dLocal / step;
                        events.push({ t, dist: distEvent });
                    }
                }
            }
            
            events.sort((a, b) => a.t - b.t);
            
            for (const event of events) {
                const interp = [
                    p0[0] + event.t * (p1[0] - p0[0]),
                    p0[1] + event.t * (p1[1] - p0[1])
                ];
                segPts.push(interp);
                segments.push({ segment: [...segPts], isBridge });
                segPts = [interp];
                inBridge = !inBridge;
                if (!inBridge) bridgeIdx++;
            }
            
            segPts.push(p1);
            curDist += step;
        }
        
        if (segPts.length >= 2) {
            segments.push({ segment: segPts, isBridge });
        }
        
        return segments;
    }
}
