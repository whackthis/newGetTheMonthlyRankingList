import requests
import csv

RANK_API = "https://athena.eslite.com/api/v1/best_sellers/online/month?l1=3&page={}&per_page=20"
PRODUCT_API = "https://athena.eslite.com/api/v1/products/{}"

headers = {
    "User-Agent": "Mozilla/5.0"
}

books = []

for page in range(1,6):

    print("抓排行榜第",page,"頁")

    data = requests.get(RANK_API.format(page),headers=headers).json()

    for item in data.get("products",[]):

        title = item.get("name","")
        product_id = item.get("id","")

        if not product_id:
            continue

        product_url = PRODUCT_API.format(product_id)

        product_data = requests.get(product_url,headers=headers).json()

        isbn = product_data.get("isbn13","")

        print(title,"->",isbn)

        books.append([title,isbn,product_id])

with open("eslite_isbn.csv","w",newline="",encoding="utf-8-sig") as f:

    writer = csv.writer(f)

    writer.writerow(["書名","ISBN13","product_id"])

    writer.writerows(books)

print("完成")