開發撈每月誠品與博客來中文紙本圖書排行榜，並比對是否有館藏後提供採編組採購。可以請教東陽如何進行。


[IT] 網路書店暢銷書相關網址，博客來每次請求間隔需大於 30 秒

1. 誠品暢銷書：https://athena.eslite.com/api/v1/best_sellers/online/month?l1=3&page=1&per_page=100

2. 誠品單一書籍資料網址：https://athena.eslite.com/api/v1/products/{productId}

3. 博客來暢銷書：https://www.books.com.tw/web/sys_saletopb/books/?attribute=30

4. 博客來單一書籍資料網址：https://www.books.com.tw/products/{productId}

5. 館藏查詢（ISBN）：https://nycu.alma.exlibrisgroup.com/view/sru/886UST_NYCU?version=1.2&operation=searchRetrieve&query=alma.isbn={isbn}

增加項目



劉柏凱：
誠品全站暢銷榜、中文書、月榜：
https://www.eslite.com/best-sellers/online/3?type=2

博客來暢銷榜、中文書、月榜：
https://www.books.com.tw/web/sys_saletopb/books/?attribute=30


統計方式：
博客來部分
1. 找到程式碼：books_top_chinese_month-12.py
2. 找到月榜網址：https://www.books.com.tw/web/sys_saletopb/books/?attribute=30
3. 使用ctrl+u撈取如上月榜的原始碼
4. 將如上原始碼貼到目標文件，例如：RANKING_HTML_FILE = Path("books_source-11.html")（可以新增檔案）
5. 修改輸出文件的檔名，OUTPUT_CSV = "books_info-12.csv"
6. 開終端機執行books_top_chinese_month-12.py


誠品部分
1. 找到程式碼：eslite_top_chinese_month-12.py
2. 修改輸出文件的檔名eslite_books-12.csv
