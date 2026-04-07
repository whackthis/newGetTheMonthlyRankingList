import csv
import random
import re
import time
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

RANKING_HTML_FILE = Path("books_source-12.html")
PRODUCT_BASE_URL = "https://www.books.com.tw/products/"
OUTPUT_CSV = "books_info-12.csv"

SLEEP_MIN = 58.0
SLEEP_MAX = 60.0
PAGE_TIMEOUT_MS = 90000
HEADLESS = False  # 博客來常擋 headless，預設改成 False

PRODUCT_ID_RE = re.compile(r"/products/(\d{10})")
ISBN_RE = re.compile(r"\b(?:97[89]\d{10}|\d{10})\b")
DATE_RE = re.compile(r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})")



def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()



def normalize_date(text: str) -> str:
    text = normalize_space(text)
    match = DATE_RE.search(text)
    if not match:
        return ""
    y, m, d = re.split(r"[/-]", match.group(1))
    return f"{int(y):04d}/{int(m):02d}/{int(d):02d}"



def normalize_isbn(text: str) -> str:
    text = normalize_space(text)
    match = ISBN_RE.search(text)
    return match.group(0) if match else ""



def clean_product_url(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme or "https"
    netloc = parts.netloc or "www.books.com.tw"
    return urlunsplit((scheme, netloc, parts.path, "", ""))



def build_product_url(product_id: str) -> str:
    return f"{PRODUCT_BASE_URL}{product_id}"



def parse_ranking_items_from_html(html: str) -> List[Tuple[str, str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    results: List[Tuple[str, str, str]] = []
    seen_ids = set()

    for title_a in soup.select("div.type02_bd-a h4 a"):
        raw_href = title_a.get("href", "").strip()
        match = PRODUCT_ID_RE.search(raw_href)
        if not match:
            continue

        product_id = match.group(1)
        if product_id in seen_ids:
            continue

        title = normalize_space(title_a.get_text(" ", strip=True))
        product_url = build_product_url(product_id)
        seen_ids.add(product_id)
        results.append((product_id, title, product_url))

    return results



def detect_ebook(soup: BeautifulSoup) -> str:
    version_block = soup.select_one("div.mod.type02_p011")
    if version_block:
        for span in version_block.find_all("span"):
            if normalize_space(span.get_text()) == "電子書":
                return "有電子書"

    for span in soup.find_all("span"):
        if normalize_space(span.get_text()) == "電子書":
            return "有電子書"

    return "無電子書"



def extract_author(soup: BeautifulSoup) -> str:
    detail_area = soup.select_one("div.type02_p003") or soup

    for li in detail_area.select("li"):
        li_text = normalize_space(li.get_text(" ", strip=True)).replace("：", ":")
        if "作者:" not in li_text or "原文作者:" in li_text:
            continue

        anchors = []
        for a in li.find_all("a"):
            text = normalize_space(a.get_text(" ", strip=True))
            href = a.get("href", "")
            if not text or text == "新功能介紹":
                continue
            if "adv_author/1" in href:
                anchors.append(text)

        if anchors:
            return ", ".join(anchors)

        if ":" in li_text:
            return li_text.split(":", 1)[1].strip()

    return ""



def parse_product_page(html: str, fallback_title: str, product_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")

    title = fallback_title
    author = ""
    publisher = ""
    publish_date = ""
    isbn = ""
    ebook = detect_ebook(soup)

    h1 = soup.select_one("h1")
    if h1:
        title = normalize_space(h1.get_text(" ", strip=True))
    elif soup.title:
        page_title = normalize_space(soup.title.get_text(" ", strip=True))
        if page_title and page_title != "www.books.com.tw":
            title = page_title.replace("博客來-", "").strip()

    detail_area = soup.select_one("div.type02_p003") or soup
    author = extract_author(soup)

    for li in detail_area.select("li"):
        li_text = normalize_space(li.get_text(" ", strip=True)).replace("：", ":")
        if not li_text:
            continue

        if li_text.startswith("出版社:") and not publisher:
            publisher_span = li.select_one("span")
            if publisher_span:
                publisher = normalize_space(publisher_span.get_text(" ", strip=True))
            else:
                publisher = normalize_space(li_text.split(":", 1)[1])
            continue

        if li_text.startswith("出版日期:") and not publish_date:
            publish_date = normalize_date(li_text.split(":", 1)[1])
            continue

        if (li_text.startswith("ISBN:") or li_text.startswith("EAN:")) and not isbn:
            isbn = normalize_isbn(li_text)
            continue

    meta_desc = soup.select_one('meta[name="description"]')
    meta_og_url = soup.select_one('meta[property="og:url"]')

    if not isbn and meta_desc and meta_desc.get("content"):
        isbn = normalize_isbn(meta_desc["content"])

    if not publish_date and meta_desc and meta_desc.get("content"):
        publish_date = normalize_date(meta_desc["content"])

    if not publisher:
        publisher_a = soup.select_one("li a[href*='sys_puballb'] span")
        if publisher_a:
            publisher = normalize_space(publisher_a.get_text(" ", strip=True))
        elif meta_desc and meta_desc.get("content"):
            m = re.search(r"出版社：([^，]+)", meta_desc["content"])
            if m:
                publisher = normalize_space(m.group(1))

    if title == fallback_title and meta_desc and meta_desc.get("content"):
        m = re.search(r"書名：([^，]+)", meta_desc["content"])
        if m:
            title = normalize_space(m.group(1))

    if not author and meta_desc and meta_desc.get("content"):
        m = re.search(r"作者：([^，]+)", meta_desc["content"])
        if m:
            author = normalize_space(m.group(1))

    if meta_og_url and meta_og_url.get("content"):
        product_url = clean_product_url(meta_og_url["content"])

    return [
        title,
        author,
        publisher,
        publish_date,
        isbn,
        clean_product_url(product_url),
        ebook,
    ]



def is_blocked_page(html: str, product_id: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    title_text = normalize_space(soup.title.get_text(" ", strip=True)) if soup.title else ""

    if title_text in {"www.books.com.tw", "", "驗證中"}:
        return True

    if soup.select_one("h1"):
        return False

    og_url = soup.select_one('meta[property="og:url"]')
    if og_url and product_id in (og_url.get("content") or ""):
        return False

    desc = soup.select_one('meta[name="description"]')
    if desc and normalize_isbn(desc.get("content", "")):
        return False

    html_text = normalize_space(soup.get_text(" ", strip=True))[:300]
    block_keywords = ["驗證", "機器人", "異常", "稍後再試", "存取受限", "Access Denied"]
    return any(k in html_text for k in block_keywords) or True



def fetch_product_html(page, product_url: str, product_id: str) -> str:
    referer = "https://www.books.com.tw/web/sys_saletopb/books/?attribute=30"

    for attempt in range(1, 4):
        page.goto(product_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS, referer=referer)
        page.wait_for_timeout(4000 + attempt * 1500)

        try:
            page.wait_for_selector("h1, meta[property='og:url']", timeout=12000)
        except PlaywrightTimeoutError:
            pass

        html = page.content()
        if not is_blocked_page(html, product_id):
            return html

        if attempt < 3:
            print(f"  第 {attempt} 次疑似被擋，重試中...", flush=True)
            page.wait_for_timeout(5000 + attempt * 2000)
            page.goto("https://www.books.com.tw/", wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
            page.wait_for_timeout(2500)

    raise RuntimeError("頁面疑似被博客來阻擋，抓到的不是商品頁")



def write_csv(rows: List[List[str]]) -> None:
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "書名",
            "作者",
            "出版社",
            "出版日期",
            "ISBN/EAN",
            "商品網址",
            "是否有電子書",
        ])
        writer.writerows(rows)



def main() -> None:
    if not RANKING_HTML_FILE.exists():
        raise FileNotFoundError(f"找不到排行榜 HTML 檔案：{RANKING_HTML_FILE}")

    ranking_html = RANKING_HTML_FILE.read_text(encoding="utf-8", errors="replace")
    ranking_items = parse_ranking_items_from_html(ranking_html)

    if not ranking_items:
        raise RuntimeError("未從 books_source-12.html 解析到任何商品編號。")

    print(f"共解析到 {len(ranking_items)} 本書")
    rows: List[List[str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        context = browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
            extra_http_headers={
                "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Upgrade-Insecure-Requests": "1",
            },
        )

        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
            Object.defineProperty(navigator, 'language', {get: () => 'zh-TW'});
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-TW', 'zh', 'en-US', 'en']});
        """)

        page = context.new_page()
        page.goto("https://www.books.com.tw/", wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        page.wait_for_timeout(4000)

        for idx, (product_id, title, product_url) in enumerate(ranking_items, 1):
            print(f"[{idx}/{len(ranking_items)}] {product_id} {title}")
            try:
                html = fetch_product_html(page, product_url, product_id)
                row = parse_product_page(html, title, product_url)
            except Exception as e:
                print(f"  抓取失敗：{e}")
                row = [title, "", "", "", "", clean_product_url(product_url), ""]

            print("  " + " | ".join(row))
            rows.append(row)

            if idx < len(ranking_items):
                time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

        browser.close()

    write_csv(rows)
    print(f"已輸出：{OUTPUT_CSV}")


if __name__ == "__main__":
    main()
