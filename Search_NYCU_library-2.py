import time
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import quote

# ===== 參數設定 =====
INPUT_FILE = "isbn_list.xlsx"
OUTPUT_FILE = "isbn_query_result-1.xlsx"

URL_TEMPLATE = (
    "https://nycu.alma.exlibrisgroup.com/view/sru/886UST_NYCU"
    "?version=1.2&operation=searchRetrieve&query=alma.isbn={isbn}"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

NS = {
    "srw": "http://www.loc.gov/zing/srw/"
}


def read_isbns_from_excel(file_path: str) -> list[str]:
    """從 Excel 讀取 isbn 欄位"""
    df = pd.read_excel(file_path, dtype={"isbn": str})

    if "isbn" not in df.columns:
        raise ValueError("Excel 檔案中找不到 'isbn' 欄位，請確認第一列欄名為 isbn")

    isbns = (
        df["isbn"]
        .fillna("")
        .astype(str)
        .str.strip()
        .tolist()
    )

    # 過濾空值
    isbns = [isbn for isbn in isbns if isbn]
    return isbns


def query_number_of_records(isbn: str) -> tuple[str, str]:
    """
    查詢單一 ISBN
    回傳: (numberOfRecords, query_url)
    """
    encoded_isbn = quote(isbn)
    url = URL_TEMPLATE.format(isbn=encoded_isbn)

    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    node = root.find(".//srw:numberOfRecords", NS)

    number_of_records = node.text if node is not None else ""
    return number_of_records, url


def main():
    try:
        isbns = read_isbns_from_excel(INPUT_FILE)
    except Exception as e:
        print(f"讀取 Excel 失敗：{e}")
        return

    if not isbns:
        print("Excel 裡沒有可查詢的 ISBN")
        return

    results = []

    print(f"共讀取到 {len(isbns)} 筆 ISBN，開始查詢...")

    for idx, isbn in enumerate(isbns, start=1):
        try:
            number_of_records, query_url = query_number_of_records(isbn)

            # 自動判斷是否有館藏
            has_holding = "是" if number_of_records.isdigit() and int(number_of_records) > 0 else "否"

            results.append({
                "isbn": isbn,
                "numberOfRecords": number_of_records,
                "是否有館藏": has_holding,
                "query_url": query_url
            })

            print(f"[{idx}/{len(isbns)}] {isbn} -> numberOfRecords={number_of_records}, 是否有館藏={has_holding}")

        except Exception as e:
            results.append({
                "isbn": isbn,
                "numberOfRecords": "",
                "是否有館藏": "查詢失敗",
                "query_url": "",
                "error": str(e)
            })

            print(f"[{idx}/{len(isbns)}] {isbn} -> 查詢失敗：{e}")

        time.sleep(0.5)  # 避免請求太快

    # 輸出 Excel
    out_df = pd.DataFrame(results)

    # 若沒有 error 欄，補一欄避免欄位不一致
    if "error" not in out_df.columns:
        out_df["error"] = ""

    try:
        out_df.to_excel(OUTPUT_FILE, index=False)
        print(f"\n查詢完成，已輸出：{OUTPUT_FILE}")
    except Exception as e:
        print(f"輸出 Excel 失敗：{e}")


if __name__ == "__main__":
    main()