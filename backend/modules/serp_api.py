"""
SerpAPI Google Scholar 检索模块
通过SerpAPI获取Google Scholar的论文搜索和被引列表
"""

import logging
import re
import time
import httpx
from typing import Optional, Dict, List

from backend.config import SERPAPI_SETTINGS

logger = logging.getLogger("citation_analyzer.serp_api")

SERP_API_KEY = SERPAPI_SETTINGS["api_key"]
BASE_URL = SERPAPI_SETTINGS["base_url"]


def set_api_key(key: str):
    global SERP_API_KEY
    SERP_API_KEY = key


def _make_request(params: dict, timeout: int = 30) -> Optional[dict]:
    """发送SerpAPI请求"""
    if not SERP_API_KEY:
        logger.warning("[SerpAPI] API key未设置")
        return None
    params["api_key"] = SERP_API_KEY
    for attempt in range(3):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(BASE_URL, params=params)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    logger.warning(f"[SerpAPI] 速率限制，等待重试 ({attempt+1}/3)")
                    time.sleep(5 * (attempt + 1))
                else:
                    logger.warning(f"[SerpAPI] 请求失败: {resp.status_code} - {resp.text[:200]}")
                    return None
        except Exception as e:
            logger.warning(f"[SerpAPI] 请求异常 ({attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(3)
    return None


def search_paper(title: str) -> Optional[Dict]:
    """通过SerpAPI搜索论文，返回标准化的论文信息"""
    logger.info(f"[SerpAPI] 搜索论文: {title[:60]}...")
    
    data = _make_request({
        "engine": "google_scholar",
        "q": title,
        "num": 5
    })
    
    if not data:
        return None
    
    results = data.get("organic_results", [])
    if not results:
        logger.info("[SerpAPI] 未找到结果")
        return None
    
    # 找最匹配的结果
    title_lower = title.lower().strip()
    best = None
    for r in results:
        r_title = r.get("title", "").lower().strip()
        if title_lower in r_title or r_title in title_lower:
            best = r
            break
    
    if not best:
        best = results[0]
    
    # 提取信息
    cited_by = best.get("inline_links", {}).get("cited_by", {})
    
    paper = {
        "title": best.get("title", ""),
        "serp_result_id": best.get("result_id", ""),
        "cites_id": cited_by.get("cites_id", ""),
        "citation_count": cited_by.get("total", 0),
        "snippet": best.get("snippet", ""),
        "scholar_link": best.get("link", ""),
        "link": best.get("link", ""),
        "source": "serpapi"
    }
    
    logger.info(f"[SerpAPI] 找到论文: {paper['title'][:50]}, 被引: {paper['citation_count']}")
    return paper


def _extract_authors_from_pub_info(pub_info: Dict) -> List[Dict]:
    authors_list = []
    if "authors" in pub_info:
        for author in pub_info["authors"]:
            if isinstance(author, dict):
                name = (author.get("name") or "").strip()
            else:
                name = str(author).strip()
            if name:
                authors_list.append({"name": name})
        return authors_list

    summary = (pub_info.get("summary") or "").strip()
    if not summary:
        return authors_list

    head = summary.split(" - ")[0].strip()
    head = re.sub(r'\b(19|20)\d{2}\b.*$', '', head).strip(" ,;")
    for name in re.split(r',\s*|;\s*|\s+and\s+', head):
        clean = name.strip()
        if clean and len(clean) > 1:
            authors_list.append({"name": clean})
    return authors_list


def _extract_venue_from_pub_info(pub_info: Dict) -> str:
    summary = (pub_info.get("summary") or "").strip()
    if " - " not in summary:
        return ""
    parts = [part.strip() for part in summary.split(" - ") if part.strip()]
    if len(parts) < 2:
        return ""
    return parts[-1]


def get_citations(cites_id: str, max_results: int = 100) -> List[Dict]:
    """获取被引论文列表"""
    if not cites_id:
        logger.warning("[SerpAPI] 无cites_id，无法获取被引列表")
        return []
    
    logger.info(f"[SerpAPI] 获取被引列表, cites_id={cites_id}, max={max_results}")
    
    all_papers = []
    start = 0
    per_page = 20  # SerpAPI每页最多20条
    
    while len(all_papers) < max_results:
        data = _make_request({
            "engine": "google_scholar",
            "cites": cites_id,
            "start": start,
            "num": per_page
        })
        
        if not data:
            break
        
        results = data.get("organic_results", [])
        if not results:
            break
        
        for r in results:
            cited_by = r.get("inline_links", {}).get("cited_by", {})
            pub_info = r.get("publication_info", {})
            authors_list = _extract_authors_from_pub_info(pub_info)
            
            paper = {
                "paperId": r.get("result_id", ""),
                "title": r.get("title", ""),
                "abstract": r.get("snippet", ""),
                "year": None,
                "authors": authors_list,
                "venue": _extract_venue_from_pub_info(pub_info),
                "externalIds": {},
                "url": r.get("link", ""),
                "scholar_link": r.get("link", ""),
                "scholar_cites_id": cited_by.get("cites_id", ""),
                "scholar_citation_count": cited_by.get("total", 0) or 0,
                "source": "serpapi"
            }
            
            # 尝试从资源链接中提取arxiv ID
            for resource in r.get("resources", []):
                link = resource.get("link", "")
                if "arxiv.org" in link:
                    arxiv_match = re.search(r'(\d{4}\.\d{4,5})', link)
                    if arxiv_match:
                        paper["externalIds"]["ArXiv"] = arxiv_match.group(1)
            
            # 从主链接提取arxiv ID
            main_link = r.get("link", "")
            if "arxiv.org" in main_link:
                arxiv_match = re.search(r'(\d{4}\.\d{4,5})', main_link)
                if arxiv_match:
                    paper["externalIds"]["ArXiv"] = arxiv_match.group(1)
            
            all_papers.append(paper)
            
            if len(all_papers) >= max_results:
                break
        
        start += per_page
        time.sleep(1)  # 避免速率限制
    
    logger.info(f"[SerpAPI] 获取到 {len(all_papers)} 篇被引论文")
    return all_papers


def google_search(query: str, num: int = 5) -> List[Dict]:
    """通用 Google 搜索（用于学者主页、机构信息等网页级检索）"""
    logger.info(f"[SerpAPI] Google搜索: {query[:60]}...")
    data = _make_request({
        "engine": "google",
        "q": query,
        "num": num,
        "hl": "en",
    })
    if not data:
        return []

    results = []
    for r in data.get("organic_results", []):
        results.append({
            "title": r.get("title", ""),
            "link": r.get("link", ""),
            "snippet": r.get("snippet", ""),
            "displayed_link": r.get("displayed_link", ""),
        })

    kg = data.get("knowledge_graph", {})
    if kg:
        results.insert(0, {
            "title": kg.get("title", ""),
            "link": kg.get("source", {}).get("link", ""),
            "snippet": kg.get("description", ""),
            "displayed_link": "",
            "knowledge_graph": True,
        })
    return results


def google_scholar_author_search(author_name: str) -> List[Dict]:
    """通过 Google Search 搜索学者的 Google Scholar 主页信息"""
    logger.info(f"[SerpAPI] Scholar作者搜索: {author_name}")
    results = google_search(f"{author_name} site:scholar.google.com", num=3)
    profiles = []
    for r in results:
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        link = r.get("link", "")
        if "scholar.google" in link:
            profiles.append({
                "name": author_name,
                "affiliation": snippet[:120] if snippet else "",
                "cited_by": 0,
                "interests": [],
                "link": link,
            })
    if not profiles:
        web = google_search(f"{author_name} researcher affiliation", num=3)
        for r in web:
            if r.get("snippet"):
                profiles.append({
                    "name": author_name,
                    "affiliation": r.get("snippet", "")[:120],
                    "cited_by": 0,
                    "interests": [],
                    "link": r.get("link", ""),
                })
                break
    return profiles


def google_ai_mode_query(query: str) -> Optional[Dict]:
    """使用 Google AI Mode API 进行结构化问答（摘要型补充检索）"""
    logger.info(f"[SerpAPI] AI Mode查询: {query[:60]}...")
    data = _make_request({
        "engine": "google_ai_mode",
        "q": query,
        "hl": "en",
    }, timeout=60)
    if not data:
        return None

    text_blocks = data.get("text_blocks", [])
    full_text = ""
    for block in text_blocks:
        snippet = block.get("snippet", "")
        if snippet:
            full_text += snippet + "\n"
        items = block.get("list", [])
        for item in items:
            if isinstance(item, dict):
                s = item.get("snippet", "")
                if s:
                    full_text += f"  - {s}\n"

    references = []
    for ref in data.get("references", []):
        references.append({
            "title": ref.get("title", ""),
            "link": ref.get("link", ""),
            "snippet": ref.get("snippet", ""),
            "source": ref.get("source", ""),
        })

    return {
        "text": full_text.strip(),
        "references": references,
    }


def search_author_info(author_name: str, paper_title: str = "") -> Dict:
    """
    综合利用 SerpApi 检索学者信息：
    1. 先查 Google Scholar Profiles
    2. 再用 Google Search 补充
    """
    info = {
        "name": author_name,
        "institution": "",
        "country": "",
        "cited_by": 0,
        "interests": [],
    }

    profiles = google_scholar_author_search(author_name)
    if profiles:
        top = profiles[0]
        info["institution"] = top.get("affiliation", "")
        info["cited_by"] = top.get("cited_by", 0)
        info["interests"] = top.get("interests", [])
        info["scholar_author_id"] = top.get("author_id", "")

    if not info["institution"]:
        query = f"{author_name} researcher affiliation"
        if paper_title:
            query += f" \"{paper_title[:40]}\""
        web_results = google_search(query, num=3)
        for r in web_results:
            snippet = r.get("snippet", "")
            if snippet and len(snippet) > 20:
                info["web_snippet"] = snippet
                break

    return info


def test_serp_api():
    """测试SerpAPI模块"""
    paper = search_paper("Reflexion: Language Agents with Verbal Reinforcement Learning")
    if paper:
        print(f"✓ 搜索成功: {paper['title'][:50]}")
        print(f"  被引: {paper['citation_count']}, cites_id: {paper['cites_id']}")
        
        if paper["cites_id"]:
            citations = get_citations(paper["cites_id"], max_results=5)
            print(f"✓ 获取被引: {len(citations)} 篇")
            for c in citations[:3]:
                print(f"  - {c['title'][:60]}")
    else:
        print("✗ 搜索失败")

    web = google_search("Geoffrey Hinton researcher", num=3)
    print(f"\n✓ Google搜索: {len(web)} 条结果")
    for r in web[:2]:
        print(f"  - {r['title'][:60]}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_serp_api()
