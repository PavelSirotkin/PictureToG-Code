/**
 * Viewer3D — 3D визуализация G-кода с использованием Three.js
 * 
 * Парсит G-код и отображает траекторию инструмента в 3D с анимацией
 */

class GCodeViewer3D {
    constructor(container) {
        this.container = container;
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        this.toolpathGroup = null;
        this.animationFrame = null;
        this.parsedPath = [];
        
        // Анимация
        this.isPlaying = false;
        this.animationProgress = 0;
        this.rapidLines = null;
        this.feedLines = null;
        this.completedFeedLines = null;
        
        this._init();
    }

    /**
     * Инициализация Three.js сцены
     */
    _init() {
        // Сцена
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x1a1a2e);

        // Камера
        const aspect = this.container.clientWidth / this.container.clientHeight;
        this.camera = new THREE.PerspectiveCamera(45, aspect, 0.1, 10000);
        this.camera.position.set(100, 100, 100);
        this.camera.lookAt(0, 0, 0);

        // Рендерер
        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.container.appendChild(this.renderer.domElement);

        // Освещение
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        this.scene.add(ambientLight);

        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
        directionalLight.position.set(50, 100, 50);
        this.scene.add(directionalLight);

        // Оси координат
        const axesHelper = new THREE.AxesHelper(50);
        this.scene.add(axesHelper);

        // Сетка
        const gridHelper = new THREE.GridHelper(200, 20, 0x444444, 0x222222);
        this.scene.add(gridHelper);

        // Orbit Controls (без сглаживания для быстрой отрисовки)
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = false;
        this.controls.screenSpacePanning = false;
        this.controls.minDistance = 10;
        this.controls.maxDistance = 500;

        // Группа для траектории
        this.toolpathGroup = new THREE.Group();
        this.scene.add(this.toolpathGroup);

        // Обработка изменения размера
        window.addEventListener('resize', () => this._onResize());

        // Запуск рендеринга
        this._animate();
    }

    /**
     * Парсинг G-кода и построение 3D траектории
     */
    loadGCode(gcode) {
        // Очистка предыдущей траектории
        this._clearToolpath();
        this.parsedPath = [];
        this.gcodeLines = gcode.split('\n');
        this.animationProgress = 0;
        this.isPlaying = false;

        const lines = this.gcodeLines;
        let currentPos = { x: 0, y: 0, z: 5 };
        let isSpindleOn = false;
        let lineIndex = 0;

        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith(';')) continue;

            // Удаляем комментарии
            const cleanLine = trimmed.split(';')[0].trim();
            if (!cleanLine) continue;

            // Парсим команду
            const cmd = this._parseGCodeLine(cleanLine);
            if (!cmd) continue;

            // Обработка команд
            if (cmd.type === 'M03') {
                isSpindleOn = true;
            } else if (cmd.type === 'M05') {
                isSpindleOn = false;
            } else if (cmd.type === 'G0' || cmd.type === 'G1') {
                const newPos = {
                    x: cmd.x !== undefined ? cmd.x : currentPos.x,
                    y: cmd.y !== undefined ? cmd.y : currentPos.y,
                    z: cmd.z !== undefined ? cmd.z : currentPos.z
                };

                // Добавляем сегмент с номером строки
                this.parsedPath.push({
                    from: { ...currentPos },
                    to: { ...newPos },
                    type: cmd.type,
                    isSpindleOn: isSpindleOn,
                    lineIndex: lineIndex
                });

                currentPos = newPos;
            }
            lineIndex++;
        }

        // Строим 3D модель
        this._buildToolpath();
        this._fitCameraToPath();
    }

    /**
     * Парсинг строки G-кода
     */
    _parseGCodeLine(line) {
        const tokens = line.split(/\s+/);
        const cmd = { type: null };

        for (const token of tokens) {
            const letter = token[0];
            const value = parseFloat(token.substring(1));

            if (letter === 'G' || letter === 'M') {
                cmd.type = token;
            } else if (letter === 'X') {
                cmd.x = value;
            } else if (letter === 'Y') {
                cmd.y = value;
            } else if (letter === 'Z') {
                cmd.z = value;
            } else if (letter === 'F') {
                cmd.f = value;
            }
        }

        return cmd.type ? cmd : null;
    }

    /**
     * Построение 3D траектории (упрощенная цветовая схема)
     */
    _buildToolpath() {
        // Группируем сегменты по типу
        const rapidPoints = [];
        const feedPoints = [];

        for (const segment of this.parsedPath) {
            const from = new THREE.Vector3(segment.from.x, segment.from.z, -segment.from.y);
            const to = new THREE.Vector3(segment.to.x, segment.to.z, -segment.to.y);

            if (segment.type === 'G0') {
                rapidPoints.push(from, to);
            } else {
                feedPoints.push(from, to);
            }
        }

        // Холостой ход (синий, полупрозрачный)
        if (rapidPoints.length > 0) {
            const geometry = new THREE.BufferGeometry().setFromPoints(rapidPoints);
            const material = new THREE.LineBasicMaterial({ 
                color: 0x4a9eff, 
                opacity: 0.3,
                transparent: true
            });
            this.rapidLines = new THREE.LineSegments(geometry, material);
            this.toolpathGroup.add(this.rapidLines);
        }

        // Рабочий ход (серый - не выполнено)
        if (feedPoints.length > 0) {
            const geometry = new THREE.BufferGeometry().setFromPoints(feedPoints);
            const material = new THREE.LineBasicMaterial({ 
                color: 0x555555
            });
            this.feedLines = new THREE.LineSegments(geometry, material);
            this.toolpathGroup.add(this.feedLines);

            // Создаём копию для выполненных сегментов (зелёный)
            const completedGeometry = new THREE.BufferGeometry().setFromPoints(feedPoints);
            const completedMaterial = new THREE.LineBasicMaterial({ 
                color: 0x00ff88
            });
            this.completedFeedLines = new THREE.LineSegments(completedGeometry, completedMaterial);
            this.completedFeedLines.geometry.setDrawRange(0, 0); // Изначально ничего не рисуем
            this.toolpathGroup.add(this.completedFeedLines);
        }

        // Добавляем точки начала и конца
        this._addMarker(this.parsedPath[0].from, 0x00ff00, 2); // Начало - зелёный
        const lastSegment = this.parsedPath[this.parsedPath.length - 1];
        this._addMarker(lastSegment.to, 0xff0000, 2); // Конец - красный
    }

    /**
     * Добавление маркера (сфера)
     */
    _addMarker(pos, color, size) {
        const geometry = new THREE.SphereGeometry(size, 16, 16);
        const material = new THREE.MeshBasicMaterial({ color: color });
        const sphere = new THREE.Mesh(geometry, material);
        sphere.position.set(pos.x, pos.z, -pos.y);
        this.toolpathGroup.add(sphere);
    }

    /**
     * Очистка траектории
     */
    _clearToolpath() {
        while (this.toolpathGroup.children.length > 0) {
            const child = this.toolpathGroup.children[0];
            if (child.geometry) child.geometry.dispose();
            if (child.material) child.material.dispose();
            this.toolpathGroup.remove(child);
        }
        this.rapidLines = null;
        this.feedLines = null;
        this.completedFeedLines = null;
    }

    /**
     * Подгонка камеры под траекторию
     */
    _fitCameraToPath() {
        if (this.parsedPath.length === 0) return;

        // Вычисляем bounding box
        let minX = Infinity, minY = Infinity, minZ = Infinity;
        let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;

        for (const segment of this.parsedPath) {
            for (const pos of [segment.from, segment.to]) {
                minX = Math.min(minX, pos.x);
                minY = Math.min(minY, pos.y);
                minZ = Math.min(minZ, pos.z);
                maxX = Math.max(maxX, pos.x);
                maxY = Math.max(maxY, pos.y);
                maxZ = Math.max(maxZ, pos.z);
            }
        }

        const centerX = (minX + maxX) / 2;
        const centerY = (minY + maxY) / 2;
        const centerZ = (minZ + maxZ) / 2;

        const sizeX = maxX - minX;
        const sizeY = maxY - minY;
        const sizeZ = maxZ - minZ;
        const maxSize = Math.max(sizeX, sizeY, sizeZ);

        // Позиционируем камеру (изометрия по умолчанию)
        const distance = maxSize * 1.5;
        this.camera.position.set(
            centerX + distance * 0.7,
            centerZ + distance * 0.7,
            -centerY + distance * 0.7
        );

        this.controls.target.set(centerX, centerZ, -centerY);
        this.controls.update();
    }

    /**
     * Установка вида камеры
     */
    setView(viewType) {
        if (this.parsedPath.length === 0) return;

        const target = this.controls.target;
        const distance = 150;

        switch (viewType) {
            case 'top':
                this.camera.position.set(target.x, target.y + distance, target.z);
                break;
            case 'front':
                this.camera.position.set(target.x, target.y, target.z + distance);
                break;
            case 'side':
                this.camera.position.set(target.x + distance, target.y, target.z);
                break;
            case 'iso':
                this.camera.position.set(
                    target.x + distance * 0.7,
                    target.y + distance * 0.7,
                    target.z + distance * 0.7
                );
                break;
        }

        this.controls.update();
    }

    /**
     * Установка прогресса анимации (0-100)
     */
    setAnimationProgress(progress) {
        this.animationProgress = Math.max(0, Math.min(100, progress));
        this._updateAnimation();
    }

    /**
     * Обновление визуализации анимации
     */
    _updateAnimation() {
        if (!this.completedFeedLines || !this.feedLines) return;

        // Считаем количество рабочих сегментов
        const feedSegmentCount = this.parsedPath.filter(s => s.type === 'G1').length;
        const completedSegments = Math.floor((this.animationProgress / 100) * feedSegmentCount);

        // Обновляем диапазон отрисовки
        this.completedFeedLines.geometry.setDrawRange(0, completedSegments * 2);
        
        // Вызываем callback для обновления строки G-кода
        if (this.onLineChange) {
            const currentLineIndex = this._getCurrentLineIndex(completedSegments);
            this.onLineChange(currentLineIndex);
        }
    }

    /**
     * Получить индекс текущей строки G-кода по количеству выполненных сегментов
     */
    _getCurrentLineIndex(completedSegments) {
        if (completedSegments === 0) return 0;
        
        let feedSegmentIndex = 0;
        for (let i = 0; i < this.parsedPath.length; i++) {
            if (this.parsedPath[i].type === 'G1') {
                if (feedSegmentIndex >= completedSegments) {
                    return this.parsedPath[i].lineIndex;
                }
                feedSegmentIndex++;
            }
        }
        
        return this.gcodeLines.length - 1;
    }


    /**
     * Обработка изменения размера
     */
    _onResize() {
        if (!this.container.clientWidth || !this.container.clientHeight) return;

        const width = this.container.clientWidth;
        const height = this.container.clientHeight;

        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }

    /**
     * Анимация
     */
    _animate() {
        this.animationFrame = requestAnimationFrame(() => this._animate());
        this.controls.update();
        this.renderer.render(this.scene, this.camera);
    }

    /**
     * Очистка ресурсов
     */
    dispose() {
        if (this.animationFrame) {
            cancelAnimationFrame(this.animationFrame);
        }
        
        this.isPlaying = false;
        this._clearToolpath();
        
        if (this.renderer) {
            this.renderer.dispose();
            if (this.renderer.domElement.parentNode) {
                this.renderer.domElement.parentNode.removeChild(this.renderer.domElement);
            }
        }
        
        if (this.controls) {
            this.controls.dispose();
        }
    }
}
