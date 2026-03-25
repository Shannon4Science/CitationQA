"""
ArXiv API 模块
提供论文搜索和内容获取功能
"""

import httpx
import time
import re
import logging
import xml.etree.ElementTree as ET
from typing import Optional, Dict, List
from urllib.parse import quote

logger = logging.getLogger("citation_analyzer.arxiv")

ARXIV_API_BASE = "http://export.arxiv.org/api"
ARXIV_HTML_BASE = "https://arxiv.org/html"
ARXIV_ABS_BASE = "https://arxiv.org/abs"
ARXIV_PDF_BASE = "https://arxiv.org/pdf"
RATE_LIMIT_DELAY = 3.0  # arXiv要求3秒间隔

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


class ArxivClient:
    """ArXiv API 客户端"""

    def __init__(self):
        self.client = httpx.Client(
            timeout=30.0,
            headers={"User-Agent": "CitationQualityAnalyzer/1.0"},
            follow_redirects=True
        )
        self.last_request_time = 0

    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self.last_request_time = time.time()

    def _parse_entry(self, entry) -> Dict:
        """解析单个ArXiv API条目"""
        paper = {}
        
        title_el = entry.find(f"{ATOM_NS}title")
        paper["title"] = " ".join(title_el.text.split()) if title_el is not None and title_el.text else ""
        
        abstract_el = entry.find(f"{ATOM_NS}summary")
        paper["abstract"] = " ".join(abstract_el.text.split()) if abstract_el is not None and abstract_el.text else ""
        
        # 提取arXiv ID
        id_el = entry.find(f"{ATOM_NS}id")
        if id_el is not None and id_el.text:
            arxiv_id_match = re.search(r"(\d+\.\d+)", id_el.text)
            paper["arxiv_id"] = arxiv_id_match.group(1) if arxiv_id_match else ""
            paper["url"] = id_el.text
        
        # 作者
        authors = []
        for author_el in entry.findall(f"{ATOM_NS}author"):
            name_el = author_el.find(f"{ATOM_NS}name")
            affil_el = author_el.find(f"{ARXIV_NS}affiliation")
            author_info = {"name": name_el.text if name_el is not None else ""}
            if affil_el is not None and affil_el.text:
                author_info["affiliation"] = affil_el.text
            authors.append(author_info)
        paper["authors"] = authors
        
        # 发布日期
        published_el = entry.find(f"{ATOM_NS}published")
        if published_el is not None and published_el.text:
            paper["published"] = published_el.text[:10]
            paper["year"] = int(published_el.text[:4])
        
        # 分类
        categories = []
        for cat_el in entry.findall(f"{ATOM_NS}category"):
            term = cat_el.get("term", "")
            if term:
                categories.append(term)
        paper["categories"] = categories
        
        # PDF链接
        for link_el in entry.findall(f"{ATOM_NS}link"):
            if link_el.get("title") == "pdf":
                paper["pdf_url"] = link_el.get("href", "")
        
        # DOI
        doi_el = entry.find(f"{ARXIV_NS}doi")
        if doi_el is not None and doi_el.text:
            paper["doi"] = doi_el.text
        
        return paper

    def search_paper(self, title: str) -> Optional[Dict]:
        """通过标题搜索论文"""
        self._rate_limit()
        logger.info(f"[ArXiv] 搜索论文: {title}")
        
        query = f"ti:\"{title}\""
        url = f"{ARXIV_API_BASE}/query?search_query={quote(query)}&start=0&max_results=5"
        
        try:
            response = self.client.get(url)
            response.raise_for_status()
            
            root = ET.fromstring(response.text)
            entries = root.findall(f"{ATOM_NS}entry")
            
            for entry in entries:
                paper = self._parse_entry(entry)
                if paper.get("title", "").lower().strip() == title.lower().strip():
                    logger.info(f"[ArXiv] 找到精确匹配: {paper['title']}")
                    return paper
            
            if entries:
                paper = self._parse_entry(entries[0])
                logger.info(f"[ArXiv] 返回最相关结果: {paper.get('title', 'N/A')}")
                return paper
            
            logger.warning(f"[ArXiv] 未找到论文: {title}")
            return None
        except Exception as e:
            logger.error(f"[ArXiv] 搜索失败: {e}")
            return None

    def get_paper_by_id(self, arxiv_id: str) -> Optional[Dict]:
        """通过arXiv ID获取论文信息"""
        self._rate_limit()
        logger.info(f"[ArXiv] 获取论文: {arxiv_id}")
        
        url = f"{ARXIV_API_BASE}/query?id_list={arxiv_id}"
        
        try:
            response = self.client.get(url)
            response.raise_for_status()
            
            root = ET.fromstring(response.text)
            entries = root.findall(f"{ATOM_NS}entry")
            
            if entries:
                return self._parse_entry(entries[0])
            return None
        except Exception as e:
            logger.error(f"[ArXiv] 获取论文失败: {e}")
            return None

    def get_html_content(self, arxiv_id: str) -> Optional[str]:
        """获取ArXiv论文的HTML全文"""
        self._rate_limit()
        logger.info(f"[ArXiv] 获取HTML内容: {arxiv_id}")
        
        url = f"{ARXIV_HTML_BASE}/{arxiv_id}"
        
        try:
            response = self.client.get(url, follow_redirects=True)
            if response.status_code == 200:
                logger.info(f"[ArXiv] 成功获取HTML内容: {arxiv_id}")
                return response.text
            logger.warning(f"[ArXiv] HTML内容不可用: {arxiv_id}, HTTP {response.status_code}")
            return None
        except Exception as e:
            logger.error(f"[ArXiv] 获取HTML内容失败: {e}")
            return None

    def download_pdf(self, arxiv_id: str, save_path: str) -> bool:
        """下载ArXiv论文PDF"""
        self._rate_limit()
        logger.info(f"[ArXiv] 下载PDF: {arxiv_id}")
        
        url = f"{ARXIV_PDF_BASE}/{arxiv_id}.pdf"
        
        try:
            response = self.client.get(url, follow_redirects=True)
            if response.status_code == 200 and len(response.content) > 1000:
                with open(save_path, "wb") as f:
                    f.write(response.content)
                logger.info(f"[ArXiv] PDF下载成功: {save_path}")
                return True
            logger.warning(f"[ArXiv] PDF下载失败: {arxiv_id}")
            return False
        except Exception as e:
            logger.error(f"[ArXiv] PDF下载异常: {e}")
            return False

    def close(self):
        self.client.close()


def test_arxiv():
    """测试ArXiv模块"""
    client = ArxivClient()
    
    print("=" * 60)
    print("测试1: 搜索论文 - Earth-Agent")
    paper = client.search_paper("Earth-Agent: Unlocking the Full Landscape of Earth Observation with Agents")
    if paper:
        print(f"  标题: {paper.get('title')}")
        print(f"  ArXiv ID: {paper.get('arxiv_id')}")
        print(f"  年份: {paper.get('year')}")
        print(f"  作者: {[a['name'] for a in paper.get('authors', [])[:3]]}")
    else:
        print("  未找到!")
    
    print("\n" + "=" * 60)
    print("测试2: 搜索论文 - Reflexion")
    paper2 = client.search_paper("Reflexion: Language Agents with Verbal Reinforcement Learning")
    if paper2:
        print(f"  标题: {paper2.get('title')}")
        print(f"  ArXiv ID: {paper2.get('arxiv_id')}")
        print(f"  年份: {paper2.get('year')}")
    else:
        print("  未找到!")
    
    # 测试HTML获取
    if paper:
        print("\n测试3: 获取HTML内容")
        html = client.get_html_content(paper["arxiv_id"])
        if html:
            print(f"  HTML内容长度: {len(html)} 字符")
        else:
            print("  HTML不可用")
    
    client.close()
    print("\n测试完成!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_arxiv()
