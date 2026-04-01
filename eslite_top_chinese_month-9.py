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

        product_id = item.get("id", "")

        if not product_id:
            continue

        # RANK_API 抓其他資料
        title = item.get("name", "")
        author = item.get("author", "")
        publisher = item.get("manufacturer", "")
        publish_date = item.get("manufacturer_date", "")[:10]

        # 商品網址
        product_url = f"https://www.eslite.com/product/{product_id}"

        # PRODUCT_API 抓 ISBN
        product_data = requests.get(PRODUCT_API.format(product_id), headers=headers).json()

        isbn = (
            product_data.get("isbn13")
            or product_data.get("isbn")
            or product_data.get("ean")
            or ""
        )

        print(f"{title} | {author} | {publisher} | {publish_date} | {isbn} | {product_id} | {product_url}")

        books.append([
            title,
            author,
            publisher,
            publish_date,
            isbn,
            product_id,
            product_url
        ])

with open("eslite_books-9.csv", "w", newline="", encoding="utf-8-sig") as f:

    writer = csv.writer(f)

    writer.writerow([
        "書名",
        "作者",
        "出版社",
        "出版日期",
        "ISBN/EAN",
        "product_id",
        "商品網址"
    ])

    writer.writerows(books)

print("完成")