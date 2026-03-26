"""
搜索型 LLM 客户端
专用于学者信息检索、引用位置核验、联网证据抓取等需要 web_search 的场景。
独立于主评估 LLM 配置，统一使用配置文件中的模型 + Responses API。
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI
from backend.modules.llm_config import get_search_timeout, build_search_llm_config

logger = logging.getLogger("citation_analyzer.search_llm")

MAX_RETRIES = 3
RETRY_DELAY = 5
NO_RESULT_SENTINEL = "<检索失败或无引用>"

SCHOLAR_INFO_PROMPT = """你是一名极其谨慎的学者身份核验助手。你的任务是联网搜索并确认“论文作者”信息，绝不能把同名学者、期刊、会议、实验室主页或错误机构误判成目标作者。

【待确认作者】
- 作者姓名：{author_name}
- 关联论文标题：{paper_title}
- 额外上下文提示：{institution_hint}

【必须遵守的核验规则】
1. 必须先确认此人确实是论文《{paper_title}》的作者之一，再输出其个人信息。
2. 优先参考：作者主页、大学/研究机构官网、Google Scholar、DBLP、ORCID、Semantic Scholar、官方 Fellow/院士名单、企业研究院主页。
3. “institution” 必须是作者当前或最可信的任职机构，不能填写期刊、会议、出版社、论文发表 venue。
4. “country” 必须填写机构所在国家，使用中文国名；无法可靠确认时留空。
5. “title” 只填写较稳定且可验证的职位/职称，例如 Professor、Research Scientist、Assistant Professor、Principal Scientist、Senior Researcher；无法确认时留空。
6. “honors” 只写可核验的重要头衔或荣誉，例如 IEEE Fellow、ACM Fellow、中国科学院院士、图灵奖等；不确定不要猜。
7. “google_scholar_citations” 只有在搜索结果明确出现时才填写整数，否则填 0。
8. “is_renowned” 只有在有明确证据表明作者属于以下之一时才为 true：院士、重要学会 Fellow、国家级杰出人才、国际知名企业研究负责人/首席科学家、领域公认顶尖人物。
9. “renowned_level” 只能是 two_academy_member / fellow / other_academy / distinguished / industry_leader / none 之一。
10. 需要主动处理作者姓名的中英文差异、拼音、缩写、括号别名，例如 “Wei Zhang / 张伟 / W. Zhang / Zhang Wei（张伟）” 可能是同一人；只有在证据充分时才合并。
11. 如果作者身份存在明显歧义、找不到可信来源、或无法确认与该论文匹配，请保守处理：字段尽量留空，is_renowned=false，renowned_level=none，match_confidence 设为 low。

【输出要求】
只返回一个 JSON 对象，不要加 Markdown，不要加解释文字，字段必须完整，格式如下：
{{
  "name": "作者标准姓名",
  "name_en": "英文姓名，无法确认则空字符串",
  "name_zh": "中文姓名或母语姓名，无法确认则空字符串",
  "aliases": ["别名1", "别名2"],
  "institution": "当前或最可信任职机构",
  "country": "中文国家名",
  "title": "职位/职称",
  "honors": "重要头衔或荣誉，没有则空字符串",
  "google_scholar_citations": 0,
  "is_renowned": false,
  "renowned_level": "none",
  "match_confidence": "high|medium|low",
  "evidence_summary": "用中文简短说明你为何确认这是该作者，30-80字"
}}"""

CITING_AUTHOR_ROSTER_PROMPT = """你是一名极其谨慎的论文作者核验助手。请联网确认论文《{paper_title}》的完整作者名单，并尽量补全作者中英文别名与署名机构。

【论文信息】
- 标题：{paper_title}
- 年份：{paper_year}
- 已知候选链接：{candidate_links}
- 已知作者线索：{known_authors}

【核验要求】
1. 必须先确认这篇论文真实存在，且标题基本匹配。
2. 优先使用官方论文页、PDF、HTML、arXiv/OpenReview、出版社页面、Google Scholar、DBLP、Semantic Scholar 等可信来源。
3. 需要尽量返回完整作者顺序；如果只能确认部分作者，只返回已确认的部分，不能编造。
4. 必须意识到作者可能存在英文名、中文名、拼音、缩写、括号别名等形式，尽量合并为同一作者并同时返回。
5. institution 优先填写该作者在此论文署名时最可信的机构；无法确认则留空。

【输出要求】
只返回一个 JSON 对象，不要加 Markdown，不要加额外说明：
{{
  "paper_verified": true,
  "authors": [
    {{
      "name": "作者标准显示名",
      "name_en": "英文名，无法确认则空字符串",
      "name_zh": "中文名或母语姓名，无法确认则空字符串",
      "institution": "该作者与此论文最相关的机构",
      "match_confidence": "high|medium|low"
    }}
  ],
  "evidence_summary": "中文简述你如何确认作者名单与姓名别名，40-120字"
}}"""

CITATION_ASSESS_PROMPT = """你是一名细致的搜索专家和论文阅读专家。请你联网确认论文《{citing_title}》全文中，哪些地方引用了目标论文《{target_title}》。

【目标论文】
- 标题：{target_title}
- 作者：{target_authors}
- 年份：{target_year}

【施引论文】
- 标题：{citing_title}
- 作者：{citing_authors}
- 年份：{citing_year}
- 发表场所：{citing_venue}
- 候选链接：{candidate_links}
- 已知辅助线索：{citation_hints}
- 预抓取全文线索：{fulltext_hint}

【你的硬性要求】
1. 必须先确认施引论文真实存在，并尽量打开其官方页面、PDF、HTML、arXiv/OpenReview/期刊页面或其他可信全文页面。
2. 必须在施引论文中找到目标论文的真实引用证据，优先同时确认：
   - 参考文献中出现目标论文；
   - 正文中出现引用位置、引用句子或与目标论文对应的编号/作者-年份引用。
3. 不允许幻觉。若没有搜到可信全文，或无法确认正文真实引用，或只有模糊二手转述而无原文证据，请直接返回：
{no_result}
4. 如果找到了引用，必须给出“真实引用原句/原段”，并明确说明所在部分（例如 Introduction、Related Work、Method、Experiments、Appendix）。
5. 如果你无法给出至少 1 条真实 citation_locations（即真实原句 + 章节 + 用途），也必须返回 {no_result}，不能输出空列表冒充成功。
6. 引用情感只能是：positive（明确肯定/赞扬/采用并认可）、neutral（客观陈述/背景介绍/列举相关工作）、critical（明确指出不足/批评）、mixed（同时有肯定和批评）。
7. 引用质量评分 quality_score 只能是 1-5 的整数：
   - 1：仅非常表层提及，几乎没有实质讨论
   - 2：相关工作简述，有基本定位
   - 3：有较明确的用途说明或局部比较
   - 4：较深入地讨论方法、基准、差异或局部借鉴
   - 5：多处深入引用，实质用于方法、实验、基准或失败分析
8. citation_type 只能是：background_mention / related_work_brief / method_reference / experiment_comparison / multiple_deep
9. citation_depth 只能是：superficial / moderate / substantial
10. 如果系统已提供“预抓取全文线索”或“已知辅助线索”，可将其作为导航，但你仍必须亲自打开可信页面核验后才能下结论。
11. 目标论文和作者在正文/参考文献中可能以标题缩写、作者-年份格式、编号引用、英文名/中文名/缩写形式出现，必须主动考虑这些变体。

【成功时输出格式】
只返回一个 JSON 对象，不要加 Markdown，不要加额外说明：
{{
  "status": "ok",
  "reference_verified": true,
  "citation_locations": [
    {{
      "section": "章节名称",
      "context": "引用原句或紧邻原文，尽量保留原文，不要改写",
      "purpose": "该处引用目的的中文说明"
    }}
  ],
  "citation_type": "background_mention|related_work_brief|method_reference|experiment_comparison|multiple_deep",
  "citation_depth": "superficial|moderate|substantial",
  "citation_sentiment": "positive|neutral|critical|mixed",
  "quality_score": 1,
  "summary": "中文一句话总结该论文如何引用目标论文，30-80字",
  "detailed_analysis": "中文详细分析，120-220字，必须基于已核验到的引用证据",
  "evidence_summary": "中文简述你是如何确认引用存在的，40-120字"
}}
"""


class SearchLLMClient:
    """搜索型 LLM 客户端 — 用于需要联网搜索能力的分析任务"""

    def __init__(self):
        self.config = build_search_llm_config()
        self.client = OpenAI(
            base_url=self.config["base_url"],
            api_key=self.config["api_key"],
            timeout=get_search_timeout(),
            max_retries=0,
        )

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            parts = [SearchLLMClient._normalize_text(item) for item in value]
            return "\n".join([p for p in parts if p]).strip()
        if isinstance(value, dict):
            for key in ("text", "content", "output_text", "value"):
                if key in value:
                    text = SearchLLMClient._normalize_text(value.get(key))
                    if text:
                        return text
            return ""
        return str(value).strip()

    def _extract_text_and_sources(self, response: Any) -> Tuple[str, List[str]]:
        text = self._normalize_text(getattr(response, "output_text", ""))
        sources: List[str] = []

        try:
            payload = response.model_dump()
        except Exception:
            payload = {}

        for item in payload.get("output", []) or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message" and not text:
                text_parts = []
                for content_item in item.get("content", []) or []:
                    if isinstance(content_item, dict) and content_item.get("type") == "output_text":
                        text_parts.append(self._normalize_text(content_item.get("text")))
                text = "\n".join([p for p in text_parts if p]).strip()
            if item.get("type") == "web_search_call":
                action = item.get("action", {}) or {}
                for src in action.get("sources", []) or []:
                    if isinstance(src, dict):
                        url = (src.get("url") or "").strip()
                        if url and url not in sources:
                            sources.append(url)

        return text.strip(), sources

    @staticmethod
    def _dedupe_strings(values: List[str]) -> List[str]:
        result: List[str] = []
        for value in values:
            clean = (value or "").strip()
            if clean and clean not in result:
                result.append(clean)
        return result

    @staticmethod
    def _compact_text(value: str, limit: int = 1200) -> str:
        value = (value or "").strip()
        if len(value) <= limit:
            return value
        return value[:limit] + "...[truncated]"

    def _build_candidate_links(
        self,
        paper: Dict,
        extra_candidate_links: Optional[List[str]] = None,
    ) -> List[str]:
        candidate_links: List[str] = []
        for value in (
            paper.get("url"),
            paper.get("scholar_link"),
            paper.get("open_access_pdf"),
        ):
            link = (value or "").strip()
            if link and link not in candidate_links:
                candidate_links.append(link)

        doi = (paper.get("doi") or "").strip()
        if doi:
            doi_url = f"https://doi.org/{doi}"
            if doi_url not in candidate_links:
                candidate_links.append(doi_url)

        arxiv_id = (paper.get("arxiv_id") or "").strip()
        if arxiv_id:
            for arxiv_url in (
                f"https://arxiv.org/abs/{arxiv_id}",
                f"https://arxiv.org/pdf/{arxiv_id}",
                f"https://arxiv.org/html/{arxiv_id}",
            ):
                if arxiv_url not in candidate_links:
                    candidate_links.append(arxiv_url)

        for link in extra_candidate_links or []:
            link = (link or "").strip()
            if link and link not in candidate_links:
                candidate_links.append(link)
        return candidate_links

    @staticmethod
    def _format_citation_hints(citation_contexts: Optional[List[Dict]]) -> str:
        if not citation_contexts:
            return "无"
        lines = []
        for idx, ctx in enumerate(citation_contexts[:5], start=1):
            section = (ctx.get("location") or ctx.get("section") or "unknown").strip()
            method = (ctx.get("method") or "unknown").strip()
            context = SearchLLMClient._compact_text(ctx.get("context", ""), 260)
            lines.append(f"{idx}. section={section}; method={method}; context={context}")
        return "\n".join(lines) if lines else "无"

    def _request(self, input_text: str) -> Tuple[str, List[str]]:
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(
                    "[SearchLLM] sending request: model=%s, base_url=%s, attempt=%s/%s",
                    self.config["model"],
                    self.config["base_url"],
                    attempt + 1,
                    MAX_RETRIES,
                )
                response = self.client.responses.create(
                    model=self.config["model"],
                    tools=[{"type": "web_search"}],
                    include=["web_search_call.action.sources"],
                    input=input_text,
                )
                text, sources = self._extract_text_and_sources(response)
                if text:
                    logger.info(
                        f"[SearchLLM] responses.create success, text_len={len(text)}, sources={len(sources)}"
                    )
                    return text, sources
                try:
                    preview = json.dumps(response.model_dump(), ensure_ascii=False)[:400]
                except Exception:
                    preview = "<unavailable>"
                logger.warning(
                    f"[SearchLLM] empty response content (attempt {attempt + 1}/{MAX_RETRIES}), preview={preview}"
                )
            except Exception as exc:
                error_str = str(exc)
                retryable = any(code in error_str for code in ("429", "500", "502", "503", "504", "timeout"))
                if attempt < MAX_RETRIES - 1 and retryable:
                    wait_seconds = RETRY_DELAY * (attempt + 1)
                    logger.warning(
                        f"[SearchLLM] request failed, retry in {wait_seconds}s: {error_str[:200]}"
                    )
                    time.sleep(wait_seconds)
                    continue
                logger.error(f"[SearchLLM] request failed: {error_str[:300]}")
                return "", []
        return "", []

    @staticmethod
    def _strip_markdown_fence(raw: str) -> str:
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return raw.strip()

    def search_query(self, query: str) -> str:
        text, _ = self._request(query)
        return text

    def search_query_with_sources(self, query: str) -> Dict[str, Any]:
        text, sources = self._request(query)
        return {"text": text, "sources": sources}

    def search_json(self, query: str) -> Optional[Any]:
        raw = self.search_query(query)
        return self._parse_json_text(raw)

    def _parse_json_text(self, raw: str) -> Optional[Any]:
        if not raw:
            return None
        raw = self._strip_markdown_fence(raw)
        try:
            return json.loads(raw)
        except Exception:
            match = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except Exception:
                    pass
        return None

    @staticmethod
    def _normalize_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes", "y")
        return bool(value)

    @staticmethod
    def _normalize_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def search_scholar_info(self, author_name: str, paper_title: str,
                            institution_hint: str = "") -> Dict:
        prompt = SCHOLAR_INFO_PROMPT.format(
            author_name=author_name.strip(),
            paper_title=paper_title.strip(),
            institution_hint=institution_hint.strip() or "无",
        )
        result = self.search_query_with_sources(prompt)
        parsed = self._parse_json_text(result.get("text", ""))

        if isinstance(parsed, dict):
            parsed.setdefault("name", author_name)
            parsed.setdefault("name_en", "")
            parsed.setdefault("name_zh", "")
            parsed.setdefault("aliases", [])
            parsed.setdefault("institution", "")
            parsed.setdefault("country", "")
            parsed.setdefault("title", "")
            parsed.setdefault("honors", "")
            parsed.setdefault("google_scholar_citations", 0)
            parsed.setdefault("is_renowned", False)
            parsed.setdefault("renowned_level", "none")
            parsed.setdefault("match_confidence", "low")
            parsed.setdefault("evidence_summary", "")
            if not isinstance(parsed.get("aliases"), list):
                parsed["aliases"] = []
            parsed["google_scholar_citations"] = self._normalize_int(
                parsed.get("google_scholar_citations", 0), 0
            )
            parsed["is_renowned"] = self._normalize_bool(parsed.get("is_renowned", False))
            parsed["sources"] = result.get("sources", [])
            return parsed

        return {
            "name": author_name,
            "name_en": "",
            "name_zh": "",
            "aliases": [],
            "institution": "",
            "country": "",
            "title": "",
            "honors": "",
            "google_scholar_citations": 0,
            "is_renowned": False,
            "renowned_level": "none",
            "match_confidence": "low",
            "evidence_summary": "",
            "sources": result.get("sources", []),
        }

    def search_paper_authors(
        self,
        paper_title: str,
        paper_year: Any = "",
        candidate_links: Optional[List[str]] = None,
        known_authors: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        prompt = CITING_AUTHOR_ROSTER_PROMPT.format(
            paper_title=paper_title.strip(),
            paper_year=paper_year or "未知",
            candidate_links="; ".join(self._dedupe_strings(candidate_links or [])) or "无",
            known_authors=", ".join(
                [a.get("name", "").strip() for a in (known_authors or []) if a.get("name")]
            ) or "无",
        )
        result = self.search_query_with_sources(prompt)
        parsed = self._parse_json_text(result.get("text", ""))

        if isinstance(parsed, dict):
            parsed.setdefault("paper_verified", False)
            parsed.setdefault("authors", [])
            parsed.setdefault("evidence_summary", "")
            parsed["paper_verified"] = self._normalize_bool(parsed.get("paper_verified", False))
            cleaned_authors = []
            for author in parsed.get("authors", []):
                if not isinstance(author, dict):
                    continue
                cleaned_authors.append({
                    "name": (author.get("name") or "").strip(),
                    "name_en": (author.get("name_en") or "").strip(),
                    "name_zh": (author.get("name_zh") or "").strip(),
                    "institution": (author.get("institution") or "").strip(),
                    "match_confidence": (author.get("match_confidence") or "low").strip() or "low",
                })
            parsed["authors"] = [a for a in cleaned_authors if a.get("name")]
            parsed["sources"] = result.get("sources", [])
            return parsed

        return {
            "paper_verified": False,
            "authors": [],
            "evidence_summary": "",
            "sources": result.get("sources", []),
        }

    def search_author_country(self, author_name: str, paper_title: str) -> Dict:
        query = (
            f"论文《{paper_title}》的作者中包含「{author_name}」。"
            f"请联网核验其当前机构和所在国家，只返回JSON："
            f'{{"institution": "机构名", "country": "国家名"}}'
        )
        result = self.search_json(query)
        if isinstance(result, dict):
            return result
        return {"institution": "", "country": ""}

    def search_citation_assessment(
        self,
        target_paper: Dict,
        citing_paper: Dict,
        extra_candidate_links: Optional[List[str]] = None,
        citation_contexts: Optional[List[Dict]] = None,
        fulltext_hint: str = "",
    ) -> Optional[Dict]:
        target_authors = ", ".join(
            [a.get("name", "") for a in (target_paper.get("authors", []) or []) if a.get("name")]
        ) or "未知"
        citing_authors = ", ".join(
            [a.get("name", "") for a in (citing_paper.get("authors", []) or [])[:8] if a.get("name")]
        ) or "未知"

        candidate_links = self._build_candidate_links(
            citing_paper,
            extra_candidate_links=extra_candidate_links,
        )

        prompt = CITATION_ASSESS_PROMPT.format(
            target_title=target_paper.get("title", "").strip(),
            target_authors=target_authors,
            target_year=target_paper.get("year", "未知"),
            citing_title=citing_paper.get("title", "").strip(),
            citing_authors=citing_authors,
            citing_year=citing_paper.get("year", "未知"),
            citing_venue=citing_paper.get("venue", "") or "未知",
            candidate_links="; ".join(candidate_links) if candidate_links else "无",
            citation_hints=self._format_citation_hints(citation_contexts),
            fulltext_hint=self._compact_text(fulltext_hint or "无", 1000) or "无",
            no_result=NO_RESULT_SENTINEL,
        )

        raw_text, sources = self._request(prompt)
        if not raw_text:
            return None

        if NO_RESULT_SENTINEL in raw_text:
            return {
                "status": "not_found",
                "raw_text": raw_text.strip(),
                "sources": sources,
            }

        parsed = self._parse_json_text(raw_text)
        if not isinstance(parsed, dict):
            return None

        parsed["sources"] = sources
        parsed.setdefault("status", "ok")
        parsed.setdefault("reference_verified", False)
        parsed.setdefault("citation_locations", [])
        parsed.setdefault("citation_type", "unknown")
        parsed.setdefault("citation_depth", "unknown")
        parsed.setdefault("citation_sentiment", "unknown")
        parsed.setdefault("quality_score", 0)
        parsed.setdefault("summary", "")
        parsed.setdefault("detailed_analysis", "")
        parsed.setdefault("evidence_summary", "")
        parsed.setdefault("raw_text", raw_text.strip())
        parsed["reference_verified"] = self._normalize_bool(parsed.get("reference_verified", False))
        parsed["quality_score"] = self._normalize_int(parsed.get("quality_score", 0), 0)
        if not isinstance(parsed.get("citation_locations"), list):
            parsed["citation_locations"] = []
        parsed["citation_locations"] = [
            item for item in parsed["citation_locations"]
            if isinstance(item, dict) and (item.get("context") or item.get("section"))
        ]
        if not parsed["citation_locations"]:
            if parsed["reference_verified"] or parsed.get("evidence_summary") or sources:
                parsed["status"] = "partial"
                return parsed
            return {
                "status": "not_found",
                "raw_text": raw_text.strip(),
                "sources": sources,
            }
        return parsed
