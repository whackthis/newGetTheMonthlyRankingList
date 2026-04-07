import csv
import random
import re
import time
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

RANKING_HTML_FILE = Path("books_source-12.html")
PRODUCT_BASE_URL = "https://www.books.com.tw/products/"
OUTPUT_CSV = "books_info-12.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.books.com.tw/",
}

REQUEST_TIMEOUT = 30
SLEEP_MIN = 53.0
SLEEP_MAX = 56.0

PRODUCT_ID_RE = re.compile(r"/products/(\d{10})")
ISBN_RE = re.compile(r"\b(?:97[89]\d{10}|\d{10})\b")
DATE_RE = re.compile(r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_date(text: str) -> str:
    text = normalize_space(text)
    match = DATE_RE.search(text)
    if not match:
        return text
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

    if not isbn:
        meta_desc = soup.select_one('meta[name="description"]')
        if meta_desc and meta_desc.get("content"):
            isbn = normalize_isbn(meta_desc["content"])

    if not publisher:
        publisher_a = soup.select_one("li:has(a[href*='sys_puballb']) span")
        if publisher_a:
            publisher = normalize_space(publisher_a.get_text(" ", strip=True))

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


def fetch_product_html(session: requests.Session, url: str) -> str:
    response = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


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
    session = requests.Session()
    session.headers.update(HEADERS)

    # 先打首頁拿 cookie
    try:
        session.get("https://www.books.com.tw/", timeout=REQUEST_TIMEOUT)
    except Exception:
        pass

    for idx, (product_id, title, product_url) in enumerate(ranking_items, 1):
        print(f"[{idx}/{len(ranking_items)}] {product_id} {title}")
        try:
            html = fetch_product_html(session, product_url)
            row = parse_product_page(html, title, product_url)
        except Exception as e:
            print(f"  抓取失敗：{e}")
            row = [title, "", "", "", "", clean_product_url(product_url), ""]

        print("  " + " | ".join(row))
        rows.append(row)

        if idx < len(ranking_items):
            time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    write_csv(rows)
    print(f"已輸出：{OUTPUT_CSV}")


if __name__ == "__main__":
    main()
