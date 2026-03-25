"""
PubMed API 模块 (E-utilities)
提供论文搜索功能
"""

import httpx
import time
import logging
import xml.etree.ElementTree as ET
from typing import Optional, Dict, List

logger = logging.getLogger("citation_analyzer.pubmed")

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
RATE_LIMIT_DELAY = 0.4  # PubMed限制每秒3次请求


class PubMedClient:
    """PubMed E-utilities API 客户端"""

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

    def search_paper(self, title: str, max_results: int = 5) -> List[Dict]:
        """通过标题搜索PubMed论文"""
        self._rate_limit()
        logger.info(f"[PubMed] 搜索论文: {title}")
        
        try:
            # Step 1: ESearch
            search_params = {
                "db": "pubmed",
                "term": f"{title}[Title]",
                "retmax": max_results,
                "retmode": "json",
                "sort": "relevance"
            }
            
            response = self.client.get(f"{EUTILS_BASE}/esearch.fcgi", params=search_params)
            response.raise_for_status()
            search_data = response.json()
            
            id_list = search_data.get("esearchresult", {}).get("idlist", [])
            if not id_list:
                logger.warning(f"[PubMed] 未找到论文: {title}")
                return []
            
            # Step 2: EFetch获取详情
            self._rate_limit()
            fetch_params = {
                "db": "pubmed",
                "id": ",".join(id_list),
                "retmode": "xml",
                "rettype": "abstract"
            }
            
            response = self.client.get(f"{EUTILS_BASE}/efetch.fcgi", params=fetch_params)
            response.raise_for_status()
            
            return self._parse_efetch_xml(response.text)
        except Exception as e:
            logger.error(f"[PubMed] 搜索失败: {e}")
            return []

    def get_citing_papers(self, pmid: str) -> List[str]:
        """获取引用某篇论文的PMID列表"""
        self._rate_limit()
        logger.info(f"[PubMed] 获取被引论文: PMID {pmid}")
        
        try:
            params = {
                "dbfrom": "pubmed",
                "db": "pubmed",
                "id": pmid,
                "linkname": "pubmed_pubmed_citedin",
                "retmode": "json"
            }
            
            response = self.client.get(f"{EUTILS_BASE}/elink.fcgi", params=params)
            response.raise_for_status()
            data = response.json()
            
            citing_ids = []
            linksets = data.get("linksets", [])
            for linkset in linksets:
                for linksetdb in linkset.get("linksetdbs", []):
                    if linksetdb.get("linkname") == "pubmed_pubmed_citedin":
                        for link in linksetdb.get("links", []):
                            citing_ids.append(str(link))
            
            logger.info(f"[PubMed] 找到 {len(citing_ids)} 篇被引论文")
            return citing_ids
        except Exception as e:
            logger.error(f"[PubMed] 获取被引失败: {e}")
            return []

    def get_papers_by_ids(self, pmids: List[str]) -> List[Dict]:
        """通过PMID列表获取论文详情"""
        if not pmids:
            return []
        
        self._rate_limit()
        logger.info(f"[PubMed] 获取 {len(pmids)} 篇论文详情")
        
        try:
            params = {
                "db": "pubmed",
                "id": ",".join(pmids[:200]),  # 最多200个
                "retmode": "xml",
                "rettype": "abstract"
            }
            
            response = self.client.get(f"{EUTILS_BASE}/efetch.fcgi", params=params)
            response.raise_for_status()
            
            return self._parse_efetch_xml(response.text)
        except Exception as e:
            logger.error(f"[PubMed] 获取论文详情失败: {e}")
            return []

    def _parse_efetch_xml(self, xml_text: str) -> List[Dict]:
        """解析EFetch返回的XML"""
        papers = []
        try:
            root = ET.fromstring(xml_text)
            for article in root.findall(".//PubmedArticle"):
                paper = {}
                
                # PMID
                pmid_el = article.find(".//PMID")
                paper["pmid"] = pmid_el.text if pmid_el is not None else ""
                
                # 标题
                title_el = article.find(".//ArticleTitle")
                paper["title"] = title_el.text if title_el is not None and title_el.text else ""
                
                # 摘要
                abstract_parts = []
                for abs_el in article.findall(".//AbstractText"):
                    if abs_el.text:
                        label = abs_el.get("Label", "")
                        if label:
                            abstract_parts.append(f"{label}: {abs_el.text}")
                        else:
                            abstract_parts.append(abs_el.text)
                paper["abstract"] = " ".join(abstract_parts)
                
                # 作者
                authors = []
                for author_el in article.findall(".//Author"):
                    last = author_el.findtext("LastName", "")
                    first = author_el.findtext("ForeName", "")
                    affil = author_el.findtext(".//Affiliation", "")
                    if last:
                        authors.append({
                            "name": f"{first} {last}".strip(),
                            "affiliation": affil
                        })
                paper["authors"] = authors
                
                # 年份
                year_el = article.find(".//PubDate/Year")
                if year_el is not None and year_el.text:
                    paper["year"] = int(year_el.text)
                
                # DOI
                for id_el in article.findall(".//ArticleId"):
                    if id_el.get("IdType") == "doi":
                        paper["doi"] = id_el.text
                    elif id_el.get("IdType") == "pmc":
                        paper["pmc_id"] = id_el.text
                
                # 期刊
                journal_el = article.find(".//Journal/Title")
                paper["venue"] = journal_el.text if journal_el is not None else ""
                
                papers.append(paper)
        except ET.ParseError as e:
            logger.error(f"[PubMed] XML解析错误: {e}")
        
        return papers

    def close(self):
        self.client.close()


def test_pubmed():
    """测试PubMed模块"""
    client = PubMedClient()
    
    print("=" * 60)
    print("测试1: 搜索论文")
    papers = client.search_paper("Reflexion: Language Agents with Verbal Reinforcement Learning")
    if papers:
        for p in papers[:3]:
            print(f"  PMID: {p.get('pmid')}, 标题: {p.get('title', 'N/A')[:80]}")
    else:
        print("  未找到 (CS论文可能不在PubMed中)")
    
    print("\n" + "=" * 60)
    print("测试2: 搜索医学论文")
    papers2 = client.search_paper("Attention Is All You Need")
    if papers2:
        for p in papers2[:3]:
            print(f"  PMID: {p.get('pmid')}, 标题: {p.get('title', 'N/A')[:80]}")
    else:
        print("  未找到")
    
    client.close()
    print("\n测试完成!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_pubmed()
