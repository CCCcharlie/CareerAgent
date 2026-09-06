import json
import re
from typing import Any, Dict

import httpx


class ResumeMatcher:
    """简历匹配器：单次推理完成简历选择和多维度结构化打分。"""

    def __init__(
        self,
        resume_texts: Dict[str, str],
        base_url: str,
        model: str,
    ) -> None:
        """初始化多份简历文本与模型配置。

        Args:
            resume_texts: 字典，键为简历标识（如 "dev", "ba_pm"），值为简历文本
            base_url: Ollama API 地址
            model: 使用的文本模型名称
        """
        self.resume_texts = {k: (v or "")[:2000] for k, v in resume_texts.items()}
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def score_job(
        self, title: str, description: str, company: str, salary: str
    ) -> Dict[str, Any]:
        """对单个岗位进行简历选择 + 多维度评分（单次 API 调用）。

        工作流程：
        1. 将所有简历以 XML 格式注入 Prompt
        2. AI 自动选择最合适的简历
        3. 基于选中的简历进行五维度评分

        评分维度包括：
        1. 技术/技能匹配度（权重 30%）
        2. 经验年限匹配度（权重 20%）
        3. 项目/行业背景匹配度（权重 25%）
        4. 薪资期望匹配度（权重 15%）
        5. 综合发展潜力（权重 10%）
        """
        jd = (description or "")[:1500]

        # 构建简历 XML 块
        resumes_xml = "\n".join([
            f'<resume id="{key}">\n{text}\n</resume>'
            for key, text in self.resume_texts.items()
        ])

        prompt = f"""你是一个专业的岗位匹配评分器。请严格按照以下 JSON 格式输出，不要输出任何额外的解释文本。

## 任务说明
1. **阅读所有简历**：下方提供了多份候选人简历，每份用 `<resume id="xxx">` 标签包裹
2. **分析岗位需求**：根据 JD 的技术栈、职责方向、经验要求等
3. **选择最佳简历**：判断哪份简历最适合该岗位，记录其 id
4. **基于选中简历打分**：严格使用选中的简历内容进行五维度评分

## 评分标准（总分 1-10）
- 9-10：极度匹配，强烈推荐
- 7-8：高度匹配，推荐
- 5-6：基本匹配，可考虑
- 3-4：勉强匹配，需谨慎
- 1-2：不匹配，不建议

## 五维度评分细则

请从以下 5 个维度分别评分（1-10分），然后计算加权总分：

1. **技术/技能匹配度**（权重 30%）
   - 核心技术栈是否吻合
   - 工具/框架熟悉程度
   - 专业技能覆盖度

2. **经验年限匹配度**（权重 20%）
   - 工作年限是否符合岗位要求
   - 相关领域经验深度
   - 职业发展阶段匹配

3. **项目/行业背景匹配度**（权重 25%）
   - 过往项目与岗位职责的相关性
   - 行业背景是否一致
   - 业务理解能力

4. **薪资期望匹配度**（权重 15%）
   - 候选人期望与岗位预算的匹配
   - 性价比评估

5. **综合发展潜力**（权重 10%）
   - 学习能力和成长性
   - 文化契合度
   - 长期价值

## 输出格式

{{
  "selected_resume": "dev_resume",
  "dimension_scores": {{
    "technical_skills": 8.5,
    "experience": 7.0,
    "project_background": 9.0,
    "salary_match": 8.0,
    "growth_potential": 7.5
  }},
  "weighted_score": 8.15,
  "analysis": "1. 简历选择理由：JD要求Python/Django，dev_resume有5年相关经验...；2. 技术匹配：...；3. 经验匹配：...；4. 项目背景：...；5. 薪资：...；6. 潜力：...",
  "score": 8.15,
  "reason": "技术栈高度吻合，项目经验丰富，薪资期望合理，具备较强学习能力"
}}

## 可用简历

{resumes_xml}

## 岗位信息
- 标题：{title}
- 公司：{company}
- 薪资：{salary}
- 描述：{jd}

请输出 JSON："""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": "json",
            "think": False,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 800,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(f"{self.base_url}/api/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()

            content = str(data.get("response", "")).strip()
            if not content:
                content = str(data.get("thinking", "")).strip()

            return self._parse_json(content)
        except httpx.HTTPError as exc:
            print(f"❌ 评分模型请求失败：{exc}")
            return {"score": 5, "reason": "请求失败"}
        except Exception as exc:
            print(f"❌ 评分模型处理异常：{exc}")
            return {"score": 5, "reason": "处理异常"}

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any]:
        """解析模型 JSON 输出（增强版：提取选中简历 + 多维度分数）。"""
        text = (content or "").strip()
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()

        if not text:
            return {"score": 5, "reason": "解析失败"}

        parsed: Dict[str, Any]
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            json_text = ResumeMatcher._extract_first_json_object(text)
            if not json_text:
                score_match = re.search(
                    r'"?score"?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)',
                    text,
                    flags=re.IGNORECASE,
                )
                reason_match = re.search(
                    r'"?reason"?\s*[:=]\s*"?(.*?)"?\s*(?:[,}\n]|$)',
                    text,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                if score_match:
                    fallback_reason = (
                        reason_match.group(1).strip()
                        if reason_match
                        else "模型输出非标准JSON，已兜底提取"
                    )
                    parsed = {
                        "score": float(score_match.group(1)),
                        "reason": fallback_reason,
                    }
                else:
                    print(f"⚠️ 评分结果解析失败，原始输出片段：{text[:300]}")
                    return {"score": 5, "reason": "解析失败"}
            else:
                try:
                    parsed = json.loads(json_text)
                except json.JSONDecodeError:
                    print(f"⚠️ 评分结果解析失败，原始输出片段：{text[:300]}")
                    return {"score": 5, "reason": "解析失败"}
        except Exception as exc:
            print(f"❌ JSON解析具体报错: {exc}\n原始内容: {text[:100]}")
            return {"score": 5, "reason": "解析失败"}

        if not isinstance(parsed, dict):
            print(f"⚠️ 评分结果不是 JSON 对象，原始输出片段：{text[:300]}")
            return {"score": 5, "reason": "解析失败"}

        selected_resume = str(parsed.get("selected_resume", "unknown"))
        weighted_score = parsed.get("weighted_score")
        score_source = weighted_score if weighted_score is not None else parsed.get("score", 5)
        try:
            score = float(score_source)
        except (TypeError, ValueError):
            score = 5.0
        score = max(1.0, min(10.0, score))
        reason = str(parsed.get("reason", "解析失败")).strip() or "解析失败"
        dimension_scores = parsed.get("dimension_scores", {})
        analysis = parsed.get("analysis", "")

        return {
            "score": score,
            "reason": reason,
            "selected_resume": selected_resume,
            "dimension_scores": dimension_scores if isinstance(dimension_scores, dict) else {},
            "analysis": str(analysis),
        }

    @staticmethod
    def _extract_first_json_object(text: str) -> str:
        """从文本中提取首个完整 JSON 对象。"""
        start = text.find("{")
        if start < 0:
            return ""
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        return ""
