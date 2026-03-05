import requests
from bs4 import BeautifulSoup

url = "https://www.books.com.tw/web/sys_saletopb/books/?attribute=30"

headers = {
    "User-Agent": "Mozilla/5.0"
}

res = requests.get(url, headers=headers)
res.encoding = "utf-8"

soup = BeautifulSoup(res.text, "html.parser")

titles = soup.select("h4 a")

for i, t in enumerate(titles, 1):
    print(f"{i}. {t.text.strip()}")