# URL 校验行为说明

## 实际实现

`UniversalJobDescriptionExtractor.extract_url()` 不使用
`_validate_page_url()`，也不维护 `/feed/`、`/in/` 或 `/messaging/` 等路径
黑名单。实际规则是：从候选 URL 中提取岗位 ID；无法提取时返回 `None`。

支持的 ID 格式：

```text
/jobs/view/123456/
?currentJobId=123456
```

正则匹配不区分大小写，因此 `currentjobid`、`currentJobId` 等写法都可用。
成功后输出统一格式：

```text
https://www.linkedin.com/jobs/view/123456/
```

## 候选优先级

`extract_url()` 按以下顺序检查候选值：

1. 当前 `page.url`
2. `og:url` meta 标签
3. canonical link
4. 第一个包含 `/jobs/view/` 的页面链接

例如，搜索或推荐页面本身带有 `currentJobId` 时，可直接规范化为岗位 URL；
不带 ID 的 preferences、个人主页或 feed 页面则返回 `None`。

第 4 项是最后兜底，且只读取首个匹配链接。它在前三项都没有有效 ID 时
才会使用，因此不应被理解为对当前详情面板的绝对证明。边界行为由
`tests/test_extractor.py` 覆盖。

## 不包含的能力

当前模块没有以下实现：

- 路径黑名单或 `_validate_page_url()`
- 四级 URL fallback pipeline
- Trafilatura
- URL 校验成功后才允许正文提取的强耦合门控

正文提取和 URL 提取可独立成功或失败；调用方可在 URL 缺失时继续使用有效
正文进行评分。
