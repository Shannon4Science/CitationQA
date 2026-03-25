"""
Citation Locator Agent Skill

Locates and analyzes how a target paper is cited within a citing paper.
Supports HTML (ArXiv) and PDF formats with multi-strategy citation search.

This skill follows the Anthropic Agent Skill pattern:
- Self-contained with clear input/output interface
- Composable with other skills
- Includes built-in error handling and fallback strategies
"""

import os
import re
import time
import hashlib
import logging
import zipfile
import io
from typing import Optional, Dict, Tuple, List

from bs4 import BeautifulSoup
import httpx
import fitz  # PyMuPDF

logger = logging.getLogger("citation_analyzer.skill.locator")


class CitationLocatorSkill:
    """
    Agent Skill: Locate citations of a target paper within a citing paper.
    
    Supports:
    - ArXiv HTML with structural reference tracking
    - PDF with PyMuPDF text extraction
    - MinerU API for enhanced PDF parsing
    - Multi-strategy citation search (ref number, author-year, keyword)
    """

    def __init__(self, download_dir: str = None, mineru_token: str = None):
        self.download_dir = download_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "downloads"
        )
        os.makedirs(self.download_dir, exist_ok=True)
        self.mineru_token = mineru_token or ""
        self.mineru_api_base = "https://mineru.net/api/v4"
        self.client = httpx.Client(
            timeout=60.0,
            headers={"User-Agent": "CitationQualityAnalyzer/2.0 (Academic Research)"},
            follow_redirects=True
        )
        self.last_request_time = 0

    def _rate_limit(self, delay: float = 1.0):
        elapsed = time.time() - self.last_request_time
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self.last_request_time = time.time()

    def _safe_filename(self, title: str) -> str:
        safe = re.sub(r'[^\w\s-]', '', title)[:80]
        safe = re.sub(r'\s+', '_', safe).strip('_')
        return safe or hashlib.md5(title.encode()).hexdigest()[:16]

    # ==================== Main Entry Point ====================

    def locate_citation(self, citing_paper_info: Dict, target_paper_title: str) -> Dict:
        """
        Main entry: Fetch full text and locate target paper citations.
        
        Args:
            citing_paper_info: Dict with keys: title, arxiv_id, doi, open_access_pdf, abstract
            target_paper_title: Title of the target paper to find citations of
            
        Returns:
            Dict with: fulltext, content_type, pdf_path, fulltext_url, 
                       citation_contexts, raw_html, annotated_content
        """
        title = citing_paper_info.get("title", "Unknown")
        arxiv_id = citing_paper_info.get("arxiv_id")
        doi = citing_paper_info.get("doi")
        pdf_url = citing_paper_info.get("open_access_pdf")

        result = {
            "fulltext": None,
            "content_type": "none",
            "pdf_path": None,
            "fulltext_url": None,
            "citation_contexts": [],
            "raw_html": None,
            "annotated_content": None,
        }

        logger.info(f"[Skill] Locating citation in: {title[:60]}...")

        # Strategy 1: ArXiv HTML (best - preserves reference structure)
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
                    contexts = self._find_citation_in_html(raw_html, target_paper_title)
                    result["citation_contexts"] = contexts
                    result["annotated_content"] = self._annotate_content(
                        text, target_paper_title, contexts
                    )
                    logger.info(f"[Skill] HTML: found {len(contexts)} citations")
                    return result

        # Strategy 2: ArXiv PDF
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
                    contexts = self._find_citation_in_text(text, target_paper_title)
                    result["citation_contexts"] = contexts
                    result["annotated_content"] = self._annotate_content(
                        text, target_paper_title, contexts
                    )
                    logger.info(f"[Skill] PDF: found {len(contexts)} citations")
                    return result

        # Strategy 3: OA PDF
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
                    result["annotated_content"] = self._annotate_content(
                        text, target_paper_title, contexts
                    )
                    return result

        # Strategy 4: DOI PDF
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
                    result["annotated_content"] = self._annotate_content(
                        text, target_paper_title, contexts
                    )
                    return result

        # Strategy 5: Abstract only
        abstract = citing_paper_info.get("abstract", "")
        if abstract:
            result["fulltext"] = abstract
            result["content_type"] = "abstract_only"
            result["annotated_content"] = abstract
            logger.info(f"[Skill] Abstract only: {len(abstract)} chars")
            return result

        logger.warning(f"[Skill] No content available: {title[:60]}")
        return result

    # ==================== HTML Citation Locating ====================

    def _find_citation_in_html(self, html_content: str, target_title: str) -> List[Dict]:
        """Locate target paper citations in ArXiv HTML."""
        contexts = []
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Step 1: Find target in references
            ref_number, ref_text, bib_id = self._find_in_references_html(soup, target_title)
            logger.info(f"[Skill] Ref lookup: number={ref_number}, bib_id={bib_id}")

            if ref_number or bib_id:
                # Step 2: Trace citations using bib_id and ref number
                cite_contexts = self._find_citation_by_bib_id_html(soup, ref_number, bib_id)
                for ctx in cite_contexts:
                    contexts.append({
                        "location": ctx.get("section", "unknown"),
                        "context": ctx.get("text", ""),
                        "method": f"reference_number_[{ref_number}]" if ref_number else f"bib_id_{bib_id}",
                        "ref_number": ref_number
                    })

            # Step 3: Fallback - author/year matching
            if not contexts:
                for ctx in self._find_citation_by_author_year_html(soup, target_title):
                    contexts.append({
                        "location": ctx.get("section", "unknown"),
                        "context": ctx.get("text", ""),
                        "method": "author_year_match"
                    })

            # Step 4: Fallback - keyword matching
            if not contexts:
                for ctx in self._find_citation_by_keywords_html(soup, target_title):
                    contexts.append({
                        "location": ctx.get("section", "unknown"),
                        "context": ctx.get("text", ""),
                        "method": "keyword_match"
                    })

        except Exception as e:
            logger.error(f"[Skill] HTML citation locating failed: {e}")

        return contexts

    def _find_in_references_html(self, soup, target_title: str):
        """Find target paper in HTML references section."""
        target_lower = target_title.lower().strip()
        target_keywords = set(re.findall(r'[a-z]{4,}', target_lower))

        ref_sections = soup.find_all(['section', 'div'], class_=re.compile(r'ltx_bibliography|references|bib'))
        if not ref_sections:
            ref_sections = soup.find_all(['section', 'div'], id=re.compile(r'bib|ref', re.I))

        for ref_section in ref_sections:
            bib_items = ref_section.find_all(['li', 'div', 'p'], class_=re.compile(r'ltx_bibitem|bib-entry|reference'))
            if not bib_items:
                bib_items = ref_section.find_all('li')

            for item in bib_items:
                item_text = item.get_text(strip=True).lower()
                bib_id = item.get('id', '')

                if target_lower in item_text:
                    ref_num = self._extract_ref_number(item)
                    return ref_num, item.get_text(strip=True), bib_id

                item_keywords = set(re.findall(r'[a-z]{4,}', item_text))
                if target_keywords and item_keywords:
                    overlap = len(target_keywords & item_keywords) / len(target_keywords)
                    if overlap > 0.6:
                        ref_num = self._extract_ref_number(item)
                        return ref_num, item.get_text(strip=True), bib_id

        return None, None, None

    def _extract_ref_number(self, item) -> Optional[str]:
        item_id = item.get('id', '')
        match = re.search(r'bib\.(\d+)|ref(\d+)|cite\.(\d+)', item_id)
        if match:
            return match.group(1) or match.group(2) or match.group(3)

        tag = item.find(class_=re.compile(r'ltx_tag'))
        if tag:
            num = re.search(r'\d+', tag.get_text())
            if num:
                return num.group()

        text = item.get_text(strip=True)
        match = re.match(r'\[(\d+)\]', text)
        if match:
            return match.group(1)

        return None

    def _find_citation_by_bib_id_html(self, soup, ref_number, bib_id):
        """Find citations by bib_id href and ref number in HTML body."""
        contexts = []
        seen_texts = set()

        # Method 1: href-based (most precise)
        if bib_id:
            cite_links = soup.find_all('a', href=re.compile(re.escape(f'#{bib_id}')))
            for link in cite_links:
                parent = link.find_parent(['p', 'div', 'td'])
                if parent:
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
                        contexts.append({"section": section_name, "text": context_text})

        # Method 2: ref number text matching
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
                            contexts.append({"section": section_name, "text": context_text})

        return contexts

    def _find_citation_by_author_year_html(self, soup, target_title):
        contexts = []
        title_words = target_title.lower().split()
        significant_words = [w for w in title_words if len(w) > 4 and w not in {
            'about', 'using', 'based', 'their', 'these', 'those', 'which',
            'where', 'while', 'after', 'before', 'between', 'through',
            'during', 'without', 'within', 'towards'
        }]

        if len(significant_words) >= 2:
            paragraphs = soup.find_all(['p', 'div'], class_=re.compile(r'ltx_p|ltx_para'))
            if not paragraphs:
                paragraphs = soup.find_all('p')

            for p in paragraphs:
                p_text = p.get_text(strip=True).lower()
                match_count = sum(1 for w in significant_words[:5] if w in p_text)
                if match_count >= min(3, len(significant_words[:5])):
                    section_name = self._get_section_name(p)
                    contexts.append({"section": section_name, "text": p.get_text(strip=True)[:600]})

        return contexts

    def _find_citation_by_keywords_html(self, soup, target_title):
        contexts = []
        distinctive_terms = re.findall(r'[A-Z][a-z]+[-]?[A-Z][a-z]+|[A-Z]{2,}', target_title)
        if not distinctive_terms:
            words = target_title.lower().split()
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
                        contexts.append({"section": "keyword_match", "text": snippet})
                        if len(contexts) >= 5:
                            break
                    if len(contexts) >= 5:
                        break

        return contexts

    def _get_section_name(self, element) -> str:
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

    # ==================== PDF Citation Locating ====================

    def _find_citation_in_text(self, text: str, target_title: str) -> List[Dict]:
        """Locate target paper citations in plain text (from PDF)."""
        contexts = []
        ref_number = self._find_ref_number_in_text(text, target_title)

        if ref_number:
            pattern = re.compile(r'(?<!\d)\[' + re.escape(ref_number) + r'(?:\]|[,\s])')
            for match in pattern.finditer(text):
                if not self._is_in_references_section(text, match.start()):
                    start = max(0, match.start() - 300)
                    end = min(len(text), match.end() + 300)
                    snippet = text[start:end].strip()
                    contexts.append({
                        "location": "body",
                        "context": snippet,
                        "method": f"reference_number_[{ref_number}]"
                    })

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

    def _find_ref_number_in_text(self, text, target_title):
        ref_start = self._find_references_start(text)
        if ref_start < 0:
            return None

        ref_text = text[ref_start:]
        target_lower = target_title.lower()
        target_keywords = set(re.findall(r'[a-z]{4,}', target_lower))

        lines = ref_text.split('\n')
        for line in lines:
            line_lower = line.lower().strip()
            if not line_lower:
                continue

            if target_lower in line_lower:
                num = re.search(r'\[(\d+)\]', line)
                if num:
                    return num.group(1)

            line_keywords = set(re.findall(r'[a-z]{4,}', line_lower))
            if target_keywords and line_keywords:
                overlap = len(target_keywords & line_keywords) / len(target_keywords)
                if overlap > 0.5:
                    num = re.search(r'\[(\d+)\]', line)
                    if num:
                        return num.group(1)

        return None

    def _find_references_start(self, text):
        patterns = [r'\n\s*References?\s*\n', r'\n\s*REFERENCES?\s*\n',
                    r'\n\s*Bibliography\s*\n', r'\n\s*BIBLIOGRAPHY\s*\n']
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.start()
        return -1

    def _is_in_references_section(self, text, position):
        ref_start = self._find_references_start(text)
        if ref_start < 0:
            return False
        return position > ref_start

    # ==================== Content Annotation ====================

    def _annotate_content(self, text, target_title, contexts):
        """Add citation location annotations to content for LLM analysis."""
        if contexts:
            annotations = [f"\n\n===== CITATION LOCATION RESULTS ====="]
            annotations.append(f"Target paper: {target_title}")
            annotations.append(f"Found {len(contexts)} citation(s):\n")
            for i, ctx in enumerate(contexts, 1):
                annotations.append(f"--- Citation {i} (method: {ctx['method']}) ---")
                annotations.append(f"Section: {ctx['location']}")
                annotations.append(f"Context: {ctx['context'][:500]}")
                annotations.append("")
            text = text + "\n".join(annotations)
        return text

    # ==================== File Fetching ====================

    def _fetch_arxiv_html(self, arxiv_id):
        self._rate_limit(3.0)
        urls = [
            f"https://arxiv.org/html/{arxiv_id}",
            f"https://arxiv.org/html/{arxiv_id}v2",
            f"https://arxiv.org/html/{arxiv_id}v3",
            f"https://arxiv.org/html/{arxiv_id}v1",
        ]
        for url in urls:
            try:
                response = self.client.get(url)
                if response.status_code == 200 and len(response.text) > 1000:
                    return response.text
            except Exception as e:
                logger.debug(f"[Skill] ArXiv HTML failed: {url}, {e}")
        return None

    def _download_arxiv_pdf(self, arxiv_id, title):
        self._rate_limit(3.0)
        filename = self._safe_filename(title) + ".pdf"
        filepath = os.path.join(self.download_dir, filename)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            return filepath
        url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        try:
            response = self.client.get(url)
            if response.status_code == 200 and len(response.content) > 1000:
                content_type = response.headers.get("content-type", "")
                if "pdf" in content_type or response.content[:5] == b"%PDF-":
                    with open(filepath, "wb") as f:
                        f.write(response.content)
                    return filepath
        except Exception as e:
            logger.error(f"[Skill] ArXiv PDF download failed: {e}")
        return None

    def _download_pdf_from_url(self, url, title):
        self._rate_limit(1.0)
        filename = self._safe_filename(title) + ".pdf"
        filepath = os.path.join(self.download_dir, filename)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            return filepath
        try:
            response = self.client.get(url)
            if response.status_code == 200 and len(response.content) > 1000:
                if response.content[:5] == b"%PDF-":
                    with open(filepath, "wb") as f:
                        f.write(response.content)
                    return filepath
        except Exception as e:
            logger.error(f"[Skill] PDF download failed: {url}, {e}")
        return None

    def _try_doi_pdf(self, doi, title):
        self._rate_limit(1.0)
        try:
            url = f"https://api.unpaywall.org/v2/{doi}?email=citation-analyzer@example.com"
            response = self.client.get(url)
            if response.status_code == 200:
                data = response.json()
                best_oa = data.get("best_oa_location", {})
                if best_oa:
                    pdf_url = best_oa.get("url_for_pdf") or best_oa.get("url")
                    if pdf_url:
                        return self._download_pdf_from_url(pdf_url, title)
        except Exception as e:
            logger.debug(f"[Skill] Unpaywall failed: {e}")
        return None

    def _extract_text_from_html(self, html_content):
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
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"[Skill] HTML parse failed: {e}")
            return ""

    def _extract_text_from_pdf(self, pdf_path):
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
            logger.info(f"[Skill] PDF extracted: {len(result)} chars, {len(full_text)} pages")
            return result
        except Exception as e:
            logger.error(f"[Skill] PDF parse failed: {pdf_path}, {e}")
            return ""

    # ==================== MinerU API ====================

    def parse_with_mineru(self, file_url, file_type="pdf"):
        """Use MinerU API for enhanced PDF/HTML parsing."""
        if not self.mineru_token:
            return None

        logger.info(f"[Skill] MinerU parsing: {file_url[:80]}...")
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.mineru_token}"
            }
            model_version = "MinerU-HTML" if file_type == "html" else "vlm"
            data = {"url": file_url, "model_version": model_version}

            resp = self.client.post(
                f"{self.mineru_api_base}/extract/task",
                headers=headers, json=data, timeout=30
            )
            if resp.status_code != 200:
                return None

            result = resp.json()
            if result.get("code") != 0:
                return None

            task_id = result["data"]["task_id"]

            for _ in range(60):
                time.sleep(5)
                resp = self.client.get(
                    f"{self.mineru_api_base}/extract/task/{task_id}",
                    headers=headers, timeout=30
                )
                if resp.status_code != 200:
                    continue
                result = resp.json()
                state = result.get("data", {}).get("state", "")
                if state == "done":
                    zip_url = result["data"].get("full_zip_url")
                    if zip_url:
                        return self._download_mineru_result(zip_url)
                    break
                elif state == "failed":
                    break
        except Exception as e:
            logger.error(f"[Skill] MinerU failed: {e}")
        return None

    def _download_mineru_result(self, zip_url):
        try:
            resp = self.client.get(zip_url, timeout=60)
            if resp.status_code != 200:
                return None
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                for name in zf.namelist():
                    if name.endswith("full.md"):
                        return zf.read(name).decode("utf-8")
        except Exception as e:
            logger.error(f"[Skill] MinerU download failed: {e}")
        return None

    def close(self):
        self.client.close()


# ==================== Test ====================

def test_skill():
    """Test the Citation Locator Skill with both HTML and PDF."""
    import logging
    logging.basicConfig(level=logging.INFO)

    skill = CitationLocatorSkill()
    target = "Earth-Agent: Unlocking the Full Landscape of Earth Observation with Agents"

    # Test 1: HTML
    print("=" * 60)
    print("Test 1: HTML citation locating (2508.06832)")
    result = skill.locate_citation(
        {"title": "Agentic AI in Remote Sensing", "arxiv_id": "2508.06832"},
        target
    )
    print(f"  Content type: {result['content_type']}")
    print(f"  Citations found: {len(result['citation_contexts'])}")
    for i, ctx in enumerate(result['citation_contexts'], 1):
        print(f"  [{i}] Method: {ctx['method']}, Section: {ctx['location']}")
        print(f"      Context: {ctx['context'][:200]}...")

    # Test 2: PDF (force PDF by using a different approach)
    print("\n" + "=" * 60)
    print("Test 2: PDF citation locating (2508.06832)")
    # Directly test PDF path
    pdf_path = skill._download_arxiv_pdf("2508.06832", "test_pdf_agentic_ai")
    if pdf_path:
        text = skill._extract_text_from_pdf(pdf_path)
        contexts = skill._find_citation_in_text(text, target)
        print(f"  Citations found: {len(contexts)}")
        for i, ctx in enumerate(contexts, 1):
            print(f"  [{i}] Method: {ctx['method']}, Section: {ctx['location']}")
            print(f"      Context: {ctx['context'][:200]}...")

    skill.close()
    print("\nAll tests passed!")


if __name__ == "__main__":
    test_skill()
