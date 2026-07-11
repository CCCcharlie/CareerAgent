import asyncio
import math
import random

from playwright.async_api import Page


class HumanActions:
    """拟人化操作器：实现随机延迟与轨迹点击。"""

    def __init__(self, page: Page, min_delay: float, max_delay: float) -> None:
        """初始化页面对象与默认延迟区间。"""
        self.page = page
        self.min_delay = min_delay
        self.max_delay = max_delay

    async def random_delay(self, min_s: float = None, max_s: float = None) -> None:
        """随机等待指定范围秒数。"""
        low = self.min_delay if min_s is None else min_s
        high = self.max_delay if max_s is None else max_s
        await asyncio.sleep(random.uniform(low, high))

    async def human_click(self, x: float, y: float) -> None:
        """模拟人类鼠标轨迹并点击指定坐标。"""
        start_x = random.uniform(80, 450)
        start_y = random.uniform(80, 300)
        steps = random.randint(5, 12)
        ctrl_x = (start_x + x) / 2 + random.uniform(-120, 120)
        ctrl_y = (start_y + y) / 2 + random.uniform(-120, 120)

        await self.page.mouse.move(start_x, start_y)
        for i in range(1, steps + 1):
            t = i / steps
            bx, by = self._bezier_point(start_x, start_y, ctrl_x, ctrl_y, x, y, t)
            jitter_x = random.uniform(-3, 3)
            jitter_y = random.uniform(-3, 3)
            await self.page.mouse.move(bx + jitter_x, by + jitter_y)
            await asyncio.sleep(random.uniform(0.01, 0.04))

        await asyncio.sleep(random.uniform(0.3, 0.7))
        await self.page.mouse.click(x, y)
        await self.random_delay()

    @staticmethod
    def _bezier_point(
        x0: float, y0: float, x1: float, y1: float, x2: float, y2: float, t: float
    ) -> tuple[float, float]:
        """计算二次贝塞尔曲线上的点。"""
        one_minus_t = 1 - t
        x = one_minus_t * one_minus_t * x0 + 2 * one_minus_t * t * x1 + t * t * x2
        y = one_minus_t * one_minus_t * y0 + 2 * one_minus_t * t * y1 + t * t * y2
        if math.isnan(x) or math.isnan(y):
            return x2, y2
        return x, y
