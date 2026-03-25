"""
LLM 引用质量评估模块 v4.0
使用外部LLM对论文引用质量进行评估
增强功能：
  - 网络错误重试策略（5次，间隔6秒）
  - 优化的引用定位提示词（先找参考文献编号，再定位正文）
  - 支持预定位的引用上下文
  - 提供通用文本调用接口，供全文抓取模块做HTML辅助解析
"""

import json
import logging
import re
import time
from typing import Any, Optional, Dict, List
from urllib import error as urllib_error
from urllib import request as urllib_request

from openai import OpenAI
from backend.modules.llm_config import build_llm_configs
from backend.modules.search_llm_client import SearchLLMClient

logger = logging.getLogger("citation_analyzer.llm_evaluator")

# LLM配置 - 优先使用用户指定的服务，备用OpenAI
LLM_CONFIGS = build_llm_configs()

# 重试配置
MAX_RETRIES = 5
RETRY_DELAY = 6  # 秒
RETRYABLE_STATUS_CODES = {402, 429, 500, 502, 503, 504}

# 单篇引用质量评估的Prompt（优化版 - 引导LLM先找参考文献编号再定位）
SINGLE_EVAL_PROMPT = """你是一位学术论文引用质量分析专家。请分析以下被引论文（citing paper）是如何引用目标论文（target paper）的。

## 目标论文（被分析引用质量的论文）
标题：{target_title}
摘要：{target_abstract}

## 被引论文（引用了目标论文的论文）
标题：{citing_title}
作者：{citing_authors}
年份：{citing_year}
发表场所：{citing_venue}

## 被引论文的内容
{citing_content}

{citation_hints}

## 分析步骤（请按以下步骤进行分析）
1. 首先，在参考文献/References部分查找目标论文的标题，确认其引用编号（如[23]）
2. 如果找到引用编号，在正文中搜索该编号出现的所有位置
3. 如果没有编号，查看引用格式是否为"作者姓氏(年份)"格式，并据此搜索
4. 对每个引用位置，分析其所在章节和引用目的
5. 综合所有引用位置，评估引用质量

请严格按照以下JSON格式输出（不要输出其他内容）：
```json
{{
    "citation_locations": [
        {{
            "section": "引用所在的章节名称（如Introduction, Related Work, Method, Experiments等）",
            "context": "引用的上下文原文（50-150字）",
            "purpose": "引用目的的简要说明"
        }}
    ],
    "citation_type": "引用类型，必须是以下之一：background_mention（背景提及）、related_work_brief（相关工作简要提及）、method_reference（方法重点参考）、experiment_comparison（实验对比/benchmark）、multiple_deep（多处深入引用）",
    "citation_depth": "引用深度，必须是以下之一：superficial（表面引用）、moderate（中等深度）、substantial（深入引用）",
    "citation_sentiment": "引用态度，必须是以下之一：positive（正面）、neutral（中性）、critical（批评）、mixed（混合）",
    "quality_score": "引用质量评分，1-5的整数，1=最低质量仅提及，5=最高质量深入使用",
    "summary": "一句话总结该论文如何引用目标论文（中文，30-80字）",
    "detailed_analysis": "详细分析该引用的质量和意义（中文，100-200字）"
}}
```"""

# 仅摘要评估的Prompt
ABSTRACT_ONLY_PROMPT = """你是一位学术论文引用质量分析专家。由于无法获取被引论文的全文，请基于摘要进行简要分析。

## 目标论文（被分析引用质量的论文）
标题：{target_title}

## 被引论文
标题：{citing_title}
作者：{citing_authors}
年份：{citing_year}
发表场所：{citing_venue}
摘要：{citing_abstract}

请严格按照以下JSON格式输出（不要输出其他内容）：
```json
{{
    "citation_locations": [],
    "citation_type": "unknown",
    "citation_depth": "unknown",
    "citation_sentiment": "unknown",
    "quality_score": 0,
    "summary": "基于摘要的一句话总结（中文，30-80字）",
    "detailed_analysis": "无法获取全文进行详细分析。基于摘要推测：...（中文，50-100字）",
    "fulltext_available": false
}}
```"""

# 综合评估的Prompt
COMPREHENSIVE_EVAL_PROMPT = """你是一位学术论文被引质量分析专家。请基于以下所有被引论文的单篇评估结果，生成一份综合评估报告。

## 目标论文
标题：{target_title}
摘要：{target_abstract}
总被引次数：{total_citations}
分析的被引论文数：{analyzed_count}

## 各被引论文的评估结果
{evaluations_summary}

请严格按照以下JSON格式输出综合评估（不要输出其他内容）：
```json
{{
    "overall_impact_score": "总体影响力评分，1-10的整数",
    "citation_quality_distribution": {{
        "background_mention": "背景提及的数量",
        "related_work_brief": "相关工作简要提及的数量",
        "method_reference": "方法重点参考的数量",
        "experiment_comparison": "实验对比的数量",
        "multiple_deep": "多处深入引用的数量",
        "unknown": "无法判断的数量"
    }},
    "depth_distribution": {{
        "superficial": "表面引用数量",
        "moderate": "中等深度数量",
        "substantial": "深入引用数量",
        "unknown": "无法判断数量"
    }},
    "sentiment_distribution": {{
        "positive": "正面引用数量",
        "neutral": "中性引用数量",
        "critical": "批评引用数量",
        "mixed": "混合态度数量",
        "unknown": "无法判断数量"
    }},
    "key_findings": [
        "关键发现1（中文）",
        "关键发现2（中文）",
        "关键发现3（中文）"
    ],
    "overall_summary": "综合评估总结（中文，200-400字，简短精确）",
    "influence_areas": ["该论文主要影响的研究领域1", "领域2"],
    "notable_citations": ["值得注意的高质量引用论文标题1", "标题2"]
}}
```"""


class LLMEvaluator:
    """LLM引用质量评估器 v4.0"""

    def __init__(self):
        self.client = None
        self.active_config = None
        self.model = None
        self.search_client = SearchLLMClient()
        self._init_client()

    def _normalize_text_content(self, content: Any) -> str:
        """兼容不同OpenAI兼容服务的content结构，统一提取为文本。"""
        if content is None:
            return ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                text = self._normalize_text_content(item)
                if text:
                    parts.append(text)
            return "\n".join(parts).strip()
        if isinstance(content, dict):
            for key in ("text", "content", "value", "output_text"):
                text = content.get(key)
                if isinstance(text, str) and text.strip():
                    return text.strip()
            return ""
        return str(content).strip()

    def _extract_response_text(self, response_data: Any) -> str:
        """从原始响应JSON中尽可能稳健地提取模型文本。"""
        if isinstance(response_data, str):
            return response_data.strip()
        if not isinstance(response_data, dict):
            return ""

        choices = response_data.get("choices") or []
        if choices:
            choice = choices[0] or {}
            message = choice.get("message") or {}
            content = self._normalize_text_content(message.get("content"))
            if content:
                return content

            delta = choice.get("delta") or {}
            content = self._normalize_text_content(delta.get("content"))
            if content:
                return content

            content = self._normalize_text_content(choice.get("text"))
            if content:
                return content

        content = self._normalize_text_content(response_data.get("output_text"))
        if content:
            return content

        outputs = response_data.get("output") or []
        parts = []
        for item in outputs:
            if not isinstance(item, dict):
                continue
            content = self._normalize_text_content(item.get("content"))
            if content:
                parts.append(content)
        return "\n".join(parts).strip()

    def _post_chat_completion(
        self,
        config: Dict[str, str],
        messages: List[Dict[str, str]],
        max_tokens: int,
        timeout: int,
        temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        """优先使用 Responses API，必要时回退到兼容 chat completions。"""
        try:
            client = OpenAI(
                base_url=config["base_url"],
                api_key=config["api_key"],
                timeout=timeout,
                max_retries=0,
            )
            input_payload = [
                {
                    "role": message["role"],
                    "content": [{"type": "input_text", "text": message["content"]}],
                }
                for message in messages
            ]
            payload: Dict[str, Any] = {
                "model": config["model"],
                "input": input_payload,
                "max_output_tokens": max_tokens,
            }
            if temperature is not None:
                payload["temperature"] = temperature
            logger.info(
                "[LLM] sending request via responses.create: model=%s, base_url=%s",
                config["model"],
                config["base_url"],
            )
            response = client.responses.create(**payload)
            return response.model_dump()
        except Exception as resp_exc:
            logger.debug(f"[LLM] Responses API failed, fallback to chat/completions: {resp_exc}")

        payload = {
            "model": config["model"],
            "messages": messages,
            "max_tokens": max_tokens
        }
        if temperature is not None:
            payload["temperature"] = temperature

        url = f"{config['base_url'].rstrip('/')}/chat/completions"
        request = urllib_request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config['api_key']}"
            },
            method="POST"
        )

        try:
            logger.info(
                "[LLM] sending request via chat/completions: model=%s, base_url=%s",
                config["model"],
                config["base_url"],
            )
            with urllib_request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {exc.code}: {error_body[:300]}") from exc
        except urllib_error.URLError as exc:
            raise RuntimeError(f"Connection error: {exc.reason}") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON response: {body[:300]}") from exc

    def _request_text(
        self,
        config: Dict[str, str],
        messages: List[Dict[str, str]],
        max_tokens: int,
        timeout: int,
        temperature: Optional[float] = None
    ) -> tuple[str, Dict[str, Any]]:
        response_data = self._post_chat_completion(
            config=config,
            messages=messages,
            max_tokens=max_tokens,
            timeout=timeout,
            temperature=temperature
        )
        return self._extract_response_text(response_data), response_data

    def _init_client(self):
        """初始化LLM客户端，尝试多个配置，验证返回内容非空"""
        for config in LLM_CONFIGS:
            if not config.get("base_url") or not config.get("api_key"):
                continue
            try:
                content, response_data = self._request_text(
                    config=config,
                    messages=[{"role": "user", "content": "Please respond with exactly: OK"}],
                    max_tokens=20,
                    timeout=30
                )

                if content:
                    self.client = config
                    self.active_config = config
                    self.model = config["model"]
                    logger.info(f"[LLM] 使用配置: {config['name']} ({config['base_url']}), 测试响应: {content[:20]}")
                    return

                preview = json.dumps(response_data, ensure_ascii=False)[:200]
                logger.warning(f"[LLM] 配置 {config['name']} 返回空内容，原始响应: {preview}")
            except Exception as e:
                logger.warning(f"[LLM] 配置 {config['name']} 连接失败: {e}")

        logger.error("[LLM] 所有LLM配置均连接失败!")

    def call_text(
        self,
        prompt: str,
        system_prompt: str = "You are a precise research assistant.",
        max_tokens: int = 1000,
        temperature: float = 0.2,
        timeout: int = 120
    ) -> Optional[str]:
        """通用文本调用接口，供其他模块复用当前LLM配置。"""
        if not self.active_config:
            logger.error("[LLM] 客户端未初始化")
            return None

        for attempt in range(MAX_RETRIES):
            try:
                content, response_data = self._request_text(
                    config=self.active_config,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=timeout
                )

                if content:
                    logger.info(f"[LLM] 调用成功, 响应长度: {len(content)} 字符")
                    return content

                preview = json.dumps(response_data, ensure_ascii=False)[:200]
                logger.warning(
                    f"[LLM] 调用返回空内容 (尝试 {attempt+1}/{MAX_RETRIES})，原始响应: {preview}"
                )

            except Exception as e:
                error_str = str(e)
                is_retryable = False
                for code in RETRYABLE_STATUS_CODES:
                    if str(code) in error_str:
                        is_retryable = True
                        break
                if "timeout" in error_str.lower() or "connection" in error_str.lower():
                    is_retryable = True

                if is_retryable and attempt < MAX_RETRIES - 1:
                    logger.warning(
                        f"[LLM] 网络错误 (尝试 {attempt+1}/{MAX_RETRIES}): {error_str[:100]}. 等待{RETRY_DELAY}秒后重试..."
                    )
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(f"[LLM] 调用失败 (尝试 {attempt+1}/{MAX_RETRIES}): {error_str[:200]}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)

        return None

    def _call_llm(self, prompt: str) -> Optional[str]:
        """
        调用LLM并返回响应文本
        网络错误重试策略：5次，间隔6秒
        """
        return self.call_text(
            prompt=prompt,
            system_prompt="你是一位专业的学术论文引用质量分析专家。请严格按照要求的JSON格式输出，不要输出其他内容。",
            max_tokens=2000,
            temperature=0.3,
            timeout=120
        )

    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """从LLM响应中解析JSON"""
        if not response:
            return None

        # 尝试直接解析
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # 尝试从markdown代码块中提取
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试找到第一个{到最后一个}
        start = response.find('{')
        end = response.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(response[start:end+1])
            except json.JSONDecodeError:
                pass

        logger.error(f"[LLM] 无法解析JSON响应: {response[:200]}...")
        return None

    def _build_search_result(self, search_eval: Dict, title: str, citing_paper: Dict,
                             content_type: str) -> Dict:
        return {
            "citing_title": title,
            "citing_year": citing_paper.get("year"),
            "content_type": content_type,
            "fulltext_available": content_type in ("html", "pdf"),
            "citation_locations": search_eval.get("citation_locations", []) or [],
            "citation_type": search_eval.get("citation_type", "unknown"),
            "citation_depth": search_eval.get("citation_depth", "unknown"),
            "citation_sentiment": search_eval.get("citation_sentiment", "unknown"),
            "quality_score": int(search_eval.get("quality_score", 0) or 0),
            "summary": search_eval.get("summary", ""),
            "detailed_analysis": search_eval.get("detailed_analysis", ""),
            "reference_verified": bool(search_eval.get("reference_verified", False)),
            "evidence_summary": search_eval.get("evidence_summary", ""),
            "evidence_sources": search_eval.get("sources", []),
            "evaluation_method": search_eval.get("evaluation_method", "web_search"),
        }

    def evaluate_single_citation(self, target_paper: Dict, citing_paper: Dict,
                                  citing_content: str, content_type: str,
                                  citation_contexts: List[Dict] = None,
                                  extra_candidate_links: List[str] = None,
                                  fulltext_hint: str = "",
                                  allow_search: bool = True,
                                  search_only: bool = False) -> Dict:
        """
        评估单篇被引论文的引用质量
        
        Args:
            target_paper: 目标论文信息
            citing_paper: 被引论文信息
            citing_content: 被引论文内容（全文或标注后的内容）
            content_type: 内容类型 (html/pdf/abstract_only)
            citation_contexts: 预定位的引用上下文列表
        """
        title = citing_paper.get("title", "Unknown")
        logger.info(f"[LLM] 评估引用质量: {title[:60]}...")

        authors = ", ".join([a.get("name", "") for a in citing_paper.get("authors", [])[:5]])

        search_eval = None
        if allow_search:
            # 优先使用配置文件中的搜索型 LLM + web_search 联网核验引用位置与情感。
            # 若未检索到可信引用证据或解析失败，则回退到全文/摘要评估工作流。
            try:
                search_eval = self.search_client.search_citation_assessment(
                    target_paper,
                    citing_paper,
                    extra_candidate_links=extra_candidate_links,
                    citation_contexts=citation_contexts,
                    fulltext_hint=fulltext_hint,
                )
            except Exception as exc:
                logger.warning(f"[LLM] 联网引用核验异常: {exc}")
                search_eval = None

            if isinstance(search_eval, dict) and search_eval.get("status") == "ok":
                logger.info(
                    f"[LLM] 联网引用核验成功: {title[:60]}..., sources={len(search_eval.get('sources', []))}"
                )
                return self._build_search_result(search_eval, title, citing_paper, content_type)

            if search_only:
                return search_eval or {
                    "status": "not_found",
                    "raw_text": "",
                    "sources": [],
                }

            if isinstance(search_eval, dict) and search_eval.get("status") == "partial":
                logger.info(
                    f"[LLM] 联网引用核验拿到部分证据但定位不足，回退全文评估: {title[:60]}..."
                )
            elif isinstance(search_eval, dict) and search_eval.get("status") == "not_found":
                logger.info(f"[LLM] 联网引用核验未找到可靠证据，回退全文评估: {title[:60]}...")
            elif search_eval is None:
                logger.info(f"[LLM] 联网引用核验失败，回退全文评估: {title[:60]}...")
        elif search_only:
            return {"status": "not_found", "raw_text": "", "sources": []}

        if content_type in ("html", "pdf"):
            # 全文评估 - 截断过长的内容
            content = citing_content
            if len(content) > 15000:
                content = content[:8000] + "\n\n...[内容截断]...\n\n" + content[-7000:]

            # 构建引用提示
            citation_hints = ""
            if citation_contexts:
                hints = ["## 预定位的引用位置（供参考）"]
                for i, ctx in enumerate(citation_contexts, 1):
                    hints.append(f"### 引用位置 {i}")
                    hints.append(f"- 定位方法: {ctx.get('method', 'unknown')}")
                    hints.append(f"- 所在章节: {ctx.get('location', 'unknown')}")
                    hints.append(f"- 上下文: {ctx.get('context', '')[:300]}")
                citation_hints = "\n".join(hints)

            prompt = SINGLE_EVAL_PROMPT.format(
                target_title=target_paper.get("title", ""),
                target_abstract=target_paper.get("abstract", "")[:500],
                citing_title=title,
                citing_authors=authors,
                citing_year=citing_paper.get("year", "N/A"),
                citing_venue=citing_paper.get("venue", "N/A"),
                citing_content=content,
                citation_hints=citation_hints
            )
        else:
            # 仅摘要评估
            prompt = ABSTRACT_ONLY_PROMPT.format(
                target_title=target_paper.get("title", ""),
                citing_title=title,
                citing_authors=authors,
                citing_year=citing_paper.get("year", "N/A"),
                citing_venue=citing_paper.get("venue", "N/A"),
                citing_abstract=citing_paper.get("abstract", "无摘要")[:500]
            )

        response = self._call_llm(prompt)
        result = self._parse_json_response(response)

        if result:
            result["citing_title"] = title
            result["citing_year"] = citing_paper.get("year")
            result["content_type"] = content_type
            result["fulltext_available"] = content_type in ("html", "pdf")
            result.setdefault("reference_verified", bool(result.get("citation_locations")))
            result.setdefault("evidence_summary", "")
            result.setdefault("evidence_sources", [])
            result.setdefault("evaluation_method", "fulltext_fallback")
            return result

        # 返回默认结果
        return {
            "citing_title": title,
            "citing_year": citing_paper.get("year"),
            "content_type": content_type,
            "fulltext_available": content_type in ("html", "pdf"),
            "citation_type": "unknown",
            "citation_depth": "unknown",
            "citation_sentiment": "unknown",
            "quality_score": 0,
            "summary": "LLM评估失败，无法生成分析结果",
            "detailed_analysis": "LLM调用失败或响应解析失败",
            "citation_locations": [],
            "reference_verified": False,
            "evidence_summary": "",
            "evidence_sources": [],
            "evaluation_method": "failed"
        }

    def generate_comprehensive_evaluation(self, target_paper: Dict,
                                           evaluations: List[Dict]) -> Dict:
        """生成综合评估报告"""
        logger.info(f"[LLM] 生成综合评估，共 {len(evaluations)} 篇被引论文")

        eval_lines = []
        for i, ev in enumerate(evaluations):
            line = (f"[{i+1}] {ev.get('citing_title', 'N/A')} ({ev.get('citing_year', 'N/A')})\n"
                   f"    类型: {ev.get('citation_type', 'unknown')}, "
                   f"深度: {ev.get('citation_depth', 'unknown')}, "
                   f"态度: {ev.get('citation_sentiment', 'unknown')}, "
                   f"评分: {ev.get('quality_score', 0)}/5\n"
                   f"    摘要: {ev.get('summary', 'N/A')}")
            eval_lines.append(line)

        evaluations_summary = "\n\n".join(eval_lines)

        prompt = COMPREHENSIVE_EVAL_PROMPT.format(
            target_title=target_paper.get("title", ""),
            target_abstract=target_paper.get("abstract", "")[:500],
            total_citations=target_paper.get("citation_count", 0),
            analyzed_count=len(evaluations),
            evaluations_summary=evaluations_summary
        )

        response = self._call_llm(prompt)
        result = self._parse_json_response(response)

        if result:
            return result

        return {
            "overall_impact_score": 0,
            "citation_quality_distribution": {},
            "depth_distribution": {},
            "sentiment_distribution": {},
            "key_findings": ["综合评估生成失败"],
            "overall_summary": "LLM综合评估调用失败",
            "influence_areas": [],
            "notable_citations": []
        }


def run_llm_smoke_test(prompt: str = "hello") -> Dict[str, Any]:
    """按当前LLM配置做最小调用测试。"""
    evaluator = LLMEvaluator()
    if not evaluator.active_config:
        return {
            "ok": False,
            "error": "LLM客户端初始化失败",
            "response": ""
        }

    try:
        content, response_data = evaluator._request_text(
            config=evaluator.active_config,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
            timeout=60
        )
    except Exception as exc:
        return {
            "ok": False,
            "config_name": evaluator.active_config.get("name"),
            "base_url": evaluator.active_config.get("base_url"),
            "model": evaluator.model,
            "error": str(exc),
            "response": ""
        }

    return {
        "ok": bool(content),
        "config_name": evaluator.active_config.get("name"),
        "base_url": evaluator.active_config.get("base_url"),
        "model": evaluator.model,
        "prompt": prompt,
        "response": content,
        "raw_response_preview": json.dumps(response_data, ensure_ascii=False)[:500]
    }


def test_llm_evaluator():
    """测试LLM评估模块"""
    logging.basicConfig(level=logging.INFO)
    evaluator = LLMEvaluator()

    if not evaluator.client:
        print("LLM客户端初始化失败!")
        return

    print("=" * 60)
    print("测试: LLM引用质量评估（带引用定位提示）")

    target = {
        "title": "Earth-Agent: Unlocking the Full Landscape of Earth Observation with Agents",
        "abstract": "Earth observation (EO) is critical for understanding environmental changes."
    }

    citing = {
        "title": "OpenEarthAgent: A Unified Framework for Tool-Augmented Geospatial Agents",
        "authors": [{"name": "Test Author"}],
        "year": 2025,
        "venue": "arXiv"
    }

    test_content = """
    Introduction
    Recent advances in AI agents have shown great potential in Earth observation tasks. 
    Earth-Agent [1] proposed a comprehensive framework for EO with agents.
    
    Related Work
    Earth-Agent [1] demonstrated that agents can effectively handle diverse EO tasks.
    
    References
    [1] Earth-Agent: Unlocking the Full Landscape of Earth Observation with Agents
    """

    # 带预定位引用上下文
    citation_contexts = [
        {"location": "Introduction", "context": "Earth-Agent [1] proposed a comprehensive framework", "method": "reference_number_[1]"},
        {"location": "Related Work", "context": "Earth-Agent [1] demonstrated that agents can effectively", "method": "reference_number_[1]"}
    ]

    result = evaluator.evaluate_single_citation(target, citing, test_content, "html", citation_contexts)
    print(f"  引用类型: {result.get('citation_type')}")
    print(f"  引用深度: {result.get('citation_depth')}")
    print(f"  质量评分: {result.get('quality_score')}/5")
    print(f"  总结: {result.get('summary')}")

    print("\n测试完成!")


if __name__ == "__main__":
    test_llm_evaluator()
