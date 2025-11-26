from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, Text
from sqlalchemy.sql import func
from database import Base

# Mapping Tabel 'rekomendasi_zat' (Hanya untuk dibaca FastAPI)
class RekomendasiZat(Base):
    __tablename__ = "rekomendasi_zat"
    id = Column(Integer, primary_key=True)
    nama_penyakit = Column(String(255))
    # Kolom lain tidak perlu ditulis kalau FastAPI tidak pakai, cukup yang penting aja

class LogKelembapan(Base):
    __tablename__ = "log_kelembapan"
    id = Column(Integer, primary_key=True, index=True)
    tanaman_id = Column(Integer)
    kelembapan_tanah = Column(Float)
    pompa_on = Column(Boolean)
    sumber_perintah = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

class LogTangki(Base):
    __tablename__ = "log_tangki"
    id = Column(Integer, primary_key=True, index=True)
    ketinggian_air = Column(Float)
    persentase_isi = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

class PenyakitDaun(Base):
    __tablename__ = "penyakit_daun"
    id = Column(Integer, primary_key=True, index=True)
    tanaman_id = Column(Integer)
    user_id = Column(Integer)
    gambar = Column(String(255))
    hasil_deteksi = Column(String(100))
    tingkat_keyakinan = Column(Float)
    detail_persentase = Column(Text) # JSON String
    rekomendasi_id = Column(Integer) # Ini yang akan kita cari otomatis
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())