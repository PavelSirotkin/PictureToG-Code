/**
 * Preview — Отрисовка превью на Canvas
 * Аналог ui/preview.py
 * 
 * Реализует:
 * - Отрисовку контуров
 * - Отрисовку карты высот (рельеф)
 * - Отрисовку бинаризации
 */

class PreviewRenderer {
    /**
     * Отрисовка контуров на canvas
     * @param {HTMLCanvasElement} canvas 
     * @param {Array<Array<[number, number]>>} chains 
     * @param {number} canvasW 
     * @param {number} canvasH 
     */
    static drawContours(canvas, chains, canvasW, canvasH) {
        const ctx = canvas.getContext('2d');
        canvas.width = canvasW;
        canvas.height = canvasH;
        
        // Очистка
        ctx.fillStyle = '#1a1a2e';
        ctx.fillRect(0, 0, canvasW, canvasH);
        
        if (!chains || chains.length === 0) return;
        
        // Получаем bounding box
        const [minX, minY, maxX, maxY] = Geometry.getBounds(chains);
        const srcW = maxX - minX || 1;
        const srcH = maxY - minY || 1;
        
        // Масштабируем с сохранением пропорций и отступами
        const padding = 30;
        const availW = canvasW - padding * 2;
        const availH = canvasH - padding * 2;
        const scale = Math.min(availW / srcW, availH / srcH);
        
        const offsetX = (canvasW - srcW * scale) / 2;
        const offsetY = (canvasH - srcH * scale) / 2;
        
        // Рисуем сетку
        PreviewRenderer._drawGrid(ctx, canvasW, canvasH);
        
        // Рисуем контуры
        ctx.lineWidth = 1.5;
        
        for (let ci = 0; ci < chains.length; ci++) {
            const chain = chains[ci];
            
            // Цвет в зависимости от порядка
            const hue = (ci * 37) % 360;
            ctx.strokeStyle = `hsl(${hue}, 70%, 65%)`;
            ctx.fillStyle = `hsla(${hue}, 70%, 65%, 0.1)`;
            
            ctx.beginPath();
            for (let i = 0; i < chain.length; i++) {
                const x = (chain[i][0] - minX) * scale + offsetX;
                const y = canvasH - ((chain[i][1] - minY) * scale + offsetY); // Y инвертирован
                
                if (i === 0) {
                    ctx.moveTo(x, y);
                } else {
                    ctx.lineTo(x, y);
                }
            }
            ctx.closePath();
            ctx.fill();
            ctx.stroke();
        }
        
        // Рисуем bounding box
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
        ctx.lineWidth = 1;
        ctx.setLineDash([5, 5]);
        ctx.strokeRect(offsetX, offsetY, srcW * scale, srcH * scale);
        ctx.setLineDash([]);
    }

    /**
     * Отрисовка карты высот
     * @param {HTMLCanvasElement} canvas 
     * @param {Uint8Array} heightmap 
     * @param {number} imgW 
     * @param {number} imgH 
     * @param {number} canvasW 
     * @param {number} canvasH 
     */
    static drawHeightmap(canvas, heightmap, imgW, imgH, canvasW, canvasH) {
        const ctx = canvas.getContext('2d');
        canvas.width = canvasW;
        canvas.height = canvasH;
        
        // Создаём изображение из карты высот
        const imageData = ctx.createImageData(imgW, imgH);
        const data = imageData.data;
        
        for (let i = 0; i < heightmap.length; i++) {
            const val = heightmap[i];
            // Цветовая схема: тёмное = глубже (синий), светлое = выше (жёлтый)
            const idx = i * 4;
            
            // Градиент от синего к жёлтому через зелёный
            const t = val / 255;
            if (t < 0.5) {
                const s = t * 2;
                data[idx] = Math.round(30 * (1 - s) + 0 * s);     // R
                data[idx + 1] = Math.round(50 * (1 - s) + 180 * s); // G
                data[idx + 2] = Math.round(180 * (1 - s) + 100 * s); // B
            } else {
                const s = (t - 0.5) * 2;
                data[idx] = Math.round(0 * (1 - s) + 255 * s);
                data[idx + 1] = Math.round(180 * (1 - s) + 255 * s);
                data[idx + 2] = Math.round(100 * (1 - s) + 100 * s);
            }
            data[idx + 3] = 255;
        }
        
        // Рисуем с масштабированием
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = imgW;
        tempCanvas.height = imgH;
        const tempCtx = tempCanvas.getContext('2d');
        tempCtx.putImageData(imageData, 0, 0);
        
        // Очистка
        ctx.fillStyle = '#1a1a2e';
        ctx.fillRect(0, 0, canvasW, canvasH);
        
        // Масштабируем с сохранением пропорций
        const padding = 10;
        const availW = canvasW - padding * 2;
        const availH = canvasH - padding * 2;
        const scale = Math.min(availW / imgW, availH / imgH);
        const drawW = imgW * scale;
        const drawH = imgH * scale;
        const offsetX = (canvasW - drawW) / 2;
        const offsetY = (canvasH - drawH) / 2;
        
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(tempCanvas, offsetX, offsetY, drawW, drawH);
        
        // Подпись
        ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
        ctx.font = '11px Segoe UI';
        ctx.fillText(`Карта высот: ${imgW}×${imgH}px`, 10, canvasH - 10);
    }

    /**
     * Отрисовка бинаризации
     * @param {HTMLCanvasElement} canvas 
     * @param {ImageData} binaryImageData 
     * @param {number} canvasW 
     * @param {number} canvasH 
     */
    static drawBinaryPreview(canvas, binaryImageData, canvasW, canvasH) {
        const ctx = canvas.getContext('2d');
        canvas.width = canvasW;
        canvas.height = canvasH;
        
        // Очистка
        ctx.fillStyle = '#1a1a2e';
        ctx.fillRect(0, 0, canvasW, canvasH);
        
        const imgW = binaryImageData.width;
        const imgH = binaryImageData.height;
        
        // Масштабируем
        const padding = 10;
        const availW = canvasW - padding * 2;
        const availH = canvasH - padding * 2;
        const scale = Math.min(availW / imgW, availH / imgH);
        const drawW = imgW * scale;
        const drawH = imgH * scale;
        const offsetX = (canvasW - drawW) / 2;
        const offsetY = (canvasH - drawH) / 2;
        
        // Рисуем бинаризованное изображение
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = imgW;
        tempCanvas.height = imgH;
        const tempCtx = tempCanvas.getContext('2d');
        tempCtx.putImageData(binaryImageData, 0, 0);
        
        ctx.imageSmoothingEnabled = false; // pixelated для бинаризации
        ctx.drawImage(tempCanvas, offsetX, offsetY, drawW, drawH);
        
        // Подпись
        ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
        ctx.font = '11px Segoe UI';
        ctx.fillText(`Бинаризация: ${imgW}×${imgH}px`, 10, canvasH - 10);
    }

    /**
     * Отрисовка исходного изображения
     * @param {HTMLCanvasElement} canvas 
     * @param {HTMLImageElement} image 
     * @param {number} canvasW 
     * @param {number} canvasH 
     */
    static drawImage(canvas, image, canvasW, canvasH) {
        const ctx = canvas.getContext('2d');
        canvas.width = canvasW;
        canvas.height = canvasH;
        
        // Очистка
        ctx.fillStyle = '#1a1a2e';
        ctx.fillRect(0, 0, canvasW, canvasH);
        
        // Масштабируем с сохранением пропорций
        const padding = 10;
        const availW = canvasW - padding * 2;
        const availH = canvasH - padding * 2;
        const scaleX = availW / image.width;
        const scaleY = availH / image.height;
        const scale = Math.min(scaleX, scaleY);
        const drawW = image.width * scale;
        const drawH = image.height * scale;
        const offsetX = (canvasW - drawW) / 2;
        const offsetY = (canvasH - drawH) / 2;
        
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(image, offsetX, offsetY, drawW, drawH);
    }

    /**
     * Отрисовка сетки
     */
    static _drawGrid(ctx, canvasW, canvasH) {
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
        ctx.lineWidth = 1;
        
        const gridSize = 50;
        
        for (let x = 0; x < canvasW; x += gridSize) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, canvasH);
            ctx.stroke();
        }
        
        for (let y = 0; y < canvasH; y += gridSize) {
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(canvasW, y);
            ctx.stroke();
        }
    }
}
