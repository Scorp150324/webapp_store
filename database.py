from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Thay đổi 'root' và mật khẩu của bạn nếu có
DB_USER = "root"
DB_PASSWORD = ""
DB_HOST = "localhost"
DB_PORT = "3306"
DB_NAME = "store_management_db"

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()