import requests
import re
import csv
import time
from bs4 import BeautifulSoup

API = "https://athena.eslite.com/api/v1/best_sellers/online/month?l1=3&page={}&per_page=20"

headers = {
    "User-Agent": "Mozilla/5.0"
}

isbn_pattern = re.compile(r'ISBN13\s*/\s*(97[89]\d{10})')

books = []

for page in range(1, 6):
    print("抓排行榜第", page, "頁")

    url = API.format(page)
    data = requests.get(url, headers=headers).json()

    for item in data["products"]:
        title = item["name"]
        product_id = item["id"]

        product_url = f"https://www.eslite.com/product/{product_id}"

        print("抓:", title)

        html = requests.get(product_url, headers=headers).text
        soup = BeautifulSoup(html, "html.parser")

        isbn = ""

        for span in soup.select("span"):
            text = span.get_text(strip=True)
            m = isbn_pattern.search(text)
            if m:
                isbn = m.group(1)
                break

        books.append([title, isbn, product_url])

        time.sleep(1)

with open("eslite_isbn.csv", "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(["書名", "ISBN13", "URL"])
    writer.writerows(books)

print("完成")