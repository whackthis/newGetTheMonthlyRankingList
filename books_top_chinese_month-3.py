import re
import csv
import time
import json
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlsplit, urlunsplit

LIST_URL = "https://www.books.com.tw/web/sys_saletopb/books/?attribute=30"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

def clean_url(u: str) -> str:
    """去掉 query 參數，避免 loc 造成差異；保留主網址即可。"""
    s = urlsplit(u)
    return urlunsplit((s.scheme, s.netloc, s.path, "", ""))

def request_with_retry(session: requests.Session, url: str, retries=5, timeout=20) -> str:
    last_exc = None
    for i in range(retries):
        try:
            r = session.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception as e:
            last_exc = e
            # 指數退避 + 隨機抖動，降低 10054
            sleep_s = (2 ** i) + random.uniform(1.2, 1.8)
            time.sleep(sleep_s)
    raise last_exc

ISBN_RE = re.compile(r"\b\d{10,13}\b")

def extract_isbn_from_product_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # 1) JSON-LD：找 isbn
    for tag in soup.select('script[type="application/ld+json"]'):
        txt = (tag.string or "").strip()
        if not txt:
            continue
        try:
            obj = json.loads(txt)

            def walk(x):
                if isinstance(x, dict):
                    for k, v in x.items():
                        if k.lower() == "isbn" and isinstance(v, str):
                            m = ISBN_RE.search(v)
                            if m:
                                return m.group(0)
                        got = walk(v)
                        if got:
                            return got
                elif isinstance(x, list):
                    for it in x:
                        got = walk(it)
                        if got:
                            return got
                return None

            got = walk(obj)
            if got:
                return got
        except Exception:
            pass

    # 2) 詳細資料：<li>ISBN：...</li>
    for li in soup.select("li"):
        t = li.get_text(strip=True)
        if "ISBN" in t:
            m = ISBN_RE.search(t)
            if m:
                return m.group(0)

    # 3) meta description 備援
    meta = soup.select_one('meta[name="description"]')
    if meta and meta.get("content"):
        m = ISBN_RE.search(meta["content"])
        if m:
            return m.group(0)

    return ""

def main():
    session = requests.Session()

    # 抓排行榜頁
    list_html = request_with_retry(session, LIST_URL)
    soup = BeautifulSoup(list_html, "html.parser")

    items = []
    for li in soup.select("li.item"):
        a = li.select_one("h4 a")
        if not a:
            continue
        title = a.get_text(strip=True)
        url = clean_url(a.get("href", "").strip())
        if url:
            items.append((title, url))

    print("排行榜抓到本數：", len(items))

    rows = []
    for idx, (title, url) in enumerate(items, 1):
        print(f"[{idx}/{len(items)}] {title}")
        html = request_with_retry(session, url)
        isbn = extract_isbn_from_product_html(html)
        rows.append([title, isbn, url])

        # 節奏放慢一點更不容易被踢
        time.sleep(random.uniform(100.2, 200.2))

    with open("books_isbn-2.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["書名", "ISBN", "URL"])
        w.writerows(rows)

    print("完成：books_isbn-2.csv")

if __name__ == "__main__":
    main()