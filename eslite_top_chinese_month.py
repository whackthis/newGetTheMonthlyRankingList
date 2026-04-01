import requests

url = "https://athena.eslite.com/api/v1/best_sellers/online/month?l1=3&page=1&per_page=100"

headers = {
    "User-Agent": "Mozilla/5.0"
}

res = requests.get(url, headers=headers)
data = res.json()

books = data["products"]

for i, book in enumerate(books, 1):
    print(f"{i}. {book['name']}")