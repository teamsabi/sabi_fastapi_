from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# --- KONFIGURASI DATABASE ---
# Format URL: mysql+pymysql://USERNAME:PASSWORD@HOST:PORT/NAMA_DATABASE

# Hilangkan tanda pagar (#) di bawah ini dan ganti passwordnya, lalu beri pagar pada Opsi 1
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://root:123@127.0.0.1:3306/web"

# 1. Membuat Engine (Mesin penghubung)
# 'pool_pre_ping=True' berguna agar koneksi otomatis nyambung lagi kalau putus
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    pool_pre_ping=True
)

# 2. Membuat Session (Sesi komunikasi)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 3. Membuat Base Class (Induk dari semua model tabel nanti)
Base = declarative_base()

# 4. Dependency (Fungsi 'Get DB')
# Fungsi ini akan dipanggil di setiap endpoint (main.py)
# Gunanya: Buka koneksi -> Lakukan request -> Tutup koneksi otomatis
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()