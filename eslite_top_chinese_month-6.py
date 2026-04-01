import requests
import csv

RANK_API = "https://athena.eslite.com/api/v1/best_sellers/online/month?l1=3&page={}&per_page=20"
PRODUCT_API = "https://athena.eslite.com/api/v1/products/{}"

headers = {
    "User-Agent": "Mozilla/5.0"
}

books = []

for page in range(1, 6):
    print("抓排行榜第", page, "頁")

    data = requests.get(RANK_API.format(page), headers=headers).json()

    for item in data.get("products", []):
        title = item.get("name", "")
        product_id = item.get("id", "")

        if not product_id:
            continue

        product_data = requests.get(PRODUCT_API.format(product_id), headers=headers).json()

        # 依序取值：isbn13 → isbn → ean
        code = (
            product_data.get("isbn13")
            or product_data.get("isbn")
            or product_data.get("ean")
            or ""
        )

        author = product_data.get("author", "")
        publisher = product_data.get("manufacturer", "")

        print(title, "->", code)

        books.append([title, code, author, publisher, product_id])

with open("eslite_codes-1.csv", "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(["書名", "ISBN/EAN", "作者", "出版社", "product_id"])
    writer.writerows(books)

print("完成")