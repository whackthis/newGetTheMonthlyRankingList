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
            sleep_s = (2 ** i) + random.uniform(1.2, 1.8)
            time.sleep(sleep_s)
    raise last_exc

# 放寬：可抓 10~13 碼
ISBN_RE = re.compile(r"\b\d{10,13}\b")

def extract_book_info_from_product_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "title": "",
        "author": "",
        "publisher": "",
        "publish_date": "",
        "isbn": "",
    }

    # 1) 書名：先抓 h1，抓不到再用 <title>
    h1 = soup.select_one("h1")
    if h1:
        result["title"] = h1.get_text(strip=True)

    if not result["title"]:
        title_tag = soup.select_one("title")
        if title_tag:
            page_title = title_tag.get_text(strip=True)
            # 例如：博客來-鏈鋸人 (首刷限定版) 22
            result["title"] = re.sub(r"^博客來[-－]", "", page_title).strip()

    # 2) 先抓商品資訊區的作者 / 出版社 / 出版日期
    # 例如：
    # 作者：藤本樹
    # 出版社：天下雜誌
    # 出版日期：2025/02/05
    for li in soup.select("li"):
        text = li.get_text(" ", strip=True)

        if not result["author"] and "作者：" in text:
            a = li.select_one("a")
            if a:
                result["author"] = a.get_text(strip=True)
            else:
                m = re.search(r"作者：\s*(.+)", text)
                if m:
                    result["author"] = m.group(1).strip()

        if not result["publisher"] and "出版社：" in text:
            span = li.select_one("span")
            if span:
                result["publisher"] = span.get_text(strip=True)
            else:
                a = li.select_one("a")
                if a:
                    result["publisher"] = a.get_text(strip=True)
                else:
                    m = re.search(r"出版社：\s*(.+)", text)
                    if m:
                        result["publisher"] = m.group(1).strip()

        if not result["publish_date"] and "出版日期：" in text:
            m = re.search(r"出版日期：\s*([0-9]{4}/[0-9]{2}/[0-9]{2})", text)
            if m:
                result["publish_date"] = m.group(1)

    # 3) 作者介紹區塊備援
    # 結構常見為：
    # <h3>作者介紹</h3>
    # <div class="bd"><div class="content">...<strong>艾瑞克‧喬根森（Eric Jorgenson）</strong>...
    if not result["author"]:
        for h3 in soup.select("h3"):
            h3_text = h3.get_text(strip=True)
            if "作者介紹" in h3_text:
                bd = h3.find_next("div", class_="bd")
                if bd:
                    strongs = bd.select("strong")
                    for st in strongs:
                        txt = st.get_text(" ", strip=True)
                        if txt and "作者簡介" not in txt:
                            result["author"] = txt
                            break
                if result["author"]:
                    break

    # 4) ISBN：JSON-LD
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
                result["isbn"] = got
                break
        except Exception:
            pass

    # 5) 詳細資料 / meta description 備援
    if not result["isbn"]:
        for li in soup.select("li"):
            text = li.get_text(" ", strip=True)
            if "ISBN" in text or "EAN" in text:
                m = ISBN_RE.search(text)
                if m:
                    result["isbn"] = m.group(0)
                    break

    if not result["isbn"]:
        meta = soup.select_one('meta[name="description"]')
        if meta and meta.get("content"):
            m = ISBN_RE.search(meta["content"])
            if m:
                result["isbn"] = m.group(0)

    return result

def main():
    session = requests.Session()

    list_html = request_with_retry(session, LIST_URL)
    soup = BeautifulSoup(list_html, "html.parser")

    items = []
    for li in soup.select("li.item"):
        a = li.select_one("h4 a")
        if not a:
            continue
        rank_title = a.get_text(strip=True)
        url = clean_url(a.get("href", "").strip())
        if url:
            items.append((rank_title, url))

    print("排行榜抓到本數：", len(items))

    rows = []
    for idx, (rank_title, url) in enumerate(items, 1):
        print(f"[{idx}/{len(items)}] {rank_title}")

        html = request_with_retry(session, url)
        info = extract_book_info_from_product_html(html)

        title = info["title"] or rank_title
        author = info["author"]
        publisher = info["publisher"]
        publish_date = info["publish_date"]
        isbn = info["isbn"]

        if not isbn:
            print(f"沒抓到 ISBN: {title} -> {url}")

        print(f"{title} | {author} | {publisher} | {publish_date} | {isbn} | {url}")

        rows.append([
            title,
            author,
            publisher,
            publish_date,
            isbn,
            url
        ])

        time.sleep(random.uniform(80.2, 100.2))

    with open("books_info-4-1.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["書名", "作者", "出版社", "出版日期", "ISBN", "URL"])
        w.writerows(rows)

    print("完成：books_info-4-1.csv")

if __name__ == "__main__":
    main()