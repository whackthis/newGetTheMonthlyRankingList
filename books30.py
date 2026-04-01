import requests
from bs4 import BeautifulSoup

url = "https://www.books.com.tw/web/sys_saletopb/books/?attribute=30"

headers = {
    "User-Agent": "Mozilla/5.0"
}

# 取得網頁
res = requests.get(url, headers=headers)
res.encoding = "utf-8"

# 解析HTML
soup = BeautifulSoup(res.text, "html.parser")

# 找所有 h4
h4_tags = soup.find_all("h4")

print("抓到的書名：\n")

for h4 in h4_tags:
    title = h4.get_text(strip=True)
    
    # 只保留有中文的標題
    if any('\u4e00' <= ch <= '\u9fff' for ch in title):
        print(title)