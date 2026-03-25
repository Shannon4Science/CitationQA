"""
统一学术检索模块 v4.0
聚合 Semantic Scholar、ArXiv、PubMed、SerpAPI、ADS ABS 五个源的搜索结果
被引列表从 Semantic Scholar、ArXiv(通过SS)、PubMed、SerpAPI、ADS ABS 获取并取并集去重
新增单篇被引论文独立影响力评分
"""

import logging
import re
from typing import Optional, Dict, List
from urllib.parse import urlparse
from .semantic_scholar import SemanticScholarClient
from .arxiv_api import ArxivClient
from .pubmed_api import PubMedClient
from . import serp_api
from . import adsabs_api

logger = logging.getLogger("citation_analyzer.paper_search")


class UnifiedPaperSearch:
    """统一论文检索客户端 - 5源聚合"""

    def __init__(self, serp_api_key: str = "", ads_api_key: str = ""):
        self.ss_client = SemanticScholarClient()
        self.arxiv_client = ArxivClient()
        self.pubmed_client = PubMedClient()
        self.last_citation_stats: Dict = {}
        
        # 设置新增API的key
        if serp_api_key:
            serp_api.set_api_key(serp_api_key)
        if ads_api_key:
            adsabs_api.set_api_key(ads_api_key)

    def search_paper(self, title: str) -> Optional[Dict]:
        """
        搜索论文，从5个源获取信息并合并
        优先使用Semantic Scholar作为主信息源
        """
        logger.info(f"[UnifiedSearch] 搜索论文: {title}")
        
        # 1. Semantic Scholar搜索
        ss_paper = None
        try:
            ss_paper = self.ss_client.search_paper_by_title(title)
            if ss_paper:
                logger.info(f"[UnifiedSearch] Semantic Scholar找到: {ss_paper.get('title', '')[:50]}")
        except Exception as e:
            logger.warning(f"[UnifiedSearch] Semantic Scholar搜索失败: {e}")
        
        # 2. ArXiv搜索
        arxiv_paper = None
        try:
            arxiv_paper = self.arxiv_client.search_paper(title)
            if arxiv_paper:
                logger.info(f"[UnifiedSearch] ArXiv找到: {arxiv_paper.get('title', '')[:50]}")
        except Exception as e:
            logger.warning(f"[UnifiedSearch] ArXiv搜索失败: {e}")
        
        # 3. PubMed搜索
        pubmed_paper = None
        try:
            pubmed_papers = self.pubmed_client.search_paper(title)
            pubmed_paper = pubmed_papers[0] if pubmed_papers else None
            if pubmed_paper:
                logger.info(f"[UnifiedSearch] PubMed找到: {pubmed_paper.get('title', '')[:50]}")
        except Exception as e:
            logger.warning(f"[UnifiedSearch] PubMed搜索失败: {e}")
        
        # 4. SerpAPI搜索
        serp_paper = None
        try:
            serp_paper = serp_api.search_paper(title)
            if serp_paper:
                logger.info(f"[UnifiedSearch] SerpAPI找到: {serp_paper.get('title', '')[:50]}, 被引: {serp_paper.get('citation_count', 0)}")
        except Exception as e:
            logger.warning(f"[UnifiedSearch] SerpAPI搜索失败: {e}")
        
        # 5. ADS ABS搜索
        ads_paper = None
        try:
            ads_paper = adsabs_api.search_paper(title)
            if ads_paper:
                logger.info(f"[UnifiedSearch] ADS ABS找到: {ads_paper.get('title', '')[:50]}, 被引: {ads_paper.get('citation_count', 0)}")
        except Exception as e:
            logger.warning(f"[UnifiedSearch] ADS ABS搜索失败: {e}")
        
        if not ss_paper and not arxiv_paper and not serp_paper and not ads_paper:
            logger.warning(f"[UnifiedSearch] 所有源均未找到论文: {title}")
            return None
        
        # 合并信息
        merged = self._merge_paper_info(ss_paper, arxiv_paper, pubmed_paper, serp_paper, ads_paper)
        logger.info(f"[UnifiedSearch] 合并后论文信息: {merged.get('title', 'N/A')}, 被引: {merged.get('citation_count', 0)}")
        return merged

    def get_citations(self, paper_info: Dict, limit: int = 1000) -> List[Dict]:
        """
        获取被引论文列表，从5个源获取并取并集去重
        """
        logger.info(f"[UnifiedSearch] 获取被引论文，限制: {limit}")
        
        all_citations = {}  # 用标准化title作为key去重
        source_counts = {
            "semantic_scholar": 0,
            "pubmed": 0,
            "serpapi": 0,
            "adsabs": 0,
        }
        
        # 1. Semantic Scholar被引
        ss_paper_id = paper_info.get("ss_paper_id")
        if ss_paper_id:
            try:
                ss_citations = self.ss_client.get_citations(ss_paper_id, limit=limit)
                source_counts["semantic_scholar"] = len(ss_citations)
                logger.info(f"[UnifiedSearch] Semantic Scholar返回 {len(ss_citations)} 篇被引")
                for c in ss_citations:
                    key = self._normalize_title(c.get("title", ""))
                    if key and key not in all_citations:
                        all_citations[key] = self._normalize_citation(c, source="semantic_scholar")
                    elif key and key in all_citations:
                        self._merge_citation_info(all_citations[key], c, "semantic_scholar")
            except Exception as e:
                logger.warning(f"[UnifiedSearch] Semantic Scholar被引获取失败: {e}")
        
        # 2. PubMed被引
        pmid = paper_info.get("pmid")
        if pmid:
            try:
                citing_pmids = self.pubmed_client.get_citing_papers(pmid)
                if citing_pmids:
                    pubmed_papers = self.pubmed_client.get_papers_by_ids(citing_pmids[:200])
                    source_counts["pubmed"] = len(pubmed_papers)
                    logger.info(f"[UnifiedSearch] PubMed返回 {len(pubmed_papers)} 篇被引")
                    for p in pubmed_papers:
                        key = self._normalize_title(p.get("title", ""))
                        if key and key not in all_citations:
                            all_citations[key] = self._normalize_pubmed_citation(p)
                        elif key and key in all_citations:
                            self._merge_citation_info(all_citations[key], self._normalize_pubmed_citation(p), "pubmed")
            except Exception as e:
                logger.warning(f"[UnifiedSearch] PubMed被引获取失败: {e}")
        
        # 3. SerpAPI被引 (Google Scholar)
        serp_cites_id = paper_info.get("serp_cites_id")
        if serp_cites_id:
            try:
                serp_max = min(limit, 100)  # SerpAPI限制每次最多获取100条
                serp_citations = serp_api.get_citations(serp_cites_id, max_results=serp_max)
                source_counts["serpapi"] = len(serp_citations)
                logger.info(f"[UnifiedSearch] SerpAPI返回 {len(serp_citations)} 篇被引")
                for c in serp_citations:
                    key = self._normalize_title(c.get("title", ""))
                    if key and key not in all_citations:
                        all_citations[key] = self._normalize_serp_citation(c)
                    elif key and key in all_citations:
                        self._merge_citation_info(all_citations[key], self._normalize_serp_citation(c), "serpapi")
            except Exception as e:
                logger.warning(f"[UnifiedSearch] SerpAPI被引获取失败: {e}")
        
        # 4. ADS ABS被引
        ads_bibcode = paper_info.get("ads_bibcode")
        if ads_bibcode:
            try:
                ads_max = min(limit, 200)
                ads_citations = adsabs_api.get_citations(ads_bibcode, max_results=ads_max)
                source_counts["adsabs"] = len(ads_citations)
                logger.info(f"[UnifiedSearch] ADS ABS返回 {len(ads_citations)} 篇被引")
                for c in ads_citations:
                    key = self._normalize_title(c.get("title", ""))
                    if key and key not in all_citations:
                        all_citations[key] = self._normalize_ads_citation(c)
                    elif key and key in all_citations:
                        self._merge_citation_info(all_citations[key], self._normalize_ads_citation(c), "adsabs")
            except Exception as e:
                logger.warning(f"[UnifiedSearch] ADS ABS被引获取失败: {e}")
        
        result = [self._finalize_citation_metrics(citation) for citation in all_citations.values()]
        self.last_citation_stats = {
            "source_counts": source_counts,
            "dedup_count": len(result),
        }
        logger.info(f"[UnifiedSearch] 5源去重后共 {len(result)} 篇被引论文")
        return result

    def _normalize_title(self, title: str) -> str:
        """标准化标题用于去重"""
        if not title:
            return ""
        title = title.lower().strip()
        title = re.sub(r'[^\w\s]', '', title)
        title = re.sub(r'\s+', ' ', title)
        return title

    @staticmethod
    def _normalize_author_key(name: str) -> str:
        name = re.sub(r'\s*[\(（][^\)）]*[\)）]', '', name or "").strip()
        zh = re.sub(r'[^\u4e00-\u9fff]', '', name)
        if len(zh) >= 2:
            return zh
        ascii_key = re.sub(r'[^a-zA-Z]', '', name).lower()
        if len(ascii_key) >= 4:
            return ascii_key
        return re.sub(r'\s+', ' ', name).lower()

    def _merge_author_lists(self, existing: List[Dict], incoming: List[Dict]) -> List[Dict]:
        merged: List[Dict] = []
        seen: Dict[str, int] = {}

        def _push(author: Dict):
            if not isinstance(author, dict):
                return
            name = (author.get("name") or "").strip()
            if not name:
                return
            clean = {
                "name": name,
                "author_id": author.get("author_id") or author.get("authorId", "") or "",
                "institution": author.get("institution", "") or "",
                "name_en": author.get("name_en", "") or "",
                "name_zh": author.get("name_zh", "") or "",
            }
            key = self._normalize_author_key(name)
            if not key:
                key = name.lower()
            if key in seen:
                target = merged[seen[key]]
                for field in ("author_id", "institution", "name_en", "name_zh"):
                    if not target.get(field) and clean.get(field):
                        target[field] = clean[field]
                return
            seen[key] = len(merged)
            merged.append(clean)

        for author in existing or []:
            _push(author)
        for author in incoming or []:
            if isinstance(author, str):
                _push({"name": author})
            else:
                _push(author)
        return merged

    def _infer_publication_source(self, url: str, venue: str = "") -> Dict:
        domain = urlparse(url).netloc.lower() if url else ""
        if domain.startswith("www."):
            domain = domain[4:]

        source_label = venue or domain or "unknown"
        source_type = "未识别来源"
        source_score = 1

        domain_rules = [
            (
                {
                    "openaccess.thecvf.com", "thecvf.com", "cvf.thecvf.com", "neurips.cc",
                    "iclr.cc", "aclanthology.org", "aaai.org", "dl.acm.org", "acm.org",
                    "ieeexplore.ieee.org", "usenix.org"
                },
                "顶会/学会平台",
                4
            ),
            (
                {"nature.com", "science.org", "cell.com", "thelancet.com", "nejm.org"},
                "旗舰期刊平台",
                4
            ),
            (
                {
                    "link.springer.com", "springer.com", "sciencedirect.com", "elsevier.com",
                    "wiley.com", "oup.com", "cambridge.org", "tandfonline.com",
                    "mdpi.com", "frontiersin.org"
                },
                "学术出版社/期刊平台",
                3
            ),
            (
                {"arxiv.org", "openreview.net", "preprints.org", "biorxiv.org", "medrxiv.org"},
                "预印本/开放评审平台",
                2
            ),
        ]

        for domains, label, score in domain_rules:
            if domain in domains:
                source_type = label
                source_score = score
                source_label = domain
                break

        venue_lower = (venue or "").lower()
        if source_type == "未识别来源" and venue_lower:
            if any(token in venue_lower for token in ("neurips", "iclr", "cvpr", "iccv", "acl", "emnlp", "aaai", "acm", "ieee")):
                source_type = "顶会/学会平台"
                source_score = 4
                source_label = venue
            elif any(token in venue_lower for token in ("nature", "science", "cell", "lancet", "nejm")):
                source_type = "旗舰期刊平台"
                source_score = 4
                source_label = venue
            elif "arxiv" in venue_lower or "preprint" in venue_lower:
                source_type = "预印本/开放评审平台"
                source_score = 2
                source_label = venue

        return {
            "publication_source": source_label,
            "publication_source_type": source_type,
            "publication_source_score": source_score,
            "publication_domain": domain,
        }

    def _citation_count_bonus(self, citation_count: int) -> int:
        if citation_count >= 5000:
            return 6
        if citation_count >= 1000:
            return 5
        if citation_count >= 300:
            return 4
        if citation_count >= 100:
            return 3
        if citation_count >= 30:
            return 2
        if citation_count >= 10:
            return 1
        return 0

    def _influence_level(self, score: int) -> str:
        if score >= 9:
            return "极高"
        if score >= 7:
            return "高"
        if score >= 5:
            return "中"
        if score >= 3:
            return "较低"
        return "低"

    def _finalize_citation_metrics(self, citation: Dict) -> Dict:
        metrics = self._infer_publication_source(
            url=citation.get("scholar_link") or citation.get("url", ""),
            venue=citation.get("venue", "")
        )

        scholar_citation_count = (
            citation.get("scholar_citation_count")
            or citation.get("citation_count")
            or 0
        )
        influence_score = max(
            1,
            min(10, metrics["publication_source_score"] + self._citation_count_bonus(int(scholar_citation_count)))
        )

        citation.update(metrics)
        citation["scholar_citation_count"] = int(scholar_citation_count)
        citation["paper_influence_score"] = influence_score
        citation["paper_influence_level"] = self._influence_level(influence_score)
        citation["paper_influence_reason"] = (
            f"Google Scholar被引 {citation['scholar_citation_count']} 次，"
            f"发表来源判断为 {citation['publication_source']}（{citation['publication_source_type']}）"
        )
        return citation

    def _merge_paper_info(self, ss_paper, arxiv_paper, pubmed_paper, serp_paper, ads_paper) -> Dict:
        """合并多源论文信息"""
        merged = {
            "title": "",
            "abstract": "",
            "year": None,
            "authors": [],
            "venue": "",
            "citation_count": 0,
            "ss_paper_id": None,
            "arxiv_id": None,
            "doi": None,
            "pmid": None,
            "url": "",
            "open_access_pdf": None,
            "external_ids": {},
            "influential_citation_count": 0,
            "serp_cites_id": None,
            "ads_bibcode": None,
        }
        
        if ss_paper:
            merged["title"] = ss_paper.get("title", "")
            merged["abstract"] = ss_paper.get("abstract", "") or ""
            merged["year"] = ss_paper.get("year")
            merged["citation_count"] = ss_paper.get("citationCount", 0) or 0
            merged["ss_paper_id"] = ss_paper.get("paperId")
            merged["url"] = ss_paper.get("url", "")
            merged["venue"] = ss_paper.get("venue", "")
            merged["influential_citation_count"] = ss_paper.get("influentialCitationCount", 0) or 0
            
            merged["authors"] = self._merge_author_lists(
                merged["authors"],
                [
                    {
                        "name": a.get("name", ""),
                        "author_id": a.get("authorId", "")
                    }
                    for a in ss_paper.get("authors", [])
                ]
            )
            
            ext_ids = ss_paper.get("externalIds", {}) or {}
            merged["external_ids"] = ext_ids
            merged["arxiv_id"] = ext_ids.get("ArXiv")
            merged["doi"] = ext_ids.get("DOI")
            
            oap = ss_paper.get("openAccessPdf")
            if oap and isinstance(oap, dict):
                merged["open_access_pdf"] = oap.get("url")
        
        if arxiv_paper:
            if not merged["title"]:
                merged["title"] = arxiv_paper.get("title", "")
            if not merged["abstract"]:
                merged["abstract"] = arxiv_paper.get("abstract", "")
            if not merged["year"]:
                merged["year"] = arxiv_paper.get("year")
            if not merged["arxiv_id"]:
                merged["arxiv_id"] = arxiv_paper.get("arxiv_id")
            merged["authors"] = self._merge_author_lists(
                merged["authors"],
                [{"name": a.get("name", "")} for a in arxiv_paper.get("authors", [])]
            )
            if not merged["doi"]:
                merged["doi"] = arxiv_paper.get("doi")
        
        if pubmed_paper:
            if not merged["pmid"]:
                merged["pmid"] = pubmed_paper.get("pmid")
            if not merged["abstract"]:
                merged["abstract"] = pubmed_paper.get("abstract", "")
            merged["authors"] = self._merge_author_lists(
                merged["authors"],
                pubmed_paper.get("authors", [])
            )
        
        if serp_paper:
            merged["serp_cites_id"] = serp_paper.get("cites_id")
            # 使用SerpAPI的被引数作为参考（Google Scholar通常更全）
            serp_count = serp_paper.get("citation_count", 0) or 0
            if serp_count > merged["citation_count"]:
                merged["citation_count"] = serp_count
            if not merged["title"]:
                merged["title"] = serp_paper.get("title", "")
            if not merged["url"]:
                merged["url"] = serp_paper.get("link", "")
            merged["authors"] = self._merge_author_lists(
                merged["authors"],
                serp_paper.get("authors", [])
            )
        
        if ads_paper:
            merged["ads_bibcode"] = ads_paper.get("bibcode")
            if not merged["title"]:
                merged["title"] = ads_paper.get("title", "")
            if not merged["abstract"]:
                merged["abstract"] = ads_paper.get("abstract", "")
            if not merged["year"]:
                merged["year"] = ads_paper.get("year")
            if not merged["arxiv_id"] and ads_paper.get("arxiv_id"):
                merged["arxiv_id"] = ads_paper["arxiv_id"]
            if not merged["doi"] and ads_paper.get("doi"):
                merged["doi"] = ads_paper["doi"]
            merged["authors"] = self._merge_author_lists(
                merged["authors"],
                ads_paper.get("authors", [])
            )
        
        return merged

    def _normalize_citation(self, citation: Dict, source: str) -> Dict:
        """标准化Semantic Scholar被引论文信息"""
        ext_ids = citation.get("externalIds", {}) or {}
        oap = citation.get("openAccessPdf")
        pdf_url = None
        if oap and isinstance(oap, dict):
            pdf_url = oap.get("url")
        
        authors = self._merge_author_lists([], citation.get("authors", []) or [])
        
        return {
            "title": citation.get("title", ""),
            "abstract": citation.get("abstract", "") or "",
            "year": citation.get("year"),
            "authors": authors,
            "venue": citation.get("venue", ""),
            "citation_count": citation.get("citationCount", 0) or 0,
            "scholar_citation_count": 0,
            "scholar_cites_id": "",
            "scholar_link": "",
            "ss_paper_id": citation.get("paperId"),
            "arxiv_id": ext_ids.get("ArXiv"),
            "doi": ext_ids.get("DOI"),
            "pmid": ext_ids.get("PubMed"),
            "url": citation.get("url", ""),
            "open_access_pdf": pdf_url,
            "contexts": citation.get("_contexts", []),
            "intents": citation.get("_intents", []),
            "is_influential": citation.get("_isInfluential", False),
            "sources": [source],
        }

    def _normalize_pubmed_citation(self, paper: Dict) -> Dict:
        """标准化PubMed被引论文信息"""
        return {
            "title": paper.get("title", ""),
            "abstract": paper.get("abstract", "") or "",
            "year": paper.get("year"),
            "authors": self._merge_author_lists([], paper.get("authors", [])),
            "venue": paper.get("venue", ""),
            "citation_count": 0,
            "scholar_citation_count": 0,
            "scholar_cites_id": "",
            "scholar_link": "",
            "ss_paper_id": None,
            "arxiv_id": None,
            "doi": paper.get("doi"),
            "pmid": paper.get("pmid"),
            "url": "",
            "open_access_pdf": None,
            "contexts": [],
            "intents": [],
            "is_influential": False,
            "sources": ["pubmed"],
        }

    def _normalize_serp_citation(self, paper: Dict) -> Dict:
        """标准化SerpAPI被引论文信息"""
        arxiv_id = paper.get("externalIds", {}).get("ArXiv")
        return {
            "title": paper.get("title", ""),
            "abstract": paper.get("abstract", "") or "",
            "year": paper.get("year"),
            "authors": self._merge_author_lists([], paper.get("authors", [])),
            "venue": paper.get("venue", ""),
            "citation_count": 0,
            "scholar_citation_count": paper.get("scholar_citation_count", 0) or 0,
            "scholar_cites_id": paper.get("scholar_cites_id", ""),
            "scholar_link": paper.get("scholar_link", ""),
            "ss_paper_id": paper.get("paperId"),
            "arxiv_id": arxiv_id,
            "doi": (paper.get("externalIds", {}) or {}).get("DOI"),
            "pmid": None,
            "url": paper.get("url", ""),
            "open_access_pdf": None,
            "contexts": [],
            "intents": [],
            "is_influential": False,
            "sources": ["serpapi"],
        }

    def _normalize_ads_citation(self, paper: Dict) -> Dict:
        """标准化ADS ABS被引论文信息"""
        ext_ids = paper.get("externalIds", {})
        return {
            "title": paper.get("title", ""),
            "abstract": paper.get("abstract", "") or "",
            "year": paper.get("year"),
            "authors": self._merge_author_lists([], paper.get("authors", [])),
            "venue": paper.get("venue", ""),
            "citation_count": paper.get("citationCount", 0) or 0,
            "scholar_citation_count": 0,
            "scholar_cites_id": "",
            "scholar_link": "",
            "ss_paper_id": paper.get("paperId"),
            "arxiv_id": ext_ids.get("ArXiv"),
            "doi": ext_ids.get("DOI"),
            "pmid": None,
            "url": "",
            "open_access_pdf": None,
            "contexts": [],
            "intents": [],
            "is_influential": False,
            "sources": ["adsabs"],
        }

    def _merge_citation_info(self, existing: Dict, new_data: Dict, source: str) -> Dict:
        """合并重复被引论文的信息"""
        if source not in existing.get("sources", []):
            existing["sources"].append(source)
        
        if not existing.get("abstract") and new_data.get("abstract"):
            existing["abstract"] = new_data["abstract"]
        existing["authors"] = self._merge_author_lists(
            existing.get("authors", []),
            new_data.get("authors", [])
        )
        if not existing.get("open_access_pdf"):
            oap = new_data.get("openAccessPdf")
            if oap and isinstance(oap, dict):
                existing["open_access_pdf"] = oap.get("url")
            elif new_data.get("open_access_pdf"):
                existing["open_access_pdf"] = new_data.get("open_access_pdf")
        if not existing.get("arxiv_id"):
            ext_ids = new_data.get("externalIds", {}) or {}
            if ext_ids.get("ArXiv"):
                existing["arxiv_id"] = ext_ids["ArXiv"]
            elif new_data.get("arxiv_id"):
                existing["arxiv_id"] = new_data.get("arxiv_id")
        if not existing.get("doi"):
            ext_ids = new_data.get("externalIds", {}) or {}
            existing["doi"] = ext_ids.get("DOI") or new_data.get("doi")
        if not existing.get("pmid"):
            ext_ids = new_data.get("externalIds", {}) or {}
            existing["pmid"] = ext_ids.get("PubMed") or new_data.get("pmid")
        if not existing.get("url") and new_data.get("url"):
            existing["url"] = new_data["url"]
        if not existing.get("scholar_link") and new_data.get("scholar_link"):
            existing["scholar_link"] = new_data["scholar_link"]
        if not existing.get("venue") and new_data.get("venue"):
            existing["venue"] = new_data["venue"]
        if not existing.get("year") and new_data.get("year"):
            existing["year"] = new_data["year"]
        if not existing.get("ss_paper_id") and new_data.get("paperId"):
            existing["ss_paper_id"] = new_data["paperId"]
        if new_data.get("scholar_citation_count", 0) > existing.get("scholar_citation_count", 0):
            existing["scholar_citation_count"] = new_data.get("scholar_citation_count", 0)
        if new_data.get("scholar_cites_id") and not existing.get("scholar_cites_id"):
            existing["scholar_cites_id"] = new_data["scholar_cites_id"]
        
        return existing

    def close(self):
        self.ss_client.close()
        self.arxiv_client.close()
        self.pubmed_client.close()


def test_unified_search():
    """测试统一搜索模块"""
    search = UnifiedPaperSearch()
    
    print("=" * 60)
    print("测试: 搜索 Earth-Agent 并获取被引")
    paper = search.search_paper("Earth-Agent: Unlocking the Full Landscape of Earth Observation with Agents")
    if paper:
        print(f"  标题: {paper['title']}")
        print(f"  SS ID: {paper['ss_paper_id']}")
        print(f"  ArXiv ID: {paper['arxiv_id']}")
        print(f"  ADS bibcode: {paper['ads_bibcode']}")
        print(f"  SerpAPI cites_id: {paper['serp_cites_id']}")
        print(f"  被引次数: {paper['citation_count']}")
        
        citations = search.get_citations(paper, limit=50)
        print(f"\n  5源去重后被引论文数: {len(citations)}")
        for i, c in enumerate(citations[:5]):
            print(f"  [{i+1}] {c['title'][:70]}")
            print(f"      来源: {c.get('sources')}, ArXiv: {c.get('arxiv_id')}")
    
    search.close()
    print("\n测试完成!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_unified_search()
