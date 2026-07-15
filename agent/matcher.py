import json
from typing import Any, Dict

import httpx


class ResumeMatcher:
    """简历匹配器：调用本地文本模型对岗位进行打分。"""

    def __init__(self, resume_text: str, base_url: str, model: str) -> None:
        """初始化简历文本与模型配置。"""
        self.resume_text = (resume_text or "")[:1500]
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def score_job(
        self, title: str, description: str, company: str, salary: str
    ) -> Dict[str, Any]:
        """对单个岗位评分并返回 JSON 结果。"""
        jd = (description or "")[:1000]
        prompt = f"""你是一个岗位匹配评分器。请只输出 JSON，不要输出解释。

评分标准（1-10）：
- 8-10：高度匹配
- 6-7：基本匹配
- 4-5：勉强匹配
- 1-3：不匹配

评分维度：
1) 技术栈匹配度
2) 经验年限
3) 项目方向
4) 薪资范围

候选人简历摘要：
{self.resume_text}

岗位信息：
- 标题：{title}
- 公司：{company}
- 薪资：{salary}
- 描述：{jd}

仅返回以下 JSON：
{{"score": 7.5, "reason": "一句话理由"}}
"""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 200,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(f"{self.base_url}/api/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()
            content = data.get("response", "").strip()
            return self._parse_json(content)
        except httpx.HTTPError as exc:
            print(f"❌ 评分模型请求失败：{exc}")
            return {"score": 5, "reason": "解析失败"}
        except Exception as exc:
            print(f"❌ 评分模型处理异常：{exc}")
            return {"score": 5, "reason": "解析失败"}

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any]:
        """解析模型 JSON 输出。"""
        text = content
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            data = json.loads(text)
            score = float(data.get("score", 5))
            reason = str(data.get("reason", "解析失败")).strip() or "解析失败"
            return {"score": score, "reason": reason}
        except Exception:
            return {"score": 5, "reason": "解析失败"}
