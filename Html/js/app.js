/**
 * App — Главное приложение PictureToG-Code (Web)
 * Аналог ui/app.py
 * 
 * Связывает все модули и управляет UI логикой.
 */

class PictureToGCodeApp {
    constructor() {
        // Состояние
        this.imageProcessor = new ImageProcessor();
        this.chains = [];
        this.heightmap = null;
        this.currentGCode = '';
        this.currentDistDict = null;
        this.aspectLocked = true;
        this.lastAspectW = 0;
        this.lastAspectH = 0;
        this.viewer3D = null;
        this.current3DView = '2D'; // '2D' или '3D'

        // DOM элементы
        this.elements = {};

        this._initElements();
        this._bindEvents();
        this._loadSettings();
        this._updatePreviewSize();
    }

    /**
     * Инициализация DOM элементов
     */
    _initElements() {
        this.elements = {
            // Файлы
            imageInput: document.getElementById('imageInput'),
            btnOpenImage: document.getElementById('btnOpenImage'),
            imageInfo: document.getElementById('imageInfo'),

            // Режим
            modeRadios: document.querySelectorAll('input[name="mode"]'),

            // Шаблоны
            templateSelect: document.getElementById('templateSelect'),

            // Общие параметры
            toolDiameter: document.getElementById('toolDiameter'),
            feedrate: document.getElementById('feedrate'),
            depth: document.getElementById('depth'),
            numPasses: document.getElementById('numPasses'),
            safeZ: document.getElementById('safeZ'),
            spindleSpeed: document.getElementById('spindleSpeed'),

            // Контур
            contourParams: document.getElementById('contourParams'),
            simplifyEps: document.getElementById('simplifyEps'),
            threshold: document.getElementById('threshold'),
            thresholdValue: document.getElementById('thresholdValue'),
            blurSize: document.getElementById('blurSize'),
            minArea: document.getElementById('minArea'),
            approxFactor: document.getElementById('approxFactor'),
            invert: document.getElementById('invert'),
            bridgeMode: document.getElementById('bridgeMode'),
            bridgeSize: document.getElementById('bridgeSize'),
            bridgeCount: document.getElementById('bridgeCount'),
            btnPreviewThreshold: document.getElementById('btnPreviewThreshold'),
            smoothPasses: document.getElementById('smoothPasses'),
            resampleStep: document.getElementById('resampleStep'),

            // Рельеф
            reliefParams: document.getElementById('reliefParams'),
            strategy: document.getElementById('strategy'),
            stepoverPct: document.getElementById('stepoverPct'),
            plungeFeed: document.getElementById('plungeFeed'),
            blurRelief: document.getElementById('blurRelief'),

            // Размер вывода
            outputWidth: document.getElementById('outputWidth'),
            outputHeight: document.getElementById('outputHeight'),
            btnLockAspect: document.getElementById('btnLockAspect'),

            // Кнопки
            btnGenerate: document.getElementById('btnGenerate'),

            // Статистика
            statsSection: document.getElementById('statsSection'),
            statsContent: document.getElementById('statsContent'),

            // Превью
            previewCanvas: document.getElementById('previewCanvas'),
            previewInfo: document.getElementById('previewInfo'),
            previewPlaceholder: document.getElementById('previewPlaceholder'),

            // G-code панель
            gcodePanel: document.getElementById('gcodePanel'),
            gcodeOutput: document.getElementById('gcodeOutput'),
            btnCopyGCode: document.getElementById('btnCopyGCode'),
            btnSaveGCode2: document.getElementById('btnSaveGCode2'),

            // Модалка
            thresholdModal: document.getElementById('thresholdModal'),
            btnCloseModal: document.getElementById('btnCloseModal'),
            thresholdPreviewCanvas: document.getElementById('thresholdPreviewCanvas'),

            // Загрузка
            loadingOverlay: document.getElementById('loadingOverlay'),
            loadingText: document.getElementById('loadingText'),

            // 3D Viewer
            btn2DView: document.getElementById('btn2DView'),
            btn3DView: document.getElementById('btn3DView'),
            viewer3DContainer: document.getElementById('viewer3DContainer'),
            view3DButtons: document.getElementById('view3DButtons'),
            
            // Animation controls
            animationControls: document.getElementById('animationControls'),
            animationSlider: document.getElementById('animationSlider'),
            animationProgress: document.getElementById('animationProgress'),
        };
    }

    /**
     * Привязка событий
     */
    _bindEvents() {
        const el = this.elements;

        // Открытие изображения
        el.btnOpenImage.addEventListener('click', () => el.imageInput.click());
        el.imageInput.addEventListener('change', (e) => this._handleImageLoad(e));

        // Сохранение G-кода
        el.btnSaveGCode2.addEventListener('click', () => this._saveGCode());

        // Переключение режима
        el.modeRadios.forEach(radio => {
            radio.addEventListener('change', (e) => this._handleModeChange(e));
        });

        // Шаблон
        el.templateSelect.addEventListener('change', () => this._handleTemplateChange());

        // Порог — обновление значения
        el.threshold.addEventListener('input', () => {
            el.thresholdValue.textContent = el.threshold.value;
        });

        // Предпросмотр бинаризации
        el.btnPreviewThreshold.addEventListener('click', () => this._showBinaryPreview());

        // Блокировка пропорций
        el.btnLockAspect.addEventListener('click', () => this._toggleAspectLock());

        // Размер вывода — автопропорции
        el.outputWidth.addEventListener('input', () => this._handleSizeInput('width'));
        el.outputHeight.addEventListener('input', () => this._handleSizeInput('height'));

        // Генерация
        el.btnGenerate.addEventListener('click', () => this._generateGCode());

        // Копирование G-кода
        el.btnCopyGCode.addEventListener('click', () => this._copyGCode());

        // Закрытие модалки
        el.btnCloseModal.addEventListener('click', () => el.thresholdModal.classList.add('hidden'));
        el.thresholdModal.addEventListener('click', (e) => {
            if (e.target === el.thresholdModal) el.thresholdModal.classList.add('hidden');
        });

        // Изменение размера окна — перерисовка превью
        window.addEventListener('resize', () => this._redrawPreview());

        // ResizeObserver для контейнера превью — при показе/скрытии G-code панели
        if (typeof ResizeObserver !== 'undefined') {
            const previewContainer = this.elements.previewCanvas.parentElement;
            const resizeObserver = new ResizeObserver(() => this._redrawPreview());
            resizeObserver.observe(previewContainer);
        }

        // 3D View переключатели
        this.elements.btn2DView.addEventListener('click', () => this._switch2DView());
        this.elements.btn3DView.addEventListener('click', () => this._switch3DView());

        // 3D View кнопки камеры
        this.elements.view3DButtons.querySelectorAll('[data-view]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                if (this.viewer3D) {
                    this.viewer3D.setView(e.target.dataset.view);
                }
            });
        });

        // Animation controls - ползунок
        this.elements.animationSlider.addEventListener('input', (e) => {
            if (this.viewer3D) {
                const progress = parseFloat(e.target.value);
                this.viewer3D.setAnimationProgress(progress);
                this.elements.animationProgress.textContent = Math.round(progress) + '%';
            }
        });

        // Автосохранение при изменении параметров
        const allInputs = document.querySelectorAll('input, select, textarea');
        allInputs.forEach(input => {
            input.addEventListener('change', () => this._saveSettings());
        });
    }

    /**
     * Обработка загрузки изображения
     */
    async _handleImageLoad(event) {
        const file = event.target.files[0];
        if (!file) return;

        this._showLoading('Загрузка изображения...');

        try {
            const result = await this.imageProcessor.loadImage(file);

            // Сбрасываем предыдущие результаты
            this.chains = [];
            this.heightmap = null;
            this.currentGCode = '';
            this.currentDistDict = null;

            this.elements.imageInfo.textContent = `${file.name} — ${result.width}×${result.height}px`;
            this.elements.previewPlaceholder.classList.add('hidden');
            this.elements.btnGenerate.disabled = false;

            // Сбрасываем G-code панель
            this.elements.gcodeOutput.innerHTML = '<span class="gcode-comment">; Сгенерируйте G-код для отображения</span>';
            this.elements.statsContent.innerHTML = '';
            this.elements.statsContent.style.display = 'none';

            // Сохраняем пропорции
            this.lastAspectW = result.width;
            this.lastAspectH = result.height;

            // Сбрасываем шаблон
            this.elements.templateSelect.value = '(нет)';

            // Рисуем изображение
            this._redrawPreview();

            this._hideLoading();
        } catch (err) {
            this._hideLoading();
            alert(`Ошибка загрузки изображения: ${err.message}`);
        }
    }

    /**
     * Переключение режима
     */
    _handleModeChange(event) {
        const mode = event.target.value;
        const el = this.elements;

        if (mode === 'Контур') {
            el.contourParams.classList.remove('hidden');
            el.reliefParams.classList.add('hidden');
        } else {
            el.contourParams.classList.add('hidden');
            el.reliefParams.classList.remove('hidden');
        }

        this._redrawPreview();
    }

    /**
     * Обработка выбора шаблона
     */
    _handleTemplateChange() {
        const templateName = this.elements.templateSelect.value;
        
        if (templateName === '(нет)') {
            // Очищаем, если было изображение
            return;
        }

        const size = parseFloat(this.elements.outputWidth.value) || 50;
        this.chains = Templates.generate(templateName, size);
        
        if (this.chains.length > 0) {
            this.elements.previewPlaceholder.classList.add('hidden');
            this.elements.btnGenerate.disabled = false;
            this.elements.imageInfo.textContent = `Шаблон: ${templateName}`;
            this._redrawPreview();
        }
    }

    /**
     * Переключение блокировки пропорций
     */
    _toggleAspectLock() {
        this.aspectLocked = !this.aspectLocked;
        const btn = this.elements.btnLockAspect;
        btn.classList.toggle('locked', this.aspectLocked);
        btn.title = this.aspectLocked ? 'Сохранять пропорции' : 'Свободные пропорции';
    }

    /**
     * Обработка ввода размера
     */
    _handleSizeInput(source) {
        if (!this.aspectLocked) return;
        if (!this.lastAspectW || !this.lastAspectH) return;

        const el = this.elements;
        const aspect = this.lastAspectW / this.lastAspectH;

        if (source === 'width' && el.outputWidth.value) {
            el.outputHeight.value = Math.round(parseFloat(el.outputWidth.value) / aspect);
        } else if (source === 'height' && el.outputHeight.value) {
            el.outputWidth.value = Math.round(parseFloat(el.outputHeight.value) * aspect);
        }
    }

    /**
     * Перерисовка превью
     */
    _redrawPreview() {
        const canvas = this.elements.previewCanvas;
        const container = canvas.parentElement;
        const w = container.clientWidth;
        const h = container.clientHeight;

        if (w === 0 || h === 0) return;

        const mode = this._getMode();

        if (this.chains.length > 0 && mode === 'Контур') {
            PreviewRenderer.drawContours(canvas, this.chains, w, h);
            this.elements.previewInfo.textContent = `Контуров: ${this.chains.length}`;
        } else if (this.heightmap && mode === 'Рельеф') {
            PreviewRenderer.drawHeightmap(
                canvas, this.heightmap, 
                this.imageProcessor.width, this.imageProcessor.height, 
                w, h
            );
            this.elements.previewInfo.textContent = '';
        } else if (this.imageProcessor.originalImage) {
            PreviewRenderer.drawImage(
                canvas, 
                this.imageProcessor.originalImage, 
                w, h
            );
            this.elements.previewInfo.textContent = 
                `${this.imageProcessor.width}×${this.imageProcessor.height}px`;
        }
    }

    /**
     * Предпросмотр бинаризации
     */
    _showBinaryPreview() {
        if (!this.imageProcessor.grayscaleData) {
            alert('Сначала загрузите изображение');
            return;
        }

        const threshold = parseInt(this.elements.threshold.value);
        const invert = this.elements.invert.checked;
        const blurSize = parseInt(this.elements.blurSize.value) || 0;

        const imageData = this.imageProcessor.getBinaryPreview(threshold, invert, blurSize);
        if (!imageData) return;

        const modalCanvas = this.elements.thresholdPreviewCanvas;
        const modal = this.elements.thresholdModal;
        
        modal.classList.remove('hidden');
        
        // Рисуем с задержкой чтобы модалка успела отрендериться
        requestAnimationFrame(() => {
            const container = modalCanvas.parentElement;
            PreviewRenderer.drawBinaryPreview(
                modalCanvas, 
                imageData, 
                Math.min(container.clientWidth, 800),
                Math.min(container.clientHeight, 600)
            );
        });
    }

    /**
     * Генерация G-кода
     */
    async _generateGCode() {
        const mode = this._getMode();

        this._showLoading(mode === 'Контур' ? 'Генерация G-кода (контуры)...' : 'Генерация G-кода (рельеф)...');

        // Даём UI обновиться
        await new Promise(r => setTimeout(r, 50));

        try {
            if (mode === 'Контур') {
                this._generateContourGCode();
            } else {
                this._generateReliefGCode();
            }
        } catch (err) {
            this._hideLoading();
            alert(`Ошибка генерации G-кода: ${err.message}`);
            console.error(err);
            return;
        }

        this._hideLoading();
    }

    /**
     * Генерация контурного G-кода
     */
    _generateContourGCode() {
        const el = this.elements;
        let chains;

        // Если шаблон — используем его
        const templateName = el.templateSelect.value;
        if (templateName !== '(нет)') {
            const size = parseFloat(el.outputWidth.value) || 50;
            chains = Templates.generate(templateName, size);
        } else if (!this.imageProcessor.grayscaleData) {
            throw new Error('Загрузите изображение или выберите шаблон');
        } else {
            // Извлекаем контуры из изображения
            const threshold = parseInt(el.threshold.value);
            const invert = el.invert.checked;
            const blurSize = parseInt(el.blurSize.value) || 0;
            const minArea = parseInt(el.minArea.value) || 10;
            const approxFactor = parseFloat(el.approxFactor.value) || 0.001;

            // Бинаризация
            let data = this.imageProcessor.grayscaleData;
            if (blurSize > 0) {
                data = this.imageProcessor.gaussianBlur(
                    data, 
                    this.imageProcessor.width, 
                    this.imageProcessor.height, 
                    blurSize
                );
            }

            const binary = this.imageProcessor.threshold(data, threshold, invert);

            // Извлечение контуров
            const smoothPasses = parseInt(el.smoothPasses.value) || 0;
            const resampleStep = parseFloat(el.resampleStep.value) || 0;
            chains = this.imageProcessor.extractContours(
                binary,
                this.imageProcessor.width,
                this.imageProcessor.height,
                minArea,
                approxFactor,
                smoothPasses,
                resampleStep
            );

            if (chains.length === 0) {
                throw new Error('Не найдено контуров. Попробуйте изменить порог бинаризации.');
            }
        }

        // Масштабируем
        const outW = parseFloat(el.outputWidth.value) || null;
        const outH = parseFloat(el.outputHeight.value) || null;
        chains = Geometry.scaleChains(chains, outW, outH, this.aspectLocked);

        this.chains = chains;

        // Параметры для контурной резки (один проход)
        const params = {
            toolDia: parseFloat(el.toolDiameter.value),
            feedrate: parseFloat(el.feedrate.value),
            finalDepth: parseFloat(el.depth.value),
            simplifyEps: parseFloat(el.simplifyEps.value),
            safeZ: parseFloat(el.safeZ.value),
            spindleSpeed: parseFloat(el.spindleSpeed.value),
        };

        // Генерация
        const result = GCodeGenerator.chainsToGcode(chains, params);
        this._displayGCodeResult(result.gcode, result.distDict, params.feedrate);

        // Перерисовка превью контуров
        this._redrawPreview();
    }

    /**
     * Генерация рельефного G-кода
     */
    _generateReliefGCode() {
        const el = this.elements;

        if (!this.imageProcessor.grayscaleData) {
            throw new Error('Загрузите изображение для рельефа');
        }

        const blurSize = parseInt(el.blurRelief.value) || 0;
        this.heightmap = this.imageProcessor.getHeightmap(blurSize);

        const outW = parseFloat(el.outputWidth.value) || this.imageProcessor.width;
        const outH = parseFloat(el.outputHeight.value) || this.imageProcessor.height;

        const params = {
            toolDia: parseFloat(el.toolDiameter.value),
            stepoverPct: parseFloat(el.stepoverPct.value),
            maxDepth: parseFloat(el.depth.value),
            feedrate: parseFloat(el.feedrate.value),
            plungeFeed: parseFloat(el.plungeFeed.value),
            safeZ: parseFloat(el.safeZ.value),
            outputW: outW,
            outputH: outH,
            strategy: el.strategy.value,
            spindleSpeed: parseFloat(el.spindleSpeed.value),
        };

        const result = GCodeGenerator.heightmapToGcode(
            this.heightmap,
            this.imageProcessor.width,
            this.imageProcessor.height,
            params
        );

        this._displayGCodeResult(result.gcode, result.distDict, params.feedrate);

        // Перерисовка превью
        this._redrawPreview();
    }

    /**
     * Отображение результата G-кода
     */
    _displayGCodeResult(gcode, distDict, feedrate) {
        this.currentGCode = gcode;
        this.currentDistDict = distDict;

        // Отображаем G-код с подсветкой синтаксиса
        this.elements.gcodeOutput.innerHTML = GCodeGenerator.highlightGcode(gcode);

        // Статистика
        const totalTime = GCodeGenerator.formatTimeEstimate(distDict, feedrate);
        const totalDist = ((distDict.rapid_dist + distDict.feed_dist) / 1000).toFixed(2);

        this.elements.statsContent.innerHTML = `
            <div class="stat-row">
                <span class="stat-label">Время обработки:</span>
                <span class="stat-value">${totalTime}</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Общий путь:</span>
                <span class="stat-value">${totalDist} м</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Холостой ход:</span>
                <span class="stat-value">${(distDict.rapid_dist / 1000).toFixed(3)} м</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Рабочий ход:</span>
                <span class="stat-value">${(distDict.feed_dist / 1000).toFixed(3)} м</span>
            </div>
        `;
        this.elements.statsContent.style.display = 'block';

        // Обновляем 3D визуализацию если она активна
        if (this.current3DView === '3D' && this.viewer3D) {
            this.viewer3D.loadGCode(gcode);
        }
    }

    /**
     * Сохранение G-кода в файл
     */
    _saveGCode() {
        if (!this.currentGCode) {
            alert('Сначала сгенерируйте G-код');
            return;
        }

        const blob = new Blob([this.currentGCode], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'output.nc';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    /**
     * Копирование G-кода в буфер
     */
    async _copyGCode() {
        if (!this.currentGCode) return;
        
        try {
            await navigator.clipboard.writeText(this.currentGCode);
            const btn = this.elements.btnCopyGCode;
            const originalText = btn.textContent;
            btn.textContent = '✓ Скопировано!';
            setTimeout(() => btn.textContent = originalText, 1500);
        } catch (err) {
            // Fallback для старых браузеров
            const textarea = document.createElement('textarea');
            textarea.value = this.currentGCode;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
    }

    /**
     * Получить текущий режим
     */
    _getMode() {
        const checked = document.querySelector('input[name="mode"]:checked');
        return checked ? checked.value : 'Контур';
    }

    /**
     * Обновить размер вывода при старте
     */
    _updatePreviewSize() {
        // Если есть изображение и размеры пустые — предлагаем 1px = 1mm
        if (this.lastAspectW && this.lastAspectH) {
            // Оставляем пустым для автоматического режима
        }
    }

    /**
     * Показать индикатор загрузки
     */
    _showLoading(text) {
        this.elements.loadingText.textContent = text || 'Обработка...';
        this.elements.loadingOverlay.classList.remove('hidden');
    }

    /**
     * Скрыть индикатор загрузки
     */
    _hideLoading() {
        this.elements.loadingOverlay.classList.add('hidden');
    }

    /**
     * Сохранение настроек в localStorage
     */
    _saveSettings() {
        const el = this.elements;
        const settings = {
            toolDiameter: el.toolDiameter.value,
            feedrate: el.feedrate.value,
            depth: el.depth.value,
            numPasses: el.numPasses.value,
            safeZ: el.safeZ.value,
            spindleSpeed: el.spindleSpeed.value,
            simplifyEps: el.simplifyEps.value,
            threshold: el.threshold.value,
            blurSize: el.blurSize.value,
            minArea: el.minArea.value,
            approxFactor: el.approxFactor.value,
            invert: el.invert.checked,
            bridgeMode: el.bridgeMode.checked,
            bridgeSize: el.bridgeSize.value,
            bridgeCount: el.bridgeCount.value,
            smoothPasses: el.smoothPasses.value,
            resampleStep: el.resampleStep.value,
            stepoverPct: el.stepoverPct.value,
            plungeFeed: el.plungeFeed.value,
            blurRelief: el.blurRelief.value,
            strategy: el.strategy.value,
            mode: this._getMode(),
            template: el.templateSelect.value,
            outputWidth: el.outputWidth.value,
            outputHeight: el.outputHeight.value,
            lockAspect: this.aspectLocked,
        };

        try {
            localStorage.setItem('pictureToGCodeSettings', JSON.stringify(settings));
        } catch (e) {
            console.warn('Не удалось сохранить настройки:', e);
        }
    }

    /**
     * Загрузка настроек из localStorage
     */
    _loadSettings() {
        let settings;
        try {
            const raw = localStorage.getItem('pictureToGCodeSettings');
            if (raw) settings = JSON.parse(raw);
        } catch (e) {
            console.warn('Не удалось загрузить настройки:', e);
        }

        if (!settings) return;

        const el = this.elements;

        // Восстанавливаем значения
        if (settings.toolDiameter) el.toolDiameter.value = settings.toolDiameter;
        if (settings.feedrate) el.feedrate.value = settings.feedrate;
        if (settings.depth) el.depth.value = settings.depth;
        if (settings.numPasses) el.numPasses.value = settings.numPasses;
        if (settings.safeZ) el.safeZ.value = settings.safeZ;
        if (settings.spindleSpeed) el.spindleSpeed.value = settings.spindleSpeed;
        if (settings.simplifyEps) el.simplifyEps.value = settings.simplifyEps;
        if (settings.threshold) {
            el.threshold.value = settings.threshold;
            el.thresholdValue.textContent = settings.threshold;
        }
        if (settings.blurSize) el.blurSize.value = settings.blurSize;
        if (settings.minArea) el.minArea.value = settings.minArea;
        if (settings.approxFactor) el.approxFactor.value = settings.approxFactor;
        if (settings.invert !== undefined) el.invert.checked = settings.invert;
        if (settings.bridgeMode !== undefined) el.bridgeMode.checked = settings.bridgeMode;
        if (settings.bridgeSize) el.bridgeSize.value = settings.bridgeSize;
        if (settings.bridgeCount) el.bridgeCount.value = settings.bridgeCount;
        if (settings.smoothPasses !== undefined) el.smoothPasses.value = settings.smoothPasses;
        if (settings.resampleStep !== undefined) el.resampleStep.value = settings.resampleStep;
        if (settings.stepoverPct) el.stepoverPct.value = settings.stepoverPct;
        if (settings.plungeFeed) el.plungeFeed.value = settings.plungeFeed;
        if (settings.blurRelief) el.blurRelief.value = settings.blurRelief;
        if (settings.strategy) el.strategy.value = settings.strategy;
        if (settings.template) el.templateSelect.value = settings.template;
        if (settings.outputWidth !== undefined) el.outputWidth.value = settings.outputWidth;
        if (settings.outputHeight !== undefined) el.outputHeight.value = settings.outputHeight;
        if (settings.lockAspect !== undefined) {
            this.aspectLocked = settings.lockAspect;
            el.btnLockAspect.classList.toggle('locked', this.aspectLocked);
        }

        // Режим
        if (settings.mode) {
            const radio = document.querySelector(`input[name="mode"][value="${settings.mode}"]`);
            if (radio) {
                radio.checked = true;
                this._handleModeChange({ target: radio });
            }
        }
    }

    /**
     * Переключение на 2D вид
     */
    _switch2DView() {
        this.current3DView = '2D';
        this.elements.btn2DView.classList.add('active');
        this.elements.btn3DView.classList.remove('active');
        this.elements.previewCanvas.classList.remove('hidden');
        this.elements.viewer3DContainer.classList.add('hidden');
        this.elements.view3DButtons.classList.add('hidden');
        this.elements.animationControls.classList.add('hidden');

        // Очищаем 3D viewer
        if (this.viewer3D) {
            this.viewer3D.dispose();
            this.viewer3D = null;
        }

        this._redrawPreview();
    }

    /**
     * Переключение на 3D вид
     */
    _switch3DView() {
        if (!this.currentGCode) {
            alert('Сначала сгенерируйте G-код');
            return;
        }

        this.current3DView = '3D';
        this.elements.btn2DView.classList.remove('active');
        this.elements.btn3DView.classList.add('active');
        this.elements.previewCanvas.classList.add('hidden');
        this.elements.viewer3DContainer.classList.remove('hidden');
        this.elements.view3DButtons.classList.remove('hidden');
        this.elements.animationControls.classList.remove('hidden');

        // Инициализируем 3D viewer
        if (!this.viewer3D) {
            this.viewer3D = new GCodeViewer3D(this.elements.viewer3DContainer);
            
            // Устанавливаем callback для подсветки строк G-кода
            this.viewer3D.onLineChange = (lineIndex) => {
                this._highlightGCodeLine(lineIndex);
            };
        }

        // Загружаем G-код
        this.viewer3D.loadGCode(this.currentGCode);
        
        // Сбрасываем анимацию
        this.elements.animationSlider.value = 0;
        this.elements.animationProgress.textContent = '0%';
    }

    /**
     * Подсветка строки G-кода
     */
    _highlightGCodeLine(lineIndex) {
        const gcodeOutput = this.elements.gcodeOutput;
        const lines = gcodeOutput.querySelectorAll('.gcode-line');
        
        // Убираем предыдущую подсветку
        lines.forEach(line => line.classList.remove('gcode-line-active'));
        
        // Подсвечиваем текущую строку
        if (lines[lineIndex]) {
            lines[lineIndex].classList.add('gcode-line-active');
            
            // Прокручиваем к текущей строке
            lines[lineIndex].scrollIntoView({ 
                behavior: 'smooth', 
                block: 'center' 
            });
        }
    }
}

// Инициализация приложения при загрузке DOM
document.addEventListener('DOMContentLoaded', () => {
    window.app = new PictureToGCodeApp();
});
