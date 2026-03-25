"""
Semantic Scholar API 模块
提供论文搜索、被引论文获取等功能
"""

import httpx
import time
import logging
from typing import Optional, Dict, List, Any

from backend.config import SEMANTIC_SCHOLAR_SETTINGS

logger = logging.getLogger("citation_analyzer.semantic_scholar")

BASE_URL = SEMANTIC_SCHOLAR_SETTINGS["base_url"]
RATE_LIMIT_DELAY = 1.0  # 未认证用户限制更严格
DEFAULT_API_KEY = SEMANTIC_SCHOLAR_SETTINGS.get("api_key", "")


class SemanticScholarClient:
    """Semantic Scholar API 客户端"""

    def __init__(self, api_key: Optional[str] = None):
        api_key = api_key if api_key is not None else DEFAULT_API_KEY
        headers = {"User-Agent": "CitationQualityAnalyzer/1.0"}
        if api_key:
            headers["x-api-key"] = api_key
        self.client = httpx.Client(
            timeout=30.0,
            headers=headers,
            follow_redirects=True
        )
        self.last_request_time = 0
        self.api_key = api_key

    def _rate_limit(self):
        """速率限制"""
        delay = 0.5 if self.api_key else RATE_LIMIT_DELAY
        elapsed = time.time() - self.last_request_time
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self.last_request_time = time.time()

    def search_paper_by_title(self, title: str) -> Optional[Dict]:
        """通过标题精确搜索论文"""
        self._rate_limit()
        logger.info(f"[SemanticScholar] 搜索论文: {title}")
        
        params = {
            "query": title,
            "fields": "paperId,title,abstract,year,citationCount,authors,externalIds,url,venue,openAccessPdf,publicationTypes,influentialCitationCount"
        }
        
        try:
            # 先尝试精确匹配
            response = self.client.get(f"{BASE_URL}/paper/search/match", params={"query": title, "fields": params["fields"]})
            if response.status_code == 200:
                data = response.json()
                # API可能返回 {"data": [...]} 或直接返回 {"paperId": ...}
                if isinstance(data, dict) and "data" in data and data["data"]:
                    paper = data["data"][0]
                    logger.info(f"[SemanticScholar] 精确匹配到论文: {paper.get('title', 'N/A')}")
                    return paper
                elif isinstance(data, dict) and "paperId" in data:
                    logger.info(f"[SemanticScholar] 精确匹配到论文: {data.get('title', 'N/A')}")
                    return data
            
            # 退回到相关性搜索
            self._rate_limit()
            response = self.client.get(f"{BASE_URL}/paper/search", params={**params, "limit": 5})
            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    # 选择标题最匹配的
                    for paper in data["data"]:
                        if paper.get("title", "").lower().strip() == title.lower().strip():
                            logger.info(f"[SemanticScholar] 相关搜索匹配到论文: {paper.get('title', 'N/A')}")
                            return paper
                    # 返回第一个结果
                    logger.info(f"[SemanticScholar] 返回最相关结果: {data['data'][0].get('title', 'N/A')}")
                    return data["data"][0]
            elif response.status_code == 429:
                logger.warning(f"[SemanticScholar] 速率限制，等待重试...")
                time.sleep(3)
                response = self.client.get(f"{BASE_URL}/paper/search", params={**params, "limit": 5})
                if response.status_code == 200:
                    data = response.json()
                    if data.get("data"):
                        return data["data"][0]
            
            logger.warning(f"[SemanticScholar] 未找到论文: {title}")
            return None
        except Exception as e:
            logger.error(f"[SemanticScholar] 搜索论文失败: {e}")
            return None

    def get_paper_details(self, paper_id: str) -> Optional[Dict]:
        """获取论文详细信息"""
        self._rate_limit()
        logger.info(f"[SemanticScholar] 获取论文详情: {paper_id}")
        
        fields = "paperId,title,abstract,year,citationCount,authors,externalIds,url,venue,openAccessPdf,publicationTypes,influentialCitationCount,tldr"
        
        try:
            response = self.client.get(f"{BASE_URL}/paper/{paper_id}", params={"fields": fields})
            if response.status_code == 200:
                return response.json()
            logger.warning(f"[SemanticScholar] 获取论文详情失败: HTTP {response.status_code}")
            return None
        except Exception as e:
            logger.error(f"[SemanticScholar] 获取论文详情异常: {e}")
            return None

    def get_citations(self, paper_id: str, limit: int = 1000, offset: int = 0) -> List[Dict]:
        """获取被引论文列表"""
        self._rate_limit()
        logger.info(f"[SemanticScholar] 获取被引论文: {paper_id}, limit={limit}, offset={offset}")
        
        fields = "paperId,title,abstract,year,citationCount,authors,externalIds,url,venue,openAccessPdf,contexts,intents,isInfluential"
        
        all_citations = []
        current_offset = offset
        
        try:
            while len(all_citations) < limit:
                batch_limit = min(1000, limit - len(all_citations))
                params = {
                    "fields": fields,
                    "offset": current_offset,
                    "limit": batch_limit
                }
                
                response = self.client.get(f"{BASE_URL}/paper/{paper_id}/citations", params=params)
                if response.status_code != 200:
                    logger.warning(f"[SemanticScholar] 获取被引失败: HTTP {response.status_code}")
                    break
                
                data = response.json()
                citations = data.get("data", [])
                
                if not citations:
                    break
                
                for citation in citations:
                    citing_paper = citation.get("citingPaper", {})
                    if citing_paper and citing_paper.get("paperId"):
                        citing_paper["_contexts"] = citation.get("contexts", [])
                        citing_paper["_intents"] = citation.get("intents", [])
                        citing_paper["_isInfluential"] = citation.get("isInfluential", False)
                        all_citations.append(citing_paper)
                
                if "next" not in data:
                    break
                current_offset = data["next"]
                self._rate_limit()
            
            logger.info(f"[SemanticScholar] 获取到 {len(all_citations)} 篇被引论文")
            return all_citations
        except Exception as e:
            logger.error(f"[SemanticScholar] 获取被引论文异常: {e}")
            return all_citations

    def close(self):
        self.client.close()


def test_semantic_scholar():
    """测试Semantic Scholar模块"""
    client = SemanticScholarClient()
    
    # 测试1: 搜索论文
    print("=" * 60)
    print("测试1: 搜索论文 - Earth-Agent")
    paper = client.search_paper_by_title("Earth-Agent: Unlocking the Full Landscape of Earth Observation with Agents")
    if paper:
        print(f"  标题: {paper.get('title')}")
        print(f"  Paper ID: {paper.get('paperId')}")
        print(f"  年份: {paper.get('year')}")
        print(f"  被引次数: {paper.get('citationCount')}")
        print(f"  外部ID: {paper.get('externalIds', {})}")
        
        # 测试2: 获取被引
        print("\n测试2: 获取被引论文")
        citations = client.get_citations(paper["paperId"], limit=20)
        print(f"  获取到 {len(citations)} 篇被引论文")
        for i, c in enumerate(citations[:5]):
            print(f"  [{i+1}] {c.get('title', 'N/A')}")
    else:
        print("  未找到论文!")
    
    # 测试3: 搜索 Reflexion
    print("\n" + "=" * 60)
    print("测试3: 搜索论文 - Reflexion")
    paper2 = client.search_paper_by_title("Reflexion: Language Agents with Verbal Reinforcement Learning")
    if paper2:
        print(f"  标题: {paper2.get('title')}")
        print(f"  Paper ID: {paper2.get('paperId')}")
        print(f"  被引次数: {paper2.get('citationCount')}")
        
        # 获取前5篇被引
        citations2 = client.get_citations(paper2["paperId"], limit=5)
        print(f"  获取到 {len(citations2)} 篇被引论文")
        for i, c in enumerate(citations2[:5]):
            print(f"  [{i+1}] {c.get('title', 'N/A')}")
    else:
        print("  未找到论文!")
    
    client.close()
    print("\n测试完成!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_semantic_scholar()
