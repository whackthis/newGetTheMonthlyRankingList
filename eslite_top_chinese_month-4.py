import requests
import re

url = "https://www.eslite.com/product/10012014082682972728007"
html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text

m = re.search(r'(?:ISBN13|EAN)\s*/\s*(97[89]\d{10})', html)

if m:
    print("抓到 ISBN:", m.group(1))
else:
    print("抓不到")
    print(html[:2000])