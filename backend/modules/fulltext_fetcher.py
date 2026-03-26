"""
论文全文获取与解析模块 v4.0
支持从ArXiv HTML、PDF下载、Semantic Scholar OA PDF、站点落地页解析等多种方式获取全文
增强功能：
  - HTML源码引用定位（保留超链接结构）
  - 落地页规则/HTML/LLM辅助 PDF 发现
  - MinerU API PDF解析
  - 引用位置智能搜索
  - PyMuPDF本地PDF解析（MinerU不可用时的备选）
"""

import os
import re
import time
import hashlib
import logging
import zipfile
import io
from typing import Optional, Dict, Tuple, List
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
import httpx
import fitz  # PyMuPDF

from backend.config import MINERU_SETTINGS
from backend.config import PROXY_SETTINGS
from .llm_evaluator import LLMEvaluator

logger = logging.getLogger("citation_analyzer.fulltext")

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def _mineru_token() -> str:
    return MINERU_SETTINGS["api_token"]

def _mineru_base() -> str:
    return MINERU_SETTINGS["base_url"]


def set_mineru_token(token: str):
    MINERU_SETTINGS["api_token"] = token


class FulltextFetcher:
    """论文全文获取器 v4.0"""

    def __init__(self, download_dir: str = None):
        self.download_dir = download_dir or DOWNLOAD_DIR
        os.makedirs(self.download_dir, exist_ok=True)
        self.default_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36 "
                "CitationQualityAnalyzer/4.0"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
            "Cache-Control": "no-cache",
        }
        self.client = httpx.Client(
            timeout=60.0,
            headers=self.default_headers,
            follow_redirects=True
        )
        self.last_request_time = 0
        self._llm_evaluator = None

    def _rate_limit(self, delay: float = 1.0):
        elapsed = time.time() - self.last_request_time
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self.last_request_time = time.time()

    def _safe_filename(self, title: str) -> str:
        """生成安全的文件名"""
        safe = re.sub(r'[^\w\s-]', '', title)[:80]
        safe = re.sub(r'\s+', '_', safe).strip('_')
        return safe or hashlib.md5(title.encode()).hexdigest()[:16]

    def fetch_fulltext(self, paper_info: Dict) -> Tuple[Optional[str], str, Optional[str], Optional[str]]:
        """
        获取论文全文

        Returns:
            (fulltext_content, content_type, pdf_path, fulltext_url)
            content_type: "html", "pdf", "abstract_only", "none"
            pdf_path: PDF文件路径（如果下载了PDF）
            fulltext_url: 全文链接（HTML或PDF的URL）
        """
        title = paper_info.get("title", "Unknown")
        arxiv_id = paper_info.get("arxiv_id")
        doi = paper_info.get("doi")
        pdf_url = paper_info.get("open_access_pdf")
        source_url = paper_info.get("url", "")

        logger.info(f"[Fulltext] 尝试获取全文: {title[:60]}...")

        # 策略1: ArXiv HTML (最佳，结构化内容)
        if arxiv_id:
            html_content = self._fetch_arxiv_html(arxiv_id)
            if html_content:
                text = self._extract_text_from_html(html_content)
                html_url = f"https://arxiv.org/html/{arxiv_id}"
                if text and len(text) > 500:
                    logger.info(f"[Fulltext] 通过ArXiv HTML获取成功: {len(text)} 字符")
                    return text, "html", None, html_url

        # 策略2: ArXiv PDF
        if arxiv_id:
            pdf_path = self._download_arxiv_pdf(arxiv_id, title)
            pdf_link = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            if pdf_path:
                text = self._extract_text_from_pdf(pdf_path)
                if text and len(text) > 500:
                    logger.info(f"[Fulltext] 通过ArXiv PDF获取成功: {len(text)} 字符")
                    return text, "pdf", pdf_path, pdf_link

        # 策略3: Semantic Scholar OA PDF
        if pdf_url:
            pdf_path = self._download_pdf_from_url(pdf_url, title)
            if pdf_path:
                text = self._extract_text_from_pdf(pdf_path)
                if text and len(text) > 500:
                    logger.info(f"[Fulltext] 通过OA PDF获取成功: {len(text)} 字符")
                    return text, "pdf", pdf_path, pdf_url

        # 策略4: 从论文落地页尽量发现可下载PDF
        if source_url and "arxiv.org" not in source_url.lower():
            pdf_path, discovered_pdf_url = self._try_source_page_pdf(paper_info)
            if pdf_path:
                text = self._extract_text_from_pdf(pdf_path)
                if text and len(text) > 500:
                    logger.info(f"[Fulltext] 通过落地页发现PDF并获取成功: {len(text)} 字符")
                    return text, "pdf", pdf_path, discovered_pdf_url

        # 策略5: 通过DOI尝试获取
        if doi:
            pdf_path = self._try_doi_pdf(doi, title)
            if pdf_path:
                text = self._extract_text_from_pdf(pdf_path)
                if text and len(text) > 500:
                    doi_url = f"https://doi.org/{doi}"
                    logger.info(f"[Fulltext] 通过DOI PDF获取成功: {len(text)} 字符")
                    return text, "pdf", pdf_path, doi_url

        # 策略6: 仅摘要
        abstract = paper_info.get("abstract", "")
        if abstract:
            logger.info(f"[Fulltext] 仅获取到摘要: {len(abstract)} 字符")
            return abstract, "abstract_only", None, None

        logger.warning(f"[Fulltext] 无法获取任何内容: {title[:60]}")
        return None, "none", None, None

    def fetch_fulltext_with_citation_context(
        self, paper_info: Dict, target_paper_title: str
    ) -> Dict:
        """
        获取全文并定位目标论文的引用位置

        Returns:
            {
                "fulltext": str,
                "content_type": str,
                "pdf_path": str or None,
                "fulltext_url": str or None,
                "citation_contexts": [{"location": str, "context": str, "method": str}],
                "raw_html": str or None,  # 原始HTML（如果是HTML类型）
                "annotated_content": str,  # 标注了引用位置的内容
            }
        """
        title = paper_info.get("title", "Unknown")
        arxiv_id = paper_info.get("arxiv_id")
        doi = paper_info.get("doi")
        pdf_url = paper_info.get("open_access_pdf")
        source_url = paper_info.get("url", "")

        result = {
            "fulltext": None,
            "content_type": "none",
            "pdf_path": None,
            "fulltext_url": None,
            "citation_contexts": [],
            "raw_html": None,
            "annotated_content": None,
        }

        logger.info(f"[Fulltext] 获取全文并定位引用: {title[:60]}...")

        # 策略1: ArXiv HTML（最佳 - 保留引用结构）
        if arxiv_id:
            raw_html = self._fetch_arxiv_html(arxiv_id)
            if raw_html and len(raw_html) > 1000:
                html_url = f"https://arxiv.org/html/{arxiv_id}"
                text = self._extract_text_from_html(raw_html)
                if text and len(text) > 500:
                    result["fulltext"] = text
                    result["content_type"] = "html"
                    result["fulltext_url"] = html_url
                    result["raw_html"] = raw_html

                    # 在HTML中定位引用
                    contexts = self._find_citation_in_html(raw_html, target_paper_title)
                    result["citation_contexts"] = contexts

                    # 生成标注内容
                    annotated = self._annotate_html_content(raw_html, target_paper_title, contexts)
                    result["annotated_content"] = annotated

                    logger.info(f"[Fulltext] HTML全文获取成功，找到 {len(contexts)} 处引用")
                    return result

        # 策略2: ArXiv PDF
        if arxiv_id:
            pdf_path = self._download_arxiv_pdf(arxiv_id, title)
            pdf_link = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            if pdf_path:
                text = self._extract_text_from_pdf(pdf_path)
                if text and len(text) > 500:
                    result["fulltext"] = text
                    result["content_type"] = "pdf"
                    result["pdf_path"] = pdf_path
                    result["fulltext_url"] = pdf_link

                    # 在PDF文本中定位引用
                    contexts = self._find_citation_in_text(text, target_paper_title)
                    result["citation_contexts"] = contexts
                    result["annotated_content"] = self._annotate_text_content(text, target_paper_title, contexts)

                    logger.info(f"[Fulltext] PDF全文获取成功，找到 {len(contexts)} 处引用")
                    return result

        # 策略3: OA PDF
        if pdf_url:
            pdf_path = self._download_pdf_from_url(pdf_url, title)
            if pdf_path:
                text = self._extract_text_from_pdf(pdf_path)
                if text and len(text) > 500:
                    result["fulltext"] = text
                    result["content_type"] = "pdf"
                    result["pdf_path"] = pdf_path
                    result["fulltext_url"] = pdf_url

                    contexts = self._find_citation_in_text(text, target_paper_title)
                    result["citation_contexts"] = contexts
                    result["annotated_content"] = self._annotate_text_content(text, target_paper_title, contexts)

                    logger.info(f"[Fulltext] OA PDF全文获取成功，找到 {len(contexts)} 处引用")
                    return result

        # 策略4: 从论文落地页尽量发现PDF
        if source_url and "arxiv.org" not in source_url.lower():
            pdf_path, discovered_pdf_url = self._try_source_page_pdf(paper_info)
            if pdf_path:
                text = self._extract_text_from_pdf(pdf_path)
                if text and len(text) > 500:
                    result["fulltext"] = text
                    result["content_type"] = "pdf"
                    result["pdf_path"] = pdf_path
                    result["fulltext_url"] = discovered_pdf_url

                    contexts = self._find_citation_in_text(text, target_paper_title)
                    result["citation_contexts"] = contexts
                    result["annotated_content"] = self._annotate_text_content(text, target_paper_title, contexts)
                    logger.info(f"[Fulltext] 落地页发现PDF成功，找到 {len(contexts)} 处引用")
                    return result

        # 策略5: DOI PDF
        if doi:
            pdf_path = self._try_doi_pdf(doi, title)
            if pdf_path:
                text = self._extract_text_from_pdf(pdf_path)
                if text and len(text) > 500:
                    result["fulltext"] = text
                    result["content_type"] = "pdf"
                    result["pdf_path"] = pdf_path
                    result["fulltext_url"] = f"https://doi.org/{doi}"

                    contexts = self._find_citation_in_text(text, target_paper_title)
                    result["citation_contexts"] = contexts
                    result["annotated_content"] = self._annotate_text_content(text, target_paper_title, contexts)
                    return result

        # 策略6: 仅摘要
        abstract = paper_info.get("abstract", "")
        if abstract:
            result["fulltext"] = abstract
            result["content_type"] = "abstract_only"
            result["annotated_content"] = abstract
            logger.info(f"[Fulltext] 仅获取到摘要: {len(abstract)} 字符")
            return result

        logger.warning(f"[Fulltext] 无法获取任何内容: {title[:60]}")
        return result

    # ==================== HTML引用定位 ====================

    def _find_citation_in_html(self, html_content: str, target_title: str) -> List[Dict]:
        """
        在ArXiv HTML中定位目标论文的引用位置
        步骤:
        1. 在参考文献列表中找到目标论文
        2. 提取其引用编号（如[23]）
        3. 在正文中找到所有使用该编号的位置
        4. 如果没有编号，使用作者+年份模糊匹配
        """
        contexts = []
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Step 1: 在参考文献中查找目标论文
            ref_number, ref_text, bib_id = self._find_in_references_html(soup, target_title)
            logger.info(f"[Fulltext] 参考文献查找结果: ref_number={ref_number}, bib_id={bib_id}")

            if ref_number or bib_id:
                # Step 2: 用bib_id和引用编号在正文中查找
                cite_contexts = self._find_citation_by_bib_id_html(soup, ref_number, bib_id)
                for ctx in cite_contexts:
                    contexts.append({
                        "location": ctx.get("section", "unknown"),
                        "context": ctx.get("text", ""),
                        "method": f"reference_number_[{ref_number}]" if ref_number else f"bib_id_{bib_id}",
                        "ref_number": ref_number
                    })

            # Step 3: 如果没找到编号或没找到引用位置，尝试作者+年份匹配
            if not contexts:
                author_contexts = self._find_citation_by_author_year_html(soup, target_title)
                for ctx in author_contexts:
                    contexts.append({
                        "location": ctx.get("section", "unknown"),
                        "context": ctx.get("text", ""),
                        "method": "author_year_match"
                    })

            # Step 4: 直接标题关键词匹配
            if not contexts:
                keyword_contexts = self._find_citation_by_keywords_html(soup, target_title)
                for ctx in keyword_contexts:
                    contexts.append({
                        "location": ctx.get("section", "unknown"),
                        "context": ctx.get("text", ""),
                        "method": "keyword_match"
                    })

        except Exception as e:
            logger.error(f"[Fulltext] HTML引用定位失败: {e}")

        logger.info(f"[Fulltext] HTML引用定位: 找到 {len(contexts)} 处引用")
        return contexts

    def _find_in_references_html(self, soup: BeautifulSoup, target_title: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """在HTML参考文献列表中查找目标论文，返回(引用编号, 引用文本, bib_id)"""
        target_lower = target_title.lower().strip()
        # 提取关键词用于模糊匹配
        target_keywords = set(re.findall(r'[a-z]{4,}', target_lower))

        # 查找参考文献区域
        ref_sections = soup.find_all(['section', 'div'], class_=re.compile(r'ltx_bibliography|references|bib'))
        if not ref_sections:
            ref_sections = soup.find_all(['section', 'div'], id=re.compile(r'bib|ref', re.I))

        for ref_section in ref_sections:
            # 查找每个参考文献条目
            bib_items = ref_section.find_all(['li', 'div', 'p'], class_=re.compile(r'ltx_bibitem|bib-entry|reference'))
            if not bib_items:
                bib_items = ref_section.find_all('li')

            for item in bib_items:
                item_text = item.get_text(strip=True).lower()
                bib_id = item.get('id', '')

                # 精确标题匹配
                if target_lower in item_text:
                    ref_num = self._extract_ref_number(item)
                    return ref_num, item.get_text(strip=True), bib_id

                # 模糊匹配（关键词重叠度）
                item_keywords = set(re.findall(r'[a-z]{4,}', item_text))
                if target_keywords and item_keywords:
                    overlap = len(target_keywords & item_keywords) / len(target_keywords)
                    if overlap > 0.6:
                        ref_num = self._extract_ref_number(item)
                        return ref_num, item.get_text(strip=True), bib_id

        return None, None, None

    def _extract_ref_number(self, item) -> Optional[str]:
        """从参考文献条目中提取引用编号"""
        # 方法1: 从id属性提取
        item_id = item.get('id', '')
        match = re.search(r'bib\.(\d+)|ref(\d+)|cite\.(\d+)', item_id)
        if match:
            return match.group(1) or match.group(2) or match.group(3)

        # 方法2: 从class中的tag提取
        tag = item.find(class_=re.compile(r'ltx_tag'))
        if tag:
            num = re.search(r'\d+', tag.get_text())
            if num:
                return num.group()

        # 方法3: 从文本开头提取
        text = item.get_text(strip=True)
        match = re.match(r'\[(\d+)\]', text)
        if match:
            return match.group(1)

        return None

    def _find_citation_by_bib_id_html(self, soup: BeautifulSoup, ref_number: Optional[str], bib_id: Optional[str]) -> List[Dict]:
        """通过bib_id和引用编号在HTML正文中查找引用位置"""
        contexts = []
        seen_texts = set()  # 去重

        # 方法1: 通过href中的bib_id查找（最精确）
        if bib_id:
            cite_links = soup.find_all('a', href=re.compile(re.escape(f'#{bib_id}')))
            for link in cite_links:
                parent = link.find_parent(['p', 'div', 'td'])
                if parent:
                    # 排除参考文献区域本身
                    parent_classes = ' '.join(parent.get('class', []))
                    if 'ltx_bibitem' in parent_classes or 'ltx_bibliography' in parent_classes:
                        continue
                    bib_parent = parent.find_parent(class_=re.compile(r'ltx_bibliography'))
                    if bib_parent:
                        continue

                    section_name = self._get_section_name(parent)
                    context_text = parent.get_text(strip=True)
                    if len(context_text) > 800:
                        link_text = link.get_text(strip=True)
                        idx = context_text.find(link_text)
                        if idx >= 0:
                            start = max(0, idx - 300)
                            end = min(len(context_text), idx + 300)
                            context_text = context_text[start:end]

                    text_key = context_text[:100]
                    if text_key not in seen_texts:
                        seen_texts.add(text_key)
                        contexts.append({
                            "section": section_name,
                            "text": context_text
                        })

        # 方法2: 通过引用编号文本查找（补充）
        if ref_number and not contexts:
            cite_links = soup.find_all('a', class_=re.compile(r'ltx_ref'))
            for link in cite_links:
                link_text = link.get_text(strip=True)
                if link_text == ref_number:
                    parent = link.find_parent(['p', 'div', 'td'])
                    if parent:
                        bib_parent = parent.find_parent(class_=re.compile(r'ltx_bibliography'))
                        if bib_parent:
                            continue
                        section_name = self._get_section_name(parent)
                        context_text = parent.get_text(strip=True)
                        if len(context_text) > 800:
                            idx = context_text.find(link_text)
                            if idx >= 0:
                                start = max(0, idx - 300)
                                end = min(len(context_text), idx + 300)
                                context_text = context_text[start:end]

                        text_key = context_text[:100]
                        if text_key not in seen_texts:
                            seen_texts.add(text_key)
                            contexts.append({
                                "section": section_name,
                                "text": context_text
                            })

        return contexts

    def _find_citation_by_author_year_html(self, soup: BeautifulSoup, target_title: str) -> List[Dict]:
        """通过作者+年份在HTML中模糊匹配引用"""
        contexts = []

        # 从标题中提取可能的关键信息
        # 尝试提取年份和关键词
        title_words = target_title.lower().split()
        significant_words = [w for w in title_words if len(w) > 4 and w not in {'about', 'using', 'based', 'their', 'these', 'those', 'which', 'where', 'while', 'after', 'before', 'between', 'through', 'during', 'without', 'within', 'towards'}]

        if len(significant_words) >= 2:
            # 在正文段落中搜索
            paragraphs = soup.find_all(['p', 'div'], class_=re.compile(r'ltx_p|ltx_para'))
            if not paragraphs:
                paragraphs = soup.find_all('p')

            for p in paragraphs:
                p_text = p.get_text(strip=True).lower()
                # 检查是否包含多个关键词
                match_count = sum(1 for w in significant_words[:5] if w in p_text)
                if match_count >= min(3, len(significant_words[:5])):
                    section_name = self._get_section_name(p)
                    contexts.append({
                        "section": section_name,
                        "text": p.get_text(strip=True)[:600]
                    })

        return contexts

    def _find_citation_by_keywords_html(self, soup: BeautifulSoup, target_title: str) -> List[Dict]:
        """通过标题关键词在HTML中查找引用"""
        contexts = []
        # 提取标题中最有特征的词
        title_lower = target_title.lower()
        # 查找特征性的复合词或专有名词
        distinctive_terms = re.findall(r'[A-Z][a-z]+[-]?[A-Z][a-z]+|[A-Z]{2,}', target_title)
        if not distinctive_terms:
            words = title_lower.split()
            distinctive_terms = [w for w in words if len(w) > 5][:3]

        if distinctive_terms:
            body = soup.find('article') or soup.find('main') or soup.find('body')
            if body:
                text = body.get_text()
                for term in distinctive_terms:
                    pattern = re.compile(re.escape(term), re.IGNORECASE)
                    for match in pattern.finditer(text):
                        start = max(0, match.start() - 200)
                        end = min(len(text), match.end() + 200)
                        snippet = text[start:end].strip()
                        contexts.append({
                            "section": "keyword_match",
                            "text": snippet
                        })
                        if len(contexts) >= 5:
                            break
                    if len(contexts) >= 5:
                        break

        return contexts

    def _get_section_name(self, element) -> str:
        """获取元素所在的章节名称"""
        current = element
        for _ in range(10):
            parent = current.find_parent(['section', 'div'])
            if parent:
                heading = parent.find(['h1', 'h2', 'h3', 'h4', 'h5'])
                if heading:
                    return heading.get_text(strip=True)[:100]
                current = parent
            else:
                break
        return "unknown_section"

    def _annotate_html_content(self, html_content: str, target_title: str, contexts: List[Dict]) -> str:
        """生成标注了引用位置的内容，供LLM分析"""
        soup = BeautifulSoup(html_content, "html.parser")

        # 移除脚本和样式
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()

        # 获取主要内容
        main = soup.find("article") or soup.find("main") or soup.find("div", class_="ltx_page_content")
        if not main:
            main = soup

        text = main.get_text(separator="\n", strip=True)

        # 在文本中标注引用位置
        if contexts:
            annotations = []
            annotations.append(f"\n\n===== 引用定位结果 =====")
            annotations.append(f"目标论文: {target_title}")
            annotations.append(f"找到 {len(contexts)} 处引用:\n")
            for i, ctx in enumerate(contexts, 1):
                annotations.append(f"--- 引用位置 {i} (方法: {ctx['method']}) ---")
                annotations.append(f"章节: {ctx['location']}")
                annotations.append(f"上下文: {ctx['context'][:500]}")
                annotations.append("")
            text = text + "\n".join(annotations)

        return text

    # ==================== PDF文本引用定位 ====================

    def _find_citation_in_text(self, text: str, target_title: str) -> List[Dict]:
        """在纯文本中定位目标论文的引用位置"""
        contexts = []
        text_lower = text.lower()
        target_lower = target_title.lower().strip()

        # Step 1: 在参考文献中查找
        ref_number = self._find_ref_number_in_text(text, target_title)

        if ref_number:
            # 用引用编号在正文中查找
            pattern = re.compile(r'(?<!\d)\[' + re.escape(ref_number) + r'(?:\]|[,\s])')
            for match in pattern.finditer(text):
                start = max(0, match.start() - 300)
                end = min(len(text), match.end() + 300)
                snippet = text[start:end].strip()
                # 排除参考文献区域
                if not self._is_in_references_section(text, match.start()):
                    contexts.append({
                        "location": "body",
                        "context": snippet,
                        "method": f"reference_number_[{ref_number}]"
                    })

        # Step 2: 标题关键词匹配
        if not contexts:
            distinctive_terms = re.findall(r'[A-Z][a-z]+[-]?[A-Z][a-z]+|[A-Z]{2,}', target_title)
            if not distinctive_terms:
                words = target_title.split()
                distinctive_terms = [w for w in words if len(w) > 5][:3]

            for term in distinctive_terms:
                pattern = re.compile(re.escape(term), re.IGNORECASE)
                for match in pattern.finditer(text):
                    if not self._is_in_references_section(text, match.start()):
                        start = max(0, match.start() - 200)
                        end = min(len(text), match.end() + 200)
                        snippet = text[start:end].strip()
                        contexts.append({
                            "location": "body",
                            "context": snippet,
                            "method": "keyword_match"
                        })
                        if len(contexts) >= 5:
                            break
                if len(contexts) >= 5:
                    break

        return contexts

    def _find_ref_number_in_text(self, text: str, target_title: str) -> Optional[str]:
        """在文本的参考文献部分查找目标论文的引用编号"""
        # 找到参考文献区域
        ref_start = self._find_references_start(text)
        if ref_start < 0:
            return None

        ref_text = text[ref_start:]
        target_lower = target_title.lower()
        target_keywords = set(re.findall(r'[a-z]{4,}', target_lower))

        # 按行搜索
        lines = ref_text.split('\n')
        for line in lines:
            line_lower = line.lower().strip()
            if not line_lower:
                continue

            # 精确匹配
            if target_lower in line_lower:
                num = re.search(r'\[(\d+)\]|\((\d+)\)|^\s*(\d+)[\.\)]', line)
                if num:
                    return next((group for group in num.groups() if group), None)

            # 模糊匹配
            line_keywords = set(re.findall(r'[a-z]{4,}', line_lower))
            if target_keywords and line_keywords:
                overlap = len(target_keywords & line_keywords) / len(target_keywords)
                if overlap > 0.5:
                    num = re.search(r'\[(\d+)\]|\((\d+)\)|^\s*(\d+)[\.\)]', line)
                    if num:
                        return next((group for group in num.groups() if group), None)

        return None

    def _find_references_start(self, text: str) -> int:
        """找到参考文献部分的起始位置"""
        patterns = [
            r'\n\s*References?\s*\n',
            r'\n\s*REFERENCES?\s*\n',
            r'\n\s*Bibliography\s*\n',
            r'\n\s*BIBLIOGRAPHY\s*\n',
            r'\n\s*Works\s+Cited\s*\n',
            r'\n\s*WORKS\s+CITED\s*\n',
            r'\n\s*Literature\s+Cited\s*\n',
            r'\n\s*REFERENCES\s+AND\s+NOTES\s*\n',
            r'\n\s*参考文献\s*\n',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.start()
        return -1

    def _is_in_references_section(self, text: str, position: int) -> bool:
        """判断给定位置是否在参考文献区域内"""
        ref_start = self._find_references_start(text)
        if ref_start < 0:
            return False
        return position > ref_start

    def _annotate_text_content(self, text: str, target_title: str, contexts: List[Dict]) -> str:
        """为PDF文本添加引用位置标注"""
        if contexts:
            annotations = []
            annotations.append(f"\n\n===== 引用定位结果 =====")
            annotations.append(f"目标论文: {target_title}")
            annotations.append(f"找到 {len(contexts)} 处引用:\n")
            for i, ctx in enumerate(contexts, 1):
                annotations.append(f"--- 引用位置 {i} (方法: {ctx['method']}) ---")
                annotations.append(f"章节: {ctx['location']}")
                annotations.append(f"上下文: {ctx['context'][:500]}")
                annotations.append("")
            text = text + "\n".join(annotations)
        return text

    # ==================== 基础获取方法 ====================

    def _get_proxy_candidates(self) -> List[str]:
        candidates = []
        for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
            value = os.environ.get(key)
            if value and value not in candidates:
                candidates.append(value)

        fallback_proxy = PROXY_SETTINGS.get("fallback_proxy", "").strip()
        if fallback_proxy and fallback_proxy not in candidates:
            candidates.append(fallback_proxy)
        return candidates

    def _http_get(self, url: str, accept: Optional[str] = None) -> httpx.Response:
        headers = {}
        if accept:
            headers["Accept"] = accept

        last_exc = None
        original_response = None
        try:
            response = self.client.get(url, headers=headers)
            original_response = response
            if response.status_code not in {403, 429, 503}:
                return response
            logger.debug(f"[Fulltext] 直接请求状态 {response.status_code}，尝试代理: {url}")
        except Exception as exc:
            last_exc = exc

        for proxy_url in self._get_proxy_candidates():
            try:
                with httpx.Client(
                    timeout=60.0,
                    headers=self.default_headers,
                    follow_redirects=True,
                    proxy=proxy_url
                ) as proxy_client:
                    response = proxy_client.get(url, headers=headers)
                    if response.status_code < 400:
                        logger.debug(f"[Fulltext] 通过代理访问成功: {url}")
                        return response
                    if original_response is None:
                        original_response = response
            except Exception as exc:
                last_exc = exc

        if original_response is not None:
            return original_response
        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"HTTP GET失败: {url}")

    def _fetch_page_html(self, url: str) -> Optional[str]:
        self._rate_limit(1.0)
        try:
            response = self._http_get(url, accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
            content_type = response.headers.get("content-type", "").lower()
            if response.status_code == 200 and ("html" in content_type or "<html" in response.text.lower()):
                return response.text
            logger.debug(f"[Fulltext] 页面HTML获取失败: {url}, status={response.status_code}, ctype={content_type}")
        except Exception as e:
            logger.debug(f"[Fulltext] 页面HTML请求失败: {url}, {e}")
        return None

    def _normalize_candidate_url(self, page_url: str, candidate_url: str) -> Optional[str]:
        if not candidate_url:
            return None
        candidate_url = candidate_url.strip().strip("\"'").replace("&amp;", "&")
        if not candidate_url or candidate_url.lower().startswith(("javascript:", "data:", "mailto:")):
            return None
        normalized = urljoin(page_url, candidate_url)
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"}:
            return None
        return normalized

    def _dedupe_urls(self, urls: List[str]) -> List[str]:
        seen = set()
        result = []
        for url in urls:
            if url and url not in seen:
                seen.add(url)
                result.append(url)
        return result

    def _site_specific_pdf_candidates(self, page_url: str, html_content: Optional[str] = None) -> List[str]:
        parsed = urlparse(page_url)
        domain = parsed.netloc.lower()
        candidates = []

        if "openreview.net" in domain:
            forum_id = parse_qs(parsed.query).get("id", [None])[0]
            if forum_id and "/forum" in parsed.path:
                candidates.append(f"https://openreview.net/pdf?id={forum_id}")

        if "preprints.org" in domain:
            match = re.search(r"/manuscript/([^/?#]+)", parsed.path)
            if match:
                manuscript_id = match.group(1)
                versions = []
                version_match = re.search(r"/v(\d+)(?:/|$)", parsed.path)
                if version_match:
                    versions.append(version_match.group(1))
                if html_content:
                    versions.extend(re.findall(rf"/manuscript/{re.escape(manuscript_id)}/v(\d+)/download", html_content, re.I))
                    versions.extend(re.findall(r"Version\s*(\d+)", html_content, re.I))
                if not versions:
                    versions = ["1"]
                for version in self._dedupe_urls([str(v) for v in versions])[:5]:
                    candidates.append(f"https://www.preprints.org/manuscript/{manuscript_id}/v{version}/download")

        return self._dedupe_urls(candidates)

    def _extract_pdf_urls_from_html(self, page_url: str, html_content: str) -> List[str]:
        if not html_content:
            return []

        candidates = []
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            for tag in soup.find_all(["a", "link", "meta", "iframe", "button"]):
                for attr in ("href", "src", "content", "data-href", "data-url", "data-download"):
                    value = tag.get(attr)
                    if not value:
                        continue
                    value_lower = str(value).lower()
                    if any(token in value_lower for token in ("pdf", "download", "fulltext", "manuscript")):
                        normalized = self._normalize_candidate_url(page_url, str(value))
                        if normalized:
                            candidates.append(normalized)

                onclick = tag.get("onclick")
                if onclick:
                    for match in re.findall(r"""https?://[^\s"'<>]+|/[^\s"'<>]*(?:pdf|download)[^\s"'<>]*""", onclick, re.I):
                        normalized = self._normalize_candidate_url(page_url, match)
                        if normalized:
                            candidates.append(normalized)
        except Exception as e:
            logger.debug(f"[Fulltext] HTML候选链接解析失败: {e}")

        for match in re.findall(r"""https?://[^\s"'<>]+""", html_content, re.I):
            if any(token in match.lower() for token in ("pdf", "download", "manuscript")):
                normalized = self._normalize_candidate_url(page_url, match)
                if normalized:
                    candidates.append(normalized)

        for match in re.findall(r"""/[^\s"'<>]*(?:pdf|download)[^\s"'<>]*""", html_content, re.I):
            normalized = self._normalize_candidate_url(page_url, match)
            if normalized:
                candidates.append(normalized)

        return self._dedupe_urls(candidates)

    def _trim_html_for_llm(self, html_content: str, limit: int = 24000) -> str:
        if len(html_content) <= limit:
            return html_content
        head = html_content[:16000]
        tail = html_content[-8000:]
        return head + "\n\n...[HTML content truncated]...\n\n" + tail

    def _get_llm_evaluator(self) -> Optional[LLMEvaluator]:
        if self._llm_evaluator is None:
            try:
                evaluator = LLMEvaluator()
                if evaluator.active_config:
                    self._llm_evaluator = evaluator
            except Exception as e:
                logger.warning(f"[Fulltext] 初始化LLM辅助解析失败: {e}")
        return self._llm_evaluator

    def _extract_pdf_url_with_llm(self, page_url: str, html_content: str, title: str) -> Optional[str]:
        evaluator = self._get_llm_evaluator()
        if not evaluator or not html_content:
            return None

        prompt = f"""请帮助我从论文页面中提取一个可直接下载PDF的链接。

要求：
1. 原始页面URL：{page_url}
2. 论文标题：{title}
3. 你会看到页面HTML源码片段，请只寻找“可直接下载PDF文件”的URL
4. 优先返回真正的PDF下载地址，而不是摘要页、论坛页、登录页或引用页
5. 如果找到相对路径，请自动补成绝对URL
6. 严格只输出以下格式之一，不要输出任何其他内容：
<pdfurl>https://example.com/file.pdf</pdfurl>
或
<pdfurl>NONE</pdfurl>

页面HTML如下：
```html
{self._trim_html_for_llm(html_content)}
```"""

        response = evaluator.call_text(
            prompt=prompt,
            system_prompt="You extract direct PDF download links from academic paper HTML. Output only the required tag.",
            max_tokens=200,
            temperature=0.0,
            timeout=90
        )
        if not response:
            return None

        match = re.search(r"<pdfurl>\s*(.*?)\s*</pdfurl>", response, re.I | re.S)
        if not match:
            return None

        candidate = match.group(1).strip()
        if not candidate or candidate.upper() == "NONE":
            return None
        return self._normalize_candidate_url(page_url, candidate)

    def _try_source_page_pdf(self, paper_info: Dict) -> Tuple[Optional[str], Optional[str]]:
        page_url = paper_info.get("url", "")
        title = paper_info.get("title", "Unknown")
        if not page_url:
            return None, None

        logger.info(f"[Fulltext] 尝试从落地页发现PDF: {page_url}")
        html_content = self._fetch_page_html(page_url)

        candidates = []
        if page_url.lower().endswith(".pdf") or "/download" in page_url.lower():
            candidates.append(page_url)
        candidates.extend(self._site_specific_pdf_candidates(page_url, html_content))
        if html_content:
            candidates.extend(self._extract_pdf_urls_from_html(page_url, html_content))
        candidates = self._dedupe_urls(candidates)

        for candidate_url in candidates:
            pdf_path = self._download_pdf_from_url(candidate_url, title)
            if pdf_path:
                logger.info(f"[Fulltext] 通过规则/HTML发现PDF: {candidate_url}")
                return pdf_path, candidate_url

        if html_content:
            llm_pdf_url = self._extract_pdf_url_with_llm(page_url, html_content, title)
            if llm_pdf_url:
                pdf_path = self._download_pdf_from_url(llm_pdf_url, title)
                if pdf_path:
                    logger.info(f"[Fulltext] 通过LLM发现PDF: {llm_pdf_url}")
                    return pdf_path, llm_pdf_url

        return None, None

    def _fetch_arxiv_html(self, arxiv_id: str) -> Optional[str]:
        """获取ArXiv HTML版本（优先获取最新版本）"""
        self._rate_limit(3.0)

        # 优先无版本号（自动获取最新）和高版本号
        urls = [
            f"https://arxiv.org/html/{arxiv_id}",
            f"https://arxiv.org/html/{arxiv_id}v2",
            f"https://arxiv.org/html/{arxiv_id}v3",
            f"https://arxiv.org/html/{arxiv_id}v1",
        ]

        for url in urls:
            try:
                response = self._http_get(url)
                if response.status_code == 200 and len(response.text) > 1000:
                    return response.text
            except Exception as e:
                logger.debug(f"[Fulltext] ArXiv HTML请求失败: {url}, {e}")

        return None

    def _download_arxiv_pdf(self, arxiv_id: str, title: str) -> Optional[str]:
        """下载ArXiv PDF"""
        self._rate_limit(3.0)

        filename = self._safe_filename(title) + ".pdf"
        filepath = os.path.join(self.download_dir, filename)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            logger.info(f"[Fulltext] PDF已存在: {filepath}")
            return filepath

        url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        try:
            response = self._http_get(url, accept="application/pdf,*/*")
            if response.status_code == 200 and len(response.content) > 1000:
                content_type = response.headers.get("content-type", "")
                if "pdf" in content_type or response.content[:5] == b"%PDF-":
                    with open(filepath, "wb") as f:
                        f.write(response.content)
                    logger.info(f"[Fulltext] PDF下载成功: {filepath}")
                    return filepath
        except Exception as e:
            logger.error(f"[Fulltext] ArXiv PDF下载失败: {e}")

        return None

    def _download_pdf_from_url(self, url: str, title: str) -> Optional[str]:
        """从URL下载PDF"""
        self._rate_limit(1.0)

        filename = self._safe_filename(title) + ".pdf"
        filepath = os.path.join(self.download_dir, filename)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            return filepath

        try:
            response = self._http_get(url, accept="application/pdf,*/*")
            if response.status_code == 200 and len(response.content) > 1000:
                content_type = response.headers.get("content-type", "").lower()
                if response.content[:5] == b"%PDF-" or "application/pdf" in content_type:
                    with open(filepath, "wb") as f:
                        f.write(response.content)
                    logger.info(f"[Fulltext] PDF下载成功: {filepath}")
                    return filepath
            logger.debug(
                f"[Fulltext] PDF响应无效: {url}, status={response.status_code}, "
                f"ctype={response.headers.get('content-type', '')}, size={len(response.content)}"
            )
        except Exception as e:
            logger.error(f"[Fulltext] PDF下载失败: {url}, {e}")

        return None

    def _try_doi_pdf(self, doi: str, title: str) -> Optional[str]:
        """尝试通过DOI获取PDF"""
        self._rate_limit(1.0)

        try:
            url = f"https://api.unpaywall.org/v2/{doi}?email=citation-analyzer@example.com"
            response = self._http_get(url, accept="application/json,*/*")
            if response.status_code == 200:
                data = response.json()
                best_oa = data.get("best_oa_location", {})
                if best_oa:
                    pdf_url = best_oa.get("url_for_pdf") or best_oa.get("url")
                    if pdf_url:
                        return self._download_pdf_from_url(pdf_url, title)
        except Exception as e:
            logger.debug(f"[Fulltext] Unpaywall查询失败: {e}")

        return None

    def _extract_text_from_html(self, html_content: str) -> str:
        """从HTML提取论文文本"""
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            for tag in soup.find_all(["script", "style", "nav", "header", "footer"]):
                tag.decompose()

            main_content = soup.find("article") or soup.find("main") or soup.find("div", class_="ltx_page_content")

            if main_content:
                text = main_content.get_text(separator="\n", strip=True)
            else:
                text = soup.get_text(separator="\n", strip=True)

            lines = [line.strip() for line in text.split("\n") if line.strip()]
            text = "\n".join(lines)

            return text
        except Exception as e:
            logger.error(f"[Fulltext] HTML解析失败: {e}")
            return ""

    def _extract_text_from_pdf(self, pdf_path: str) -> str:
        """使用PyMuPDF从PDF提取文本"""
        try:
            doc = fitz.open(pdf_path)
            full_text = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                if text:
                    full_text.append(f"[Page {page_num + 1}]\n{text}")

            doc.close()

            result = "\n\n".join(full_text)
            logger.info(f"[Fulltext] PDF提取完成: {len(result)} 字符, {len(full_text)} 页")
            return result
        except Exception as e:
            logger.error(f"[Fulltext] PDF解析失败: {pdf_path}, {e}")
            return ""

    # ==================== MinerU API ====================

    def parse_with_mineru(self, file_url: str, file_type: str = "pdf") -> Optional[str]:
        """
        使用MinerU API解析文档
        
        Args:
            file_url: 文件URL
            file_type: 文件类型 (pdf/html)
        
        Returns:
            解析后的markdown文本
        """
        if not _mineru_token():
            logger.warning("[Fulltext] MinerU API token未设置，跳过MinerU解析")
            return None

        logger.info(f"[Fulltext] 使用MinerU解析: {file_url[:80]}...")

        try:
            # 创建解析任务
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_mineru_token()}"
            }

            model_version = "MinerU-HTML" if file_type == "html" else "vlm"
            data = {
                "url": file_url,
                "model_version": model_version
            }

            resp = self.client.post(
                f"{_mineru_base()}/extract/task",
                headers=headers,
                json=data,
                timeout=30
            )

            if resp.status_code != 200:
                logger.warning(f"[Fulltext] MinerU创建任务失败: {resp.status_code} - {resp.text[:200]}")
                return None

            result = resp.json()
            if result.get("code") != 0:
                logger.warning(f"[Fulltext] MinerU创建任务失败: {result.get('msg')}")
                return None

            task_id = result["data"]["task_id"]
            logger.info(f"[Fulltext] MinerU任务已创建: {task_id}")

            # 轮询等待结果
            for attempt in range(60):  # 最多等5分钟
                time.sleep(5)
                resp = self.client.get(
                    f"{_mineru_base()}/extract/task/{task_id}",
                    headers=headers,
                    timeout=30
                )

                if resp.status_code != 200:
                    continue

                result = resp.json()
                state = result.get("data", {}).get("state", "")

                if state == "done":
                    zip_url = result["data"].get("full_zip_url")
                    if zip_url:
                        return self._download_and_extract_mineru_result(zip_url)
                    break
                elif state == "failed":
                    err = result["data"].get("err_msg", "unknown")
                    logger.warning(f"[Fulltext] MinerU解析失败: {err}")
                    break
                elif state in ("pending", "running", "converting"):
                    progress = result.get("data", {}).get("extract_progress", {})
                    logger.debug(f"[Fulltext] MinerU进度: {state} - {progress}")
                    continue

        except Exception as e:
            logger.error(f"[Fulltext] MinerU API调用失败: {e}")

        return None

    def _download_and_extract_mineru_result(self, zip_url: str) -> Optional[str]:
        """下载并解压MinerU结果"""
        try:
            resp = self.client.get(zip_url, timeout=60)
            if resp.status_code != 200:
                return None

            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                # 查找full.md文件
                for name in zf.namelist():
                    if name.endswith("full.md"):
                        content = zf.read(name).decode("utf-8")
                        logger.info(f"[Fulltext] MinerU解析结果: {len(content)} 字符")
                        return content

        except Exception as e:
            logger.error(f"[Fulltext] MinerU结果下载失败: {e}")

        return None

    def close(self):
        self.client.close()


def test_fulltext():
    """测试全文获取和引用定位"""
    logging.basicConfig(level=logging.INFO)
    fetcher = FulltextFetcher()

    target_title = "Earth-Agent: Unlocking the Full Landscape of Earth Observation with Agents"

    # 测试1: HTML引用定位
    print("=" * 60)
    print("测试1: 从ArXiv HTML中定位引用")
    print("URL: https://arxiv.org/html/2508.06832v2")

    html_content = fetcher._fetch_arxiv_html("2508.06832")
    if html_content:
        print(f"  HTML获取成功: {len(html_content)} 字符")
        contexts = fetcher._find_citation_in_html(html_content, target_title)
        print(f"  找到 {len(contexts)} 处引用:")
        for i, ctx in enumerate(contexts, 1):
            print(f"  [{i}] 方法: {ctx['method']}")
            print(f"      章节: {ctx['location']}")
            print(f"      上下文: {ctx['context'][:200]}...")
    else:
        print("  HTML获取失败")

    # 测试2: PDF引用定位
    print("\n" + "=" * 60)
    print("测试2: 从ArXiv PDF中定位引用")
    print("URL: https://arxiv.org/pdf/2508.06832")

    pdf_path = fetcher._download_arxiv_pdf("2508.06832", "test_agentic_ai_remote_sensing")
    if pdf_path:
        text = fetcher._extract_text_from_pdf(pdf_path)
        print(f"  PDF文本提取成功: {len(text)} 字符")
        contexts = fetcher._find_citation_in_text(text, target_title)
        print(f"  找到 {len(contexts)} 处引用:")
        for i, ctx in enumerate(contexts, 1):
            print(f"  [{i}] 方法: {ctx['method']}")
            print(f"      章节: {ctx['location']}")
            print(f"      上下文: {ctx['context'][:200]}...")
    else:
        print("  PDF下载失败")

    fetcher.close()
    print("\n测试完成!")


if __name__ == "__main__":
    test_fulltext()
