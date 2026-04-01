import csv
import json
import random
import re
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from requests.exceptions import HTTPError

LIST_URL = "https://www.books.com.tw/web/sys_saletopb/books/?attribute=30"
BASE_URL = "https://www.books.com.tw/"
SEARCH_URL_TEMPLATE = "https://search.books.com.tw/search/query/key/{keyword}/cat/books"
OUTPUT_CSV = "books_info-7.csv"
LOCAL_LIST_FALLBACK = Path("test.html")
HISTORY_GLOB = "books_info*.csv"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
}

ISBN_RE = re.compile(r"\b(?:97[89]\d{10}|\d{10})\b")
DATE_RE = re.compile(r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})")
PRODUCT_ID_RE = re.compile(r"/products/(\d{10})")
SEARCH_PRODUCT_ID_RE = re.compile(r"prod-itemlist-(\d{10})")
LABEL_PATTERNS = {
    "author": ("作者",),
    "original_author": ("原文作者",),
    "translator": ("譯者",),
    "illustrator": ("繪者",),
    "publisher": ("出版社",),
    "publish_date": ("出版日期",),
    "isbn": ("ISBN", "EAN"),
}
FIELDS = [
    "title",
    "author",
    "original_author",
    "translator",
    "illustrator",
    "publisher",
    "publish_date",
    "isbn",
    "url",
]


def clean_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme or "https", parts.netloc, parts.path, "", ""))


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_title(text: str) -> str:
    cleaned = normalize_space(text)
    cleaned = cleaned.replace("：", ":")
    cleaned = re.sub(r"\s*\([^)]*首刷[^)]*\)", lambda m: m.group(0), cleaned)
    return cleaned.casefold()


def normalize_date(text: str) -> str:
    match = DATE_RE.search(text or "")
    if not match:
        return normalize_space(text)
    parts = re.split(r"[/-]", match.group(1))
    year, month, day = parts
    return f"{int(year):04d}/{int(month):02d}/{int(day):02d}"


def normalize_isbn(text: str) -> str:
    text = normalize_space(text)
    match = ISBN_RE.search(text)
    if match:
        return match.group(0)
    return ""


def empty_info(*, title: str = "", url: str = "") -> Dict[str, str]:
    return {
        "title": title,
        "author": "",
        "original_author": "",
        "translator": "",
        "illustrator": "",
        "publisher": "",
        "publish_date": "",
        "isbn": "",
        "url": url,
    }


def info_score(info: Dict[str, str]) -> Tuple[int, int]:
    populated = sum(1 for key in FIELDS if key != "url" and normalize_space(info.get(key, "")))
    isbn_digits = len(re.sub(r"\D", "", info.get("isbn", "")))
    return populated, isbn_digits


def merge_info(*infos: Dict[str, str]) -> Dict[str, str]:
    merged = empty_info()
    for info in infos:
        if not info:
            continue
        for field in FIELDS:
            value = normalize_space(info.get(field, ""))
            if field == "publish_date" and value:
                value = normalize_date(value)
            if field == "isbn" and value:
                value = normalize_isbn(value)
            if value and not merged[field]:
                merged[field] = value
    return merged


def is_403(exc: Exception) -> bool:
    return isinstance(exc, HTTPError) and exc.response is not None and exc.response.status_code == 403


class BooksScraper:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def warm_up(self) -> None:
        for url in (BASE_URL, "https://search.books.com.tw/search/query/cat/all/key/%E6%9B%B8"):
            try:
                response = self.session.get(url, timeout=20)
                response.raise_for_status()
                return
            except Exception:
                continue

    def fetch_html(self, url: str, *, referer: Optional[str] = None, retries: int = 4) -> str:
        last_exc: Optional[Exception] = None
        headers = {}
        if referer:
            headers["Referer"] = referer

        for attempt in range(retries):
            try:
                response = self.session.get(url, headers=headers, timeout=25)
                response.raise_for_status()
                response.encoding = response.apparent_encoding or response.encoding or "utf-8"
                return response.text
            except Exception as exc:
                last_exc = exc
                if is_403(exc):
                    self.warm_up()
                if attempt < retries - 1:
                    time.sleep((2 ** attempt) + random.uniform(1.0, 2.0))

        assert last_exc is not None
        raise last_exc

    def fetch_list_html(self) -> Tuple[str, str]:
        for url in (
            LIST_URL,
            "https://www.books.com.tw/web/sys_saletopb/books",
            "https://www.books.com.tw/web/sys_saletopb/books/?loc=P_0000_001",
        ):
            try:
                return self.fetch_html(url, referer=BASE_URL), "remote"
            except Exception as exc:
                if not is_403(exc):
                    raise

        if LOCAL_LIST_FALLBACK.exists():
            return LOCAL_LIST_FALLBACK.read_text(encoding="utf-8", errors="replace"), f"local fallback: {LOCAL_LIST_FALLBACK}"

        raise RuntimeError(
            "博客來排行榜頁面持續回傳 403，且找不到本機備援 HTML。"
            "可以先在瀏覽器開啟排行榜頁，將頁面另存成 test.html 後再執行。"
        )


def extract_label_value(text: str) -> Tuple[str, str]:
    cleaned = normalize_space(text).replace("：", ":")
    if ":" in cleaned:
        label, value = cleaned.split(":", 1)
        return label.strip(), value.strip()
    return cleaned, ""


def set_field(result: Dict[str, str], label: str, value: str) -> None:
    if not value:
        return
    if label in LABEL_PATTERNS["author"] and not result["author"]:
        result["author"] = value
    elif label in LABEL_PATTERNS["original_author"] and not result["original_author"]:
        result["original_author"] = value
    elif label in LABEL_PATTERNS["translator"] and not result["translator"]:
        result["translator"] = value
    elif label in LABEL_PATTERNS["illustrator"] and not result["illustrator"]:
        result["illustrator"] = value
    elif label in LABEL_PATTERNS["publisher"] and not result["publisher"]:
        result["publisher"] = value
    elif label in LABEL_PATTERNS["publish_date"] and not result["publish_date"]:
        result["publish_date"] = normalize_date(value)
    elif label in LABEL_PATTERNS["isbn"] and not result["isbn"]:
        result["isbn"] = normalize_isbn(value)


def walk_json_for_fields(obj: object, result: Dict[str, str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_lower = key.lower()
            if key_lower == "isbn" and isinstance(value, str) and not result["isbn"]:
                result["isbn"] = normalize_isbn(value)
            elif key_lower == "name" and isinstance(value, str) and not result["title"]:
                result["title"] = normalize_space(value)
            elif key_lower == "author" and isinstance(value, dict):
                name = value.get("name")
                if isinstance(name, str) and not result["author"]:
                    result["author"] = normalize_space(name)
            elif key_lower == "author" and isinstance(value, list) and not result["author"]:
                authors = [normalize_space(item.get("name", "")) for item in value if isinstance(item, dict)]
                authors = [name for name in authors if name]
                if authors:
                    result["author"] = ", ".join(authors)
            elif key_lower == "publisher" and isinstance(value, dict) and not result["publisher"]:
                name = value.get("name")
                if isinstance(name, str):
                    result["publisher"] = normalize_space(name)
            elif key_lower in {"datepublished", "publisheddate"} and isinstance(value, str) and not result["publish_date"]:
                result["publish_date"] = normalize_date(value)
            walk_json_for_fields(value, result)
    elif isinstance(obj, list):
        for item in obj:
            walk_json_for_fields(item, result)


def extract_book_info_from_product_html(html: str, url: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    result = empty_info(url=url)

    title_tag = soup.select_one("h1") or soup.select_one('meta[property="og:title"]')
    if title_tag:
        if title_tag.name == "meta":
            result["title"] = normalize_space(title_tag.get("content", ""))
        else:
            result["title"] = normalize_space(title_tag.get_text(" ", strip=True))

    for li in soup.select("li"):
        label, value = extract_label_value(li.get_text(" ", strip=True))
        set_field(result, label, value)

    for tag in soup.select('script[type="application/ld+json"]'):
        text = (tag.string or tag.get_text() or "").strip()
        if not text:
            continue
        try:
            walk_json_for_fields(json.loads(text), result)
        except Exception:
            continue

    if not result["isbn"]:
        meta_description = soup.select_one('meta[name="description"]')
        if meta_description and meta_description.get("content"):
            result["isbn"] = normalize_isbn(meta_description["content"])

    return result


def parse_list_items(html: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    items: List[Tuple[str, str]] = []
    seen = set()
    for anchor in soup.select("li.item h4 a, h4 a"):
        href = clean_url(anchor.get("href", "").strip())
        title = normalize_space(anchor.get_text(" ", strip=True))
        if not href or "/products/" not in href or not title:
            continue
        key = (title, href)
        if key in seen:
            continue
        seen.add(key)
        items.append(key)
    return items


def load_history_cache(output_name: str) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
    by_url: Dict[str, Dict[str, str]] = {}
    by_title: Dict[str, Dict[str, str]] = {}
    for path in sorted(Path('.').glob(HISTORY_GLOB)):
        if path.name == output_name:
            continue
        try:
            with path.open('r', encoding='utf-8-sig', newline='') as fh:
                reader = csv.reader(fh)
                next(reader, None)
                for row in reader:
                    row = [normalize_space(cell) for cell in row]
                    if not row:
                        continue
                    info = empty_info()
                    if len(row) >= 9:
                        info.update({
                            'title': row[0], 'author': row[1], 'original_author': row[2], 'translator': row[3],
                            'illustrator': row[4], 'publisher': row[5], 'publish_date': row[6], 'isbn': row[7], 'url': row[8]
                        })
                    elif len(row) >= 6:
                        info.update({
                            'title': row[0], 'author': row[1], 'publisher': row[2], 'publish_date': row[3], 'isbn': row[4], 'url': row[5]
                        })
                    else:
                        continue
                    info['publish_date'] = normalize_date(info['publish_date']) if info['publish_date'] else ''
                    info['isbn'] = normalize_isbn(info['isbn'])
                    url = clean_url(info['url']) if info['url'] else ''
                    info['url'] = url
                    title_key = normalize_title(info['title'])
                    if url:
                        current = by_url.get(url)
                        if current is None or info_score(info) > info_score(current):
                            by_url[url] = info
                    if title_key:
                        current = by_title.get(title_key)
                        if current is None or info_score(info) > info_score(current):
                            by_title[title_key] = info
        except Exception:
            continue
    return by_url, by_title


def lookup_history(url: str, title: str, by_url: Dict[str, Dict[str, str]], by_title: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    return merge_info(
        by_url.get(clean_url(url), empty_info()),
        by_title.get(normalize_title(title), empty_info()),
    )


def parse_search_result(html: str, *, product_url: str, fallback_title: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, 'html.parser')
    target_id = ''
    match = PRODUCT_ID_RE.search(product_url)
    if match:
        target_id = match.group(1)

    card = None
    if target_id:
        card = soup.select_one(f'#prod-itemlist-{target_id}')
    if card is None:
        card = soup.select_one('.table-td[id^="prod-itemlist-"]')
    if card is None:
        return empty_info(title=fallback_title, url=product_url)

    info = empty_info(title=fallback_title, url=product_url)
    title_anchor = card.select_one('h4 a')
    if title_anchor:
        info['title'] = normalize_space(title_anchor.get('title') or title_anchor.get_text(' ', strip=True))

    authors = [normalize_space(a.get('title') or a.get_text(' ', strip=True)) for a in card.select('p.author a')]
    authors = [name for name in authors if name]
    if authors:
        info['author'] = ', '.join(authors)

    if not info['title']:
        info['title'] = fallback_title
    return info


def fetch_book_info(scraper: BooksScraper, *, rank_title: str, url: str, history_by_url: Dict[str, Dict[str, str]], history_by_title: Dict[str, Dict[str, str]]) -> Tuple[Dict[str, str], str]:
    history_info = lookup_history(url, rank_title, history_by_url, history_by_title)
    try:
        html = scraper.fetch_html(url, referer=LIST_URL)
        page_info = extract_book_info_from_product_html(html, url)
        return merge_info(page_info, history_info, empty_info(title=rank_title, url=url)), 'product page'
    except Exception as exc:
        if not is_403(exc):
            raise

    search_url = SEARCH_URL_TEMPLATE.format(keyword=quote(rank_title))
    try:
        search_html = scraper.fetch_html(search_url, referer=BASE_URL)
        search_info = parse_search_result(search_html, product_url=url, fallback_title=rank_title)
        merged = merge_info(search_info, history_info, empty_info(title=rank_title, url=url))
        return merged, 'search fallback + local cache'
    except Exception:
        merged = merge_info(history_info, empty_info(title=rank_title, url=url))
        return merged, 'local cache'


def write_csv(rows: Iterable[List[str]]) -> None:
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8-sig') as fh:
        writer = csv.writer(fh)
        writer.writerow(['書名', '作者', '原文作者', '譯者', '繪者', '出版社', '出版日期', 'ISBN', 'URL'])
        writer.writerows(rows)


def main() -> None:
    scraper = BooksScraper()
    history_by_url, history_by_title = load_history_cache(OUTPUT_CSV)
    list_html, source = scraper.fetch_list_html()
    items = parse_list_items(list_html)
    if not items:
        raise RuntimeError('未解析到任何排行榜書籍，請先確認排行榜頁面結構是否已變更。')

    print(f'排行榜來源: {source}')
    print(f'解析到 {len(items)} 本書')

    rows: List[List[str]] = []
    for idx, (rank_title, url) in enumerate(items, 1):
        print(f'[{idx}/{len(items)}] {rank_title}')
        info, info_source = fetch_book_info(
            scraper,
            rank_title=rank_title,
            url=url,
            history_by_url=history_by_url,
            history_by_title=history_by_title,
        )
        print(f'  資料來源: {info_source}')
        row = [
            info['title'] or rank_title,
            info['author'],
            info['original_author'],
            info['translator'],
            info['illustrator'],
            info['publisher'],
            info['publish_date'],
            info['isbn'],
            url,
        ]
        print(' | '.join(row))
        rows.append(row)
        time.sleep(random.uniform(3.0, 6.0))

    write_csv(rows)
    print(f'已輸出 {OUTPUT_CSV}')


if __name__ == '__main__':
    main()
