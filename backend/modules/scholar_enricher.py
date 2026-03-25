"""
学者画像补全模块
为被引论文列表补齐第一作者国家/机构、知名学者判定、自引检测、学者画像。
使用搜索型 LLM + SerpApi 进行信息补全。
"""

import logging
import re
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Callable

from backend.modules.search_llm_client import SearchLLMClient
from backend.modules import serp_api

logger = logging.getLogger("citation_analyzer.scholar_enricher")

FAMOUS_INSTITUTIONS = {
    "Google": {"keywords": ["google", "alphabet inc"], "category": "国际科技企业"},
    "DeepMind": {"keywords": ["deepmind"], "category": "国际科技企业"},
    "OpenAI": {"keywords": ["openai"], "category": "国际科技企业"},
    "Meta": {"keywords": ["meta ai", "meta research", "fair,", "facebook ai", "facebook research"], "category": "国际科技企业"},
    "Microsoft Research": {"keywords": ["microsoft research"], "category": "国际科技企业"},
    "NVIDIA": {"keywords": ["nvidia"], "category": "国际科技企业"},
    "Anthropic": {"keywords": ["anthropic"], "category": "国际科技企业"},
    "Apple": {"keywords": ["apple inc", "apple research"], "category": "国际科技企业"},
    "Amazon": {"keywords": ["amazon research", "aws research"], "category": "国际科技企业"},
    "IBM Research": {"keywords": ["ibm research"], "category": "国际科技企业"},
    "华为": {"keywords": ["huawei", "华为"], "category": "国内科技企业"},
    "阿里巴巴/达摩院": {"keywords": ["alibaba", "aliyun", "damo academy", "阿里巴巴", "达摩院"], "category": "国内科技企业"},
    "字节跳动": {"keywords": ["bytedance", "tiktok", "字节跳动"], "category": "国内科技企业"},
    "腾讯": {"keywords": ["tencent", "腾讯"], "category": "国内科技企业"},
    "百度": {"keywords": ["baidu", "百度"], "category": "国内科技企业"},
    "商汤科技": {"keywords": ["sensetime", "商汤"], "category": "国内科技企业"},
    "MIT": {"keywords": ["mit", "massachusetts institute of technology"], "category": "海外顶尖高校"},
    "Stanford": {"keywords": ["stanford"], "category": "海外顶尖高校"},
    "Harvard": {"keywords": ["harvard"], "category": "海外顶尖高校"},
    "UC Berkeley": {"keywords": ["uc berkeley", "university of california, berkeley"], "category": "海外顶尖高校"},
    "CMU": {"keywords": ["carnegie mellon", "cmu"], "category": "海外顶尖高校"},
    "Oxford": {"keywords": ["oxford"], "category": "海外顶尖高校"},
    "Cambridge": {"keywords": ["cambridge"], "category": "海外顶尖高校"},
    "ETH Zurich": {"keywords": ["eth zurich", "ethz"], "category": "海外顶尖高校"},
    "清华大学": {"keywords": ["tsinghua", "清华"], "category": "国内顶尖高校/机构"},
    "北京大学": {"keywords": ["peking university", "pku", "北京大学", "北大"], "category": "国内顶尖高校/机构"},
    "中国科学院": {"keywords": ["chinese academy of sciences", "中国科学院", "cas "], "category": "国内顶尖高校/机构"},
    "上海交通大学": {"keywords": ["shanghai jiao tong", "sjtu", "上海交通"], "category": "国内顶尖高校/机构"},
    "浙江大学": {"keywords": ["zhejiang university", "zju", "浙江大学"], "category": "国内顶尖高校/机构"},
    "复旦大学": {"keywords": ["fudan", "复旦"], "category": "国内顶尖高校/机构"},
    "哈尔滨工业大学": {"keywords": ["harbin institute of technology", "哈工大"], "category": "国内顶尖高校/机构"},
    "NUS": {"keywords": ["national university of singapore", "nus"], "category": "海外顶尖高校"},
    "Princeton": {"keywords": ["princeton"], "category": "海外顶尖高校"},
    "Cornell": {"keywords": ["cornell"], "category": "海外顶尖高校"},
    "Columbia": {"keywords": ["columbia university"], "category": "海外顶尖高校"},
    "Toronto": {"keywords": ["university of toronto"], "category": "海外顶尖高校"},
}

LEVEL_LABELS = {
    "two_academy_member": "两院院士",
    "fellow": "Fellow",
    "other_academy": "其他院士",
    "distinguished": "杰青/长江/优青",
    "industry_leader": "业界领袖",
    "none": "",
}


class ScholarEnricher:
    """学者画像补全器"""

    MAX_WORKERS = 5

    def __init__(self, log_callback: Optional[Callable] = None):
        self.search_client = SearchLLMClient()
        self.log = log_callback or logger.info
        self._author_cache: Dict[str, Dict] = {}
        self._author_roster_cache: Dict[str, Dict] = {}
        self._cache_lock = threading.Lock()

    def enrich_citations(self, target_paper: Dict, evaluations: List[Dict],
                         citations: List[Dict],
                         progress_callback: Optional[Callable] = None) -> Dict:
        """
        对已评估的被引论文列表做学者画像补全（并发版）。
        返回 {scholar_profiles, institution_stats, self_citation_indices, enriched_citations}
        """
        self.log("开始学者画像与地域层级补全...")
        total = len(evaluations)

        target_authors = [a for a in target_paper.get("authors", []) if (a.get("name") or "").strip()]
        all_citing_authors = []
        for idx, ev in enumerate(evaluations):
            citing = citations[idx] if idx < len(citations) else {}
            authors = self._resolve_citing_authors(citing)
            all_citing_authors.append(authors)

        citing_author_count = sum(len(a) for a in all_citing_authors)
        grand_total = len(target_authors) + citing_author_count
        done_counter = [0]
        counter_lock = threading.Lock()

        def _tick(name: str):
            with counter_lock:
                done_counter[0] += 1
                current = done_counter[0]
            if progress_callback:
                progress_callback(current, grand_total, name)

        self.log(f"共需查询 {grand_total} 位作者 (目标论文 {len(target_authors)} + 施引论文 {citing_author_count})，使用 {self.MAX_WORKERS} 并发")

        if progress_callback:
            progress_callback(0, grand_total, "初始化...")

        target_author_profiles = self._enrich_authors_concurrent(
            target_authors, target_paper.get("title", ""), target_paper, _tick
        )

        enriched = []
        renowned_scholars = []
        self_citation_indices = []

        for i, ev in enumerate(evaluations):
            authors = all_citing_authors[i]
            first_author = authors[0].get("name", "") if authors else ""
            citing = citations[i] if i < len(citations) else {}
            title = ev.get("citing_title", "")

            author_profiles = self._enrich_authors_concurrent(
                [a for a in authors if (a.get("name") or "").strip()],
                title, citing, _tick,
                ranks=[r for r, a in enumerate(authors, 1) if (a.get("name") or "").strip()]
            )

            first_profile = author_profiles[0] if author_profiles else {
                "country": "",
                "institution": "",
                "scholar_info": {"is_renowned": False, "renowned_level": "none"},
            }

            is_self = self._check_self_citation(author_profiles, target_author_profiles)
            if is_self:
                self_citation_indices.append(i)

            enriched_entry = {
                "first_author_country": first_profile.get("country", ""),
                "first_author_institution": first_profile.get("institution", ""),
                "is_self_citation": is_self,
                "scholar_info": first_profile.get("scholar_info", {}),
                "resolved_authors": authors,
                "authors_enriched": author_profiles,
            }
            enriched.append(enriched_entry)

            for author_profile in author_profiles:
                a_info = author_profile.get("scholar_info", {})
                if a_info.get("is_renowned"):
                    renowned_scholars.append(self._build_scholar_profile(
                        a_info,
                        author_profile.get("name", ""),
                        author_profile.get("country", ""),
                        author_profile.get("institution", ""),
                        title, ev,
                        author_rank=author_profile.get("author_rank", 1),
                    ))

            if (i + 1) % 5 == 0:
                self.log(f"  学者补全进度: {i+1}/{total}")

        institution_stats = self._compute_institution_stats(enriched, evaluations)

        deduped_scholars = self._dedup_scholars(renowned_scholars)

        self.log(f"学者补全完成: {len(deduped_scholars)} 位知名学者, "
                 f"{len(self_citation_indices)} 篇自引")

        return {
            "scholar_profiles": deduped_scholars,
            "institution_stats": institution_stats,
            "self_citation_indices": self_citation_indices,
            "self_citation_count": len(self_citation_indices),
            "enriched_citations": enriched,
        }

    def _enrich_authors_concurrent(
        self,
        authors: List[Dict],
        paper_title: str,
        citation: Dict,
        tick: Optional[Callable] = None,
        ranks: Optional[List[int]] = None,
    ) -> List[Dict]:
        """Enrich a list of authors concurrently using ThreadPoolExecutor."""
        if not authors:
            return []

        if ranks is None:
            ranks = list(range(1, len(authors) + 1))

        results = [None] * len(authors)

        def _work(idx, author, rank):
            author_name = (author.get("name") or "").strip()
            if not author_name:
                return
            country, institution, scholar_info = self._enrich_author(
                author_name, paper_title, citation, author
            )
            results[idx] = {
                "name": author_name,
                "country": country,
                "institution": institution,
                "scholar_info": scholar_info,
                "author_rank": rank,
            }
            if tick:
                tick(author_name)

        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as pool:
            futures = []
            for idx, (author, rank) in enumerate(zip(authors, ranks)):
                futures.append(pool.submit(_work, idx, author, rank))
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    logger.warning(f"Concurrent author enrichment error: {e}")

        return [r for r in results if r is not None]

    def _build_scholar_profile(
        self,
        scholar_info: Dict,
        fallback_name: str,
        country: str,
        institution: str,
        title: str,
        evaluation: Dict,
        author_rank: int,
    ) -> Dict:
        return {
            "name": scholar_info.get("name", fallback_name),
            "institution": scholar_info.get("institution", institution),
            "country": scholar_info.get("country", country),
            "title": scholar_info.get("title", ""),
            "honors": scholar_info.get("honors", ""),
            "level": scholar_info.get("renowned_level", "none"),
            "level_label": LEVEL_LABELS.get(scholar_info.get("renowned_level", "none"), ""),
            "citing_paper_title": title,
            "citing_year": evaluation.get("citing_year"),
            "citation_type": evaluation.get("citation_type", "unknown"),
            "citation_summary": evaluation.get("summary", ""),
            "is_top": scholar_info.get("renowned_level") in (
                "two_academy_member", "fellow", "other_academy"
            ),
            "author_rank": author_rank,
        }

    def _get_target_author_profiles(self, target_paper: Dict,
                                     tick: Optional[Callable] = None) -> List[Dict]:
        authors = [a for a in target_paper.get("authors", []) if (a.get("name") or "").strip()]
        return self._enrich_authors_concurrent(
            authors, target_paper.get("title", ""), target_paper, tick
        )

    @staticmethod
    def _normalize_name_variants(name: str) -> set:
        variants = set()
        clean = (name or "").strip()
        if not clean:
            return variants
        variants.add(clean.lower())
        base = re.sub(r'\s*[\(（][^\)）]*[\)）]', '', clean).strip()
        if base:
            variants.add(base.lower())
        zh = re.sub(r'[^\u4e00-\u9fff]', '', clean)
        if len(zh) >= 2:
            variants.add(zh)
        ascii_key = re.sub(r'[^a-zA-Z]', '', clean).lower()
        if len(ascii_key) >= 4:
            variants.add(ascii_key)
        return variants

    def _collect_author_variants(self, profile: Dict) -> set:
        scholar_info = profile.get("scholar_info", {}) or {}
        variants = set()
        for value in (
            profile.get("name"),
            scholar_info.get("name"),
            scholar_info.get("name_en"),
            scholar_info.get("name_zh"),
        ):
            variants.update(self._normalize_name_variants(value or ""))
        for alias in scholar_info.get("aliases", []) or []:
            variants.update(self._normalize_name_variants(alias))
        return {v for v in variants if v}

    def _same_author(self, author_a: Dict, author_b: Dict) -> bool:
        variants_a = self._collect_author_variants(author_a)
        variants_b = self._collect_author_variants(author_b)
        if variants_a & variants_b:
            return True

        name_a = (author_a.get("name") or "").lower().strip()
        name_b = (author_b.get("name") or "").lower().strip()
        parts_a = set(name_a.split()) if name_a else set()
        parts_b = set(name_b.split()) if name_b else set()
        if name_a and name_b:
            if len(parts_a & parts_b) >= 2:
                return True

        inst_a = (
            author_a.get("institution")
            or (author_a.get("scholar_info", {}) or {}).get("institution", "")
        ).lower()
        inst_b = (
            author_b.get("institution")
            or (author_b.get("scholar_info", {}) or {}).get("institution", "")
        ).lower()
        if inst_a and inst_b and parts_a and parts_b and len(parts_a & parts_b) >= 1 and inst_a == inst_b:
            return True
        return False

    def _check_self_citation(self, citing_authors: List[Dict],
                             target_authors: List[Dict]) -> bool:
        if not target_authors:
            return False
        for author in citing_authors:
            if not author.get("name"):
                continue
            for target in target_authors:
                if self._same_author(author, target):
                    return True
        return False

    def _resolve_citing_authors(self, citation: Dict) -> List[Dict]:
        title = (citation.get("title") or "").strip()
        cache_key = f"{title.lower()}||{citation.get('year') or ''}"
        if cache_key in self._author_roster_cache:
            cached = self._author_roster_cache[cache_key]
            return cached.get("authors", [])

        authors = citation.get("authors", []) or []
        candidate_links = []
        for key in ("url", "scholar_link", "open_access_pdf"):
            value = citation.get(key)
            if value:
                candidate_links.append(str(value))
        if citation.get("doi"):
            candidate_links.append(f"https://doi.org/{citation['doi']}")
        arxiv_id = citation.get("arxiv_id") or citation.get("externalIds", {}).get("ArXiv")
        if arxiv_id:
            candidate_links.extend([
                f"https://arxiv.org/abs/{arxiv_id}",
                f"https://arxiv.org/pdf/{arxiv_id}",
                f"https://arxiv.org/html/{arxiv_id}",
            ])

        try:
            roster = self.search_client.search_paper_authors(
                title,
                citation.get("year"),
                candidate_links=candidate_links,
                known_authors=authors,
            )
        except Exception as e:
            logger.warning(f"LLM author roster search failed for {title[:60]}: {e}")
            roster = {"authors": authors}

        merged = []
        seen = set()
        for author in roster.get("authors", []) + authors:
            if not isinstance(author, dict):
                continue
            name = (author.get("name") or "").strip()
            if not name:
                continue
            key = tuple(sorted(self._normalize_name_variants(name))) or (name.lower(),)
            if key in seen:
                continue
            seen.add(key)
            merged.append({
                "name": name,
                "name_en": (author.get("name_en") or "").strip(),
                "name_zh": (author.get("name_zh") or "").strip(),
                "institution": (author.get("institution") or "").strip(),
            })

        if not merged:
            merged = [{"name": a.get("name", "").strip()} for a in authors if a.get("name")]

        self._author_roster_cache[cache_key] = {"authors": merged, "roster": roster}
        return merged

    def _enrich_author(self, author_name: str, paper_title: str,
                       citation: Dict, author_seed: Optional[Dict] = None) -> tuple:
        if not author_name:
            return "", "", {"is_renowned": False, "renowned_level": "none"}

        cache_key = f"{author_name.lower().strip()}||{paper_title.lower().strip()}"
        with self._cache_lock:
            if cache_key in self._author_cache:
                info = self._author_cache[cache_key]
                return info.get("country", ""), info.get("institution", ""), info

        hint_parts = []
        if author_seed:
            for key in ("name_en", "name_zh", "institution"):
                value = author_seed.get(key)
                if value:
                    hint_parts.append(str(value))
        for key in ("venue", "url", "scholar_link", "arxiv_id", "doi"):
            value = citation.get(key)
            if value:
                if key == "doi":
                    hint_parts.append(f"https://doi.org/{value}")
                elif key == "arxiv_id":
                    hint_parts.append(f"https://arxiv.org/abs/{value}")
                else:
                    hint_parts.append(str(value))
        context_hint = " | ".join(hint_parts[:5])

        try:
            info = self.search_client.search_scholar_info(
                author_name, paper_title, context_hint
            )
        except Exception as e:
            logger.warning(f"LLM scholar search failed for {author_name}: {e}")
            info = {"name": author_name, "is_renowned": False, "renowned_level": "none",
                    "institution": "", "country": ""}

        country = info.get("country", "")
        institution = info.get("institution", "")
        with self._cache_lock:
            self._author_cache[cache_key] = info
        return country, institution, info

    def _compute_institution_stats(self, enriched: List[Dict],
                                   evaluations: List[Dict]) -> Dict:
        category_order = ["国际科技企业", "国内科技企业", "海外顶尖高校", "国内顶尖高校/机构"]
        inst_papers: Dict[str, set] = {}

        for i, entry in enumerate(enriched):
            inst = entry.get("first_author_institution", "")
            info_inst = entry.get("scholar_info", {}).get("institution", "")
            text = f"{inst} {info_inst}".lower().strip()
            title = evaluations[i].get("citing_title", "") if i < len(evaluations) else ""

            for inst_name, meta in FAMOUS_INSTITUTIONS.items():
                if any(kw in text for kw in meta["keywords"]):
                    inst_papers.setdefault(inst_name, set()).add(title)

        grouped = {}
        for cat in category_order:
            entries = []
            for inst_name, meta in FAMOUS_INSTITUTIONS.items():
                if meta["category"] == cat and inst_name in inst_papers:
                    entries.append({
                        "name": inst_name,
                        "papers": sorted(inst_papers[inst_name]),
                        "count": len(inst_papers[inst_name]),
                    })
            entries.sort(key=lambda x: -x["count"])
            if entries:
                grouped[cat] = entries
        return grouped

    @staticmethod
    def _dedup_scholars(scholars: List[Dict]) -> List[Dict]:
        def _safe_year(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0

        seen = set()
        result = []
        for s in scholars:
            name = s.get("name", "").strip()
            clean = re.sub(r'\s*[\(（][^\)）]*[\)）]', '', name).strip()
            zh = re.sub(r'[^\u4e00-\u9fff]', '', clean)
            en = re.sub(r'[^a-zA-Z]', '', clean).lower()
            key = zh if len(zh) >= 2 else en if len(en) >= 4 else clean.lower()
            if key and key not in seen:
                seen.add(key)
                result.append(s)
        result.sort(key=lambda x: (
            0 if x.get("is_top") else 1,
            -_safe_year(x.get("citing_year"))
        ))
        return result
