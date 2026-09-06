# 岗位详情提取器

`agent/extractor.py` 中的 `UniversalJobDescriptionExtractor` 负责从当前
岗位详情面板提取岗位正文与可复用的 LinkedIn 岗位 URL。它由
`BrowserManager.get_job_detail_text()` 和 `BrowserManager.get_job_url()` 调用。

## URL 提取与规范化

URL 校验使用**正向 job ID 匹配**，而不是页面路径黑名单。只有候选值中
存在以下任一种特征时，`extract_url()` 才返回结果：

- `/jobs/view/<数字 ID>`
- `currentJobId=<数字 ID>`（大小写不敏感）

成功时一律规范化为：

```text
https://www.linkedin.com/jobs/view/<job ID>/
```

候选来源与优先级如下：

1. `page.url`
2. `meta[property="og:url"]`
3. `link[rel="canonical"]`
4. 第一个 `a[href*="/jobs/view/"]` 链接

候选不含 job ID 时返回 `None`。因此 `/jobs/preferences/`、`/in/`、
`/feed/`、`/messaging/` 等非岗位页面会自然被拒绝，无需维护黑名单。

最后一项只在前三项均无法提取 job ID 时才使用。它只读取第一个匹配链接；
若页面没有当前岗位 URL 而含有相似岗位链接，可能得到该首个链接的岗位 ID。
相关边界行为由 `tests/test_extractor.py` 覆盖。

## 正文提取

`extract_description()` 与 URL 提取相互独立，按以下 selector 顺序尝试：

1. `.jobs-description-content__text`
2. `#job-details`
3. `[data-test-id="job-details"]`
4. `.job-description__content`
5. `div.jobs-box__html-content`
6. `article`
7. `[role="main"]`

每个候选文本会移除空行、裁剪每行空白；只有清洗后长度不少于 100 个字符
才返回。所有 selector 都不匹配或文本不足时返回 `None`。

当前实现不依赖 Trafilatura、全页 `body.innerText`、启发式最大文本块或
额外的 URL 门控方法。

## 测试

使用 fake Page，不启动浏览器、不访问网络：

```powershell
& .\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_extractor.py -q
```
