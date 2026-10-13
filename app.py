from flask import Flask, render_template
from sqlalchemy import text
from database import engine

app = Flask(__name__)

@app.route("/")
def index():
    # Kiểm tra kết nối và lấy thử danh sách sản phẩm từ database
    products = []
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT ProductName, SellingPrice, MainImage FROM Products LIMIT 5"))
            products = result.fetchall()
    except Exception as e:
        print(f"Lỗi kết nối CSDL: {e}")

    return render_template("index.html", products=products)

if __name__ == "__main__":
    app.run(debug=True)