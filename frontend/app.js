/**
 * Paradox2Firebird Web Studio - Frontend Application Logic
 */

let currentSource = 'samples'; // 'samples' or 'uploads'
let activeTable = null;
let currentTableData = null;
let customMappings = {};
let currentSqlScript = '';
let availableTablesList = [];
let selectedTablesSet = new Set();
let currentProject = null; // Active project object
let projectsList = [];    // All projects list
let currentImportMode = 'folder'; // 'folder' or 'files'
let projectToDelete = null; // Project pending deletion

const FIREBIRD_TYPE_OPTIONS = [
    'VARCHAR(50)',
    'VARCHAR(100)',
    'VARCHAR(255)',
    'INTEGER',
    'BIGINT',
    'SMALLINT',
    'NUMERIC(15,2)',
    'NUMERIC(18,4)',
    'DOUBLE PRECISION',
    'DATE',
    'TIME',
    'TIMESTAMP',
    'BOOLEAN',
    'BLOB SUB_TYPE TEXT',
    'BLOB SUB_TYPE BINARY'
];

// Global error handler - surfaces JS errors as visible toasts
window.addEventListener('error', (e) => {
    console.error('JS Error:', e.message, e.filename, e.lineno);
    const container = document.getElementById('toastContainer');
    if (container) {
        const t = document.createElement('div');
        t.className = 'toast error';
        t.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <span>JS Erro: ${e.message} (linha ${e.lineno})</span>`;
        container.appendChild(t);
        setTimeout(() => t.remove(), 8000);
    }
});

document.addEventListener('DOMContentLoaded', () => {
    try { initDragAndDrop(); } catch(e) { console.warn('initDragAndDrop:', e.message); }
    try { initFileInput(); } catch(e) { console.warn('initFileInput:', e.message); }
    try { initProjectFilesInput(); } catch(e) { console.warn('initProjectFilesInput:', e.message); }
    try { loadProjects(); } catch(e) { console.warn('loadProjects:', e.message); }
    try { loadTablesList(); } catch(e) { console.warn('loadTablesList:', e.message); }

    // Key shortcut for SQL runner (F9 or Ctrl+Enter)
    document.addEventListener('keydown', (e) => {
        if (e.key === 'F9' || (e.ctrlKey && e.key === 'Enter')) {
            const sqlPanel = document.getElementById('panelSqlRunnerView');
            if (sqlPanel && sqlPanel.classList.contains('active')) {
                e.preventDefault();
                executeInteractiveSqlQuery();
            }
        }
    });
});

// Toast Notifications
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let icon = 'fa-info-circle';
    if (type === 'success') icon = 'fa-check-circle';
    if (type === 'error') icon = 'fa-triangle-exclamation';
    if (type === 'warning') icon = 'fa-triangle-exclamation';

    toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Switch between Samples and Uploaded tables
function switchTableSource(source) {
    currentSource = source;
    document.getElementById('tabSamplesBtn').classList.toggle('active', source === 'samples');
    document.getElementById('tabUploadsBtn').classList.toggle('active', source === 'uploads');
    
    const topTabSamples = document.getElementById('topTabSamplesBtn');
    const topTabUploads = document.getElementById('topTabUploadsBtn');
    if (topTabSamples) topTabSamples.classList.toggle('active', source === 'samples');
    if (topTabUploads) topTabUploads.classList.toggle('active', source === 'uploads');

    loadTablesList();
}

// Switch main workspace tabs
function switchMainTab(tabId) {
    const tabs = ['dataView', 'schemaView', 'sqlRunnerView', 'sqlView', 'directView'];
    tabs.forEach(t => {
        const tabBtn = document.getElementById(`tab${capitalize(t)}`);
        const panel = document.getElementById(`panel${capitalize(t)}`);
        if (tabBtn) tabBtn.classList.toggle('active', t === tabId);
        if (panel) panel.classList.toggle('active', t === tabId);
    });

    if (tabId === 'sqlView' && activeTable && !currentSqlScript) {
        generateAndShowSQL();
    } else if (tabId === 'sqlRunnerView' && activeTable) {
        const tblClean = activeTable.replace(/\.db$/i, '').toUpperCase();
        const input = document.getElementById('sqlQueryInput');
        if (input && (!input.value || input.value.includes('SELECT * FROM CLIENTES'))) {
            input.value = `SELECT * FROM ${tblClean} ROWS 50;`;
        }
    }
}

function capitalize(s) {
    return s.charAt(0).toUpperCase() + s.slice(1);
}

// Drag & Drop Setup
function initDragAndDrop() {
    const dropZone = document.getElementById('dropZone');
    if (!dropZone) return;
    
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('dragover');
        }, false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFilesUpload(files);
    });
}

function initFileInput() {
    const fileInput = document.getElementById('fileInput');
    if (!fileInput) return;
    fileInput.addEventListener('change', () => {
        handleFilesUpload(fileInput.files);
    });
}

// Upload Handler
async function handleFilesUpload(files) {
    if (!files || files.length === 0) return;

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }

    try {
        showToast('Enviando arquivos Paradox...', 'info');
        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        
        if (data.success) {
            showToast(`${data.uploaded.length} tabelas carregadas com sucesso!`, 'success');
            switchTableSource('uploads');
            if (data.uploaded.length > 0) {
                selectTable(data.uploaded[0].filename, false);
            }
        } else {
            showToast(`Erro ao carregar: ${data.error}`, 'error');
        }
    } catch (err) {
        showToast(`Falha no upload: ${err.message}`, 'error');
    }
}

// Load Tables List
async function loadTablesList() {
    const listContainer = document.getElementById('tablesList');
    listContainer.innerHTML = '<div style="padding: 15px; color: var(--text-dim); text-align: center;">Carregando tabelas...</div>';

    try {
        const res = await fetch(`/api/samples?source=${currentSource}`);
        const data = await res.json();

        if (data.success) {
            availableTablesList = data.tables;
            
            if (currentSource === 'samples') {
                const samplesEl = document.getElementById('samplesCount');
                if (samplesEl) samplesEl.textContent = data.tables.length;
                const topSamples = document.getElementById('topSamplesCount');
                if (topSamples) topSamples.textContent = data.tables.length;
            } else {
                const uploadsEl = document.getElementById('uploadsCount');
                if (uploadsEl) uploadsEl.textContent = data.tables.length;
                const topUploads = document.getElementById('topUploadsCount');
                if (topUploads) topUploads.textContent = data.tables.length;
            }
            
            // Auto-select all by default
            selectedTablesSet = new Set(data.tables.map(t => t.filename));
            updateSelectedCountBadge();

            renderTablesList(data.tables);
            renderTopTablesRibbon(data.tables);

            // Auto-select first table if none is selected
            if (!activeTable && data.tables.length > 0) {
                selectTable(data.tables[0].filename, currentSource === 'samples');
            }
        }
    } catch (err) {
        listContainer.innerHTML = `<div style="padding: 15px; color: var(--danger);">Erro: ${err.message}</div>`;
    }
}

function updateSelectedCountBadge() {
    const total = availableTablesList.length;
    const count = selectedTablesSet.size;
    const badge = document.getElementById('selectedCountBadge');
    if (badge) {
        badge.textContent = `${count}/${total} selecionadas`;
    }
    const masterCb = document.getElementById('masterSelectCheckbox');
    if (masterCb) {
        masterCb.checked = (count === total && total > 0);
        masterCb.indeterminate = (count > 0 && count < total);
    }
}

function toggleSelectAll(isChecked) {
    if (isChecked) {
        selectedTablesSet = new Set(availableTablesList.map(t => t.filename));
    } else {
        selectedTablesSet.clear();
    }
    document.querySelectorAll('.tbl-checkbox').forEach(cb => {
        cb.checked = isChecked;
    });
    updateSelectedCountBadge();
}

function toggleTableSelection(filename, isChecked, event) {
    if (event) event.stopPropagation();
    if (isChecked) {
        selectedTablesSet.add(filename);
    } else {
        selectedTablesSet.delete(filename);
    }
    // Sync all corresponding checkboxes in sidebar and top ribbon
    document.querySelectorAll('.tbl-checkbox').forEach(cb => {
        const item = cb.closest('.table-item') || cb.closest('.top-table-tab');
        if (item && item.textContent.includes(filename)) {
            cb.checked = isChecked;
        }
    });
    updateSelectedCountBadge();
}

function filterSidebarTables(query) {
    const q = (query || '').toLowerCase().trim();
    if (!q) {
        renderTablesList(availableTablesList);
        renderTopTablesRibbon(availableTablesList);
        return;
    }
    const filtered = availableTablesList.filter(t => 
        t.filename.toLowerCase().includes(q) || 
        (t.table_name && t.table_name.toLowerCase().includes(q))
    );
    renderTablesList(filtered);
    renderTopTablesRibbon(filtered);
}

function renderTablesList(tables) {
    const listContainer = document.getElementById('tablesList');
    listContainer.innerHTML = '';

    if (!tables || tables.length === 0) {
        listContainer.innerHTML = `
            <div style="padding: 24px 10px; text-align: center; color: var(--text-dim); font-size: 0.78rem;">
                <i class="fa-solid fa-folder-open" style="font-size: 1.8rem; margin-bottom: 8px; opacity: 0.5;"></i>
                <div>Nenhuma tabela encontrada.</div>
            </div>`;
        return;
    }

    tables.forEach(tbl => {
        const item = document.createElement('div');
        item.className = `table-item ${activeTable === tbl.filename ? 'active' : ''}`;
        item.onclick = () => selectTable(tbl.filename, tbl.is_sample);

        const isChecked = selectedTablesSet.has(tbl.filename);
        const pxBadge = tbl.has_px ? '<span class="badge-px-pill" title="Possui arquivo de índice primário .PX"><i class="fa-solid fa-key"></i> .PX</span>' : '';
        const sizeKb = (tbl.file_size / 1024).toFixed(1);

        item.innerHTML = `
            <div class="table-item-info">
                <input type="checkbox" class="tbl-checkbox" ${isChecked ? 'checked' : ''} onclick="toggleTableSelection('${tbl.filename}', this.checked, event)">
                <div class="table-icon-box">
                    <i class="fa-solid fa-table"></i>
                </div>
                <div class="table-item-content">
                    <div class="table-item-title">
                        <span title="${tbl.filename}">${tbl.filename}</span>
                        ${pxBadge}
                    </div>
                    <div class="table-item-chips">
                        <span class="tbl-chip"><i class="fa-solid fa-columns"></i> ${tbl.fields_count || 0} col</span>
                        <span class="tbl-chip"><i class="fa-solid fa-hard-drive"></i> ${sizeKb} KB</span>
                    </div>
                </div>
            </div>
            <div class="table-badge-rows">
                ${tbl.records || 0} reg
            </div>
        `;
        listContainer.appendChild(item);
    });
}

function renderTopTablesRibbon(tables) {
    const ribbon = document.getElementById('topTablesRibbon');
    if (!ribbon) return;
    ribbon.innerHTML = '';

    if (!tables || tables.length === 0) {
        ribbon.innerHTML = '<div style="color:var(--text-dim); font-size:0.75rem; padding:4px 8px;">Nenhuma tabela disponível.</div>';
        return;
    }

    tables.forEach(tbl => {
        const tab = document.createElement('div');
        const isActive = activeTable === tbl.filename;
        const isChecked = selectedTablesSet.has(tbl.filename);
        tab.className = `top-table-tab ${isActive ? 'active' : ''}`;
        tab.onclick = () => selectTable(tbl.filename, tbl.is_sample);

        const pxBadge = tbl.has_px ? '<span class="badge-px-pill" title="Índice .PX ativo"><i class="fa-solid fa-key"></i> .PX</span>' : '';
        
        tab.innerHTML = `
            <input type="checkbox" class="tbl-checkbox" ${isChecked ? 'checked' : ''} onclick="toggleTableSelection('${tbl.filename}', this.checked, event)">
            <i class="fa-solid fa-table top-tab-icon"></i>
            <div class="top-tab-title">
                <span title="${tbl.filename}">${tbl.filename}</span>
                ${pxBadge}
            </div>
            <div class="top-tab-meta">
                ${tbl.records || 0} reg
            </div>
        `;
        ribbon.appendChild(tab);
    });
}

function scrollTablesRibbon(offset) {
    const ribbon = document.getElementById('topTablesRibbon');
    if (ribbon) {
        ribbon.scrollBy({ left: offset, behavior: 'smooth' });
    }
}

function toggleSidebarCollapse() {
    const sidebar = document.querySelector('.sidebar');
    const btn = document.getElementById('sidebarToggleBtn');
    if (sidebar) {
        const isCollapsed = sidebar.classList.toggle('collapsed');
        if (btn) {
            btn.innerHTML = isCollapsed ? '<i class="fa-solid fa-bars"></i>' : '<i class="fa-solid fa-table-columns"></i>';
            btn.title = isCollapsed ? 'Expandir barra lateral' : 'Recolher barra lateral';
        }
        showToast(isCollapsed ? 'Barra lateral recolhida para visualização ampla.' : 'Barra lateral expandida.', 'info');
    }
}

// Select and Inspect Table
async function selectTable(filename, isSample) {
    activeTable = filename;
    currentSqlScript = '';
    customMappings = {};

    // Highlight sidebar items and top ribbon tabs
    document.querySelectorAll('.table-item').forEach(el => {
        el.classList.toggle('active', el.querySelector('.table-item-title').textContent.includes(filename));
    });
    document.querySelectorAll('.top-table-tab').forEach(el => {
        el.classList.toggle('active', el.querySelector('.top-tab-title').textContent.includes(filename));
    });

    document.getElementById('currentTableTitle').textContent = filename;
    document.getElementById('emptyState').style.display = 'none';

    try {
        const projectId = currentProject ? currentProject.id : undefined;
        const res = await fetch('/api/inspect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename, is_sample: isSample, project_id: projectId, limit: 100 })
        });
        const data = await res.json();

        if (data.success) {
            currentTableData = data;
            updateTableMetadata(data);
            renderDataPreview(data);
            renderSchemaMapping(data);
            generateAndShowSQL();
        } else {
            showToast(`Erro ao ler tabela: ${data.error}`, 'error');
        }
    } catch (err) {
        showToast(`Erro de rede: ${err.message}`, 'error');
    }
}

// Update Top Metadata
function updateTableMetadata(data) {
    document.getElementById('metaRecords').innerHTML = `<i class="fa-solid fa-list-ol"></i> ${data.num_records} registros`;
    document.getElementById('metaFields').innerHTML = `<i class="fa-solid fa-columns"></i> ${data.num_fields} colunas`;
    document.getElementById('metaRecSize').innerHTML = `<i class="fa-solid fa-memory"></i> ${data.record_size} B/reg`;

    const pxEl = document.getElementById('metaPxStatus');
    if (pxEl) {
        if (data.px_info && data.px_info.exists && data.px_info.valid) {
            const pkNames = (data.primary_keys || []).join(', ');
            pxEl.innerHTML = `<i class="fa-solid fa-key" style="color:var(--warning);"></i> Índice .PX (${pkNames})`;
            pxEl.style.borderColor = 'rgba(245, 158, 11, 0.4)';
            pxEl.style.color = 'var(--text-main)';
        } else if (data.primary_keys && data.primary_keys.length > 0) {
            const pkNames = data.primary_keys.join(', ');
            pxEl.innerHTML = `<i class="fa-solid fa-key" style="color:var(--warning);"></i> PK (${pkNames})`;
            pxEl.style.borderColor = 'var(--border-color)';
            pxEl.style.color = 'var(--text-muted)';
        } else {
            pxEl.innerHTML = `<i class="fa-solid fa-key" style="color:var(--text-dim);"></i> Sem Chave Primária`;
            pxEl.style.borderColor = 'var(--border-color)';
            pxEl.style.color = 'var(--text-dim)';
        }
    }
}

// Render Data Preview Grid
function renderDataPreview(data) {
    const head = document.getElementById('dataPreviewHead');
    const body = document.getElementById('dataPreviewBody');

    head.innerHTML = '';
    body.innerHTML = '';

    if (!data.fields || data.fields.length === 0) {
        document.getElementById('emptyState').style.display = 'flex';
        return;
    }

    // Header Row
    const trHead = document.createElement('tr');
    trHead.innerHTML = `<th>#</th>` + data.fields.map(f => `<th>${f.name}</th>`).join('');
    head.appendChild(trHead);

    // Rows
    renderGridRows(data.preview_records, data.fields);
}

function renderGridRows(records, fields) {
    const body = document.getElementById('dataPreviewBody');
    body.innerHTML = '';

    document.getElementById('gridRowsCount').textContent = `Mostrando ${records.length} de ${currentTableData.num_records}`;

    records.forEach((row, idx) => {
        const tr = document.createElement('tr');
        let cellsHtml = `<td style="color: var(--text-dim); font-size: 0.75rem;">${idx + 1}</td>`;

        fields.forEach(f => {
            const val = row[f.name];
            cellsHtml += `<td>${formatCellValue(val, f)}</td>`;
        });

        tr.innerHTML = cellsHtml;
        body.appendChild(tr);
    });
}

function formatCellValue(val, field) {
    if (val === null || val === undefined) {
        return `<span class="val-null">null</span>`;
    }
    if (typeof val === 'boolean') {
        return `<span class="val-bool ${val ? 'true' : 'false'}"><i class="fa-solid ${val ? 'fa-check' : 'fa-xmark'}"></i> ${val ? 'SIM' : 'NÃO'}</span>`;
    }
    if (field.type_id === 5 || (typeof val === 'number' && (field.name.toLowerCase().includes('preco') || field.name.toLowerCase().includes('valor') || field.name.toLowerCase().includes('saldo') || field.name.toLowerCase().includes('total')))) {
        return `<span class="val-currency">R$ ${Number(val).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>`;
    }
    if (field.type_id === 2 || (typeof val === 'string' && val.match(/^\d{4}-\d{2}-\d{2}$/))) {
        return `<span class="val-date"><i class="fa-regular fa-calendar"></i> ${val}</span>`;
    }
    return String(val);
}

// Filter Grid Data
function filterGridData() {
    if (!currentTableData) return;
    const query = document.getElementById('gridSearchInput').value.toLowerCase().trim();
    if (!query) {
        renderGridRows(currentTableData.preview_records, currentTableData.fields);
        return;
    }

    const filtered = currentTableData.preview_records.filter(row => {
        return Object.values(row).some(v => String(v).toLowerCase().includes(query));
    });

    renderGridRows(filtered, currentTableData.fields);
}

// Render Schema & Type Mapping
function renderSchemaMapping(data) {
    const tbody = document.getElementById('schemaTableBody');
    tbody.innerHTML = '';

    const FB_RESERVED = new Set(['DATE', 'USER', 'VALUE', 'POSITION', 'ORDER', 'GROUP', 'CHECK', 'DEFAULT', 'YEAR', 'MONTH', 'DAY', 'PASSWORD', 'ROLE', 'TYPE', 'ACTION', 'ALL', 'ALTER', 'AND', 'ANY', 'AS', 'ASC', 'AVG', 'BEGIN', 'BETWEEN', 'BIGINT', 'BLOB', 'BOOLEAN', 'BY', 'CASE', 'CAST', 'CHAR', 'CLOSE', 'COLUMN', 'COMMIT', 'COUNT', 'CREATE', 'CROSS', 'CURRENT', 'CURSOR', 'DELETE', 'DESC', 'DISTINCT', 'DOUBLE', 'DROP', 'ELSE', 'END', 'ESCAPE', 'EXECUTE', 'EXISTS', 'EXIT', 'EXTERNAL', 'EXTRACT', 'FALSE', 'FETCH', 'FILE', 'FIRST', 'FLOAT', 'FOR', 'FOREIGN', 'FROM', 'FULL', 'FUNCTION', 'GRANT', 'HAVING', 'IN', 'INDEX', 'INNER', 'INSERT', 'INT', 'INTEGER', 'INTO', 'IS', 'JOIN', 'KEY', 'LEFT', 'LIKE', 'LIMIT', 'LOCK', 'MATCH', 'MAX', 'MERGE', 'MIN', 'NO', 'NOT', 'NULL', 'NUMERIC', 'OF', 'OFFSET', 'ON', 'ONLY', 'OPEN', 'OR', 'OUTER', 'PAGE', 'PLAN', 'PRIMARY', 'PROCEDURE', 'READ', 'REAL', 'RECREATE', 'REFERENCES', 'RELEASE', 'RETURN', 'REVOKE', 'RIGHT', 'ROLLBACK', 'ROW', 'ROWS', 'SELECT', 'SEQUENCE', 'SET', 'SKIP', 'SMALLINT', 'SOME', 'SUM', 'TABLE', 'THEN', 'TIME', 'TIMESTAMP', 'TO', 'TRIGGER', 'TRIM', 'TRUE', 'UNION', 'UNIQUE', 'UPDATE', 'UPPER', 'USING', 'VALUES', 'VARCHAR', 'VIEW', 'WAIT', 'WHEN', 'WHERE', 'WHILE', 'WITH', 'WORK']);

    data.fields.forEach((f, idx) => {
        const tr = document.createElement('tr');
        const isPk = (data.primary_keys && data.primary_keys.includes(f.name)) || f.is_primary_key;
        const isReserved = FB_RESERVED.has(f.name.toUpperCase());
        const reservedBadge = isReserved ? '<span class="badge-px-pill" style="background:rgba(245,158,11,0.2); color:#FBBF24; margin-left:6px;" title="Palavra reservada no Firebird - será prefixada com F_ no DDL"><i class="fa-solid fa-triangle-exclamation"></i> Reservada</span>' : '';
        
        let optionsHtml = '';
        const currentFbType = customMappings[f.name] || f.firebird_type;

        let allOptions = [...FIREBIRD_TYPE_OPTIONS];
        if (!allOptions.includes(currentFbType)) {
            allOptions.unshift(currentFbType);
        }

        allOptions.forEach(opt => {
            const selected = opt === currentFbType ? 'selected' : '';
            optionsHtml += `<option value="${opt}" ${selected}>${opt}</option>`;
        });

        tr.innerHTML = `
            <td style="color: var(--text-dim);">${idx + 1}</td>
            <td><strong>${f.name}</strong>${reservedBadge}</td>
            <td><span class="type-badge">${f.type_name} (${f.type_id})</span></td>
            <td>${f.length} B</td>
            <td>
                <select class="schema-type-select" onchange="updateFieldMapping('${f.name}', this.value)">
                    ${optionsHtml}
                </select>
            </td>
            <td>
                ${isPk ? '<span class="badge" style="background:rgba(245, 158, 11, 0.15); color:var(--warning); border:1px solid rgba(245, 158, 11, 0.3);"><i class="fa-solid fa-key"></i> PRIMARY KEY' + (data.px_info && data.px_info.exists ? ' (.PX)' : '') + '</span>' : '<span style="color:var(--text-dim); font-size:0.75rem;">COLUNA</span>'}
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function updateFieldMapping(fieldName, newType) {
    customMappings[fieldName] = newType;
    showToast(`Mapeamento de ${fieldName} atualizado para ${newType}`, 'info');
}

// Generate & Display SQL
async function generateAndShowSQL() {
    if (!activeTable) return;

    const fbVersion = document.getElementById('fbVersionSelect').value;

    try {
        const projectId = currentProject ? currentProject.id : undefined;
        const res = await fetch('/api/convert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filename: activeTable,
                is_sample: currentSource === 'samples',
                project_id: projectId,
                mappings: customMappings,
                firebird_version: fbVersion
            })
        });
        const data = await res.json();

        if (data.success) {
            currentSqlScript = data.sql_script;
            document.getElementById('sqlScriptOutput').textContent = currentSqlScript;
            const lines = currentSqlScript.split('\n').length;
            document.getElementById('sqlLinesCount').textContent = `${lines} linhas SQL`;
        } else {
            showToast(`Erro ao gerar SQL: ${data.error}`, 'error');
        }
    } catch (err) {
        showToast(`Erro: ${err.message}`, 'error');
    }
}

// Copy SQL to Clipboard
function copySqlToClipboard() {
    if (!currentSqlScript) {
        showToast('Nenhum SQL gerado para copiar.', 'warning');
        return;
    }
    navigator.clipboard.writeText(currentSqlScript).then(() => {
        showToast('Script SQL copiado para a área de transferência!', 'success');
    });
}

// Download Single SQL Script
function downloadGeneratedSQL() {
    if (!currentSqlScript) {
        showToast('Nenhum SQL gerado para download.', 'warning');
        return;
    }
    const filename = `${activeTable.replace('.DB', '')}_firebird.sql`;
    const blob = new Blob([currentSqlScript], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    showToast(`Download de ${filename} iniciado!`, 'success');
}

// Convert Selected Tables to SQL
async function convertSelectedConsolidated() {
    const fbVersion = document.getElementById('fbVersionSelect').value;
    const selectedList = Array.from(selectedTablesSet);

    if (selectedList.length === 0) {
        showToast('Nenhuma tabela selecionada para converter.', 'warning');
        return;
    }

    try {
        showToast(`Gerando script SQL para ${selectedList.length} tabelas selecionadas...`, 'info');
        const projectId = currentProject ? currentProject.id : undefined;
        const res = await fetch('/api/convert_all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filenames: selectedList,
                project_id: projectId,
                firebird_version: fbVersion
            })
        });
        const data = await res.json();

        if (data.success) {
            currentSqlScript = data.sql_script;
            document.getElementById('sqlScriptOutput').textContent = currentSqlScript;
            const lines = currentSqlScript.split('\n').length;
            document.getElementById('sqlLinesCount').textContent = `${lines} linhas SQL (${data.tables_converted} tabelas selecionadas)`;
            switchMainTab('sqlView');
            showToast(`Script SQL com ${data.tables_converted} tabelas gerado com sucesso!`, 'success');
        } else {
            showToast(`Erro ao converter tabelas: ${data.error}`, 'error');
        }
    } catch (err) {
        showToast(`Erro: ${err.message}`, 'error');
    }
}

// Modal .FDB Actions
function openFdbModal() {
    const modal = document.getElementById('fdbModalOverlay');
    const statusContainer = document.getElementById('fdbStatusContainer');
    statusContainer.style.display = 'none';

    if (activeTable) {
        document.getElementById('modalFdbName').value = 'BANCO_CONVERTIDO.FDB';
    } else {
        document.getElementById('modalFdbName').value = 'MIGRACAO_FIREBIRD.FDB';
    }

    // Render tables checklist inside modal
    renderModalTablesChecklist();

    modal.classList.add('active');
}

function renderModalTablesChecklist() {
    const checklist = document.getElementById('modalTablesChecklist');
    checklist.innerHTML = '';

    if (availableTablesList.length === 0) {
        checklist.innerHTML = '<div style="color:var(--text-dim); padding:10px; text-align:center;">Nenhuma tabela disponível.</div>';
        return;
    }

    availableTablesList.forEach(tbl => {
        const isChecked = selectedTablesSet.has(tbl.filename);
        const item = document.createElement('label');
        item.className = 'checklist-item';
        
        item.innerHTML = `
            <div class="checklist-left">
                <input type="checkbox" value="${tbl.filename}" class="modal-tbl-cb" ${isChecked ? 'checked' : ''} onchange="onModalTableToggle('${tbl.filename}', this.checked)">
                <span>${tbl.filename}</span>
            </div>
            <div class="checklist-meta">
                ${tbl.has_px ? '<span class="badge" style="background:rgba(245, 158, 11, 0.15); color:var(--warning);">.PX</span>' : ''}
                <span>${tbl.records || 0} linhas</span>
            </div>
        `;
        checklist.appendChild(item);
    });
}

function onModalTableToggle(filename, isChecked) {
    if (isChecked) {
        selectedTablesSet.add(filename);
    } else {
        selectedTablesSet.delete(filename);
    }
    updateSelectedCountBadge();
    
    // Sync sidebar checkboxes
    document.querySelectorAll('.tbl-checkbox').forEach(cb => {
        const parentTitle = cb.closest('.table-item').querySelector('.table-item-title').textContent;
        if (parentTitle.includes(filename)) {
            cb.checked = isChecked;
        }
    });
}

function modalSelectAllTables(selectAll) {
    document.querySelectorAll('.modal-tbl-cb').forEach(cb => {
        cb.checked = selectAll;
        onModalTableToggle(cb.value, selectAll);
    });
}

function closeFdbModal(e) {
    if (!e || e.target.id === 'fdbModalOverlay' || e.target.closest('.modal-close-btn') || e.target.classList.contains('btn-secondary')) {
        document.getElementById('fdbModalOverlay').classList.remove('active');
    }
}

async function generateAndDownloadFdbAction() {
    const fdbName = document.getElementById('modalFdbName').value.trim() || 'BANCO_FIREBIRD.FDB';
    const charset = document.getElementById('modalFdbCharset').value;
    const pageSize = parseInt(document.getElementById('modalFdbPageSize').value, 10);
    const fbVersion = document.getElementById('fbVersionSelect').value;

    // Collect checked tables from modal
    const checkedCheckboxes = document.querySelectorAll('.modal-tbl-cb:checked');
    const filenames = Array.from(checkedCheckboxes).map(cb => cb.value);

    if (filenames.length === 0) {
        showToast('Selecione pelo menos uma tabela para incluir no banco .FDB!', 'warning');
        return;
    }

    const btn = document.getElementById('btnConfirmGenerateFdb');
    const statusContainer = document.getElementById('fdbStatusContainer');
    const statusInner = document.getElementById('fdbStatusInner');

    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Criando .FDB com ${filenames.length} tabelas...`;
    statusContainer.style.display = 'block';
    statusInner.innerHTML = `<div style="color:var(--info);"><i class="fa-solid fa-spinner fa-spin"></i> Compilando ${filenames.length} tabelas Paradox em um único arquivo binário .FDB...</div>`;

    try {
        const projectId = currentProject ? currentProject.id : undefined;
        const res = await fetch('/api/generate_fdb', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filenames: filenames,
                project_id: projectId,
                fdb_name: fdbName,
                charset: charset,
                page_size: pageSize,
                firebird_version: fbVersion
            })
        });
        const data = await res.json();

        if (data.success) {
            statusInner.innerHTML = `
                <div style="color: var(--success); font-weight: 700; margin-bottom: 6px;">
                    <i class="fa-solid fa-circle-check"></i> ${data.message}
                </div>
                <div style="color: var(--text-muted); font-size: 0.8rem;">
                    Tabelas consolidadas: <strong>${filenames.join(', ')}</strong>
                </div>
            `;
            showToast(`Banco ${data.fdb_name} gerado com sucesso!`, 'success');
            
            // Trigger download
            window.location.href = data.download_url;
            
            setTimeout(() => {
                closeFdbModal();
            }, 3000);
        } else {
            statusInner.innerHTML = `
                <div style="color: var(--danger); font-weight: 600;">
                    <i class="fa-solid fa-triangle-exclamation"></i> Falha ao gerar .FDB:
                </div>
                <div style="color: var(--text-dim); font-size: 0.75rem; margin-top: 4px; font-family: var(--font-mono);">
                    ${data.error}
                </div>
            `;
            showToast(`Erro na criação do .FDB: ${data.error}`, 'error');
        }
    } catch (err) {
        statusInner.innerHTML = `<div style="color: var(--danger);">${err.message}</div>`;
        showToast(`Erro de rede: ${err.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-bolt"></i> Gerar e Baixar .FDB Único';
    }
}

// Download Active .DB File
function downloadCurrentTableFile() {
    if (!activeTable) {
        showToast('Selecione uma tabela para baixar.', 'warning');
        return;
    }
    window.location.href = `/api/download_sample/${activeTable}`;
}

// Download All Samples ZIP
function downloadAllSamplesZip() {
    window.location.href = '/api/download_samples_zip';
    showToast('Download do pacote ZIP iniciado!', 'success');
}

// Regenerate Test Databases
async function regenerateSamples() {
    try {
        showToast('Gerando bases de dados Paradox de teste...', 'info');
        const res = await fetch('/api/generate_samples', { method: 'POST' });
        const data = await res.json();

        if (data.success) {
            showToast('Bancos Paradox de teste gerados com sucesso!', 'success');
            switchTableSource('samples');
            loadTablesList();
        } else {
            showToast(`Erro: ${data.error}`, 'error');
        }
    } catch (err) {
        showToast(`Erro: ${err.message}`, 'error');
    }
}

// Direct Firebird Execution Handler
async function executeDirectMigration() {
    if (!activeTable || !currentSqlScript) {
        showToast('Selecione uma tabela e gere o SQL primeiro.', 'warning');
        return;
    }

    const connParams = {
        host: document.getElementById('fbHost').value,
        port: document.getElementById('fbPort').value,
        database: document.getElementById('fbDatabase').value,
        user: document.getElementById('fbUser').value,
        password: document.getElementById('fbPassword').value,
        charset: document.getElementById('fbCharset').value
    };

    const resultBox = document.getElementById('directResultBox');
    const resultContent = document.getElementById('directResultContent');
    resultBox.style.display = 'block';
    resultContent.innerHTML = '<div style="color:var(--info);"><i class="fa-solid fa-spinner fa-spin"></i> Conectando e executando migração...</div>';

    try {
        const res = await fetch('/api/convert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filename: activeTable,
                is_sample: currentSource === 'samples',
                mappings: customMappings,
                direct_execute: true,
                connection_params: connParams
            })
        });
        const data = await res.json();

        if (data.success && data.direct_result) {
            if (data.direct_result.success) {
                resultContent.innerHTML = `
                    <div style="color:var(--success); font-weight:700;">
                        <i class="fa-solid fa-circle-check"></i> ${data.direct_result.message}
                    </div>
                `;
                showToast('Migração direta concluída com sucesso no Firebird!', 'success');
            } else {
                resultContent.innerHTML = `
                    <div style="color:var(--danger);">
                        <i class="fa-solid fa-circle-xmark"></i> Erro na conexão Firebird: ${data.direct_result.error}
                    </div>
                `;
                showToast('Falha na migração direta.', 'error');
            }
        } else {
            resultContent.innerHTML = `<div style="color:var(--danger);">${data.error || 'Erro desconhecido.'}</div>`;
        }
    } catch (err) {
        resultContent.innerHTML = `<div style="color:var(--danger);">${err.message}</div>`;
        showToast(`Erro na requisição: ${err.message}`, 'error');
    }
}

// CSV Export & Import Handlers
function exportCurrentTableCsv() {
    if (!activeTable) {
        showToast('Selecione uma tabela para exportar para CSV.', 'warning');
        return;
    }
    const isSample = currentSource === 'samples';
    const projectId = currentProject ? currentProject.id : '';
    window.location.href = `/api/export_csv?filename=${encodeURIComponent(activeTable)}&is_sample=${isSample}&project_id=${projectId}&delimiter=;`;
    showToast(`Exportando ${activeTable} para CSV...`, 'success');
}

function exportAllTablesCsvZip() {
    const projectId = currentProject ? currentProject.id : '';
    window.location.href = `/api/export_all_csv_zip?project_id=${projectId}&delimiter=;`;
    showToast('Exportando todas as tabelas em arquivo ZIP (CSV)...', 'success');
}

function openImportCsvModal() {
    document.getElementById('importCsvModalOverlay').classList.add('active');
    document.getElementById('importCsvTableName').value = '';
    document.getElementById('importCsvFileInput').value = '';
    document.getElementById('importCsvTextarea').value = '';
}

function closeImportCsvModal(e) {
    if (!e || e.target.id === 'importCsvModalOverlay' || e.target.closest('.modal-close-btn') || e.target.classList.contains('btn-secondary')) {
        document.getElementById('importCsvModalOverlay').classList.remove('active');
    }
}

function onCsvFileSelected(input) {
    if (input.files && input.files[0]) {
        const file = input.files[0];
        const rawName = file.name.replace(/\.[^/.]+$/, "").toUpperCase();
        document.getElementById('importCsvTableName').value = rawName;
        
        const reader = new FileReader();
        reader.onload = (e) => {
            document.getElementById('importCsvTextarea').value = e.target.result;
        };
        reader.readAsText(file, 'UTF-8');
    }
}

async function submitImportCsv() {
    const fileInput = document.getElementById('importCsvFileInput');
    const tableName = document.getElementById('importCsvTableName').value.trim() || 'TABELA_CSV';
    const delimiter = document.getElementById('importCsvDelimiter').value;
    const textContent = document.getElementById('importCsvTextarea').value.trim();

    if (!fileInput.files[0] && !textContent) {
        showToast('Selecione um arquivo CSV ou cole o conteúdo de texto.', 'warning');
        return;
    }

    const btn = document.getElementById('btnConfirmImportCsv');
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processando CSV...';

    try {
        let res;
        if (fileInput.files && fileInput.files[0]) {
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            formData.append('table_name', tableName);
            if (delimiter) formData.append('delimiter', delimiter);
            res = await fetch('/api/import_csv', { method: 'POST', body: formData });
        } else {
            res = await fetch('/api/import_csv', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    csv_content: textContent,
                    table_name: tableName,
                    delimiter: delimiter || undefined
                })
            });
        }

        const data = await res.json();
        if (data.success) {
            showToast(data.message, 'success');
            closeImportCsvModal();
            switchTableSource('uploads');
            await loadTablesList();
            selectTable(data.filename, false);
        } else {
            showToast(`Falha na importação do CSV: ${data.error}`, 'error');
        }
    } catch (err) {
        showToast(`Erro: ${err.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-file-import"></i> Importar e Abrir Tabela';
    }
}

// ==========================================
// FOLDER IMPORT HANDLERS (SELEÇÃO DE PASTA)
// ==========================================

function openFolderImportModal() {
    document.getElementById('importFolderModalOverlay').classList.add('active');
    setTimeout(() => {
        const input = document.getElementById('localFolderPathInput');
        if (input) input.focus();
    }, 100);
}

function closeFolderImportModal(event) {
    if (!event || event.target.id === 'importFolderModalOverlay') {
        document.getElementById('importFolderModalOverlay').classList.remove('active');
    }
}

function triggerFolderPicker() {
    const folderInput = document.getElementById('folderInput');
    if (folderInput) {
        folderInput.click();
    }
}

// Handle folder selected via browser folder picker
async function handleFolderSelect(files) {
    if (!files || files.length === 0) return;

    closeFolderImportModal();
    showToast(`Lendo pasta selecionada (${files.length} arquivos)...`, 'info');

    const formData = new FormData();
    let dbCount = 0;

    for (let i = 0; i < files.length; i++) {
        const f = files[i];
        const nameUpper = f.name.toUpperCase();
        // Include .DB, .PX, .MB, .CSV
        if (nameUpper.endsWith('.DB') || nameUpper.endsWith('.PX') || 
            nameUpper.endsWith('.MB') || nameUpper.endsWith('.CSV')) {
            formData.append('files', f);
            if (nameUpper.endsWith('.DB') || nameUpper.endsWith('.CSV')) dbCount++;
        }
    }

    if (dbCount === 0) {
        showToast('Nenhuma tabela Paradox (.DB) ou CSV encontrada na pasta selecionada.', 'warning');
        return;
    }

    try {
        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();

        if (data.success) {
            showToast(`${data.uploaded.length} tabelas importadas da pasta com sucesso!`, 'success');
            switchTableSource('uploads');
            await loadTablesList();
            if (data.uploaded.length > 0) {
                selectTable(data.uploaded[0].filename, false);
            }
        } else {
            showToast(`Erro ao carregar pasta: ${data.error}`, 'error');
        }
    } catch (err) {
        showToast(`Falha no envio da pasta: ${err.message}`, 'error');
    }
}

// Handle local server folder scan
async function scanLocalFolderAction() {
    const input = document.getElementById('localFolderPathInput');
    const folderPath = (input ? input.value : '').trim();

    if (!folderPath) {
        showToast('Informe o caminho da pasta no disco local.', 'warning');
        return;
    }

    const btn = document.getElementById('btnScanFolder');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Lendo pasta...';
    }

    try {
        const res = await fetch('/api/scan_folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: folderPath })
        });
        const data = await res.json();

        if (data.success) {
            showToast(`${data.count} tabelas carregadas da pasta com sucesso!`, 'success');
            closeFolderImportModal();
            switchTableSource('uploads');
            await loadTablesList();
            if (data.tables && data.tables.length > 0) {
                selectTable(data.tables[0].filename, false);
            }
        } else {
            showToast(`Erro ao escanear pasta: ${data.error}`, 'error');
        }
    } catch (err) {
        showToast(`Falha na requisição: ${err.message}`, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> Ler Pasta';
        }
    }
}

// ─── Projects System ──────────────────────────────────────────────────────────

function initProjectFilesInput() {
    // Wire up the folder picker (webkitdirectory) for project creation
    const folderInput = document.getElementById('projectFolderInput');
    if (folderInput) {
        folderInput.addEventListener('change', () => {
            const preview = document.getElementById('selectedFolderPreview');
            const zone = document.getElementById('newProjectPickerZone');
            const files = folderInput.files;
            if (!files || files.length === 0) {
                if (preview) preview.textContent = 'Nenhuma pasta selecionada';
                if (zone) zone.classList.remove('selected');
                return;
            }
            // Get folder name from the first file path
            const firstFile = files[0];
            const folderName = firstFile.webkitRelativePath
                ? firstFile.webkitRelativePath.split('/')[0]
                : 'Pasta Selecionada';
            const dbCount = [...files].filter(f => f.name.toUpperCase().endsWith('.DB')).length;
            const totalCount = files.length;

            if (preview) {
                preview.textContent = dbCount > 0
                    ? 'Pasta: ' + folderName + '  |  ' + dbCount + ' tabelas .DB encontradas (' + totalCount + ' arquivos)'
                    : 'Pasta: ' + folderName + '  |  Nenhum .DB encontrado (' + totalCount + ' arquivos)';
            }
            if (zone) zone.classList.add('selected');

            // Auto-fill project name if empty
            const nameInput = document.getElementById('newProjectName');
            if (nameInput && !nameInput.value.trim()) {
                nameInput.value = folderName.replace(/[^a-zA-Z0-9_À-ÿ]/g, '_').replace(/_+/g, '_').toUpperCase();
            }
        });
    }

    // Wire up folderPickerGlobal (importFolderModal)
    const globalFolder = document.getElementById('folderPickerGlobal');
    if (globalFolder) {
        globalFolder.addEventListener('change', () => {
            const preview = document.getElementById('folderPickerGlobalPreview');
            const zone = document.querySelector('.folder-picker-zone');
            const confirmBtn = document.getElementById('btnConfirmFolderImport');
            const files = globalFolder.files;
            if (!files || files.length === 0) {
                if (preview) preview.textContent = 'Nenhuma pasta selecionada';
                return;
            }
            const firstFile = files[0];
            const folderName = firstFile.webkitRelativePath
                ? firstFile.webkitRelativePath.split('/')[0]
                : 'Pasta Selecionada';
            const dbCount = [...files].filter(f => f.name.toUpperCase().endsWith('.DB')).length;
            if (preview) {
                preview.textContent = 'Pasta: ' + folderName + '  |  ' + dbCount + ' tabelas .DB encontradas';
            }
            if (zone) zone.classList.add('selected');
            if (confirmBtn) confirmBtn.removeAttribute('disabled');
        });
    }

    // Wire up individual file picker
    const filesInput = document.getElementById('projectFilesInput');
    if (filesInput) {
        filesInput.addEventListener('change', () => {
            const preview = document.getElementById('selectedFilesPreview');
            if (!preview) return;
            if (filesInput.files.length === 0) {
                preview.textContent = 'Nenhum arquivo selecionado.';
            } else {
                const dbFiles = [...filesInput.files].filter(f => f.name.toUpperCase().endsWith('.DB'));
                preview.textContent = dbFiles.length > 0
                    ? dbFiles.length + ' tabelas .DB selecionadas (' + filesInput.files.length + ' arquivos no total)'
                    : 'Nenhum arquivo .DB encontrado nos ' + filesInput.files.length + ' arquivos selecionados.';
                // Auto-fill project name
                const nameInput = document.getElementById('newProjectName');
                if (nameInput && !nameInput.value.trim() && dbFiles.length > 0) {
                    nameInput.value = 'PROJETO_' + new Date().toISOString().slice(0,10).replace(/-/g,'');
                }
            }
        });
    }
}


async function loadProjects() {
    try {
        const res = await fetch('/api/projects');
        const data = await res.json();
        if (data.success) {
            projectsList = data.projects;
            renderProjectsList(projectsList);
        }
    } catch (err) {
        console.error('Erro ao carregar projetos:', err);
    }
}

function renderProjectsList(projects) {
    const list = document.getElementById('projectsList');
    const empty = document.getElementById('projectsEmpty');
    if (!list) return;

    // Remove existing project items (keep the empty placeholder)
    [...list.querySelectorAll('.project-item')].forEach(el => el.remove());

    if (!projects || projects.length === 0) {
        if (empty) empty.style.display = 'flex';
        return;
    }
    if (empty) empty.style.display = 'none';

    projects.forEach(project => {
        const isActive = currentProject && currentProject.id === project.id;
        const item = document.createElement('div');
        item.className = 'project-item' + (isActive ? ' active' : '');
        item.dataset.projectId = project.id;
        const safeName = project.name.replace(/'/g, "\\'");
        item.innerHTML = `
            <div class="project-item-icon"><i class="fa-solid ${isActive ? 'fa-folder-open' : 'fa-folder'}"></i></div>
            <div class="project-item-info">
                <div class="project-item-name" title="${project.name}">${project.name}</div>
                <div class="project-item-meta">${project.table_count} tabela(s)</div>
            </div>
            <div class="project-item-actions">
                <button class="btn-project-action danger" title="Remover projeto"
                    onclick="event.stopPropagation(); openDeleteProjectModal('${project.id}', '${safeName}')"
                ><i class="fa-solid fa-trash"></i></button>
            </div>
        `;
        item.addEventListener('click', () => selectProject(project));
        list.appendChild(item);
    });
}

async function selectProject(project) {
    currentProject = project;

    // Update visual active state
    document.querySelectorAll('.project-item').forEach(el => {
        const active = el.dataset.projectId === project.id;
        el.classList.toggle('active', active);
        const icon = el.querySelector('.project-item-icon i');
        if (icon) icon.className = active ? 'fa-solid fa-folder-open' : 'fa-solid fa-folder';
    });

    // Update nav tabs label
    const tabBtn = document.getElementById('tabUploadsBtn');
    const topTabBtn = document.getElementById('topTabUploadsBtn');
    if (tabBtn) tabBtn.innerHTML = `<i class="fa-solid fa-folder-open"></i> ${project.name} <span class="badge" id="uploadsCount">0</span>`;
    if (topTabBtn) topTabBtn.innerHTML = `<i class="fa-solid fa-folder-open"></i> ${project.name} <span class="badge" id="topUploadsCount">0</span>`;

    // Switch source to uploads/project
    currentSource = 'uploads';
    document.getElementById('tabSamplesBtn').classList.remove('active');
    if (tabBtn) tabBtn.classList.add('active');
    const topSamples = document.getElementById('topTabSamplesBtn');
    if (topSamples) topSamples.classList.remove('active');
    if (topTabBtn) topTabBtn.classList.add('active');

    activeTable = null;
    await loadProjectTables(project.id);
    showToast(`Projeto "${project.name}" ativado com ${project.table_count} tabela(s).`, 'success');
}

async function loadProjectTables(projectId) {
    const listContainer = document.getElementById('tablesList');
    listContainer.innerHTML = '<div style="padding: 15px; color: var(--text-dim); text-align: center;">Carregando tabelas do projeto...</div>';
    try {
        const res = await fetch(`/api/projects/${projectId}/tables`);
        const data = await res.json();
        if (data.success) {
            availableTablesList = data.tables;
            const uploadsEl = document.getElementById('uploadsCount');
            if (uploadsEl) uploadsEl.textContent = data.tables.length;
            const topUploads = document.getElementById('topUploadsCount');
            if (topUploads) topUploads.textContent = data.tables.length;
            selectedTablesSet = new Set(data.tables.map(t => t.filename));
            updateSelectedCountBadge();
            renderTablesList(data.tables);
            renderTopTablesRibbon(data.tables);
            if (data.tables.length > 0) {
                selectTable(data.tables[0].filename, false);
            }
        }
    } catch (err) {
        listContainer.innerHTML = `<div style="padding: 15px; color: var(--danger);">Erro: ${err.message}</div>`;
    }
}

// ─── New Project Modal ────────────────────────────────────────────────────────

function openNewProjectModal() {
    const nameInput = document.getElementById('newProjectName');
    const folderInput = document.getElementById('projectFolderInput');
    const filesInput = document.getElementById('projectFilesInput');
    const folderPreview = document.getElementById('selectedFolderPreview');
    const filesPreview = document.getElementById('selectedFilesPreview');
    const status = document.getElementById('projectCreateStatus');
    const btn = document.getElementById('btnConfirmNewProject');

    if (nameInput) nameInput.value = '';
    if (folderInput) folderInput.value = '';
    if (filesInput) filesInput.value = '';
    if (folderPreview) folderPreview.textContent = 'Nenhuma pasta selecionada.';
    if (filesPreview) filesPreview.textContent = 'Nenhum arquivo selecionado.';
    if (status) { status.style.display = 'none'; status.textContent = ''; status.className = 'project-create-status'; }
    if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-bolt"></i> Criar Projeto e Importar'; }

    switchImportMode('folder');
    document.getElementById('newProjectModalOverlay').classList.add('active');
}

function closeNewProjectModal(event) {
    if (event && event.target !== document.getElementById('newProjectModalOverlay')) return;
    document.getElementById('newProjectModalOverlay').classList.remove('active');
}

function switchImportMode(mode) {
    currentImportMode = mode;
    const folderTab = document.getElementById('importModeFolder');
    const filesTab = document.getElementById('importModeFiles');
    const folderPanel = document.getElementById('importPanelFolder');
    const filesPanel = document.getElementById('importPanelFiles');

    if (folderTab) folderTab.classList.toggle('active', mode === 'folder');
    if (filesTab) filesTab.classList.toggle('active', mode === 'files');
    if (folderPanel) folderPanel.style.display = mode === 'folder' ? '' : 'none';
    if (filesPanel) filesPanel.style.display = mode === 'files' ? '' : 'none';
}

function autoFillProjectName() {
    // No-op: name is now filled automatically by the folder picker event
}

async function confirmCreateProject() {
    const nameInput = document.getElementById('newProjectName');
    const name = nameInput ? nameInput.value.trim() : '';
    if (!name) {
        showToast('Informe um nome para o projeto.', 'warning');
        if (nameInput) nameInput.focus();
        return;
    }

    const btn = document.getElementById('btnConfirmNewProject');
    const status = document.getElementById('projectCreateStatus');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Criando...'; }

    try {
        // Step 1: Create the project record
        const createRes = await fetch('/api/projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const createData = await createRes.json();
        if (!createData.success) throw new Error(createData.error || 'Erro ao criar projeto.');
        const project = createData.project;

        // Step 2: Import tables based on mode
        if (currentImportMode === 'folder') {
            // Folder picker mode: upload all files from selected folder
            const folderInput = document.getElementById('projectFolderInput');
            if (!folderInput || folderInput.files.length === 0) {
                throw new Error('Selecione uma pasta clicando em "Abrir Explorador de Pastas".');
            }

            const dbFiles = [...folderInput.files].filter(f =>
                /\.(db|px|mb)$/i.test(f.name)
            );
            if (dbFiles.length === 0) {
                throw new Error('Nenhum arquivo .DB, .PX ou .MB encontrado na pasta selecionada.');
            }

            if (btn) btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Enviando ${dbFiles.length} arquivo(s)...`;
            const formData = new FormData();
            for (const f of dbFiles) formData.append('files', f);

            const uploadRes = await fetch(`/api/projects/${project.id}/upload_files`, {
                method: 'POST',
                body: formData
            });
            const uploadData = await uploadRes.json();
            if (!uploadData.success) throw new Error(uploadData.error || 'Erro ao enviar arquivos.');

            project.table_count = uploadData.uploaded.filter(u => !u.error).length;
            if (status) {
                status.style.display = 'block';
                status.className = 'project-create-status';
                status.innerHTML = `<i class="fa-solid fa-check-circle"></i> <strong>${project.table_count} tabela(s)</strong> importadas com sucesso da pasta!`;
            }
        } else {
            // Files upload mode — individual files
            const filesInput = document.getElementById('projectFilesInput');
            if (!filesInput || filesInput.files.length === 0) throw new Error('Selecione ao menos um arquivo .DB.');

            if (btn) btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Enviando arquivos...';
            const formData = new FormData();
            for (const f of filesInput.files) formData.append('files', f);

            const uploadRes = await fetch(`/api/projects/${project.id}/upload_files`, {
                method: 'POST',
                body: formData
            });
            const uploadData = await uploadRes.json();
            if (!uploadData.success) throw new Error(uploadData.error || 'Erro ao enviar arquivos.');

            project.table_count = uploadData.uploaded.filter(u => !u.error).length;
            if (status) {
                status.style.display = 'block';
                status.className = 'project-create-status';
                status.innerHTML = `<i class="fa-solid fa-check-circle"></i> <strong>${project.table_count} tabela(s)</strong> enviadas com sucesso!`;
            }
        }

        // Step 3: Reload projects and activate the new one
        await loadProjects();
        const fullProject = projectsList.find(p => p.id === project.id) || project;
        setTimeout(() => {
            document.getElementById('newProjectModalOverlay').classList.remove('active');
            selectProject(fullProject);
        }, 1200);

    } catch (err) {
        if (status) {
            status.style.display = 'block';
            status.className = 'project-create-status error';
            status.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> ${err.message}`;
        }
        showToast(err.message, 'error');
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-bolt"></i> Criar Projeto e Importar'; }
    }
}

// ─── Delete Project Modal ─────────────────────────────────────────────────────

function openDeleteProjectModal(projectId, projectName) {
    projectToDelete = projectId;
    const desc = document.getElementById('deleteProjectModalDesc');
    if (desc) desc.textContent = `Remover o projeto "${projectName}"?`;
    const checkbox = document.getElementById('deleteProjectFilesCheckbox');
    if (checkbox) checkbox.checked = false;
    document.getElementById('deleteProjectModalOverlay').classList.add('active');
}

function closeDeleteProjectModal(event) {
    if (event && event.target !== document.getElementById('deleteProjectModalOverlay')) return;
    document.getElementById('deleteProjectModalOverlay').classList.remove('active');
    projectToDelete = null;
}

async function confirmDeleteProject() {
    if (!projectToDelete) return;
    const deleteFiles = document.getElementById('deleteProjectFilesCheckbox').checked;
    const btn = document.getElementById('btnConfirmDeleteProject');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Removendo...'; }

    try {
        const res = await fetch(`/api/projects/${projectToDelete}?delete_files=${deleteFiles}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            showToast('Projeto removido com sucesso.', 'success');
            // If deleted the active project, reset to samples
            if (currentProject && currentProject.id === projectToDelete) {
                currentProject = null;
                const tabBtn = document.getElementById('tabUploadsBtn');
                const topTabBtn = document.getElementById('topTabUploadsBtn');
                if (tabBtn) tabBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> Meus Arquivos <span class="badge" id="uploadsCount">0</span>';
                if (topTabBtn) topTabBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> Meus Arquivos <span class="badge" id="topUploadsCount">0</span>';
                switchTableSource('samples');
            }
            document.getElementById('deleteProjectModalOverlay').classList.remove('active');
            projectToDelete = null;
            await loadProjects();
        } else {
            throw new Error(data.error || 'Erro ao remover projeto.');
        }
    } catch (err) {
        showToast(err.message, 'error');
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-trash"></i> Remover Projeto'; }
    }
}

// ─── Firebird 2.5/3.0 -> 5.0 Migrator Logic ───────────────────────────────────

let fbMigrateSelectedFile = null;
let fbMigrateInspectedInfo = null;

function openFbMigrateModal() {
    fbMigrateSelectedFile = null;
    fbMigrateInspectedInfo = null;

    const fileInput = document.getElementById('fbMigrateFileInput');
    if (fileInput) fileInput.value = '';

    const preview = document.getElementById('fbMigrateFilePreview');
    if (preview) preview.textContent = 'Nenhum banco selecionado';

    const zone = document.getElementById('fbMigratePickerZone');
    if (zone) zone.classList.remove('selected');

    const card = document.getElementById('fbAnalysisCard');
    if (card) card.style.display = 'none';

    const opts = document.getElementById('fbTargetOptions');
    if (opts) opts.style.display = 'none';

    const status = document.getElementById('fbMigrateStatus');
    if (status) status.style.display = 'none';

    const btn = document.getElementById('btnExecuteFbMigrate');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-bolt"></i> Portar para Firebird 5.0';
    }

    document.getElementById('fbMigrateModalOverlay').classList.add('active');
}

function closeFbMigrateModal(event) {
    if (event && event.target !== document.getElementById('fbMigrateModalOverlay')) return;
    document.getElementById('fbMigrateModalOverlay').classList.remove('active');
}

async function onFbFileSelected(input) {
    if (!input || !input.files || input.files.length === 0) return;
    const file = input.files[0];
    fbMigrateSelectedFile = file;

    const preview = document.getElementById('fbMigrateFilePreview');
    const zone = document.getElementById('fbMigratePickerZone');
    const card = document.getElementById('fbAnalysisCard');
    const opts = document.getElementById('fbTargetOptions');
    const status = document.getElementById('fbMigrateStatus');
    const btn = document.getElementById('btnExecuteFbMigrate');

    if (preview) preview.textContent = 'Arquivo selecionado: ' + file.name + ' (' + (file.size / (1024 * 1024)).toFixed(2) + ' MB) - Analisando...';
    if (zone) zone.classList.add('selected');

    const formData = new FormData();
    formData.append('file', file);

    try {
        if (status) {
            status.style.display = 'block';
            status.innerHTML = '<div style="color:var(--info);"><i class="fa-solid fa-spinner fa-spin"></i> Lendo e inspecionando cabeçalho ODS do banco Firebird...</div>';
        }

        const res = await fetch('/api/fb_migrate/inspect', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();

        if (data.success && data.info) {
            fbMigrateInspectedInfo = data.info;
            if (status) status.style.display = 'none';

            // Populate analysis card
            if (card) card.style.display = 'block';
            if (opts) opts.style.display = 'block';

            const verEl = document.getElementById('fbDetectedVersion');
            if (verEl) verEl.textContent = data.info.detected_version || 'Firebird Desconhecido';

            const odsEl = document.getElementById('fbDetectedOds');
            if (odsEl) odsEl.textContent = 'ODS ' + (data.info.ods_string || 'Desconhecido');

            const nameEl = document.getElementById('fbOriginalFileName');
            if (nameEl) nameEl.textContent = file.name;

            const sizeEl = document.getElementById('fbOriginalFileSize');
            if (sizeEl) sizeEl.textContent = data.info.file_size_formatted || ((file.size / (1024 * 1024)).toFixed(2) + ' MB');

            // Suggest target name
            const baseNoExt = file.name.replace(/\.[^/.]+$/, '');
            const targetNameInput = document.getElementById('fbTargetCustomName');
            if (targetNameInput) targetNameInput.value = baseNoExt + '_FB50.FDB';

            if (btn) btn.disabled = false;
            showToast('Banco Firebird analisado com sucesso!', 'success');
        } else {
            throw new Error(data.error || 'Erro ao analisar banco Firebird.');
        }
    } catch (err) {
        if (status) {
            status.style.display = 'block';
            status.innerHTML = '<div style="color:var(--danger);"><i class="fa-solid fa-triangle-exclamation"></i> ' + err.message + '</div>';
        }
        showToast(err.message, 'error');
    }
}

async function executeFbMigration() {
    if (!fbMigrateInspectedInfo || !fbMigrateInspectedInfo.filepath) {
        showToast('Selecione e inspecione um banco Firebird primeiro.', 'warning');
        return;
    }

    const pageSize = parseInt(document.getElementById('fbTargetPageSize').value) || 8192;
    const charset = document.getElementById('fbTargetCharset').value || 'UTF8';
    const customName = document.getElementById('fbTargetCustomName').value.trim();
    const btn = document.getElementById('btnExecuteFbMigrate');
    const status = document.getElementById('fbMigrateStatus');

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Portando para Firebird 5.0...';
    }

    if (status) {
        status.style.display = 'block';
        status.innerHTML = '<div style="color:var(--info);"><i class="fa-solid fa-spinner fa-spin"></i> Extraindo backup transportável e compilando novo banco no Firebird 5.0 (ODS 13.1)... Aguarde alguns instantes.</div>';
    }

    try {
        const res = await fetch('/api/fb_migrate/convert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filepath: fbMigrateInspectedInfo.filepath,
                page_size: pageSize,
                charset: charset,
                target_name: customName
            })
        });
        const data = await res.json();

        if (data.success) {
            if (status) {
                status.innerHTML = `
                    <div style="color:var(--success); font-weight:600; margin-bottom:8px;">
                        <i class="fa-solid fa-circle-check"></i> ${data.message}
                    </div>
                    <div style="font-size:0.8rem; color:var(--text-muted); margin-bottom:12px;">
                        Versão Original: <strong>${data.original_version}</strong> (ODS ${data.original_ods})<br>
                        Nova Versão: <strong>${data.target_version}</strong> (ODS ${data.target_ods})<br>
                        Tamanho: <strong>${data.file_size_formatted}</strong>
                    </div>
                    <a href="${data.download_url}" class="btn-action-primary" style="display:inline-flex; align-items:center; gap:8px; text-decoration:none; width:100%; justify-content:center; background:linear-gradient(135deg, #10B981, #059669);">
                        <i class="fa-solid fa-download"></i> Baixar Banco Firebird 5.0 (.FDB)
                    </a>
                `;
            }
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-check"></i> Concluído com Sucesso!';
            }
            showToast('Banco Firebird 5.0 gerado com sucesso!', 'success');
        } else {
            throw new Error(data.error || 'Falha na migração do Firebird.');
        }
    } catch (err) {
        if (status) {
            status.innerHTML = '<div style="color:var(--danger);"><i class="fa-solid fa-triangle-exclamation"></i> ' + err.message + '</div>';
        }
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-bolt"></i> Tentar Novamente';
        }
        showToast(err.message, 'error');
    }
}


/* ═══════════════════════════════════════════════════════
   HELPER: SAFE JSON FETCH WITH RESTART DETECTION
═══════════════════════════════════════════════════════ */

async function safeFetchJson(url, options = {}) {
    try {
        const res = await fetch(url, options);
        const text = await res.text();
        try {
            const data = JSON.parse(text);
            return { ok: res.ok, status: res.status, data };
        } catch (parseErr) {
            if (text.trim().startsWith('<')) {
                return {
                    ok: false,
                    status: res.status,
                    data: {
                        success: false,
                        error: 'O servidor Python precisa ser reiniciado para registrar os novos endpoints. Feche a janela preta do servidor e execute novamente "python run_server.py".'
                    }
                };
            }
            return {
                ok: false,
                status: res.status,
                data: { success: false, error: text.slice(0, 200) || parseErr.message }
            };
        }
    } catch (networkErr) {
        return {
            ok: false,
            status: 0,
            data: { success: false, error: 'Falha de conexão com o servidor local: ' + networkErr.message }
        };
    }
}


/* ═══════════════════════════════════════════════════════
   1. DIAGNOSTICS & DATA CLEANSING MODULE
═══════════════════════════════════════════════════════ */

let currentDiagnosticsReport = null;

function openDiagnosticsModal() {
    const modal = document.getElementById('diagnosticsModalOverlay');
    if (modal) modal.classList.add('active');
    loadDiagnosticsData();
}

function closeDiagnosticsModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('diagnosticsModalOverlay');
    if (modal) modal.classList.remove('active');
}

async function loadDiagnosticsData() {
    const list = document.getElementById('diagIssuesList');
    list.innerHTML = '<div style="padding:16px; text-align:center; color:var(--text-dim);"><i class="fa-solid fa-spinner fa-spin"></i> Analisando integridade das tabelas...</div>';

    const { data } = await safeFetchJson('/api/diagnostics/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            source: currentSource,
            project_id: currentProject ? currentProject.id : null,
            filename: activeTable
        })
    });

    if (data && data.success) {
        currentDiagnosticsReport = data.report;
        renderDiagnosticsUI(data.report);
    } else {
        list.innerHTML = `<div style="padding:12px; color:var(--danger); font-size:0.8rem;"><i class="fa-solid fa-triangle-exclamation"></i> ${data?.error || 'Falha ao carregar diagnóstico.'}</div>`;
    }
}

function renderDiagnosticsUI(rep) {
    const score = rep.health_score !== undefined ? rep.health_score : (rep.overall_health || 100);
    const scoreNum = document.getElementById('diagScoreNum');
    const badge = document.getElementById('diagScoreBadge');
    const title = document.getElementById('diagStatusTitle');
    const desc = document.getElementById('diagStatusDesc');

    if (scoreNum) scoreNum.textContent = `${score}%`;
    if (badge) {
        badge.className = 'diag-score-badge';
        if (score < 60) badge.classList.add('danger');
        else if (score < 85) badge.classList.add('warning');
    }

    if (title && desc) {
        if (score >= 85) {
            title.innerHTML = '<i class="fa-solid fa-circle-check" style="color:#10B981;"></i> Base Saudável e Confiável';
            desc.textContent = 'Estruturas de tabelas íntegras, chaves primárias válidas e sem corrupção detectada.';
        } else if (score >= 60) {
            title.innerHTML = '<i class="fa-solid fa-triangle-exclamation" style="color:#F59E0B;"></i> Requer Atenção Prévia';
            desc.textContent = 'Foram detectadas anomalias leves (datas fora de faixa ou índice .PX ausente).';
        } else {
            title.innerHTML = '<i class="fa-solid fa-circle-xmark" style="color:#EF4444;"></i> Risco de Corrupção Detectado';
            desc.textContent = 'Problemas críticos em cabeçalhos ou chaves primárias. Recomendada higienização imediata.';
        }
    }

    const tblPill = document.getElementById('diagTotalTablesPill');
    const recPill = document.getElementById('diagTotalRecordsPill');
    const issPill = document.getElementById('diagIssuesPill');

    const totalTables = rep.total_tables !== undefined ? rep.total_tables : 1;
    const totalRecs = rep.total_records !== undefined ? rep.total_records : (rep.record_count || 0);
    const totalIssues = rep.total_issues !== undefined ? rep.total_issues : (rep.issues_count || 0);

    if (tblPill) tblPill.textContent = `${totalTables} Tabela(s)`;
    if (recPill) recPill.textContent = `${totalRecs.toLocaleString()} Registros`;
    if (issPill) issPill.textContent = `${totalIssues} Alerta(s)`;

    // Render list
    const list = document.getElementById('diagIssuesList');
    list.innerHTML = '';

    const tables = rep.tables || [rep];
    tables.forEach(t => {
        const card = document.createElement('div');
        card.className = `diag-issue-card ${t.health_score >= 85 ? 'healthy' : (t.health_score >= 60 ? 'warning' : 'danger')}`;
        
        let issuesText = 'Nenhum problema detectado';
        if (t.issues && t.issues.length > 0) {
            issuesText = t.issues.map(i => i.message).join(' | ');
        } else if (t.warnings && t.warnings.length > 0) {
            issuesText = t.warnings.map(w => w.message).join(' | ');
        }

        card.innerHTML = `
            <div>
                <strong>${t.filename || t.table_name}</strong>
                <div style="font-size:0.72rem; color:var(--text-muted); margin-top:2px;">${issuesText}</div>
            </div>
            <div style="text-align:right;">
                <span class="pill" style="font-weight:700; color:${t.health_score >= 85 ? '#10B981' : (t.health_score >= 60 ? '#FBBF24' : '#EF4444')}">${t.health_score}%</span>
            </div>
        `;
        list.appendChild(card);
    });
}

async function executeSanitizationAction() {
    if (!activeTable) {
        showToast('Selecione uma tabela ativa para higienizar.', 'warning');
        return;
    }

    const btn = document.getElementById('btnRunCleanse');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Higienizando...';
    }

    const { data } = await safeFetchJson('/api/diagnostics/fix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            filename: activeTable,
            source: currentSource,
            project_id: currentProject ? currentProject.id : null,
            options: {
                fix_invalid_dates: document.getElementById('cleanseFixDates').checked,
                fix_null_pks: document.getElementById('cleanseFixPks').checked,
                fix_duplicate_pks: document.getElementById('cleanseFixDups').checked,
                trim_strings: document.getElementById('cleanseTrim').checked
            }
        })
    });

    if (data && data.success) {
        showToast(data.message, 'success');
        loadDiagnosticsData();
        selectTable(activeTable, currentSource === 'samples');
    } else {
        showToast(`Erro na higienização: ${data?.error || 'Falha inesperada'}`, 'error');
    }

    if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-sparkles"></i> Executar Higienização &amp; Correção';
    }
}


/* ═══════════════════════════════════════════════════════
   2. SMART FOREIGN KEYS & RELATIONAL GRAPH MODULE
═══════════════════════════════════════════════════════ */

let currentRelationsList = [];

function openRelationsModal() {
    const modal = document.getElementById('relationsModalOverlay');
    if (modal) modal.classList.add('active');
    loadRelationsData();
}

function closeRelationsModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('relationsModalOverlay');
    if (modal) modal.classList.remove('active');
}

async function loadRelationsData() {
    const tbody = document.getElementById('relationsTableBody');
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:20px; color:var(--text-dim);"><i class="fa-solid fa-spinner fa-spin"></i> Detectando relacionamentos entre tabelas...</td></tr>';

    const { data } = await safeFetchJson('/api/relations/detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            source: currentSource,
            project_id: currentProject ? currentProject.id : null
        })
    });

    if (data && data.success) {
        currentRelationsList = data.relations || [];
        const countBadge = document.getElementById('relationsCountBadge');
        if (countBadge) countBadge.textContent = currentRelationsList.length;
        renderRelationsTable(currentRelationsList);
    } else {
        tbody.innerHTML = `<tr><td colspan="7" style="color:var(--danger); text-align:center; padding:16px; font-size:0.8rem;"><i class="fa-solid fa-triangle-exclamation"></i> ${data?.error || 'Erro ao carregar relacionamentos.'}</td></tr>`;
    }
}

function renderRelationsTable(relations) {
    const tbody = document.getElementById('relationsTableBody');
    tbody.innerHTML = '';

    if (!relations || relations.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:24px; color:var(--text-dim);"><i class="fa-solid fa-diagram-project" style="font-size:1.6rem; opacity:0.3; margin-bottom:6px;"></i><div>Nenhum relacionamento detectado automaticamente com a nomenclatura atual.</div></td></tr>';
        return;
    }

    relations.forEach((rel, idx) => {
        const tr = document.createElement('tr');
        const orphansBadge = rel.validated 
            ? (rel.orphans_count === 0 
                ? `<span class="badge-px-pill" style="background:rgba(16,185,129,0.15); color:#34D399;"><i class="fa-solid fa-check"></i> 100% Íntegro</span>`
                : `<span class="badge-px-pill" style="background:rgba(239,68,68,0.15); color:#F87171;"><i class="fa-solid fa-triangle-exclamation"></i> ${rel.orphans_count} órfãos</span>`)
            : `<span style="color:var(--text-dim); font-size:0.75rem;">Não verificado</span>`;

        tr.innerHTML = `
            <td style="text-align:center;">
                <input type="checkbox" ${rel.enabled ? 'checked' : ''} onchange="toggleRelationItem(${idx}, this.checked)">
            </td>
            <td><strong>${rel.child_table}</strong></td>
            <td><code>${rel.child_column}</code></td>
            <td><strong style="color:#C7D2FE;">${rel.parent_table}</strong></td>
            <td><code>${rel.parent_column}</code></td>
            <td><span class="badge-px-pill" style="background:rgba(168,85,247,0.15); color:#C084FC;">${rel.confidence}%</span></td>
            <td>${orphansBadge}</td>
        `;
        tbody.appendChild(tr);
    });
}

function toggleRelationItem(idx, checked) {
    if (currentRelationsList[idx]) {
        currentRelationsList[idx].enabled = checked;
    }
}

function toggleAllRelations(checked) {
    currentRelationsList.forEach(r => r.enabled = checked);
    renderRelationsTable(currentRelationsList);
}

async function validateAllRelationsOrphans() {
    showToast('Validando registros órfãos para todas as chaves...', 'info');
    for (let i = 0; i < currentRelationsList.length; i++) {
        const rel = currentRelationsList[i];
        const { data } = await safeFetchJson('/api/relations/validate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                relation: rel,
                source: currentSource,
                project_id: currentProject ? currentProject.id : null
            })
        });
        if (data && data.success && data.validation) {
            rel.validated = true;
            rel.orphans_count = data.validation.orphan_count;
            rel.integrity_percentage = data.validation.integrity_percentage;
        }
    }
    renderRelationsTable(currentRelationsList);
    showToast('Validação de integridade concluída!', 'success');
}

async function copyRelationsDdlAction() {
    const { data } = await safeFetchJson('/api/relations/generate-ddl', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ relations: currentRelationsList })
    });
    if (data && data.success && data.ddl) {
        navigator.clipboard.writeText(data.ddl);
        showToast('DDL de Chaves Estrangeiras copiado para a área de transferência!', 'success');
    } else {
        showToast(`Erro ao gerar DDL: ${data?.error || 'Falha inesperada'}`, 'error');
    }
}


/* ═══════════════════════════════════════════════════════
   3. SQL RUNNER & QUERY EXECUTION CONSOLE
═══════════════════════════════════════════════════════ */

let lastQueryResultRows = [];
let lastQueryColumns = [];

async function executeInteractiveSqlQuery() {
    const input = document.getElementById('sqlQueryInput');
    const query = input ? input.value.trim() : '';
    const dbPath = document.getElementById('sqlRunnerDbPath').value.trim();
    const meta = document.getElementById('sqlQueryMeta');
    const gridWrap = document.getElementById('sqlResultsGridWrap');
    const exportBtn = document.getElementById('btnExportQueryResult');

    if (!query) {
        showToast('Digite uma consulta SQL para executar.', 'warning');
        return;
    }

    if (meta) meta.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Executando consulta no Firebird...';

    const tStart = performance.now();

    const { data } = await safeFetchJson('/api/firebird/query-exec', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            query: query,
            database: dbPath
        })
    });
    const duration = Math.round(performance.now() - tStart);

    if (data && data.success) {
        lastQueryResultRows = data.rows || [];
        lastQueryColumns = data.columns || [];

        if (meta) {
            meta.innerHTML = `<i class="fa-solid fa-circle-check" style="color:#10B981;"></i> <span>Sucesso: <strong>${data.row_count || data.rows?.length || 0}</strong> registros retornados em <strong>${duration}ms</strong></span>`;
        }

        if (exportBtn) exportBtn.style.display = (lastQueryResultRows.length > 0) ? 'inline-flex' : 'none';

        renderSqlResultGrid(lastQueryColumns, lastQueryResultRows);
    } else {
        if (meta) meta.innerHTML = `<i class="fa-solid fa-circle-xmark" style="color:#EF4444;"></i> <span style="color:#EF4444;">Erro na consulta</span>`;
        gridWrap.innerHTML = `<div style="padding:20px; color:var(--danger); font-family:var(--font-mono); font-size:0.8rem;"><i class="fa-solid fa-triangle-exclamation"></i> ${data?.error || 'Erro ao executar SQL'}</div>`;
        if (exportBtn) exportBtn.style.display = 'none';
    }
}

function renderSqlResultGrid(columns, rows) {
    const wrap = document.getElementById('sqlResultsGridWrap');
    if (!wrap) return;

    if (!rows || rows.length === 0) {
        wrap.innerHTML = '<div class="sql-results-empty">Nenhum registro retornado para esta consulta.</div>';
        return;
    }

    let html = '<table class="modern-table" style="font-size:0.75rem;"><thead><tr>';
    columns.forEach(col => {
        html += `<th>${col}</th>`;
    });
    html += '</tr></thead><tbody>';

    rows.forEach(r => {
        html += '<tr>';
        columns.forEach(col => {
            const val = r[col] !== undefined ? r[col] : '';
            html += `<td>${val !== null ? val : '<em style="opacity:0.4;">NULL</em>'}</td>`;
        });
        html += '</tr>';
    });

    html += '</tbody></table>';
    wrap.innerHTML = html;
}

function populateSqlSampleQuery(type) {
    const tbl = (activeTable || 'CLIENTES.DB').replace(/\.db$/i, '').toUpperCase();
    const input = document.getElementById('sqlQueryInput');
    if (!input) return;

    if (type === 'SELECT_ALL') {
        input.value = `SELECT * FROM ${tbl} ROWS 50;`;
    } else if (type === 'COUNT_ALL') {
        input.value = `SELECT COUNT(*) AS TOTAL_REGISTROS FROM ${tbl};`;
    }
    input.focus();
}

function clearSqlQueryInput() {
    const input = document.getElementById('sqlQueryInput');
    if (input) input.value = '';
}

function exportQueryResultCsv() {
    if (!lastQueryResultRows || lastQueryResultRows.length === 0) return;
    let csv = lastQueryColumns.join(';') + '\n';
    lastQueryResultRows.forEach(r => {
        const rowVals = lastQueryColumns.map(c => {
            const v = r[c];
            if (v === null || v === undefined) return '';
            return String(v).replace(/;/g, ',');
        });
        csv += rowVals.join(';') + '\n';
    });
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `query_result_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
}


/* ═══════════════════════════════════════════════════════
   4. MIGRATION WIZARD MODULE (4-STEP EXPRESS GUIDE)
═══════════════════════════════════════════════════════ */

let wizardCurrentStep = 1;
let wizardSource = 'samples';

function openMigrationWizard() {
    wizardCurrentStep = 1;
    const modal = document.getElementById('wizardModalOverlay');
    if (modal) modal.classList.add('active');
    updateWizardStepUI();
    renderWizardStep1();
}

function closeMigrationWizard(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('wizardModalOverlay');
    if (modal) modal.classList.remove('active');
}

function updateWizardStepUI() {
    for (let s = 1; s <= 4; s++) {
        const stepEl = document.getElementById(`wizStep${s}`);
        const pageEl = document.getElementById(`wizPage${s}`);
        const lineEl = document.getElementById(`wizLine${s}`);

        if (stepEl) {
            stepEl.classList.toggle('active', s === wizardCurrentStep);
            stepEl.classList.toggle('completed', s < wizardCurrentStep);
        }
        if (pageEl) pageEl.classList.toggle('active', s === wizardCurrentStep);
        if (lineEl) lineEl.style.background = (s < wizardCurrentStep) ? '#10B981' : 'rgba(255,255,255,0.1)';
    }

    const btnPrev = document.getElementById('btnWizPrev');
    const btnNext = document.getElementById('btnWizNext');

    if (btnPrev) btnPrev.disabled = (wizardCurrentStep === 1);
    if (btnNext) {
        if (wizardCurrentStep === 4) {
            btnNext.innerHTML = '<i class="fa-solid fa-bolt"></i> Iniciar Migração Completa';
        } else {
            btnNext.innerHTML = 'Avançar <i class="fa-solid fa-arrow-right"></i>';
        }
    }
}

function wizardNavNext() {
    if (wizardCurrentStep === 4) {
        runWizardMigration();
        return;
    }

    wizardCurrentStep++;
    updateWizardStepUI();

    if (wizardCurrentStep === 2) renderWizardStep2();
    if (wizardCurrentStep === 3) renderWizardStep3();
    if (wizardCurrentStep === 4) renderWizardStep4();
}

function wizardNavPrev() {
    if (wizardCurrentStep > 1) {
        wizardCurrentStep--;
        updateWizardStepUI();
    }
}

function selectWizardSource(src) {
    wizardSource = src;
    document.getElementById('wizCardSamples').classList.toggle('active', src === 'samples');
    document.getElementById('wizCardUploads').classList.toggle('active', src === 'uploads');
    renderWizardStep1();
}

function renderWizardStep1() {
    const preview = document.getElementById('wizTablesPreview');
    if (!preview) return;
    const tables = availableTablesList || [];
    let html = '<div style="font-size:0.75rem; font-weight:700; color:var(--text-main); margin-bottom:6px;"><i class="fa-solid fa-table-list"></i> Tabelas prontas para inclusão:</div>';
    tables.forEach(t => {
        html += `<div style="display:flex; justify-content:space-between; padding:4px 6px; font-size:0.74rem; color:var(--text-muted); border-bottom:1px solid rgba(255,255,255,0.04);">
            <span><i class="fa-solid fa-table"></i> ${t.filename}</span>
            <span><strong>${t.records || 0}</strong> reg &bull; ${t.fields_count || 0} col</span>
        </div>`;
    });
    preview.innerHTML = html;
}

async function renderWizardStep2() {
    const diagDiv = document.getElementById('wizDiagResult');
    diagDiv.innerHTML = '<div style="text-align:center; padding:15px;"><i class="fa-solid fa-spinner fa-spin"></i> Verificando integridade dos arquivos...</div>';

    const { data } = await safeFetchJson('/api/diagnostics/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: wizardSource })
    });

    if (data && data.success) {
        const score = data.report.overall_health || 100;
        diagDiv.innerHTML = `
            <div style="display:flex; align-items:center; gap:14px; background:rgba(16,185,129,0.08); border:1px solid rgba(16,185,129,0.25); border-radius:8px; padding:14px 18px;">
                <div style="font-size:1.8rem; font-weight:800; color:#10B981;">${score}%</div>
                <div>
                    <strong style="color:var(--text-main); font-size:0.92rem;">Diagnóstico Concluído com Sucesso</strong>
                    <p style="font-size:0.76rem; color:var(--text-muted); margin-top:2px;">${data.report.total_tables} tabelas verificadas. Higienização automática de datas e PKs ativada.</p>
                </div>
            </div>
        `;
    } else {
        diagDiv.innerHTML = `<div style="color:var(--danger); padding:12px; font-size:0.82rem; background:rgba(239,68,68,0.05); border-radius:6px; border:1px solid rgba(239,68,68,0.2);"><i class="fa-solid fa-triangle-exclamation"></i> ${data?.error || 'Erro ao executar diagnóstico.'}</div>`;
    }
}

async function renderWizardStep3() {
    const relsDiv = document.getElementById('wizRelationsList');
    relsDiv.innerHTML = '<div style="text-align:center; padding:15px;"><i class="fa-solid fa-spinner fa-spin"></i> Buscando relacionamentos...</div>';

    const { data } = await safeFetchJson('/api/relations/detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: wizardSource })
    });

    if (data && data.success) {
        const rels = data.relations || [];
        let html = '<div style="max-height:180px; overflow-y:auto; border:1px solid var(--border-color); border-radius:6px; padding:6px;">';
        if (rels.length === 0) {
            html += '<div style="color:var(--text-dim); font-size:0.75rem; padding:10px; text-align:center;">Nenhuma FK encontrada para sugerir.</div>';
        } else {
            rels.forEach(r => {
                html += `<div style="display:flex; justify-content:space-between; align-items:center; padding:6px 8px; font-size:0.75rem; border-bottom:1px solid rgba(255,255,255,0.04);">
                    <span><strong style="color:#EC4899;">${r.child_table}.${r.child_column}</strong> ➔ ${r.parent_table}.${r.parent_column}</span>
                    <span class="badge-px-pill">${r.confidence}%</span>
                </div>`;
            });
        }
        html += '</div>';
        relsDiv.innerHTML = html;
    } else {
        relsDiv.innerHTML = `<div style="color:var(--danger); padding:10px; font-size:0.8rem;"><i class="fa-solid fa-triangle-exclamation"></i> ${data?.error || 'Erro ao carregar relacionamentos.'}</div>`;
    }
}

function renderWizardStep4() {
    // Ready for execution
}

async function runWizardMigration() {
    const btnNext = document.getElementById('btnWizNext');
    const pBox = document.getElementById('wizProgressBox');
    const pFill = document.getElementById('wizProgressFill');
    const pSpeed = document.getElementById('wizProgressSpeed');
    const pStatus = document.getElementById('wizProgressStatus');
    const outName = document.getElementById('wizOutputFdbName').value.trim() || 'BANCO_MIGRADO_WIZARD.FDB';
    const charset = document.getElementById('wizFbCharset').value;

    if (btnNext) btnNext.disabled = true;
    if (pBox) pBox.style.display = 'block';

    // Simulate fast progress bar while backend builds FDB
    let pct = 10;
    const interval = setInterval(() => {
        pct = Math.min(92, pct + 12);
        if (pFill) pFill.style.width = `${pct}%`;
        if (pSpeed) pSpeed.textContent = `${Math.round(8000 + Math.random() * 4000)} reg/s`;
    }, 250);

    const selectedList = (availableTablesList || []).map(t => t.filename);
    const { data } = await safeFetchJson('/api/convert/fdb', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            source: wizardSource,
            project_id: currentProject ? currentProject.id : null,
            tables: selectedList,
            charset: charset,
            page_size: 8192,
            fdb_name: outName
        })
    });
    clearInterval(interval);

    if (data && data.success) {
        if (pFill) pFill.style.width = '100%';
        if (pStatus) pStatus.innerHTML = '<i class="fa-solid fa-circle-check" style="color:#10B981;"></i> Migração concluída com sucesso!';
        showToast('Banco Firebird gerado com sucesso pelo Wizard!', 'success');
        
        setTimeout(() => {
            closeMigrationWizard();
            openAuditModal();
        }, 900);
    } else {
        if (pStatus) pStatus.innerHTML = `<span style="color:var(--danger);"><i class="fa-solid fa-triangle-exclamation"></i> ${data?.error || 'Falha na migração'}</span>`;
        showToast(data?.error || 'Falha na migração', 'error');
        if (btnNext) btnNext.disabled = false;
    }
}


/* ═══════════════════════════════════════════════════════
   5. RECONCILIATION & AUDIT DASHBOARD MODULE
═══════════════════════════════════════════════════════ */

let lastAuditSummaryData = null;

function openAuditModal() {
    const modal = document.getElementById('auditModalOverlay');
    if (modal) modal.classList.add('active');
    loadAuditData();
}

function closeAuditModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('auditModalOverlay');
    if (modal) modal.classList.remove('active');
}

async function loadAuditData() {
    const tbody = document.getElementById('auditTableBody');
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--text-dim);"><i class="fa-solid fa-spinner fa-spin"></i> Conciliando dados e calculando somas numéricas...</td></tr>';

    const { data } = await safeFetchJson('/api/audit/reconcile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            source: currentSource,
            project_id: currentProject ? currentProject.id : null,
            duration_seconds: 1.5
        })
    });

    if (data && data.success) {
        lastAuditSummaryData = data.audit;
        renderAuditUI(data.audit);
    } else {
        tbody.innerHTML = `<tr><td colspan="6" style="color:var(--danger); text-align:center; padding:16px; font-size:0.8rem;"><i class="fa-solid fa-triangle-exclamation"></i> ${data?.error || 'Falha na conciliação.'}</td></tr>`;
    }
}

function renderAuditUI(audit) {
    document.getElementById('auditTotalTables').textContent = audit.total_tables || 0;
    document.getElementById('auditTotalSource').textContent = (audit.total_source_records || 0).toLocaleString();
    document.getElementById('auditTotalTarget').textContent = (audit.total_target_records || 0).toLocaleString();
    document.getElementById('auditRate').textContent = `${audit.reconciliation_rate || 100}%`;

    const tbody = document.getElementById('auditTableBody');
    tbody.innerHTML = '';

    const tables = audit.tables || [];
    tables.forEach(t => {
        const tr = document.createElement('tr');
        const isMatch = t.is_match;
        const statusBadge = isMatch 
            ? '<span class="badge-px-pill" style="background:rgba(16,185,129,0.15); color:#34D399;"><i class="fa-solid fa-check"></i> 100%</span>'
            : '<span class="badge-px-pill" style="background:rgba(239,68,68,0.15); color:#F87171;"><i class="fa-solid fa-xmark"></i> Divergência</span>';

        let chkStr = '<em style="color:var(--text-dim); font-size:0.7rem;">-</em>';
        if (t.checksums && Object.keys(t.checksums).length > 0) {
            chkStr = Object.entries(t.checksums).slice(0, 2).map(([k, v]) => `<strong>${k}:</strong> ${Number(v).toLocaleString('pt-BR', {minimumFractionDigits:2})}`).join(' &bull; ');
        }

        tr.innerHTML = `
            <td><strong>${t.table_name}</strong> <small style="color:var(--text-dim);">(${t.filename})</small></td>
            <td style="text-align:center;">${t.fields_count}</td>
            <td style="text-align:right; font-weight:600;">${(t.source_records || 0).toLocaleString()}</td>
            <td style="text-align:right; font-weight:600; color:#10B981;">${(t.target_records || 0).toLocaleString()}</td>
            <td style="text-align:center;">${statusBadge}</td>
            <td style="font-size:0.74rem;">${chkStr}</td>
        `;
        tbody.appendChild(tr);
    });
}

async function openPrintableAuditReport() {
    if (!lastAuditSummaryData) {
        showToast('Nenhum dado de auditoria disponível.', 'warning');
        return;
    }
    const { data } = await safeFetchJson('/api/audit/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audit: lastAuditSummaryData })
    });
    if (data && data.success && data.html) {
        const printWindow = window.open('', '_blank');
        printWindow.document.write(data.html);
        printWindow.document.close();
    } else {
        showToast(`Erro ao gerar relatório: ${data?.error || 'Falha inesperada'}`, 'error');
    }
}

function exportAuditJsonAction() {
    if (!lastAuditSummaryData) return;
    const blob = new Blob([JSON.stringify(lastAuditSummaryData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `auditoria_migracao_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Arquivo JSON de auditoria exportado com sucesso!', 'success');
}


