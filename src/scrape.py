import argparse, asyncio, csv, datetime as dt, hashlib, json, os, re
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests, yaml
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

SIGNAL_PATTERNS = {
    "discount_candidate": re.compile(r"(?i)\b(?:discount|off|promo|coupon|code|deal|offer)\b.{0,80}|\b\d{1,2}\s?%\s?(?:off|discount)?\b"),
    "payout_candidate": re.compile(r"(?i)\b(?:payout|paid out|withdrawal|withdrawals)\b.{0,100}|\$?\s?\d+(?:[.,]\d+)?\s?(?:k|m|million|thousand)\b.{0,40}\b(?:payout|paid)\b"),
    "review_count_candidate": re.compile(r"(?i)\b\d{1,3}(?:[,\.\s]\d{3})*\+?\s+(?:reviews|review)\b"),
    "rating_candidate": re.compile(r"(?i)\b(?:rating|rated|score)\b.{0,40}\b\d(?:\.\d)?\s?\/\s?5\b|\b\d(?:\.\d)?\s?\/\s?5\b"),
    "asset_class_candidate": re.compile(r"(?i)\b(forex|futures|crypto|indices|stocks|metals|commodities|energy|fx|cfd|options)\b"),
    "vendor_candidate": re.compile(r"(?i)\b(kyc|aml|crm|payments?|payouts?|affiliate|tracking|analytics|risk|platform|metatrader|mt4|mt5|ctrader|ninjatrader|tradovate|tradingview|rithmic|dxtrade|match-trader|tradelocker|sumsub|veriff|persona|zendesk|intercom)\b"),
    "challenge_candidate": re.compile(r"(?i)\b(challenge|evaluation|funded account|profit target|drawdown|daily loss|max loss|payout split|consistency rule)\b"),
    "pricing_candidate": re.compile(r"(?i)(?:\$|€|£)\s?\d{1,5}(?:[.,]\d{2})?"),
    "methodology_candidate": re.compile(r"(?i)\b(methodology|transparent|verified|verification|review moderation|sponsored|affiliate disclosure|advertisement disclosure|ranking)\b.{0,120}"),
}

KNOWN_FIRM_HINTS = [
    "FundingPips","FundedNext","The5ers","Topstep","FTMO","E8 Markets","Apex Trader Funding",
    "BrightFunded","Alpha Capital Group","Fintokei","My Funded Futures","MyFundedFutures","Tradeify",
    "Blue Guardian","Hola Prime","Take Profit Trader","Maven Trading","City Traders Imperium",
    "Funded Trading Plus","Audacity Capital","Lux Trading Firm","Uprofit","Earn2Trade","TradeDay",
    "Bulenox","OneUp Trader","AquaFunded","Goat Funded Trader","For Traders","Darwinex Zero"
]


BLOCK_PATTERNS = [
    re.compile(r"(?i)Attention Required! \| Cloudflare"),
    re.compile(r"(?i)Sorry, you have been blocked"),
    re.compile(r"(?i)Please enable cookies"),
    re.compile(r"(?i)Performance & security by\s+Cloudflare"),
]
MAX_SIGNALS_PER_TYPE_PER_PAGE = 25
MAX_SIGNALS_PER_PAGE = 120
GAS_TEXT_LIMIT = int(os.environ.get("GAS_TEXT_LIMIT", "12000"))

def detect_block(status, title, text):
    blob = f"{title}\n{text}"[:5000]
    if str(status) in {"403", "429"} and any(p.search(blob) for p in BLOCK_PATTERNS):
        return "blocked_by_cloudflare"
    if any(p.search(blob) for p in BLOCK_PATTERNS):
        return "blocked_or_bot_protection"
    return ""

def clip_rows_for_gas(rows):
    clipped = []
    for row in rows:
        r = dict(row)
        if "text" in r and isinstance(r["text"], str) and len(r["text"]) > GAS_TEXT_LIMIT:
            r["text"] = r["text"][:GAS_TEXT_LIMIT] + "\n[TRUNCATED_FOR_GOOGLE_SHEETS_FULL_TEXT_IN_ARTIFACT]"
        if "surrounding_text" in r and isinstance(r["surrounding_text"], str) and len(r["surrounding_text"]) > 1500:
            r["surrounding_text"] = r["surrounding_text"][:1500]
        clipped.append(r)
    return clipped

RAW_HEADERS = [
    "run_id","captured_at","source_group","source_name","source_class","quality_estimate","influence_estimate",
    "data_type","confidence_level","url","status","title","text_length","screenshot_path","html_path","error","text"
]
SIGNAL_HEADERS = [
    "run_id","captured_at","source_group","source_name","source_class","quality_estimate","influence_estimate",
    "url","signal_type","signal_value","surrounding_text","data_type","confidence_level","extraction_method"
]
ERROR_HEADERS = RAW_HEADERS

def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def safe_filename(value):
    h = hashlib.sha1(value.encode()).hexdigest()[:10]
    parsed = urlparse(value)
    stem = (parsed.netloc + parsed.path).strip("/").replace("/", "_") or "page"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem)[:80]
    return f"{stem}_{h}"

def normalize_url(url):
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl().rstrip("/")

def same_domain(url, base_url):
    return urlparse(url).netloc.replace("www.", "") == urlparse(base_url).netloc.replace("www.", "")

def extract_text_and_links(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = soup.get_text("\n", strip=True)
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        label = a.get_text(" ", strip=True)
        if href.startswith("http"):
            links.append({"url": normalize_url(href), "label": label[:200]})
    return title, text, links

def surrounding(text, start, end, width=140):
    return re.sub(r"\s+", " ", text[max(0, start-width):min(len(text), end+width)]).strip()

def confidence_from_status(status, error, text_length, block_reason=""):
    if block_reason:
        return "low"
    if error:
        return "low"
    if str(status).startswith("2") and text_length > 500:
        return "high"
    if str(status).startswith("2") and text_length > 0:
        return "medium"
    if str(status) in {"403", "429"}:
        return "low"
    return "pending"

def source_meta(source):
    return {
        "source_group": source.get("group", ""),
        "source_name": source.get("name", ""),
        "source_class": source.get("source_class", ""),
        "quality_estimate": source.get("quality_estimate", "pending"),
        "influence_estimate": source.get("influence_estimate", "pending"),
    }

def extract_signals(text, source, url, run_id):
    rows, captured_at = [], now_iso()
    meta = source_meta(source)
    seen = set()

    # Do not extract “signals” from anti-bot / Cloudflare pages. They pollute the dataset.
    if detect_block("", "", text):
        return []

    def add_signal(signal_type, signal_value, surrounding_text):
        nonlocal rows
        val = re.sub(r"\s+", " ", signal_value).strip()
        key = (signal_type, val.lower(), url)
        if not val or key in seen or len(rows) >= MAX_SIGNALS_PER_PAGE:
            return
        seen.add(key)
        rows.append({
            "run_id": run_id,
            "captured_at": captured_at,
            **meta,
            "url": url,
            "signal_type": signal_type,
            "signal_value": val[:250],
            "surrounding_text": surrounding_text[:1000],
            "data_type": "parsed",
            "confidence_level": "medium",
            "extraction_method": "regex_text_pattern",
        })

    firm_hits = 0
    for firm in KNOWN_FIRM_HINTS:
        for m in re.finditer(re.escape(firm), text, flags=re.I):
            add_signal("firm_name_candidate", firm, surrounding(text, m.start(), m.end()))
            firm_hits += 1
            if firm_hits >= 40 or len(rows) >= MAX_SIGNALS_PER_PAGE:
                break
        if firm_hits >= 40 or len(rows) >= MAX_SIGNALS_PER_PAGE:
            break

    for typ, pattern in SIGNAL_PATTERNS.items():
        count = 0
        for m in pattern.finditer(text):
            if count >= MAX_SIGNALS_PER_TYPE_PER_PAGE or len(rows) >= MAX_SIGNALS_PER_PAGE:
                break
            val = re.sub(r"\s+", " ", m.group(0)).strip()
            add_signal(typ, val, surrounding(text, m.start(), m.end()))
            count += 1
    return rows

async def capture_page(context, source, url, out_dir, run_id):
    page = await context.new_page()
    captured_at, status, error, title, text = now_iso(), "", "", "", ""
    html_path, screenshot_path, links = "", "", []
    try:
        response = await page.goto(url, wait_until="networkidle", timeout=source.get("timeout_ms", 45000))
        status = str(response.status) if response else ""
        await page.wait_for_timeout(source.get("delay_ms", 1500))
        html = await page.content()
        title, text, links = extract_text_and_links(html, url)
        filebase = safe_filename(url)
        if source.get("save_html", True):
            html_path = str(out_dir / "html" / f"{filebase}.html")
            Path(html_path).parent.mkdir(parents=True, exist_ok=True)
            Path(html_path).write_text(html, encoding="utf-8", errors="ignore")
        if source.get("screenshot", True):
            screenshot_path = str(out_dir / "screenshots" / f"{filebase}.png")
            Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=screenshot_path, full_page=True)
    except Exception as exc:
        error = repr(exc)
    finally:
        await page.close()
    meta = source_meta(source)
    block_reason = detect_block(status, title, text)
    if block_reason and not error:
        error = block_reason
    conf = confidence_from_status(status, error, len(text), block_reason)
    raw = {
        "run_id": run_id,
        "captured_at": captured_at,
        **meta,
        "data_type": "blocked" if block_reason else "observed",
        "confidence_level": conf,
        "url": url,
        "status": status,
        "title": title,
        "text_length": len(text),
        "screenshot_path": screenshot_path,
        "html_path": html_path,
        "error": error,
        "text": text[:60000],
    }
    return raw, ([] if block_reason else (extract_signals(text, source, url, run_id) if text else [])), links

def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/sites.yml")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-pages-total", type=int, default=250)
    ap.add_argument("--max-pages-per-site", type=int, default=50)
    ap.add_argument("--send-to-gas", action="store_true")
    args = ap.parse_args()
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out or f"data/run_{run_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    settings, raw_rows, signal_rows, error_rows, total = cfg.get("settings", {}), [], [], [], 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 1600},
            user_agent="Mozilla/5.0 (compatible; PFM-Market-Research-Bot/0.2; public market research)"
        )
        for src in cfg["sources"]:
            if src.get("enabled") is False:
                continue
            source = {**settings, **src}
            visited = set()
            queue = [(normalize_url(u), 0) for u in source.get("start_urls", [])]
            site_pages = 0
            max_depth = source.get("max_depth", source.get("max_depth_default", 1))
            same_only = source.get("same_domain_only", source.get("same_domain_only_default", True))
            while queue and site_pages < args.max_pages_per_site and total < args.max_pages_total:
                url, depth = queue.pop(0)
                url = normalize_url(url)
                if url in visited:
                    continue
                visited.add(url)
                raw, signals, links = await capture_page(context, source, url, out_dir, run_id)
                raw_rows.append(raw)
                signal_rows.extend(signals)
                site_pages += 1
                total += 1
                if raw.get("error"):
                    error_rows.append(raw)
                if depth < max_depth:
                    for link in links:
                        link_url = normalize_url(link["url"])
                        if same_only and not same_domain(link_url, source["base_url"]):
                            continue
                        if link_url not in visited and len(queue) < args.max_pages_per_site * 3:
                            queue.append((link_url, depth + 1))
        await context.close()
        await browser.close()
    write_csv(out_dir / "raw_pages.csv", raw_rows, RAW_HEADERS)
    write_csv(out_dir / "extracted_signals.csv", signal_rows, SIGNAL_HEADERS)
    write_csv(out_dir / "errors.csv", error_rows, ERROR_HEADERS)
    summary = {
        "run_id": run_id,
        "captured_at": now_iso(),
        "raw_pages": len(raw_rows),
        "signals": len(signal_rows),
        "errors": len(error_rows),
        "out_dir": str(out_dir),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.send_to_gas:
        webhook = os.environ.get("GAS_WEBHOOK_URL")
        if not webhook:
            raise RuntimeError("GAS_WEBHOOK_URL missing")
        gas_payload = {
            "summary": summary,
            "raw_pages": clip_rows_for_gas(raw_rows),
            "extracted_signals": clip_rows_for_gas(signal_rows),
            "errors": clip_rows_for_gas(error_rows),
        }
        r = requests.post(webhook, json=gas_payload, timeout=60)
        print("GAS response:", r.status_code, r.text[:500])
    print(json.dumps(summary, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
