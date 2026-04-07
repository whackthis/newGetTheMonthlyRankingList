import csv
import random
import re
import time
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

RANKING_HTML_FILE = Path("books_source-12.html")
PRODUCT_BASE_URL = "https://www.books.com.tw/products/"
OUTPUT_CSV = "books_info-12.csv"

SLEEP_MIN = 53.0
SLEEP_MAX = 56.0
BROWSER_WAIT_MS = 2500

PRODUCT_ID_RE = re.compile(r"/products/(\d{10})")
ISBN_RE = re.compile(r"\b(?:97[89]\d{10}|\d{10})\b")
DATE_RE = re.compile(r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def clean_product_url(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme or "https"
    netloc = parts.netloc or "www.books.com.tw"
    return urlunsplit((scheme, netloc, parts.path, "", ""))


def build_product_url(product_id: str) -> str:
    return f"{PRODUCT_BASE_URL}{product_id}"


def normalize_date(text: str) -> str:
    text = normalize_space(text)
    match = DATE_RE.search(text)
    if not match:
        return ""
    year, month, day = re.split(r"[/-]", match.group(1))
    return f"{int(year):04d}/{int(month):02d}/{int(day):02d}"


def normalize_isbn(text: str) -> str:
    text = normalize_space(text)
    match = ISBN_RE.search(text)
    return match.group(0) if match else ""


def parse_ranking_items_from_html(html: str) -> List[Tuple[str, str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    results: List[Tuple[str, str, str]] = []
    seen_ids = set()

    for title_a in soup.select("div.type02_bd-a h4 a"):
        href = title_a.get("href", "").strip()
        match = PRODUCT_ID_RE.search(href)
        if not match:
            continue

        product_id = match.group(1)
        if product_id in seen_ids:
            continue

        title = normalize_space(title_a.get_text(" ", strip=True))
        results.append((product_id, title, build_product_url(product_id)))
        seen_ids.add(product_id)

    return results


def detect_ebook(soup: BeautifulSoup) -> str:
    version_block = soup.select_one("div.mod.type02_p011")
    text = normalize_space(version_block.get_text(" ", strip=True)) if version_block else ""
    return "Y" if "電子書" in text else ""


def extract_author(detail_area: BeautifulSoup) -> str:
    authors: List[str] = []
    for anchor in detail_area.select("a[href*='adv_author/1']"):
        name = normalize_space(anchor.get_text(" ", strip=True))
        if name and name not in authors:
            authors.append(name)
    return ", ".join(authors)


def extract_publisher(detail_area: BeautifulSoup) -> str:
    anchor = detail_area.select_one("a[href*='sys_puballb']")
    if not anchor:
        return ""
    return normalize_space(anchor.get_text(" ", strip=True))


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

    detail_area = soup.select_one("div.type02_p003") or soup
    author = extract_author(detail_area)
    publisher = extract_publisher(detail_area)

    for li in detail_area.select("li"):
        li_text = normalize_space(li.get_text(" ", strip=True))
        if not publish_date:
            publish_date = normalize_date(li_text)
        if not isbn:
            isbn = normalize_isbn(li_text)
        if publish_date and isbn:
            break

    if not isbn:
        meta_desc = soup.select_one('meta[name="description"]')
        if meta_desc and meta_desc.get("content"):
            isbn = normalize_isbn(meta_desc["content"])

    if not publish_date:
        meta_desc = soup.select_one('meta[name="description"]')
        if meta_desc and meta_desc.get("content"):
            publish_date = normalize_date(meta_desc["content"])

    return [
        title,
        author,
        publisher,
        publish_date,
        isbn,
        clean_product_url(product_url),
        ebook,
    ]


def fetch_product_html(page, url: str) -> str:
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(BROWSER_WAIT_MS)
    return page.content()


def write_csv(rows: List[List[str]]) -> None:
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([
            "title",
            "author",
            "publisher",
            "publish_date",
            "isbn",
            "url",
            "ebook_available",
        ])
        writer.writerows(rows)


def main() -> None:
    if not RANKING_HTML_FILE.exists():
        raise FileNotFoundError(f"Missing ranking HTML file: {RANKING_HTML_FILE}")

    ranking_html = RANKING_HTML_FILE.read_text(encoding="utf-8", errors="replace")
    ranking_items = parse_ranking_items_from_html(ranking_html)
    if not ranking_items:
        raise RuntimeError("No ranking items were found in the saved ranking HTML.")

    print(f"Found {len(ranking_items)} ranking items")
    rows: List[List[str]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            locale="zh-TW",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
        )
        page = context.new_page()

        page.goto("https://www.books.com.tw/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(BROWSER_WAIT_MS)

        for idx, (product_id, title, product_url) in enumerate(ranking_items, 1):
            print(f"[{idx}/{len(ranking_items)}] {product_id} {title}")
            try:
                html = fetch_product_html(page, product_url)
                row = parse_product_page(html, title, product_url)
            except Exception as exc:
                print(f"  fetch failed: {exc}")
                row = [title, "", "", "", "", clean_product_url(product_url), ""]

            print("  " + " | ".join(row))
            rows.append(row)

            if idx < len(ranking_items):
                time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

        browser.close()

    write_csv(rows)
    print(f"Saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
