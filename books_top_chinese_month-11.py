import csv
import random
import re
import time
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

RANKING_HTML_FILE = Path("books_source-10.html")
PRODUCT_BASE_URL = "https://www.books.com.tw/products/"
OUTPUT_CSV = "books_info-11.csv"

SLEEP_MIN = 53.0
SLEEP_MAX = 56.0

PRODUCT_ID_RE = re.compile(r"/products/(\d{10})")
ISBN_RE = re.compile(r"\b(?:97[89]\d{10}|\d{10})\b")
DATE_RE = re.compile(r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def clean_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme or "https", parts.netloc, parts.path, "", ""))


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


def detect_ebook_exact_span(soup: BeautifulSoup) -> str:
    for span in soup.find_all("span"):
        if span.get_text(strip=True) == "電子書":
            return "有電子書"
    return "無電子書"


def parse_ranking_ids_from_static_html(html: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    results: List[Tuple[str, str]] = []
    seen = set()

    cards = soup.select("div.mod.type02_m035 div.mod_a > ul > li.item")

    for card in cards:
        title_a = card.select_one("div.type02_bd-a h4 a")
        if not title_a:
            continue

        href = title_a.get("href", "").strip()
        title = normalize_space(title_a.get_text(" ", strip=True))

        match = PRODUCT_ID_RE.search(href)
        if not match:
            continue

        product_id = match.group(1)
        key = (product_id, title)
        if key in seen:
            continue

        seen.add(key)
        results.append((product_id, title))

    return results


def extract_label_value(text: str) -> Tuple[str, str]:
    cleaned = normalize_space(text).replace("：", ":")
    if ":" in cleaned:
        label, value = cleaned.split(":", 1)
        return label.strip(), value.strip()
    return cleaned, ""


def fetch_html_with_browser(page, url: str) -> str:
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)
    return page.content()


def extract_author_from_li(li) -> str:
    html = str(li)

    match = re.search(r'/adv_author/1/">\s*(.*?)\s*</a>', html)
    if match:
        return normalize_space(BeautifulSoup(match.group(1), "html.parser").get_text())

    return ""


def parse_product_page(html: str, url: str, fallback_title: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    author = ""
    publisher = ""
    publish_date = ""
    isbn = ""
    ebook = detect_ebook_exact_span(soup)

    h1 = soup.select_one("h1")
    if h1:
        title = normalize_space(h1.get_text(" ", strip=True))
    else:
        title = fallback_title


    for li in soup.select("li"):
        li_text = normalize_space(li.get_text(" ", strip=True)).replace("：", ":")
        label, value = extract_label_value(li_text)
        
        if "作者" in li.get_text():
            print("嘗試從作者欄位抓作者，原始文本:", li_text)
            author = extract_author_from_li(li)

            '''
    for li in soup.select("li"):
        li_text = normalize_space(li.get_text(" ", strip=True)).replace("：", ":")
        label, value = extract_label_value(li_text)

        if not author and "作者" in li.get_text():
            # 再抓後面的第一個 <a>
            author_a = li.find_all("a")
            author = ", ".join([
                normalize_space(a.get_text())
                for a in author_a
            ]) 
            '''
            
            '''
            if author_a:
                author = normalize_space(author_a.get_text(" ", strip=True))
            else:
                author = li_text.split(":", 1)[-1].strip()
            '''

        elif label == "出版社" and not publisher:
            publisher = value

        elif label == "出版日期" and not publish_date:
            publish_date = normalize_date(value)

        elif label in ("ISBN", "EAN") and not isbn:
            isbn = normalize_isbn(value)

    if not isbn:
        meta_desc = soup.select_one('meta[name="description"]')
        if meta_desc and meta_desc.get("content"):
            isbn = normalize_isbn(meta_desc["content"])

    return [
        title,
        author,
        publisher,
        publish_date,
        isbn,
        ebook,
        url,
    ]


def write_csv(rows: List[List[str]]) -> None:
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "書名",
            "作者",
            "出版社",
            "出版日期",
            "ISBN",
            "是否有電子書",
            "URL",
        ])
        writer.writerows(rows)


def main() -> None:
    if not RANKING_HTML_FILE.exists():
        raise FileNotFoundError(f"找不到排行榜靜態源碼檔案：{RANKING_HTML_FILE}")

    ranking_html = RANKING_HTML_FILE.read_text(encoding="utf-8", errors="replace")
    ranking_items = parse_ranking_ids_from_static_html(ranking_html)

    if not ranking_items:
        raise RuntimeError("未從靜態排行榜源碼解析到任何商品編號。")

    print(f"從靜態排行榜源碼解析到 {len(ranking_items)} 本書")

    rows: List[List[str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            locale="zh-TW",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
        )

        page = context.new_page()

        # 先開首頁拿 cookie，比較像真人瀏覽
        page.goto("https://www.books.com.tw/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        for idx, (product_id, ranking_title) in enumerate(ranking_items, 1):
            url = f"{PRODUCT_BASE_URL}{product_id}"
            print(f"[{idx}/{len(ranking_items)}] {product_id} | {ranking_title}")

            try:
                html = fetch_html_with_browser(page, url)
                row = parse_product_page(html, url, ranking_title)
            except Exception as e:
                print(f"抓取失敗: {e}")
                row = [
                    ranking_title,
                    "",
                    "",
                    "",
                    "",
                    "",
                    url,
                ]

            print(" | ".join(row))
            rows.append(row)

            if idx < len(ranking_items):
                time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

        browser.close()

    write_csv(rows)
    print(f"已輸出 {OUTPUT_CSV}")


if __name__ == "__main__":
    main()