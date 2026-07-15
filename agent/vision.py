import asyncio
import base64
import io
import json
from typing import Any, Dict

import httpx
from PIL import Image

VISION_PROMPT = """你是招聘页面视觉结构解析器。你必须只输出 JSON，不要输出解释。

任务：
1) 识别页面类型，page_type 只能是: "job_list" | "job_detail" | "other"。
2) 如果是岗位列表页(job_list)，提取 jobs 数组，每个岗位包含：
   - title: 字符串
   - company: 字符串
   - salary: 字符串
   - location: 字符串
   - tags: 字符串数组
   - click_x: 数字（岗位卡片可点击中心点像素x）
   - click_y: 数字（岗位卡片可点击中心点像素y）
3) 如果是岗位列表页，还需提取翻页按钮信息：
   - has_next_page: 布尔
   - next_page_x: 数字或 null
   - next_page_y: 数字或 null
4) 如果是岗位详情页(job_detail)，提取：
   - title: 字符串
   - description: 字符串

输出 JSON 示例（列表页）：
{
  "page_type": "job_list",
  "jobs": [
    {
      "title": "...",
      "company": "...",
      "salary": "...",
      "location": "...",
      "tags": ["..."],
      "click_x": 800,
      "click_y": 350
    }
  ],
  "has_next_page": true,
  "next_page_x": 1220,
  "next_page_y": 860
}

输出 JSON 示例（详情页）：
{
  "page_type": "job_detail",
  "title": "...",
  "description": "..."
}
"""


class LocalVisionAPI:
    """本地视觉模型调用器：通过 Ollama 分析页面截图并提取结构化信息。"""

    def __init__(self, base_url: str, model: str) -> None:
        """初始化视觉模型调用配置。"""
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def analyze_page(self, image_bytes: bytes, task: str) -> Dict[str, Any]:
        """分析页面截图并返回解析后的 JSON 字典。"""
        try:
            compressed = await asyncio.to_thread(self._compress_image, image_bytes)
            encoded = base64.b64encode(compressed).decode("utf-8")
            payload = {
                "model": self.model,
                "prompt": f"{VISION_PROMPT}\n\n当前任务：{task}",
                "images": [encoded],
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 1024,
                },
            }
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(f"{self.base_url}/api/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()
            content = data.get("response", "")
            return self._parse_json(content)
        except httpx.HTTPError as exc:
            print(f"❌ 视觉模型请求失败：{exc}")
            return {"page_type": "unknown", "raw": str(exc)}
        except Exception as exc:
            print(f"❌ 视觉模型处理异常：{exc}")
            return {"page_type": "unknown", "raw": str(exc)}

    @staticmethod
    def _compress_image(image_bytes: bytes) -> bytes:
        """压缩截图：宽度超过1024时等比缩放，JPEG质量70。"""
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        if image.width > 1024:
            ratio = 1024 / float(image.width)
            new_size = (1024, int(image.height * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=70, optimize=True)
        return out.getvalue()

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any]:
        """解析模型返回内容，兼容 markdown 代码块和纯 JSON。"""
        text = content.strip()
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
            return json.loads(text)
        except Exception:
            return {"page_type": "unknown", "raw": content}
