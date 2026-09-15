"""Non-interactive development smoke using the production browser and crawl path."""
import asyncio
import argparse
import contextlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from main import (AutomationBlocked, HumanActions, JobScraper, JOB_LIST_SCOPE,
                  JOB_CARD_SELECTOR, SMOKE_COUNTERS, _read_yaml_async)
from agent.extractor import (PAGE_BUTTON_SELECTOR, PAGINATION_SELECTOR,
                             UniversalJobDescriptionExtractor)


SmokeBlocked = AutomationBlocked


async def check_access(page):
    path = urlparse(page.url).path.lower()
    if any(part in path for part in ("/login", "/checkpoint", "/challenge", "/authwall")):
        raise SmokeBlocked(f"Login/security challenge: {page.url}")
    for selector in (
        'input[type="password"]', 'input[autocomplete="one-time-code"]',
        'iframe[src*="recaptcha"][src*="bframe"]',
        'iframe[src*="hcaptcha"]', '#captcha-internal',
    ):
        for element in await page.query_selector_all(selector):
            if await element.is_visible():
                raise SmokeBlocked(f"Visible authentication/challenge control: {selector}")
    text = (await page.inner_text("body")).lower()
    if any(message in text for message in (
        "verify you are human", "let’s do a quick security check",
        "let's do a quick security check", "enter the verification code",
        "安全验证", "安全检查", "输入验证码",
    )):
        raise SmokeBlocked("Authentication/security challenge text on page")


def search_url(value):
    parsed = urlparse(value)
    if (parsed.scheme != "https" or parsed.hostname not in ("www.linkedin.com", "linkedin.com")
            or parsed.path.rstrip("/") not in ("/jobs/search", "/jobs/search-results")):
        raise argparse.ArgumentTypeError("Expected an HTTPS LinkedIn jobs search URL")
    return value


async def capture_screenshot(page, path, report):
    """An optional rendering artifact must not invalidate completed click checks."""
    try:
        await page.screenshot(path=str(path), timeout=5000)
    except Exception as exc:
        warning = f"{path.name}: {exc}"
        report.setdefault("artifact_warnings", []).append(warning)
        print(f"SCREENSHOT_WARNING {warning}")


async def inspect_dom_probe(page, browser):
    cards = await browser.get_job_cards()
    target = await browser.get_next_page_target()
    job_ids = [str(card["job_id"]) for card in cards if card.get("job_id")]
    pagination = {"target": target, "status": "UNAVAILABLE"}
    try:
        pagination = await page.evaluate("""({container, button, target}) => {
            const list = document.querySelector(container);
            const number = element => {
                const match = (element.getAttribute('aria-label') || '').match(/^Page\\s+(\\d+)$/i);
                return match ? Number(match[1]) : null;
            };
            if (!list) return {target, status:'MISSING_CONTAINER'};
            const buttons = [...list.querySelectorAll(button)];
            const current = buttons.find(element => element.getAttribute('aria-current') === 'true');
            const currentNumber = current && number(current);
            const next = buttons.filter(element => number(element) > currentNumber &&
                !element.disabled && element.getAttribute('aria-disabled') !== 'true')
                .sort((left, right) => number(left) - number(right))[0];
            if (!next) return {target, status:'NO_FOLLOWING_PAGE', current_page:currentNumber || null};
            const rect = next.getBoundingClientRect();
            const expected = {page:number(next), x:rect.x + rect.width / 2, y:rect.y + rect.height / 2};
            const matches = !!target && Math.abs(target[0] - expected.x) < 1 &&
                Math.abs(target[1] - expected.y) < 1;
            return {target, status:matches ? 'MATCHED' : 'MISMATCH', current_page:currentNumber || null,
                expected_next:expected};
        }""", {"container": PAGINATION_SELECTOR, "button": PAGE_BUTTON_SELECTOR, "target": target})
    except Exception as exc:
        pagination = {"target": target, "status": "PROBE_ERROR", "reason": str(exc)}
    return {
        "cards": len(cards),
        "unique_job_ids": len(set(job_ids)),
        "duplicate_job_ids": len(job_ids) - len(set(job_ids)),
        "pagination": pagination,
    }


async def run_search(url, output_dir, job_list_mode="vision"):
    started = time.monotonic()
    config = await _read_yaml_async(ROOT / "config.yaml")
    config.setdefault("search", {})["max_pages"] = 1
    config.setdefault("extraction", {})["job_list_mode"] = job_list_mode
    scraper = JobScraper(config=config, resume_texts={}, base_dir=ROOT)
    report = {"search_url": url, "job_list_mode": job_list_mode, "max_pages": 1, "status": "RUNNING"}

    async def detail_observer(page, phase, context, text):
        await check_access(page)
        state = await page.evaluate("""selectors => {
            const visible = e => !!(e.getClientRects().length &&
                getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).display !== 'none');
            const attrs = e => Object.fromEntries([...e.attributes].filter(a => a.name !== 'class').map(a => [a.name,a.value]));
            return {page_title:document.title, url:location.href,
                selectors:selectors.map(selector => {
                    const elements = [...document.querySelectorAll(selector)];
                    return {selector,match_count:elements.length,elements:elements.map(e => ({
                        visible:visible(e),inner_text_length:(e.innerText||'').length,
                        text_preview:(e.innerText||'').slice(0,160),attributes:attrs(e)}))};
                }),
                detail_nodes:[...document.querySelectorAll('[data-sdui-component],[componentkey],[id]')]
                    .filter(e => !e.closest('[componentkey="SearchResultsMainContent"]') &&
                        /job.*(detail|description)|description/i.test(JSON.stringify(attrs(e))))
                    .map(e => ({attributes:attrs(e),visible:visible(e),
                        inner_text_length:(e.innerText||'').length,html:e.outerHTML}))};
        }""", list(UniversalJobDescriptionExtractor.DESCRIPTION_SELECTORS))
        evidence = {**context, "phase": phase, "detail_text_length": len(text) if text is not None else None,
                    **state}
        number = len(report.get("detail_evidence", [])) + 1
        filename = f"detail_{number:02d}_{context['target_job_id']}_{phase}.json"
        (output_dir / filename).write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        report.setdefault("detail_evidence", []).append(filename)
    try:
        page = await scraper.browser.start()
        behavior = config.get("behavior", {})
        scraper.actions = HumanActions(page, min_delay=float(behavior.get("delay_min", 2)),
                                       max_delay=float(behavior.get("delay_max", 6)))
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        await check_access(page)
        try:
            await page.wait_for_selector(f"{JOB_LIST_SCOPE} {JOB_CARD_SELECTOR}", timeout=20000)
        except Exception:
            await check_access(page)
            raise
        await check_access(page)
        report["dom_probe"] = await inspect_dom_probe(page, scraper.browser)
        await capture_screenshot(page, output_dir / "before.png", report)
        # Exercise the same Vision/resolver/actions/extractor as production.
        # Resume scoring is unrelated to this search-click smoke.
        await asyncio.wait_for(
            scraper._crawl_and_score(page, score_jobs=False, access_check=check_access,
                                     detail_observer=detail_observer),
            timeout=180,
        )
        await check_access(page)
        await capture_screenshot(page, output_dir / "after.png", report)
        if job_list_mode == "vision" and not scraper.crawl_stats["VISION_JOBS"]:
            raise RuntimeError("Vision returned no jobs; search click smoke was not exercised (see run.log)")
        if job_list_mode == "dom" and not report["dom_probe"]["cards"] and not scraper.crawl_stats["VISION_JOBS"]:
            raise RuntimeError("DOM and hybrid fallback returned no jobs; search click smoke was not exercised")
        report["status"] = "COMPLETED"
    except AutomationBlocked as exc:
        report.update(status="BLOCKED", reason=str(exc), requires_human=True)
    except Exception as exc:
        report.update(status="ERROR", reason=str(exc))
    finally:
        report["stats"] = getattr(scraper, "crawl_stats", dict.fromkeys(SMOKE_COUNTERS, 0))
        report["events"] = getattr(scraper, "click_events", [])
        try:
            await asyncio.wait_for(scraper.browser.close(), timeout=15)
        except Exception as exc:
            report.update(status="ERROR", reason=f"Browser close timed out: {exc}")
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        (output_dir / "result.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-url", required=True, type=search_url)
    parser.add_argument("--job-list-mode", choices=("vision", "dom"), default="vision")
    args = parser.parse_args()
    output_dir = ROOT / "output" / f"real_smoke_{datetime.now():%Y%m%d_%H%M%S}"
    output_dir.mkdir(parents=True)
    print(f"Search smoke artifacts: {output_dir}", flush=True)
    with (output_dir / "run.log").open("w", encoding="utf-8") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            report = asyncio.run(run_search(args.search_url, output_dir, args.job_list_mode))
    print(report["status"], report.get("reason", ""))
    for key, count in report["stats"].items():
        print(f"{key}={count}")
    return 0 if report["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
