/**
 * Templates — Параметрические шаблоны
 * Аналог core/templates.py
 * 
 * Генерирует контуры для шаблонов:
 * - Брелок прямоугольный
 * - Брелок круглый
 * - Табличка с рамкой
 * - Звезда
 * - Сердце
 */

class Templates {
    /**
     * Генерирует контур шаблона
     * @param {string} name 
     * @param {number} size 
     * @returns {Array<Array<[number, number]>>}
     */
    static generate(name, size = 50) {
        switch (name) {
            case 'Брелок прямоугольный':
                return Templates._rectangularKeychain(size);
            case 'Брелок круглый':
                return Templates._circularKeychain(size);
            case 'Табличка с рамкой':
                return Templates._nameplate(size);
            case 'Звезда':
                return Templates._star(size);
            case 'Сердце':
                return Templates._heart(size);
            default:
                return [];
        }
    }

    /**
     * Брелок прямоугольный с отверстием
     */
    static _rectangularKeychain(size) {
        const w = size * 1.5;
        const h = size;
        const r = 3; // скругление углов
        
        // Внешний контур (прямоугольник со скруглёнными углами)
        const outer = Templates._roundedRect(0, 0, w, h, r);
        
        // Отверстие для кольца
        const holeR = size * 0.12;
        const holeCx = w * 0.15;
        const holeCy = h * 0.5;
        const hole = Templates._circle(holeCx, holeCy, holeR);
        
        return [outer, hole];
    }

    /**
     * Брелок круглый с отверстием
     */
    static _circularKeychain(size) {
        const outerR = size * 0.5;
        const cx = outerR;
        const cy = outerR;
        
        const outer = Templates._circle(cx, cy, outerR);
        const holeR = outerR * 0.2;
        const holeCx = cx - outerR * 0.45;
        const holeCy = cy;
        const hole = Templates._circle(holeCx, holeCy, holeR);
        
        return [outer, hole];
    }

    /**
     * Табличка с рамкой
     */
    static _nameplate(size) {
        const w = size * 2;
        const h = size;
        const frameW = size * 0.08;
        
        // Внешний контур
        const outer = [
            [0, 0], [w, 0], [w, h], [0, h], [0, 0]
        ];
        
        // Внутренняя рамка
        const inner = [
            [frameW, frameW], 
            [w - frameW, frameW], 
            [w - frameW, h - frameW], 
            [frameW, h - frameW], 
            [frameW, frameW]
        ];
        
        // 4 отверстия по углам
        const holeR = frameW * 0.4;
        const margin = frameW * 1.5;
        const holes = [
            Templates._circle(margin, margin, holeR),
            Templates._circle(w - margin, margin, holeR),
            Templates._circle(w - margin, h - margin, holeR),
            Templates._circle(margin, h - margin, holeR),
        ];
        
        return [outer, inner, ...holes];
    }

    /**
     * Звезда
     */
    static _star(size) {
        const points = [];
        const outerR = size * 0.5;
        const innerR = outerR * 0.4;
        const cx = outerR;
        const cy = outerR;
        const numPoints = 5;
        
        for (let i = 0; i < numPoints * 2; i++) {
            const angle = (Math.PI / 2) + (i * Math.PI / numPoints);
            const r = i % 2 === 0 ? outerR : innerR;
            points.push([
                cx + r * Math.cos(angle),
                cy + r * Math.sin(angle)
            ]);
        }
        
        points.push([...points[0]]); // замыкаем
        return [points];
    }

    /**
     * Сердце
     */
    static _heart(size) {
        const points = [];
        const scale = size * 0.025;
        const steps = 64;
        
        for (let i = 0; i <= steps; i++) {
            const t = (i / steps) * 2 * Math.PI;
            
            // Параметрическое уравнение сердца
            const x = 16 * Math.pow(Math.sin(t), 3);
            const y = -(13 * Math.cos(t) - 5 * Math.cos(2*t) - 2 * Math.cos(3*t) - Math.cos(4*t));
            
            points.push([
                x * scale + size * 0.5,
                y * scale + size * 0.55
            ]);
        }
        
        return [points];
    }

    /**
     * Прямоугольник со скруглёнными углами
     */
    static _roundedRect(x, y, w, h, r) {
        const points = [];
        const segments = 8; // сегментов на скругление
        
        // Верхняя сторона
        points.push([x + r, y]);
        points.push([x + w - r, y]);
        
        // Правый верхний угол
        for (let i = 0; i <= segments; i++) {
            const angle = -Math.PI / 2 + (i / segments) * Math.PI / 2;
            points.push([
                x + w - r + r * Math.cos(angle),
                y + r + r * Math.sin(angle)
            ]);
        }
        
        // Правая сторона
        points.push([x + w, y + h - r]);
        
        // Правый нижний угол
        for (let i = 0; i <= segments; i++) {
            const angle = 0 + (i / segments) * Math.PI / 2;
            points.push([
                x + w - r + r * Math.cos(angle),
                y + h - r + r * Math.sin(angle)
            ]);
        }
        
        // Нижняя сторона
        points.push([x + w - r, y + h]);
        points.push([x + r, y + h]);
        
        // Левый нижний угол
        for (let i = 0; i <= segments; i++) {
            const angle = Math.PI / 2 + (i / segments) * Math.PI / 2;
            points.push([
                x + r + r * Math.cos(angle),
                y + h - r + r * Math.sin(angle)
            ]);
        }
        
        // Левая сторона
        points.push([x, y + r]);
        
        // Левый верхний угол
        for (let i = 0; i <= segments; i++) {
            const angle = Math.PI + (i / segments) * Math.PI / 2;
            points.push([
                x + r + r * Math.cos(angle),
                y + r + r * Math.sin(angle)
            ]);
        }
        
        return points;
    }

    /**
     * Окружность
     */
    static _circle(cx, cy, r, segments = 32) {
        const points = [];
        for (let i = 0; i <= segments; i++) {
            const angle = (i / segments) * 2 * Math.PI;
            points.push([
                cx + r * Math.cos(angle),
                cy + r * Math.sin(angle)
            ]);
        }
        return points;
    }
}
