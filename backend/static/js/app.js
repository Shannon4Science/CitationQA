// Citation Quality Analyzer - Neo-Brutalist Frontend
// SSE + task restore + config panel

const BASE_PATH = document.querySelector('meta[name="base-path"]')?.content || '';

let currentTaskId = null;
let allCitations = [];
let eventSource = null;
let pollInterval = null;

// ===== Settings =====
async function openSettings() {
    const modal = document.getElementById('settings-modal');
    modal.style.display = 'flex';
    document.addEventListener('keydown', settingsEscHandler);

    try {
        const cfg = await apiCall('/api/config');
        document.getElementById('cfg-llm-model').value = cfg.llm?.model || '';
        document.getElementById('cfg-llm-api-key').value = cfg.llm?.api_key || '';
        document.getElementById('cfg-llm-primary-url').value = cfg.llm?.primary_base_url || '';
        document.getElementById('cfg-llm-secondary-url').value = cfg.llm?.secondary_base_url || '';
        document.getElementById('cfg-llm-timeout').value = cfg.llm?.search_timeout || '';
        document.getElementById('cfg-serp-api-key').value = cfg.serpapi?.api_key || '';
        document.getElementById('cfg-s2-api-key').value = cfg.semantic_scholar?.api_key || '';
        document.getElementById('cfg-ads-api-key').value = cfg.adsabs?.api_key || '';
        document.getElementById('cfg-mineru-token').value = cfg.mineru?.api_token || '';
        document.getElementById('cfg-proxy').value = cfg.proxy?.fallback_proxy || '';
    } catch (e) {
        console.warn('Failed to load config', e);
    }
}

function closeSettings() {
    document.getElementById('settings-modal').style.display = 'none';
    document.removeEventListener('keydown', settingsEscHandler);
}

let _overlayMouseDownTarget = null;

function setupOverlayClose() {
    const modal = document.getElementById('settings-modal');
    modal.addEventListener('mousedown', (e) => { _overlayMouseDownTarget = e.target; });
    modal.addEventListener('mouseup', (e) => {
        if (e.target === modal && _overlayMouseDownTarget === modal) closeSettings();
        _overlayMouseDownTarget = null;
    });
}

function settingsEscHandler(e) {
    if (e.key === 'Escape') {
        e.preventDefault();
        closeSettings();
    }
}

async function saveSettings() {
    const payload = {
        llm: {
            model: document.getElementById('cfg-llm-model').value.trim(),
            api_key: document.getElementById('cfg-llm-api-key').value.trim(),
            primary_base_url: document.getElementById('cfg-llm-primary-url').value.trim(),
            secondary_base_url: document.getElementById('cfg-llm-secondary-url').value.trim(),
            search_timeout: document.getElementById('cfg-llm-timeout').value.trim() || null,
        },
        serpapi: { api_key: document.getElementById('cfg-serp-api-key').value.trim() },
        semantic_scholar: { api_key: document.getElementById('cfg-s2-api-key').value.trim() },
        adsabs: { api_key: document.getElementById('cfg-ads-api-key').value.trim() },
        mineru: { api_token: document.getElementById('cfg-mineru-token').value.trim() },
        proxy: { fallback_proxy: document.getElementById('cfg-proxy').value.trim() },
    };

    try {
        await apiCall('/api/config', 'POST', payload);
        closeSettings();
    } catch (e) {
        alert('保存失败: ' + e.message);
    }
}

// ===== View Detailed Report =====
function viewDetailedReport() {
    if (!currentTaskId) return;
    window.open(`${BASE_PATH}/api/report/${currentTaskId}`, '_blank');
}

// ===== 页面加载时恢复任务 =====
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('paper-title').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') startAnalysis();
    });

    setupOverlayClose();

    // 尝试恢复之前的任务
    const savedTaskId = localStorage.getItem('currentTaskId');
    if (savedTaskId) {
        restoreTask(savedTaskId);
    }
});

async function restoreTask(taskId) {
    try {
        const data = await apiCall(`/api/progress/${taskId}`);
        if (data.error) {
            localStorage.removeItem('currentTaskId');
            return;
        }

        currentTaskId = taskId;

        if (data.status === 'completed') {
            // 恢复完成状态
            if (data.paper) showPaperInfo(data.paper);
            showSection('step-progress');
            document.getElementById('progress-fill').style.width = '100%';
            document.getElementById('progress-percent').textContent = '100%';
            document.getElementById('progress-detail').textContent = '分析完成';
            document.getElementById('stat-analyzed').textContent = data.analyzed || 0;
            document.getElementById('stat-fulltext').textContent = data.fulltext_count || 0;
            document.getElementById('stat-abstract').textContent = data.abstract_count || 0;
            document.getElementById('stat-stage').textContent = '完成';
            showResults(data);
        } else if (data.status === 'evaluating' || data.status === 'generating_report') {
            // 恢复进行中的任务
            if (data.paper) showPaperInfo(data.paper);
            showSection('step-progress');
            document.getElementById('progress-new-analysis').style.display = 'block';
            updateProgress(data);
            connectSSE(taskId);
        } else if (data.status === 'error') {
            localStorage.removeItem('currentTaskId');
        }
    } catch (err) {
        console.log('Task restore failed:', err);
        localStorage.removeItem('currentTaskId');
    }
}

// ===== API Helpers =====
async function apiCall(endpoint, method = 'GET', body = null) {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' }
    };
    if (body) options.body = JSON.stringify(body);

    const response = await fetch(BASE_PATH + endpoint, options);
    if (!response.ok) {
        const err = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(err.error || `HTTP ${response.status}`);
    }
    return response.json();
}

// ===== Step 1: Start Analysis =====
async function startAnalysis() {
    const titleInput = document.getElementById('paper-title');
    const title = titleInput.value.trim();

    if (!title) {
        showError('search-error', '请输入论文标题');
        return;
    }

    setButtonLoading('btn-search', true);
    hideError('search-error');

    try {
        const data = await apiCall('/api/search', 'POST', { title });

        if (data.error) {
            showError('search-error', data.error);
            return;
        }

        currentTaskId = data.task_id;
        localStorage.setItem('currentTaskId', currentTaskId);

        const normalizedPaper = {
            ...(data.paper || {}),
            dedup_citation_count: data.total_citations ?? data.paper?.dedup_citation_count ?? data.paper?.citation_count ?? 0,
            citation_count: data.total_citations ?? data.paper?.citation_count ?? 0
        };
        showPaperInfo(normalizedPaper);

        allCitations = data.citations || [];
        showCitationStep(normalizedPaper, allCitations, data.total_citations);

    } catch (err) {
        showError('search-error', `搜索失败: ${err.message}`);
    } finally {
        setButtonLoading('btn-search', false);
    }
}

// ===== Step 2: Show Paper Info =====
function showPaperInfo(paper) {
    const container = document.getElementById('paper-info-content');

    const authors = safeArray(paper.authors).map(a => a.name).filter(Boolean).join(', ');
    const dedupCount = paper.dedup_citation_count ?? paper.citation_count ?? 0;
    const rawCount = paper.raw_citation_count ?? 0;

    container.innerHTML = `
        <div class="info-row"><span class="info-label">标题</span><span class="info-value"><strong>${escapeHtml(paper.title)}</strong></span></div>
        <div class="info-row"><span class="info-label">年份</span><span class="info-value">${paper.year || 'N/A'}</span></div>
        <div class="info-row"><span class="info-label">作者</span><span class="info-value">${escapeHtml(authors) || 'N/A'}</span></div>
        <div class="info-row"><span class="info-label">发表场所</span><span class="info-value">${escapeHtml(paper.venue) || 'N/A'}</span></div>
        <div class="info-row"><span class="info-label">5源去重后被引数</span><span class="info-value"><strong>${dedupCount}</strong></span></div>
        ${rawCount && rawCount !== dedupCount ? `<div class="info-row"><span class="info-label">源接口参考值</span><span class="info-value">${rawCount}</span></div>` : ''}
        ${paper.arxiv_id ? `<div class="info-row"><span class="info-label">ArXiv</span><span class="info-value"><a href="https://arxiv.org/abs/${paper.arxiv_id}" target="_blank">${paper.arxiv_id}</a></span></div>` : ''}
        ${paper.abstract ? `<div class="info-row"><span class="info-label">摘要</span><span class="info-value" style="font-size:0.85rem;line-height:1.5;">${escapeHtml(paper.abstract).substring(0, 300)}${paper.abstract.length > 300 ? '...' : ''}</span></div>` : ''}
    `;

    showSection('step-paper-info');
}

// ===== Step 3: Citation Selection =====
function showCitationStep(paper, citations, totalCitations) {
    const infoEl = document.getElementById('citation-info');
    infoEl.innerHTML = `5源聚合去重后共获取 <strong>${totalCitations || citations.length}</strong> 篇被引论文信息。`;

    if (citations.length > 100) {
        document.getElementById('citation-options').style.display = 'block';
        buildCitationList(citations);
    } else {
        document.getElementById('citation-options').style.display = 'none';
        showSection('step-citations');
        startEvaluation(citations.map((_, i) => i));
        return;
    }

    showSection('step-citations');
}

function buildCitationList(citations) {
    const listEl = document.getElementById('citation-list');
    let html = '';

    citations.forEach((c, i) => {
        const authors = (c.authors || []).slice(0, 3).map(a => a.name).join(', ');
        const influence = c.paper_influence_score || 0;
        const scholarCites = c.scholar_citation_count || 0;
        const source = c.publication_source || c.venue || 'N/A';
        html += `
            <label class="citation-item" for="cite-${i}">
                <input type="checkbox" id="cite-${i}" data-index="${i}" onchange="updateSelectedCount()">
                <div class="citation-item-info">
                    <div class="citation-item-title">${escapeHtml(c.title || 'N/A')}</div>
                    <div class="citation-item-meta">${c.year || 'N/A'} | ${escapeHtml(authors)}</div>
                    <div class="citation-item-meta">影响力 ${influence}/10 | GS被引 ${scholarCites} | ${escapeHtml(source)}</div>
                </div>
            </label>
        `;
    });

    listEl.innerHTML = html;
}

function updateSelectedCount() {
    const checkboxes = document.querySelectorAll('#citation-list input[type="checkbox"]');
    const count = Array.from(checkboxes).filter(cb => cb.checked).length;
    document.getElementById('selected-count').textContent = `已选择: ${count}/100`;
}

function selectAutoTop100() {
    const indices = allCitations.slice(0, 100).map((_, i) => i);
    startEvaluation(indices);
}

function showManualSelect() {
    document.getElementById('manual-select').style.display = 'block';
    document.getElementById('citation-options').style.display = 'none';
}

function selectAll() {
    const checkboxes = document.querySelectorAll('#citation-list input[type="checkbox"]');
    const maxSelect = Math.min(checkboxes.length, 100);
    checkboxes.forEach((cb, i) => { cb.checked = i < maxSelect; });
    updateSelectedCount();
}

function deselectAll() {
    document.querySelectorAll('#citation-list input[type="checkbox"]').forEach(cb => { cb.checked = false; });
    updateSelectedCount();
}

function confirmManualSelect() {
    const checkboxes = document.querySelectorAll('#citation-list input[type="checkbox"]:checked');
    const indices = Array.from(checkboxes).map(cb => parseInt(cb.dataset.index));

    if (indices.length === 0) {
        alert('请至少选择一篇论文');
        return;
    }
    if (indices.length > 100) {
        alert('最多选择100篇论文');
        return;
    }

    startEvaluation(indices);
}

// ===== Step 4: Start Evaluation =====
async function startEvaluation(selectedIndices) {
    // Reset progress UI
    document.getElementById('progress-log').innerHTML = '';
    document.getElementById('progress-fill').style.width = '0%';
    document.getElementById('progress-percent').textContent = '0%';
    document.getElementById('progress-detail').textContent = '准备中...';
    document.getElementById('stat-analyzed').textContent = '0';
    document.getElementById('stat-fulltext').textContent = '0';
    document.getElementById('stat-abstract').textContent = '0';
    document.getElementById('stat-stage').textContent = '-';
    document.getElementById('scholar-progress').style.display = 'none';
    document.getElementById('step-results').style.display = 'none';
    document.getElementById('advanced-section').style.display = 'none';
    destroyCharts();

    showSection('step-progress');
    document.getElementById('progress-new-analysis').style.display = 'block';

    try {
        const data = await apiCall('/api/evaluate', 'POST', {
            task_id: currentTaskId,
            selected_indices: selectedIndices
        });

        if (data.error) {
            addLog(`错误: ${data.error}`, 'error');
            return;
        }

        // Connect SSE for real-time progress
        connectSSE(currentTaskId);

    } catch (err) {
        addLog(`启动评估失败: ${err.message}`, 'error');
        // Fallback to polling
        startProgressPolling();
    }
}

// ===== SSE Long Connection =====
function connectSSE(taskId) {
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource(`${BASE_PATH}/api/stream/${taskId}`);

    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            handleSSEData(data);
        } catch (e) {
            console.error('SSE parse error:', e);
        }
    };

    eventSource.onerror = function(err) {
        console.warn('SSE connection error, falling back to polling');
        eventSource.close();
        eventSource = null;
        // Fallback to polling
        startProgressPolling();
    };
}

function handleSSEData(data) {
    if (data.type === 'progress') {
        updateProgress(data);
    } else if (data.type === 'log') {
        addLog(data.message, data.level || 'info');
    } else if (data.type === 'completed') {
        updateProgress(data);
        if (eventSource) { eventSource.close(); eventSource = null; }
        showResults(data);
    } else if (data.type === 'error') {
        addLog(`分析出错: ${data.error || '未知错误'}`, 'error');
        if (eventSource) { eventSource.close(); eventSource = null; }
    }
}

// ===== Fallback Polling =====
function startProgressPolling() {
    if (pollInterval) clearInterval(pollInterval);

    pollInterval = setInterval(async () => {
        try {
            const data = await apiCall(`/api/progress/${currentTaskId}`);
            updateProgress(data);

            if (data.new_logs) {
                data.new_logs.forEach(log => addLog(log.message, log.level));
            }

            if (data.status === 'completed' || data.status === 'error') {
                clearInterval(pollInterval);
                pollInterval = null;

                if (data.status === 'completed') {
                    showResults(data);
                } else {
                    addLog(`分析出错: ${data.error || '未知错误'}`, 'error');
                }
            }
        } catch (err) {
            console.error('Progress poll error:', err);
        }
    }, 3000);
}

function updateProgress(data) {
    const percent = data.progress || 0;
    document.getElementById('progress-fill').style.width = `${percent}%`;
    document.getElementById('progress-percent').textContent = `${Math.round(percent)}%`;
    document.getElementById('progress-detail').textContent = data.stage || '处理中...';

    document.getElementById('stat-analyzed').textContent = data.analyzed || 0;
    document.getElementById('stat-fulltext').textContent = data.fulltext_count || 0;
    document.getElementById('stat-abstract').textContent = data.abstract_count || 0;
    document.getElementById('stat-stage').textContent = data.stage_short || '-';

    const scholarEl = document.getElementById('scholar-progress');
    if (data.scholar_total > 0) {
        scholarEl.style.display = 'block';
        const cur = data.scholar_current || 0;
        const tot = data.scholar_total || 1;
        document.getElementById('scholar-progress-count').textContent = `${cur}/${tot}`;
        document.getElementById('scholar-progress-fill').style.width = `${Math.round(cur / tot * 100)}%`;
        document.getElementById('scholar-progress-name').textContent = data.scholar_name || '';
    }
}

function addLog(message, level = 'info') {
    const logEl = document.getElementById('progress-log');
    const time = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = `log-entry log-${level}`;
    entry.textContent = `[${time}] ${message}`;
    logEl.appendChild(entry);
    logEl.scrollTop = logEl.scrollHeight;
}

// ===== Step 5: Show Results =====
function showResults(data) {
    showSection('step-results');

    const summaryEl = document.getElementById('results-summary');
    const detailEl = document.getElementById('results-detail');
    const comp = safeObject(data.comprehensive_eval);

    // Summary
    const typeNames = {
        'background_mention': '背景提及',
        'related_work_brief': '相关工作简要提及',
        'method_reference': '方法重点参考',
        'experiment_comparison': '实验对比/Benchmark',
        'multiple_deep': '多处深入引用',
        'unknown': '无法判断'
    };

    let typeDist = '';
    const dist = safeObject(comp.citation_quality_distribution);
    for (const [key, name] of Object.entries(typeNames)) {
        if (dist[key]) {
            typeDist += `<div class="dist-item"><span class="dist-item-label">${name}</span><span class="dist-item-value">${dist[key]}</span></div>`;
        }
    }

    const depthNames = { 'superficial': '表面引用', 'moderate': '中等深度', 'substantial': '深入引用', 'unknown': '无法判断' };
    let depthDist = '';
    const dd = safeObject(comp.depth_distribution);
    for (const [key, name] of Object.entries(depthNames)) {
        if (dd[key]) {
            depthDist += `<div class="dist-item"><span class="dist-item-label">${name}</span><span class="dist-item-value">${dd[key]}</span></div>`;
        }
    }

    let keyFindings = '';
    if (safeArray(comp.key_findings).length) {
        keyFindings = '<ul class="key-findings">' + safeArray(comp.key_findings).map(f => `<li>${escapeHtml(f)}</li>`).join('') + '</ul>';
    }

    summaryEl.innerHTML = `
        <h3>综合评估结果</h3>
        <div class="score-badge">总体影响力: ${comp.overall_impact_score || 'N/A'}/10</div>
        <p style="margin-top:12px;">${escapeHtml(comp.overall_summary || '')}</p>
        ${keyFindings}
        <div class="distribution-grid">
            <div class="dist-card"><h4>引用类型分布</h4>${typeDist || '<p style="font-size:0.8rem;color:var(--text-light);">无数据</p>'}</div>
            <div class="dist-card"><h4>引用深度分布</h4>${depthDist || '<p style="font-size:0.8rem;color:var(--text-light);">无数据</p>'}</div>
        </div>
    `;

    // Detail list
    const evaluations = safeArray(data.evaluations);
    let detailHtml = '<div class="results-block-title">逐篇详细分析</div>';

    evaluations.forEach((ev, i) => {
        const score = ev.quality_score || 0;
        const influence = ev.paper_influence_score || 0;
        const scoreClass = score >= 4 ? 'score-high' : score >= 2 ? 'score-medium' : 'score-low';
        const ftTag = ev.fulltext_available ? '<span class="tag tag-fulltext">全文</span>' : '<span class="tag tag-abstract">摘要</span>';
        const sentimentTag = ev.citation_sentiment ? `<span class="tag tag-sentiment">${escapeHtml(ev.citation_sentiment)}</span>` : '';
        const evalTag = ev.evaluation_method === 'web_search'
            ? '<span class="tag tag-verified">联网核验</span>'
            : '<span class="tag tag-fallback">全文回退</span>';

        // 全文链接
        let fulltextLinks = '';
        if (ev.fulltext_url) {
            fulltextLinks += `<a href="${escapeHtml(ev.fulltext_url)}" target="_blank" class="fulltext-link">全文链接</a>`;
        }
        if (ev.html_url) {
            fulltextLinks += `<a href="${escapeHtml(ev.html_url)}" target="_blank" class="fulltext-link">HTML</a>`;
        }
        if (ev.pdf_url) {
            fulltextLinks += `<a href="${escapeHtml(ev.pdf_url)}" target="_blank" class="fulltext-link">PDF</a>`;
        }

        // 引用位置
        let locationsHtml = '';
        if (safeArray(ev.citation_locations).length > 0) {
            locationsHtml = '<div class="citation-locations"><strong>引用位置:</strong>';
            safeArray(ev.citation_locations).forEach(loc => {
                locationsHtml += `<div class="location-item"><span class="location-section">${escapeHtml(loc.section || 'N/A')}</span>: ${escapeHtml((loc.context || '').substring(0, 200))}</div>`;
            });
            locationsHtml += '</div>';
        }

        const sourceMeta = [
            `论文影响力 ${influence}/10`,
            `GS被引 ${ev.scholar_citation_count || 0}`,
            ev.publication_source ? `来源 ${escapeHtml(ev.publication_source)}` : ''
        ].filter(Boolean).join(' | ');

        const evidenceHtml = ev.evidence_summary
            ? `<div class="result-item-summary"><strong>核验说明:</strong> ${escapeHtml(ev.evidence_summary)}</div>`
            : '';
        const sourceCountHtml = safeArray(ev.evidence_sources).length
            ? `<div class="result-item-summary">联网证据源: ${safeArray(ev.evidence_sources).length} 个</div>`
            : '';

        detailHtml += `
            <div class="result-item">
                <div class="result-item-header">
                    <span class="result-item-title">${i + 1}. ${escapeHtml(ev.citing_title || 'N/A')}</span>
                    <span class="result-item-score ${scoreClass}">${score}/5</span>
                </div>
                <div class="result-item-meta">
                    ${ev.citing_year || 'N/A'} |
                    <span class="tag tag-type">${ev.citation_type || 'unknown'}</span>
                    <span class="tag tag-depth">${ev.citation_depth || 'unknown'}</span>
                    ${sentimentTag}
                    ${ftTag}
                    ${evalTag}
                    ${fulltextLinks ? `<span class="fulltext-links">${fulltextLinks}</span>` : ''}
                </div>
                <div class="result-item-summary">${escapeHtml(ev.summary || '')}</div>
                <div class="result-item-summary">${sourceMeta}</div>
                ${evidenceHtml}
                ${sourceCountHtml}
                ${ev.paper_influence_reason ? `<div class="result-item-summary">${escapeHtml(ev.paper_influence_reason)}</div>` : ''}
                ${locationsHtml}
            </div>
        `;
    });

    if (!evaluations.length) {
        detailHtml += '<p class="empty-hint">当前没有可展示的逐篇详细分析结果。</p>';
    }

    detailEl.innerHTML = detailHtml;

    showAdvancedAnalytics(data);
}

// ===== Advanced Analytics Panels (inline within Step 5) =====
let chartInstances = [];
function destroyCharts() {
    chartInstances.forEach(c => { try { c.destroy(); } catch(e) {} });
    chartInstances = [];
}

function showAdvancedAnalytics(data) {
    const analytics = safeObject(data.advanced_analytics);
    const scholars = safeArray(data.scholar_profiles);

    destroyCharts();
    document.getElementById('advanced-section').style.display = 'block';

    renderCitationSummary(analytics.citation_description_summary, analytics.stats_summary);
    renderInteractiveCharts(analytics);
    renderScholars(scholars);
    renderDescriptionAnalysis(analytics.citation_description_analysis);
    renderPrediction(analytics.influence_prediction);
    renderInsights(analytics.insight_cards);
}

function renderInteractiveCharts(analytics) {
    const el = document.getElementById('advanced-charts');
    if (!analytics) { el.innerHTML = ''; return; }
    if (typeof Chart === 'undefined') {
        el.innerHTML = '<h3 class="advanced-section-title">引用分布与趋势图表</h3><p style="color:var(--text-secondary);font-size:0.85rem;">图表脚本未成功加载，暂时无法显示交互式图表。</p>';
        return;
    }

    const COLORS = ['#e8890c','#3b82c4','#4caf8a','#7c5cbf','#c45a5a','#d4892a','#6ba3d6','#48bb78','#9f7aea','#fc8181'];
    const chartPlugins = typeof ChartDataLabels !== 'undefined' ? [ChartDataLabels] : [];
    let html = '<h3 class="advanced-section-title">引用分布与趋势图表</h3><div class="charts-grid">';
    let hasCharts = false;

    const td = safeObject(analytics.time_distribution);
    if (td.labels && td.labels.length) { html += '<div class="chart-card"><h4>引用时间分布</h4><canvas id="chartTimeDist"></canvas></div>'; hasCharts = true; }
    const cd = safeObject(analytics.country_distribution_all);
    if (cd.labels && cd.labels.length) { html += '<div class="chart-card"><h4>第一作者国家/地区分布</h4><canvas id="chartCountry"></canvas></div>'; hasCharts = true; }
    const sl = safeObject(analytics.scholar_level_distribution);
    if (sl.labels && sl.labels.length) { html += '<div class="chart-card"><h4>学者层级分布</h4><canvas id="chartScholarLevel"></canvas></div>'; hasCharts = true; }
    const cda = safeObject(analytics.citation_description_analysis);
    const sd = safeObject(cda.sentiment_distribution);
    if (sd.positive || sd.neutral || sd.critical) { html += '<div class="chart-card"><h4>引用情感分布</h4><canvas id="chartSentiment"></canvas></div>'; hasCharts = true; }
    const cdp = safeObject(cda.citation_depth);
    if (cdp.core_citation || cdp.reference_citation) { html += '<div class="chart-card"><h4>引用深度分布</h4><canvas id="chartDepth"></canvas></div>'; hasCharts = true; }
    const pred = safeObject(analytics.influence_prediction);
    const trend = safeObject(pred.trend_data);
    if (trend.labels && trend.labels.length) { html += '<div class="chart-card"><h4>引用趋势预测</h4><canvas id="chartTrend"></canvas></div>'; hasCharts = true; }
    const scores = safeArray(pred.impact_scores);
    if (scores.length) { html += '<div class="chart-card"><h4>影响力维度评分</h4><canvas id="chartImpact"></canvas></div>'; hasCharts = true; }

    html += '</div>';
    if (!hasCharts) {
        html += '<p class="empty-hint">当前暂无可绘制图表的数据。</p>';
    }
    el.innerHTML = html;

    setTimeout(() => {
        if (td.labels && td.labels.length) {
            chartInstances.push(new Chart(document.getElementById('chartTimeDist'), {
                type: 'bar', data: { labels: td.labels, datasets: [{ label: '引用数量', data: td.values, backgroundColor: '#e8890c', borderRadius: 4, hoverBackgroundColor: '#d4760a' }] },
                options: { responsive: true, plugins: { legend: { display: false }, datalabels: { anchor: 'end', align: 'top', font: { size: 10 } } }, scales: { y: { beginAtZero: true } } },
                plugins: chartPlugins
            }));
        }
        if (cd.labels && cd.labels.length) {
            chartInstances.push(new Chart(document.getElementById('chartCountry'), {
                type: 'bar', data: { labels: cd.labels.slice(0,8), datasets: [{ label: '论文数', data: cd.values.slice(0,8), backgroundColor: COLORS.slice(0,8), borderRadius: 4 }] },
                options: { indexAxis: 'y', responsive: true, plugins: { legend: { display: false }, datalabels: { anchor: 'end', align: 'right', font: { size: 10 } } }, scales: { x: { beginAtZero: true } } },
                plugins: chartPlugins
            }));
        }
        if (sl.labels && sl.labels.length) {
            chartInstances.push(new Chart(document.getElementById('chartScholarLevel'), {
                type: 'doughnut', data: { labels: sl.labels, datasets: [{ data: sl.values, backgroundColor: COLORS.slice(0, sl.labels.length), hoverOffset: 12 }] },
                options: { responsive: true, plugins: { datalabels: { formatter: (v, ctx) => { const sum = ctx.dataset.data.reduce((a,b)=>a+b,0); return Math.round(v/sum*100)+'%'; }, color: '#fff', font: { weight: 'bold' } } } },
                plugins: chartPlugins
            }));
        }
        if (sd.positive || sd.neutral || sd.critical) {
            const sLabels = [], sValues = [], sColors = [];
            if (sd.positive) { sLabels.push('正面'); sValues.push(sd.positive); sColors.push('#4caf8a'); }
            if (sd.neutral) { sLabels.push('中性'); sValues.push(sd.neutral); sColors.push('#3b82c4'); }
            if (sd.critical) { sLabels.push('批评'); sValues.push(sd.critical); sColors.push('#c45a5a'); }
            chartInstances.push(new Chart(document.getElementById('chartSentiment'), {
                type: 'doughnut', data: { labels: sLabels, datasets: [{ data: sValues, backgroundColor: sColors, hoverOffset: 12 }] },
                options: { responsive: true, plugins: { datalabels: { formatter: v => v+'%', color: '#fff', font: { weight: 'bold' } } } },
                plugins: chartPlugins
            }));
        }
        if (cdp.core_citation || cdp.reference_citation) {
            const dLabels = [], dValues = [], dColors = ['#e8890c','#3b82c4','#7c5cbf'];
            if (cdp.core_citation) { dLabels.push('核心引用'); dValues.push(cdp.core_citation); }
            if (cdp.reference_citation) { dLabels.push('参考引用'); dValues.push(cdp.reference_citation); }
            if (cdp.supplementary_citation) { dLabels.push('补充说明'); dValues.push(cdp.supplementary_citation); }
            chartInstances.push(new Chart(document.getElementById('chartDepth'), {
                type: 'doughnut', data: { labels: dLabels, datasets: [{ data: dValues, backgroundColor: dColors.slice(0,dLabels.length), hoverOffset: 12 }] },
                options: { responsive: true, plugins: { datalabels: { formatter: v => v+'%', color: '#fff', font: { weight: 'bold' } } } },
                plugins: chartPlugins
            }));
        }
        if (trend.labels && trend.labels.length) {
            const actual = (trend.actual||[]).map(v => v === null ? undefined : v);
            const forecast = (trend.forecast||[]).map(v => v === null ? undefined : v);
            chartInstances.push(new Chart(document.getElementById('chartTrend'), {
                type: 'line', data: { labels: trend.labels, datasets: [
                    { label: '实际引用', data: actual, borderColor: '#e8890c', backgroundColor: 'rgba(232,137,12,0.1)', fill: true, tension: 0.3, pointRadius: 4, pointHoverRadius: 7, borderWidth: 2.5, spanGaps: false },
                    { label: '预测引用', data: forecast, borderColor: '#3b82c4', borderDash: [6,4], backgroundColor: 'rgba(59,130,196,0.08)', fill: true, tension: 0.3, pointRadius: 5, pointStyle: 'rectRot', pointHoverRadius: 8, borderWidth: 2.5, spanGaps: false }
                ]},
                options: { responsive: true, interaction: { intersect: false, mode: 'index' }, plugins: { datalabels: { display: false } }, scales: { y: { beginAtZero: true } } }
            }));
        }
        if (scores.length) {
            const fillMap = { 'fill-cyan': '#3b82c4', 'fill-green': '#4caf8a', 'fill-purple': '#7c5cbf', 'fill-orange': '#e8890c' };
            chartInstances.push(new Chart(document.getElementById('chartImpact'), {
                type: 'bar', data: { labels: scores.map(s=>s.label), datasets: [{ data: scores.map(s=>s.score), backgroundColor: scores.map(s=> fillMap[s.color_class]||'#e8890c'), borderRadius: 4, hoverBackgroundColor: scores.map(s=> fillMap[s.color_class]||'#d4760a') }] },
                options: { indexAxis: 'y', responsive: true, plugins: { legend: { display: false }, datalabels: { anchor: 'end', align: 'right', font: { size: 11, weight: 'bold' } } }, scales: { x: { beginAtZero: true, max: 100 } } },
                plugins: chartPlugins
            }));
        }
    }, 50);
}

function renderScholars(scholars) {
    const el = document.getElementById('advanced-scholars');
    if (!scholars || scholars.length === 0) {
        el.innerHTML = '<h3 class="advanced-section-title">知名学者画像一览</h3><p class="empty-hint">暂未识别到满足条件的知名学者。</p>';
        return;
    }
    let html = '<h3 class="advanced-section-title">知名学者画像一览</h3><div class="scholars-list">';
    scholars.forEach(s => {
        const topBadge = s.is_top ? '<span class="scholar-badge scholar-top">顶尖学者</span>' : '';
        const levelBadge = s.level_label ? `<span class="scholar-badge">${escapeHtml(s.level_label)}</span>` : '';
        html += `<div class="scholar-card">
            <div class="scholar-header">
                <strong>${escapeHtml(s.name || '')}</strong> ${topBadge} ${levelBadge}
            </div>
            <div class="scholar-meta">
                ${s.institution ? `<span>${escapeHtml(s.institution)}</span>` : ''}
                ${s.country ? `<span> | ${escapeHtml(s.country)}</span>` : ''}
            </div>
            ${s.honors ? `<div class="scholar-honors">${escapeHtml(s.honors)}</div>` : ''}
            ${s.citing_paper_title ? `<div class="scholar-citing">引用论文: ${escapeHtml(s.citing_paper_title.substring(0, 80))}${s.citing_paper_title.length > 80 ? '...' : ''}</div>` : ''}
            ${s.citation_summary ? `<div class="scholar-desc">${escapeHtml(s.citation_summary.substring(0, 150))}</div>` : ''}
        </div>`;
    });
    html += '</div>';
    el.innerHTML = html;
}

function renderDescriptionAnalysis(analysis) {
    const el = document.getElementById('advanced-description');
    if (!analysis) { el.innerHTML = '<h3 class="advanced-section-title">被引描述深度分析</h3><p class="empty-hint">暂无被引描述分析数据。</p>'; return; }
    let html = '<h3 class="advanced-section-title">被引描述深度分析</h3>';
    const types = safeArray(analysis.citation_types);
    if (types.length) {
        html += '<div class="desc-section"><h4>引用用途类型</h4><div class="desc-bars">';
        const maxCount = Math.max(...types.map(t => t.count || 0), 1);
        types.forEach(t => {
            const pct = Math.round((t.count / maxCount) * 100);
            html += `<div class="desc-bar-row"><span class="desc-bar-label">${escapeHtml(t.type)}</span><div class="desc-bar-track"><div class="desc-bar-fill" style="width:${pct}%"></div></div><span class="desc-bar-count">${t.count}</span></div>`;
        });
        html += '</div></div>';
    }
    const findings = safeArray(analysis.key_findings);
    if (findings.length) {
        html += '<div class="desc-section"><h4>关键发现</h4><ul class="key-findings">';
        findings.forEach(f => { html += `<li>${escapeHtml(f)}</li>`; });
        html += '</ul></div>';
    }
    if (!types.length && !findings.length) {
        html += '<p class="empty-hint">暂无足够数据进行被引描述深度分析。</p>';
    }
    el.innerHTML = html;
}

function renderPrediction(pred) {
    const el = document.getElementById('advanced-prediction');
    if (!pred) { el.innerHTML = '<h3 class="advanced-section-title">影响力预测分析</h3><p class="empty-hint">暂无预测数据。</p>'; return; }
    let html = '<h3 class="advanced-section-title">影响力预测分析</h3>';
    const metrics = safeArray(pred.prediction_metrics);
    if (metrics.length) {
        html += '<div class="prediction-metrics">';
        metrics.forEach(m => {
            html += `<div class="prediction-metric-card"><div class="metric-value">${escapeHtml(m.value || '')}</div><div class="metric-label">${escapeHtml(m.label || '')}</div><div class="metric-note">${escapeHtml(m.note || '')}</div></div>`;
        });
        html += '</div>';
    }
    const scores = safeArray(pred.impact_scores);
    if (scores.length) {
        html += '<div class="impact-scores">';
        scores.forEach(s => {
            html += `<div class="impact-score-row"><span class="impact-label">${escapeHtml(s.label)}</span><div class="impact-bar-track"><div class="impact-bar-fill ${s.color_class || ''}" style="width:${s.score}%"></div></div><span class="impact-value">${s.score}</span></div>`;
        });
        html += '</div>';
    }
    if (pred.prediction_commentary) {
        html += `<div class="prediction-commentary"><p>${escapeHtml(pred.prediction_commentary)}</p></div>`;
    }
    if (!metrics.length && !scores.length && !pred.prediction_commentary) {
        html += '<p class="empty-hint">暂无预测数据。</p>';
    }
    el.innerHTML = html;
}

function renderInsights(insights) {
    const el = document.getElementById('advanced-insights');
    if (!insights || insights.length === 0) {
        el.innerHTML = '<h3 class="advanced-section-title">数据洞察</h3><p class="empty-hint">暂无数据洞察。</p>';
        return;
    }
    let html = '<h3 class="advanced-section-title">数据洞察</h3><div class="insights-grid">';
    insights.forEach(ins => {
        const color = ins.color || 'teal';
        html += `<div class="insight-card insight-${color}"><div class="insight-icon">${ins.icon || ''}</div><div class="insight-title">${escapeHtml(ins.title || '')}</div><div class="insight-body">${ins.body || ''}</div></div>`;
    });
    html += '</div>';
    el.innerHTML = html;
}

function renderCitationSummary(summary, stats) {
    const el = document.getElementById('advanced-summary');
    let html = '';
    if (stats) {
        html += '<h3 class="advanced-section-title">分析概况</h3><div class="stats-overview">';
        html += `<div class="stat-pill">施引论文 <strong>${stats.total_papers || 0}</strong></div>`;
        html += `<div class="stat-pill">知名学者 <strong>${stats.unique_scholars || 0}</strong></div>`;
        html += `<div class="stat-pill">院士/Fellow <strong>${stats.fellow_count || 0}</strong></div>`;
        html += `<div class="stat-pill">覆盖国家 <strong>${stats.country_count || 0}</strong></div>`;
        html += `<div class="stat-pill">自引 <strong>${stats.self_citation_count || 0}</strong></div>`;
        html += '</div>';
    }
    if (summary) {
        html += `<h3 class="advanced-section-title">被引描述综合总结</h3><div class="citation-summary-text">${safeString(summary).replace(/\n/g, '<br>')}</div>`;
    }
    if (!html) {
        html = '<h3 class="advanced-section-title">分析概况</h3><p class="empty-hint">高级分析结果正在准备中或当前暂无数据。</p>';
    }
    el.innerHTML = html;
}

// ===== "分析其他论文" =====
function startNewAnalysis() {
    // 关闭SSE连接
    if (eventSource) { eventSource.close(); eventSource = null; }
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }

    // 清除任务状态
    currentTaskId = null;
    allCitations = [];
    localStorage.removeItem('currentTaskId');

    // 重置UI
    document.getElementById('step-paper-info').style.display = 'none';
    document.getElementById('step-citations').style.display = 'none';
    document.getElementById('step-progress').style.display = 'none';
    document.getElementById('step-results').style.display = 'none';
    document.getElementById('advanced-section').style.display = 'none';
    document.getElementById('progress-new-analysis').style.display = 'none';
    document.getElementById('scholar-progress').style.display = 'none';
    destroyCharts();

    // 清空进度日志
    document.getElementById('progress-log').innerHTML = '';
    document.getElementById('progress-fill').style.width = '0%';
    document.getElementById('progress-percent').textContent = '0%';
    document.getElementById('progress-detail').textContent = '准备中...';
    document.getElementById('stat-analyzed').textContent = '0';
    document.getElementById('stat-fulltext').textContent = '0';
    document.getElementById('stat-abstract').textContent = '0';
    document.getElementById('stat-stage').textContent = '-';

    // 清空输入
    document.getElementById('paper-title').value = '';
    hideError('search-error');

    // 显示输入步骤
    document.getElementById('step-input').style.display = 'block';

    // 滚动到顶部
    window.scrollTo({ top: 0, behavior: 'smooth' });

    // 聚焦输入框
    setTimeout(() => document.getElementById('paper-title').focus(), 300);
}

// ===== Download =====
function downloadReport(format) {
    if (!currentTaskId) return;
    window.open(`${BASE_PATH}/api/download/${currentTaskId}/${format}`, '_blank');
}

// ===== Utilities =====
function showSection(id) {
    document.getElementById(id).style.display = 'block';
    setTimeout(() => {
        document.getElementById(id).scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
}

function setButtonLoading(btnId, loading) {
    const btn = document.getElementById(btnId);
    const textEl = btn.querySelector('.btn-text');
    const loadingEl = btn.querySelector('.btn-loading');

    if (loading) {
        textEl.style.display = 'none';
        loadingEl.style.display = 'inline';
        btn.disabled = true;
    } else {
        textEl.style.display = 'inline';
        loadingEl.style.display = 'none';
        btn.disabled = false;
    }
}

function showError(id, message) {
    const el = document.getElementById(id);
    el.textContent = message;
    el.style.display = 'block';
}

function hideError(id) {
    document.getElementById(id).style.display = 'none';
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function safeArray(value) {
    return Array.isArray(value) ? value : [];
}

function safeObject(value) {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function safeString(value) {
    if (typeof value === 'string') return value;
    if (value === null || value === undefined) return '';
    return String(value);
}
