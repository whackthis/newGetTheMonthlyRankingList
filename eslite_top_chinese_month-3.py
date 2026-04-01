import requests
import re
import csv
import time
from bs4 import BeautifulSoup

API = "https://athena.eslite.com/api/v1/best_sellers/online/month?l1=3&page={}&per_page=20"

headers = {
    "User-Agent": "Mozilla/5.0"
}

# 比原本更寬鬆：允許 ISBN13 / 978... 或 ISBN13/978...
isbn_pattern = re.compile(r'ISBN13\s*/\s*(97[89]\d{10})')

books = []

for page in range(1, 6):
    print("抓排行榜第", page, "頁")

    url = API.format(page)
    data = requests.get(url, headers=headers).json()

    for item in data.get("products", []):
        title = item.get("name", "")
        product_id = item.get("id", "")

        if not product_id:
            continue

        product_url = f"https://www.eslite.com/product/{product_id}"
        print("抓:", title)

        html = requests.get(product_url, headers=headers).text
        soup = BeautifulSoup(html, "html.parser")

        # 關鍵：掃整頁文字，不只掃 span
        page_text = soup.get_text("\n", strip=True)

        isbn = ""
        m = isbn_pattern.search(page_text)
        if m:
            isbn = m.group(1)

        books.append([title, isbn, product_url])

        print("ISBN:", isbn if isbn else "抓不到")
        time.sleep(1)

with open("eslite_isbn.csv", "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(["書名", "ISBN13", "URL"])
    writer.writerows(books)

print("完成")