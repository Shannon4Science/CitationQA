# Citation Quality Analyzer  - 部署与使用文档

**版本**: 5.0
**作者**: 党琛颢 (Chenhao Dang)
**更新日期**: 2026-03-24

---

## 1. 系统简介

**CitationQA（Citation Quality Analyzer）** 是一个智能的学术论文被引质量评估与影响力画像系统。它接收一篇论文的标题，自动从多个学术数据源（Semantic Scholar, ArXiv, PubMed, Google Scholar, ADS ABS）检索其被引文献列表，通过并发处理获取这些文献的全文或摘要，利用大型语言模型（LLM）对每一篇引用的质量进行深度分析，并在此基础上完成学者画像补全、引用描述深度分析、影响力预测和数据洞察，最终生成一份交互式静态网页报告，同时保留 Markdown 和 PDF 导出能力。

### v5.0 特性

- **交互式静态报告页面**: 分析完成后一键生成基于 Astro + React 的交互式静态网页报告，替代传统 PDF/Markdown 导出作为主要展示方式。报告包含 Dashboard 总览、引用画廊、人口地域分布、影响力与学者、知识图谱五大模块，支持 ECharts 图表交互与 D3.js 力导向图可视化。

- **引用星座图 (Citation Constellation)**: 基于 D3.js 力导向图构建论文引用关系可视化，节点区分目标论文与施引论文，hover 时显示论文类型、年份、评分和完整标题，支持缩放和拖拽交互。
- **前端全配置化**: 所有后端配置项（LLM、SerpAPI、Semantic Scholar、ADS ABS、MinerU、代理）均可通过前端设置面板实时修改，区分必填与可选字段，无需手动编辑 `config.py` 或重启服务。
- **学者画像并发加速**: 学者画像补全阶段引入 `ThreadPoolExecutor` 并发查询（默认 5 并发），配合线程安全的作者缓存，大幅缩短单次分析的学者画像耗时。
- **学者画像实时进度**: 学者画像补全过程中实时推送当前作者查询进度（已完成 / 总数 / 当前作者姓名），前端显示进度条与作者名称。
- **Astro 静态站点构建集成**: 后端自动导出 `report.json`，调用 Astro 构建静态站点，通过 Flask 路由直接提供预渲染的 HTML 页面及 `_astro` 静态资源，无需独立部署。
- **影响力雷达图动态渲染**: 影响力维度评分支持 3+ 维雷达图和 1-2 维水平条形图的自适应切换，数据从 `influence_prediction.impact_scores` 动态读取。
- **引用趋势预测图**: 新增基于历史引用数据和 LLM 预测的年度趋势折线图（实际值 + 预测值），集成于 Impact & Scholars 模块。

### v4.0 特性

- **引用时间 · 地域分布 · 学者层级分析**: 五维分析面板 — 引用时间分布、第一作者国家/地区分布（全部施引文献）、知名学者国家/地区分布、顶尖学者国家/地区分布、学者层级分布（两院院士 / Fellow / 其他知名学者），全部由后端生成图表并嵌入报告。
- **被引描述深度分析**: 结合全文引用定位（`citation_contexts`）与搜索型 LLM 确认引用位置及评价语气，输出引用用途类型分布、引用位置分布、引用情感分布、引用深度分布、关键发现与综合说明。
- **知名学者画像一览**: 自动为每篇被引论文的第一作者补全机构、国家、荣誉头衔和学者层级（搜索型 LLM + SerpApi 联合检索），生成知名学者卡片列表。包含姓名、机构、国家、职务、荣誉称号、层级、引用论文和引用描述摘要。
- **影响力预测分析**: 基于引用年份趋势数据，结合 LLM 与线性回归回退策略，生成年度趋势预测图（含历史值与预测值）、预测指标卡片、影响力维度评分和预测评语。
- **数据洞察与画像总结**: 自动生成 4 条数据洞察卡片和被引描述综合总结，整合进综合评估报告，不另起体系。
- **后端图表生成**: 所有分析图表由后端 matplotlib 生成 PNG 文件，前端直接加载图片展示，同时嵌入 Markdown 和 PDF 报告，确保浏览器与导出报告内容一致。
- **搜索型 LLM 客户端**: 新增独立搜索型 LLM 接口，专用于学者信息检索、引用描述确认、影响力预测等需要联网搜索能力的场景；当前通过 Responses API + `web_search` 调用，并与主评估共用统一配置文件中的模型设置。
- **SerpApi 三类检索扩展**: 新增 Google Search API（学者/机构网页级检索）、Google Scholar Profiles（学者主页检索）、Google AI Mode API（结构化问答补充检索），用于学者画像补全。
- **引用定位接入主流程**: 将已有的 `fetch_fulltext_with_citation_context()` 真正接入逐篇评估链路，为 LLM 提供预定位的引用上下文，提升分析精度。
- **著名机构匹配**: 自动匹配施引论文作者所在机构是否属于国际/国内科技企业和顶尖高校（Google、OpenAI、清华、MIT 等 30+ 机构），生成机构引用统计。

### v3.0 保留特性

- **多源聚合检索**: Google Scholar (via SerpAPI)、ADS ABS、Semantic Scholar、ArXiv、PubMed 五源聚合去重。
- **增强的论文解析**: ArXiv HTML 精确定位、MinerU API PDF 解析。
- **智能LLM策略**: 网络错误自动重试、自动切换可用服务。
- **落地页PDF发现增强**: 多级回退链路提升全文获取率。
- **单篇论文影响力指标**: Google Scholar 被引次数 + 发表来源综合评分。
- **高性能并发处理**: asyncio 异步并发。
- **SSE 实时进度推送**: Server-Sent Events 长连接。
- **跨平台PDF生成**: fpdf2 + weasyprint 双引擎。

## 2. 技术栈

- **后端**: Python 3.11+, Flask, aiohttp, httpx, asyncio, ThreadPoolExecutor
- **主入口前端**: 原生 HTML, CSS, JavaScript (Neo-Brutalist 设计)
- **静态报告前端**: Astro 4, React (Islands), Tailwind CSS, ECharts, D3.js
- **学术API**: Semantic Scholar, ArXiv, PubMed, SerpAPI (Google Scholar / Google Search / Google AI Mode), ADS ABS
- **PDF处理**: PyMuPDF, fpdf2, weasyprint
- **图表生成**: matplotlib (后端), ECharts + D3.js (前端报告)
- **LLM**: 兼容 OpenAI 接口的任意模型服务（主评估 + 搜索型分析），统一由 `backend/config.py` 配置，支持前端实时修改

## 3. 系统架构

```
用户输入论文标题
    │
    ├─→ 多源被引检索 (Semantic Scholar / ArXiv / PubMed / SerpAPI / ADS ABS)
    │
    ├─→ 全文抓取与引用定位 (fetch_fulltext_with_citation_context)
    │
    ├─→ LLM 逐篇引用质量评估 (citation_type / depth / sentiment / score)
    │
    ├─→ LLM 综合评估总结
    │
    ├─→ 学者画像补全 (搜索型LLM + SerpApi)
    │       ├── 第一作者国家/机构/荣誉
    │       ├── 知名学者判定与分级
    │       ├── 自引检测
    │       └── 著名机构匹配
    │
    ├─→ 高级分析引擎
    │       ├── 引用时间·地域·学者层级五维统计
    │       ├── 被引描述深度分析
    │       ├── 影响力预测分析
    │       └── 数据洞察与画像总结
    │
    ├─→ 后端图表 PNG 生成 (matplotlib)
    │
    ├─→ 报告导出 (Markdown + PDF，含嵌入图表)
    │
    └─→ 交互式静态报告 [v5.0新增]
            ├── report.json 导出
            ├── Astro + React 静态站点构建
            ├── Dashboard / 引用画廊 / 人口地域 / 影响力学者 / 知识图谱
            └── Flask 路由直接提供预渲染页面
```

## 4. 部署步骤

### 4.1. 环境准备

- **Python**: 确保已安装 Python 3.10 或更高版本。推荐使用 conda 环境。
- **操作系统**: Windows / Linux / macOS 均支持。
- **（可选）代理**: 如果网络环境需要代理，可在 `backend/config.py` 的 `PROXY_SETTINGS["fallback_proxy"]` 中设置本地回退代理；如系统已配置 `HTTP_PROXY` / `HTTPS_PROXY`，全文抓取也会优先尝试这些代理。

### 4.2. 安装依赖

1. **创建 conda 环境（推荐）**

    ```bash
    conda create -n ref python=3.12
    conda activate ref
    ```

    或使用 venv：

    ```bash
    python -m venv venv
    # Windows
    .\venv\Scripts\activate
    # macOS / Linux
    source venv/bin/activate
    ```

2. **安装 Python 依赖**

    ```bash
    pip install -r requirements.txt
    ```

    需要的额外依赖（如尚未安装会自动提示）：

    ```bash
    pip install matplotlib httpx
    ```

3. **安装前端依赖（v5.0 交互式报告）**

    ```bash
    cd frontend
    npm install
    cd ..
    ```

    需要 Node.js 18+ 环境。首次构建报告时 Astro 会自动编译。

### 4.3. 配置 API Key、LLM 和运行参数

后端现已统一通过单一配置文件管理 API 设置与运行参数，不再依赖环境变量。请直接编辑：

- `backend/config.py`

该文件集中维护以下配置：

| 配置项 | 所在对象 | 说明 |
|------|--------|------|
| 服务端口 | `APP_SETTINGS["port"]` | Flask 服务启动端口 |
| 并发评估数 | `APP_SETTINGS["concurrency_limit"]` | 逐篇评估阶段的并发数上限 |
| 回退代理地址 | `PROXY_SETTINGS["fallback_proxy"]` | 全文抓取在直连失败时使用的本地回退代理 |
| LLM 模型名 | `LLM_SETTINGS["model"]` | 主评估与搜索型 LLM 共用模型名 |
| LLM API Key | `LLM_SETTINGS["api_key"]` | OpenAI-compatible LLM 的 API Key |
| 主 LLM Base URL | `LLM_SETTINGS["primary_base_url"]` | 主评估与搜索型分析使用的主网关地址 |
| 备用 LLM Base URL | `LLM_SETTINGS["secondary_base_url"]` | 备用网关地址 |
| 搜索超时 | `LLM_SETTINGS["search_timeout"]` | 搜索型 LLM 超时时间（秒） |
| SerpApi Key | `SERPAPI_SETTINGS["api_key"]` | Google Scholar / Google Search / AI Mode |
| SerpApi Base URL | `SERPAPI_SETTINGS["base_url"]` | SerpApi 请求地址 |
| ADS Key | `ADSABS_SETTINGS["api_key"]` | NASA ADS 密钥 |
| ADS Base URL | `ADSABS_SETTINGS["base_url"]` | NASA ADS 请求地址 |
| Semantic Scholar Key | `SEMANTIC_SCHOLAR_SETTINGS["api_key"]` | 可选 |
| Semantic Scholar Base URL | `SEMANTIC_SCHOLAR_SETTINGS["base_url"]` | Semantic Scholar 请求地址 |
| MinerU Token | `MINERU_SETTINGS["api_token"]` | PDF 解析 Token，可选 |
| MinerU Base URL | `MINERU_SETTINGS["base_url"]` | MinerU 请求地址 |
| 图像测试模型 | `IMAGE_TEST_SETTINGS["model"]` | 根目录 `test.py` 使用的图像模型 |

配置完成后，直接启动即可，无需额外导出环境变量：

```bash
conda activate ref
cd backend
python app.py
```

**注意**:
- 当前项目中的 API Key、LLM 模型名、LLM 网关地址、端口、并发数与本地回退代理地址，均统一收敛到 `backend/config.py`。
- 搜索型 LLM 不再单独写死某个搜索模型名，而是复用统一配置文件中的模型设置，并通过 Responses API 的 `web_search` 工具发起联网请求。
- `fulltext_fetcher` 仍会优先尝试系统中的 `HTTP_PROXY` / `HTTPS_PROXY`，若不可用再使用 `PROXY_SETTINGS["fallback_proxy"]`。

## 5. 运行系统

在项目根目录下，运行以下命令启动服务：

```bash
conda activate ref
cd backend
python app.py
```

服务启动后，您会看到：

```
[INFO] Starting CitationQA on port 5000
[INFO] Concurrency limit: 10
 * Running on http://127.0.0.1:5000
```

打开浏览器访问 `http://127.0.0.1:5000` 即可使用。

其中端口与并发数由 `backend/config.py` 中的 `APP_SETTINGS` 控制。

## 6. 使用说明

1. **输入标题**: 在输入框中粘贴论文的**完整且精确**的标题。
2. **开始分析**: 点击"开始分析"按钮。
3. **确认信息**: 系统显示论文基本信息（作者、年份、被引数等）供确认。
4. **选择被引**:
    - 被引数 ≤ 100：自动开始分析。
    - 被引数 > 100：可选择"自动选择前100篇"或"手动勾选"（最多100篇）。
5. **查看进度**: 实时显示 6 个阶段的进度：
    - 并发分析 → 综合评估 → 学者画像 → 高级分析 → 图表生成 → 报告生成
6. **查看结果**: 分析完成后自动展示：
    - **综合评估**: 总体影响力评分、引用类型/深度分布、关键发现。
    - **逐篇分析**: 每篇被引论文的引用类型、评分、引用位置、详细分析。
    - **高级分析**: 引用时间/地域分布图表、学者层级分布、知名学者画像卡片、被引描述深度分析、影响力预测指标与趋势图、数据洞察卡片、被引描述综合总结。
7. **查看详细报告**: 点击"查看详细报告"按钮，系统自动构建 Astro 静态页面并在新标签页打开交互式报告，包含：
    - **Dashboard**: 论文概览、引用星座图、分布图表。
    - **Citation Gallery**: 引用卡片列表，支持筛选与排序。
    - **Demographics & Geography**: 时间趋势、国家/地区分布。
    - **Impact & Scholars**: 影响力雷达图、预测趋势、知名学者画像矩阵。
    - **Knowledge Graph**: D3.js 力导向引用关系图。
8. **下载报告**: 点击按钮下载 Markdown 或 PDF 格式的完整报告（含分析图表）。
9. **分析其他论文**: 随时可点击"分析其他论文"按钮开始新任务，界面自动重置。

## 7. 项目结构

```
backend/
├── app.py                          # Flask 主入口，任务管理、SSE 与静态报告路由
├── config.py                       # 统一 API / LLM 配置文件（支持前端实时修改）
├── templates/index.html            # 主入口页面 (Neo-Brutalist)
├── static/
│   ├── css/style.css               # 主入口样式
│   └── js/app.js                   # 主入口逻辑
├── modules/
│   ├── paper_search.py             # 五源聚合检索
│   ├── fulltext_fetcher.py         # 全文获取与引用定位
│   ├── llm_evaluator.py            # LLM 逐篇/综合评估
│   ├── report_generator.py         # Markdown/PDF 报告生成
│   ├── static_site_builder.py      # Astro 静态站点构建 [v5.0新增]
│   ├── serp_api.py                 # SerpApi (Scholar/Search/AI Mode)
│   ├── search_llm_client.py        # 搜索型 LLM 客户端 [v4.0新增]
│   ├── scholar_enricher.py         # 学者画像补全（并发加速）[v4.0新增, v5.0优化]
│   ├── advanced_analytics.py       # 高级分析引擎 [v4.0新增]
│   ├── chart_generator.py          # 后端图表生成 [v4.0新增]
│   ├── semantic_scholar.py         # Semantic Scholar API
│   ├── arxiv_api.py                # ArXiv API
│   ├── pubmed_api.py               # PubMed API
│   └── adsabs_api.py               # ADS ABS API
├── reports/                        # 生成的报告
├── charts/                         # 生成的图表 PNG [v4.0新增]
├── downloads/                      # 下载的 PDF
└── logs/                           # 运行日志

frontend/                           # 交互式静态报告 [v5.0新增]
├── package.json
├── astro.config.mjs
├── tailwind.config.mjs
├── src/
│   ├── pages/index.astro           # 报告主页面
│   ├── layouts/ReportLayout.astro  # 全局布局
│   ├── components/
│   │   ├── Dashboard.astro         # Dashboard 总览
│   │   ├── CitationGallery.tsx     # 引用画廊 (React)
│   │   ├── DemographicsGeo.astro   # 人口地域分布
│   │   ├── ImpactScholars.astro    # 影响力与学者
│   │   ├── KnowledgeGraph.astro    # 知识图谱
│   │   └── MiniStarGraph.tsx       # 引用星座图 (React + D3.js)
│   ├── lib/types.ts                # TypeScript 类型定义
│   └── data/report.json            # 构建时注入的分析数据
└── dist/                           # Astro 构建产物
```

## 8. 日志与数据

- **运行日志**: `backend/logs/` 目录下，分为应用主日志 (`app_*.log`) 和任务独立日志 (`task_*.log`)。
- **分析图表**: `backend/charts/` 目录下，按 `<task_id>_<chart_type>.png` 命名。
- **下载的PDF**: `backend/downloads/<task_id>/` 目录下。
- **生成的报告**: `backend/reports/` 目录下，Markdown 和 PDF 格式。

## 9. 常见问题

**Q: 学者画像补全阶段较慢？**
A: v5.0 已引入并发查询（默认 5 并发），大幅缩短耗时。前端实时显示当前查询进度与作者姓名。如仍较慢，可通过减少选择的被引论文数量来加速。

**Q: 图表在 PDF 中显示不正常？**
A: 确保系统已安装中文字体（Windows 下 `msyh.ttf` 或 `simhei.ttf`）。图表由 matplotlib 生成，需要支持中文的字体。

**Q: SerpApi 报错 429？**
A: SerpApi 有调用频率限制。系统已内置自动重试逻辑，若频繁触发限制，请稍等片刻或升级 SerpApi 套餐。

**Q: 搜索型 LLM 无法连接？**
A: 检查 `backend/config.py` 中配置的 LLM 网关地址是否可达，或通过前端设置面板（右上角齿轮图标）直接修改配置。若使用代理环境，确认代理配置正确。

**Q: 查看详细报告时构建失败？**
A: 确保已在 `frontend/` 目录下执行过 `npm install` 安装 Astro 依赖。构建需要 Node.js 18+ 环境。

