import csv
import re
import time
from urllib.parse import urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

LIST_URL = "https://www.books.com.tw/web/sys_saletopb/books/?attribute=30"
OUTPUT_CSV = "books_info-9.csv"

session = requests.Session()

session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "zh-TW,zh;q=0.9",
    "Referer": "https://www.books.com.tw/"
})


def clean_url(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme or "https", parts.netloc, parts.path, "", ""))


def normalize(text):
    return re.sub(r"\s+", " ", text or "").strip()


def fetch(url):

    r = session.get(url, timeout=30)

    r.raise_for_status()

    r.encoding = r.apparent_encoding

    return r.text


def detect_ebook(soup):

    for span in soup.find_all("span"):

        if span.get_text(strip=True) == "電子書":

            return "有電子書"

    return "無電子書"


def parse_ranking(html):

    soup = BeautifulSoup(html, "html.parser")

    books = []

    cards = soup.select("div.mod.type02_m035 div.mod_a > ul > li.item")

    for card in cards:

        a = card.select_one("div.type02_bd-a h4 a")

        if not a:
            continue

        title = normalize(a.get_text())

        url = clean_url(a["href"])

        author = ""

        author_a = card.select_one("ul.msg li a")

        if author_a:

            author = normalize(author_a.get_text())

        books.append((title, author, url))

    return books


def parse_product(html):

    soup = BeautifulSoup(html, "html.parser")

    publisher = ""
    date = ""
    isbn = ""

    for li in soup.select("li"):

        text = normalize(li.get_text())

        if text.startswith("出版社"):

            publisher = text.split(":", 1)[-1]

        elif text.startswith("出版日期"):

            date = text.split(":", 1)[-1]

        elif "ISBN" in text:

            isbn = text.split(":", 1)[-1]

    ebook = detect_ebook(soup)

    return publisher, date, isbn, ebook


def save_csv(rows):

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:

        writer = csv.writer(f)

        writer.writerow([
            "書名",
            "作者",
            "出版社",
            "出版日期",
            "ISBN",
            "是否有電子書",
            "URL"
        ])

        writer.writerows(rows)


def main():

    print("初始化 session...")

    session.get("https://www.books.com.tw/")  # 取得 cookie

    print("抓排行榜...")

    html = fetch(LIST_URL)

    books = parse_ranking(html)

    print("排行榜數量:", len(books))

    rows = []

    for i, (title, author, url) in enumerate(books, 1):

        print(f"[{i}] {title}")

        try:

            html = fetch(url)

            publisher, date, isbn, ebook = parse_product(html)

        except Exception as e:

            print("抓取失敗:", e)

            publisher = ""
            date = ""
            isbn = ""
            ebook = ""

        row = [
            title,
            author,
            publisher,
            date,
            isbn,
            ebook,
            url
        ]

        print(" | ".join(row))

        rows.append(row)

        time.sleep(1)

    save_csv(rows)

    print("完成 →", OUTPUT_CSV)


if __name__ == "__main__":

    main()