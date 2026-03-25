"""
NASA ADS (Astrophysics Data System) API 检索模块
通过ADS API获取论文搜索和被引列表
"""

import logging
import time
import httpx
from typing import Optional, Dict, List

from backend.config import ADSABS_SETTINGS

logger = logging.getLogger("citation_analyzer.adsabs_api")

ADS_API_KEY = ADSABS_SETTINGS["api_key"]
BASE_URL = ADSABS_SETTINGS["base_url"]


def set_api_key(key: str):
    global ADS_API_KEY
    ADS_API_KEY = key


def _make_request(endpoint: str, params: dict, timeout: int = 30) -> Optional[dict]:
    """发送ADS API请求"""
    if not ADS_API_KEY:
        logger.warning("[ADS] API key未设置")
        return None
    
    headers = {"Authorization": f"Bearer {ADS_API_KEY}"}
    
    for attempt in range(3):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(f"{BASE_URL}{endpoint}", params=params, headers=headers)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    logger.warning(f"[ADS] 速率限制，等待重试 ({attempt+1}/3)")
                    time.sleep(10 * (attempt + 1))
                else:
                    logger.warning(f"[ADS] 请求失败: {resp.status_code} - {resp.text[:200]}")
                    return None
        except Exception as e:
            logger.warning(f"[ADS] 请求异常 ({attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(3)
    return None


def search_paper(title: str) -> Optional[Dict]:
    """搜索论文并返回标准化信息"""
    logger.info(f"[ADS] 搜索论文: {title[:60]}...")
    
    # 使用精确标题搜索
    data = _make_request("/search/query", {
        "q": f'title:"{title}"',
        "fl": "bibcode,title,citation_count,doi,identifier,abstract,author,year,pub",
        "rows": 5
    })
    
    if not data:
        return None
    
    docs = data.get("response", {}).get("docs", [])
    if not docs:
        # 尝试模糊搜索
        data = _make_request("/search/query", {
            "q": f'title:({title})',
            "fl": "bibcode,title,citation_count,doi,identifier,abstract,author,year,pub",
            "rows": 5
        })
        if data:
            docs = data.get("response", {}).get("docs", [])
    
    if not docs:
        logger.info("[ADS] 未找到结果")
        return None
    
    # 找最匹配的
    title_lower = title.lower().strip()
    best = None
    for d in docs:
        d_title = d.get("title", [""])[0].lower().strip()
        if title_lower in d_title or d_title in title_lower:
            best = d
            break
    
    if not best:
        best = docs[0]
    
    # 提取arxiv ID
    arxiv_id = ""
    for ident in best.get("identifier", []):
        if "arXiv:" in ident:
            arxiv_id = ident.replace("arXiv:", "")
            break
    
    paper = {
        "bibcode": best.get("bibcode", ""),
        "title": best.get("title", [""])[0],
        "citation_count": best.get("citation_count", 0),
        "doi": best.get("doi", [""])[0] if best.get("doi") else "",
        "abstract": best.get("abstract", ""),
        "authors": [{"name": a} for a in best.get("author", [])],
        "year": best.get("year"),
        "venue": best.get("pub", ""),
        "arxiv_id": arxiv_id,
        "source": "adsabs"
    }
    
    logger.info(f"[ADS] 找到论文: {paper['title'][:50]}, bibcode={paper['bibcode']}, 被引={paper['citation_count']}")
    return paper


def get_citations(bibcode: str, max_results: int = 200) -> List[Dict]:
    """获取被引论文列表"""
    if not bibcode:
        logger.warning("[ADS] 无bibcode，无法获取被引列表")
        return []
    
    logger.info(f"[ADS] 获取被引列表, bibcode={bibcode}, max={max_results}")
    
    all_papers = []
    start = 0
    rows_per_page = 50
    
    while len(all_papers) < max_results:
        data = _make_request("/search/query", {
            "q": f"citations(bibcode:{bibcode})",
            "fl": "bibcode,title,doi,identifier,abstract,year,author,pub,citation_count",
            "rows": rows_per_page,
            "start": start
        })
        
        if not data:
            break
        
        docs = data.get("response", {}).get("docs", [])
        total = data.get("response", {}).get("numFound", 0)
        
        if not docs:
            break
        
        for d in docs:
            # 提取arxiv ID
            arxiv_id = ""
            doi = ""
            for ident in d.get("identifier", []):
                if "arXiv:" in ident:
                    arxiv_id = ident.replace("arXiv:", "")
                if ident.startswith("10."):
                    doi = ident
            
            if not doi and d.get("doi"):
                doi = d["doi"][0] if isinstance(d["doi"], list) else d["doi"]
            
            paper = {
                "paperId": d.get("bibcode", ""),
                "title": d.get("title", [""])[0] if isinstance(d.get("title"), list) else d.get("title", ""),
                "abstract": d.get("abstract", ""),
                "year": d.get("year"),
                "authors": [{"name": a} for a in d.get("author", [])[:10]],
                "venue": d.get("pub", ""),
                "citationCount": d.get("citation_count", 0),
                "externalIds": {},
                "source": "adsabs"
            }
            
            if arxiv_id:
                paper["externalIds"]["ArXiv"] = arxiv_id
            if doi:
                paper["externalIds"]["DOI"] = doi
            
            all_papers.append(paper)
            
            if len(all_papers) >= max_results:
                break
        
        start += rows_per_page
        
        if start >= total:
            break
        
        time.sleep(0.5)
    
    logger.info(f"[ADS] 获取到 {len(all_papers)} 篇被引论文 (总计 {total if 'total' in dir() else '?'})")
    return all_papers


def test_adsabs_api():
    """测试ADS ABS API模块"""
    # 测试搜索Reflexion
    paper = search_paper("Reflexion: Language Agents with Verbal Reinforcement Learning")
    if paper:
        print(f"✓ 搜索成功: {paper['title'][:50]}")
        print(f"  bibcode: {paper['bibcode']}, 被引: {paper['citation_count']}")
        
        # 测试获取被引
        citations = get_citations(paper["bibcode"], max_results=5)
        print(f"✓ 获取被引: {len(citations)} 篇")
        for c in citations[:3]:
            print(f"  - {c['title'][:60]}")
            print(f"    ArXiv: {c['externalIds'].get('ArXiv', 'N/A')}")
    else:
        print("✗ Reflexion搜索失败")
    
    # 测试Earth-Agent
    print()
    paper2 = search_paper("Earth-Agent: Unlocking the Full Landscape of Earth Observation with Agents")
    if paper2:
        print(f"✓ 搜索成功: {paper2['title'][:50]}")
        print(f"  bibcode: {paper2['bibcode']}, 被引: {paper2['citation_count']}")
        
        citations2 = get_citations(paper2["bibcode"], max_results=5)
        print(f"✓ 获取被引: {len(citations2)} 篇")
        for c in citations2[:3]:
            print(f"  - {c['title'][:60]}")
    else:
        print("✗ Earth-Agent搜索失败")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_adsabs_api()
