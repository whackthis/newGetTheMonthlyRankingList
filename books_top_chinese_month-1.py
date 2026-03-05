import re
import csv
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

LIST_URL = "https://www.books.com.tw/web/sys_saletopb/books/?attribute=30"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
}

# 商品頁 ISBN 行：ISBN：978xxxxxxxxxx
ISBN_LINE_RE = re.compile(r"ISBN(?:-13)?\s*[:：]\s*([0-9Xx\-]{10,20})")

def normalize_isbn(s: str) -> str:
    return s.strip().replace("-", "").replace(" ", "").upper()

def normalize_product_url(href: str) -> str:
    """去掉 querystring，只留 https://www.books.com.tw/products/0011041755"""
    u = href.strip()
    # 可能是 //www.books.com.tw/products/... 之類
    if u.startswith("//"):
        u = "https:" + u
    u = urljoin(LIST_URL, u)

    p = urlparse(u)
    return f"{p.scheme}://{p.netloc}{p.path}"

def get_rank_items():
    """
    回傳: list of dict {rank, title, url}
    只抓排行榜主清單：li.item 內 h4 a
    """
    r = requests.get(LIST_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    items = []
    seen = set()

    for li in soup.select("li.item"):
        # 排名（可有可無）
        rank = ""
        no = li.select_one(".no_list .no")
        if no:
            rank = no.get_text(strip=True)

        a = li.select_one("h4 a")
        if not a or not a.get("href"):
            continue

        title = a.get_text(strip=True)
        url = normalize_product_url(a["href"])

        if url in seen:
            continue
        seen.add(url)

        items.append({"rank": rank, "title": title, "url": url})

    return items

def fetch_isbn(product_url: str) -> str:
    r = requests.get(product_url, headers=HEADERS, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n", strip=True)

    m = ISBN_LINE_RE.search(text)
    if not m:
        return ""

    cand = normalize_isbn(m.group(1))
    if len(cand) in (10, 13):
        return cand
    return ""

def main():
    items = get_rank_items()
    print(f"抓到排行榜主清單筆數：{len(items)}")

    rows = []
    for i, it in enumerate(items, 1):
        try:
            isbn = fetch_isbn(it["url"])
        except Exception as e:
            isbn = ""
            print(f"[{i}] 失敗：{it['url']} | {e}")

        print(f"[{i}] TOP{it['rank'] or '?'} {it['title']} | ISBN={isbn or '找不到'}")
        rows.append({
            "rank": it["rank"],
            "title": it["title"],
            "isbn": isbn,
            "url": it["url"],
        })

        time.sleep(0.8)  # 放慢一點

    with open("books_isbn.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["rank", "title", "isbn", "url"])
        w.writeheader()
        w.writerows(rows)

    print("\n完成：已輸出 books_isbn.csv")

if __name__ == "__main__":
    main()