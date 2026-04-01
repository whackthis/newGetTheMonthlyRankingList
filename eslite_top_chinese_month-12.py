import requests
import csv
import time
from datetime import datetime, timedelta

RANK_API = "https://athena.eslite.com/api/v1/best_sellers/online/month?l1=3&page={}&per_page=20"
PRODUCT_API = "https://athena.eslite.com/api/v1/products/{}"

headers = {
    "User-Agent": "Mozilla/5.0"
}

books = []

for page in range(1, 6):

    print("抓排行榜第", page, "頁")

    try:
        data = requests.get(RANK_API.format(page), headers=headers, timeout=10).json()
    except Exception as e:
        print("排行榜抓取失敗:", e)
        continue

    for item in data.get("products", []):

        product_id = item.get("id", "")

        if not product_id:
            continue

        # RANK_API 抓其他資料
        title = item.get("name", "")
        author = item.get("author", "")
        publisher = item.get("manufacturer", "")

        raw_manufacturer_date = item.get("manufacturer_date", "")
        if raw_manufacturer_date:
            dt = datetime.fromisoformat(raw_manufacturer_date)
            publish_date = (dt + timedelta(days=1)).date().isoformat()
        else:
            publish_date = "wrong_date"
        print(" !raw_manufacturer_date: " + raw_manufacturer_date + " ! \n")
        print(" !publish_date: " + publish_date + " ! ")

        # 商品網址
        product_url = f"https://www.eslite.com/product/{product_id}"

        try:
            product_data = requests.get(
                PRODUCT_API.format(product_id),
                headers=headers,
                timeout=10
            ).json()
        except Exception as e:
            print("商品API錯誤:", e)
            continue

        isbn = (
            product_data.get("isbn13")
            or product_data.get("isbn")
            or product_data.get("ean")
            or ""
        )

        # 正確抓 dual_format
        dual_format = product_data.get("dual_format", {})
        has_dual_book = dual_format.get("has_dual_book", False)

        ebook_status = "有" if has_dual_book else "沒有"

        print(f"{title} | {author} | {publisher} | {publish_date} | {isbn} | {product_id} | {product_url} | {ebook_status}")

        books.append([
            title,
            author,
            publisher,
            publish_date,
            isbn,
            product_id,
            product_url,
            ebook_status
        ])

        time.sleep(0.3)

with open("eslite_books-12.csv", "w", newline="", encoding="utf-8-sig") as f:

    writer = csv.writer(f)

    writer.writerow([
        "書名",
        "作者",
        "出版社",
        "出版日期",
        "ISBN/EAN",
        "product_id",
        "商品網址",
        "是否有電子書"
    ])

    writer.writerows(books)

print("完成")