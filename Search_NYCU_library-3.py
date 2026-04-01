import time
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import quote

# ===== 參數設定 =====
INPUT_FILE = "isbn_list-3-1.xlsx"
OUTPUT_FILE = "isbn_query_result-3-1.xlsx"

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

REQUIRED_COLUMNS = [
    "書名",
    "作者",
    "出版社",
    "出版日期",
    "ISBN/EAN",
    "商品網址",
]


def read_books_from_excel(file_path: str) -> pd.DataFrame:
    """從 Excel 讀取指定欄位"""
    df = pd.read_excel(file_path, dtype=str)

    # 檢查欄位是否存在
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Excel 檔案缺少以下欄位：{', '.join(missing_cols)}"
        )

    # 只保留需要的欄位，並轉成字串
    df = df[REQUIRED_COLUMNS].copy()

    for col in REQUIRED_COLUMNS:
        df[col] = df[col].fillna("").astype(str).str.strip()

    return df


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

    number_of_records = node.text.strip() if node is not None and node.text else ""
    return number_of_records, url


def main():
    try:
        df = read_books_from_excel(INPUT_FILE)
    except Exception as e:
        print(f"讀取 Excel 失敗：{e}")
        return

    if df.empty:
        print("Excel 沒有資料")
        return

    results = []

    print(f"共讀取到 {len(df)} 筆資料，開始查詢...")

    for idx, row in df.iterrows():
        book_name = row["書名"]
        author = row["作者"]
        publisher = row["出版社"]
        publish_date = row["出版日期"]
        isbn = row["ISBN/EAN"]
        product_url = row["商品網址"]

        result_row = {
            "書名": book_name,
            "作者": author,
            "出版社": publisher,
            "出版日期": publish_date,
            "ISBN/EAN": isbn,
            "商品網址": product_url,
            "numberOfRecords": "",
            "是否有館藏": "",
            "error": ""
        }

        try:
            if not isbn:
                result_row["是否有館藏"] = "無ISBN"
                result_row["error"] = "ISBN/EAN 為空白"
                results.append(result_row)
                print(f"[{idx + 1}/{len(df)}] ISBN 空白 -> 略過")
                continue

            number_of_records, query_url = query_number_of_records(isbn)

            has_holding = "是" if number_of_records.isdigit() and int(number_of_records) > 0 else "否"

            result_row["numberOfRecords"] = number_of_records
            result_row["是否有館藏"] = has_holding

            results.append(result_row)

            print(
                f"[{idx + 1}/{len(df)}] {isbn} -> "
                f"numberOfRecords={number_of_records}, 是否有館藏={has_holding}"
            )

        except Exception as e:
            result_row["是否有館藏"] = "查詢失敗"
            result_row["error"] = str(e)
            results.append(result_row)

            print(f"[{idx + 1}/{len(df)}] {isbn} -> 查詢失敗：{e}")

        time.sleep(0.5)  # 避免請求太快

    # 輸出 Excel
    out_df = pd.DataFrame(results)

    # 依指定順序輸出欄位
    output_columns = [
        "書名",
        "作者",
        "出版社",
        "出版日期",
        "ISBN/EAN",
        "商品網址",
        "numberOfRecords",
        "是否有館藏",
        "error"
    ]
    out_df = out_df[output_columns]

    try:
        out_df.to_excel(OUTPUT_FILE, index=False)
        print(f"\n查詢完成，已輸出：{OUTPUT_FILE}")
    except Exception as e:
        print(f"輸出 Excel 失敗：{e}")


if __name__ == "__main__":
    main()