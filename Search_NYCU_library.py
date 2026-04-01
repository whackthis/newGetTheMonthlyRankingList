import requests

url = "https://nycu.primo.exlibrisgroup.com/primaws/rest/pub/pnxs"

headers = {
    "User-Agent": "Mozilla/5.0"
}

def check_book(title):

    params = {
        "q": f"any,contains,{title}",
        "vid": "886UST_NYCU:886UST_NYCU",
        "scope": "MyInst_and_CI",
        "tab": "Everything",
        "lang": "zh-tw",
        "limit": 1,
        "offset": 0
    }

    r = requests.get(url, params=params, headers=headers)
    data = r.json()

    total = data["info"]["total"]

    return total


with open("titles.txt", encoding="utf-8") as f:
    titles = [t.strip() for t in f]

for t in titles:

    total = check_book(t)

    if total > 0:
        print(f"{t} → 有館藏 ({total})")
    else:
        print(f"{t} → 查無館藏")