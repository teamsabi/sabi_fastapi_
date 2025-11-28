from fastapi import FastAPI, Depends, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from datetime import datetime
from sqlalchemy.orm import Session
from database import engine, get_db
from typing import List
import models
import schemas
from ai_engine import LeafDiseaseDetector
import shutil
import os
import uuid
import json
import warnings

# 1. Matikan Warning
warnings.filterwarnings("ignore", category=UserWarning)

# 2. Inisialisasi
app = FastAPI(title="Smart Farming API")

os.makedirs("static/images", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# 3. Load AI Engine
ai_engine = None
@app.on_event("startup")
def startup_event():
    global ai_engine
    try:
        if os.path.exists("ai_models/model_svm.pkl"):
            ai_engine = LeafDiseaseDetector(model_folder="ai_models")
            print("✅ AI Model Loaded Successfully!")
        else:
            print("⚠️ WARNING: Model tidak ditemukan.")
    except Exception as e:
        print(f"⚠️ WARNING: Gagal load AI Model. Error: {e}")

# Global Variable
MANUAL_WATERING_ON = False

# ==========================================
# 1. ENDPOINT: IOT SENSOR KELEMBAPAN TANAH (Mode: Realtime Gauge)
# ==========================================
@app.post("/iot/soil-data", response_model=schemas.IotResponse)
def receive_soil_data(
    data: schemas.SoilDataInput, 
    db: Session = Depends(get_db)
):
    """
    Cocok untuk Gauge Chart / Speedometer.
    Hanya menyimpan 1 baris data terakhir per tanaman.
    """
    global MANUAL_WATERING_ON
    
    t_id = data.tanaman_id
    mois = data.moisture
    
    pump_status = False
    trigger = "AUTO"

    # Logika Kontrol Pompa
    if mois < 50.0:
        pump_status = True
        print(f"🌱 [AUTO] Kering ({mois}%), Pompa NYALA.")
    elif mois > 70.0:
        pump_status = False
        print(f"💧 [AUTO] Basah ({mois}%), Pompa MATI.")
        if MANUAL_WATERING_ON: 
            MANUAL_WATERING_ON = False 
    
    if MANUAL_WATERING_ON:
        pump_status = True
        trigger = "MANUAL"

    # --- LOGIKA DATABASE (UPDATE OR INSERT) ---
    try:
        # 1. Cari data lama berdasarkan ID Tanaman
        existing_data = db.query(models.LogKelembapan)\
                          .filter(models.LogKelembapan.tanaman_id == t_id)\
                          .first()
        
        if existing_data:
            # === SKENARIO A: UPDATE (Jarum Gauge Bergerak) ===
            # Kita timpa nilai lama dengan nilai baru
            existing_data.kelembapan_tanah = mois
            existing_data.pompa_on = pump_status
            existing_data.sumber_perintah = trigger
            # Paksa update waktu agar kita tahu kapan terakhir update
            # (Penting untuk status 'Last Updated' di Web)
            from sqlalchemy.sql import func
            existing_data.updated_at = func.now()
            
            db.commit()
            print(f"📝 Update Data Tanaman {t_id} -> {mois}%")
            
        else:
            # === SKENARIO B: INSERT (Baru Pertama Kali Pasang) ===
            new_log = models.LogKelembapan(
                tanaman_id=t_id,
                kelembapan_tanah=mois,
                pompa_on=pump_status,
                sumber_perintah=trigger
            )
            db.add(new_log)
            db.commit()
            print(f"✨ Data Baru Tanaman {t_id} -> {mois}%")
            
    except Exception as e:
        print(f"❌ Error DB: {e}")
        db.rollback()
    
    return {"status": "success", "pump": "ON" if pump_status else "OFF"}

# ==========================================
# 2. ENDPOINT: IOT ULTRASONIK TANGKI AIR (Mode: Water Level)
# ==========================================
@app.post("/iot/water-level", response_model=schemas.IotResponse)
def receive_tank_data(
    data: schemas.TankDataInput, 
    db: Session = Depends(get_db)
):
    """
    IoT Mengirim JSON: {"distance_cm": 20.5}
    Logika: Cek data tangki. Jika ada -> Update. Jika belum -> Insert.
    """
    TINGGI_TANGKI_CM = 100.0 
    
    dist = data.distance_cm
    water_level_cm = TINGGI_TANGKI_CM - dist
    if water_level_cm < 0: water_level_cm = 0 
    
    persen = (water_level_cm / TINGGI_TANGKI_CM) * 100
    
    # --- LOGIKA DATABASE (UPDATE OR INSERT) ---
    try:
        # 1. Ambil data pertama yang ada di tabel log_tangki
        # Karena asumsinya cuma ada 1 tangki, kita pakai .first() saja
        existing_data = db.query(models.LogTangki).first()
        
        if existing_data:
            # === SKENARIO A: UPDATE (Data Sudah Ada) ===
            existing_data.ketinggian_air = water_level_cm
            existing_data.persentase_isi = persen
            
            # Update waktu agar Web tahu ini data baru
            from sqlalchemy.sql import func
            existing_data.updated_at = func.now()
            
            db.commit()
            print(f"🛢️ Update Tangki -> {persen:.1f}%")
            
        else:
            # === SKENARIO B: INSERT (Data Belum Ada/Kosong) ===
            new_log = models.LogTangki(
                ketinggian_air=water_level_cm,
                persentase_isi=persen
            )
            db.add(new_log)
            db.commit()
            print(f"✨ Data Baru Tangki -> {persen:.1f}%")
            
    except Exception as e:
        print(f"❌ Error DB Tangki: {e}")
        db.rollback()
    
    return {"status": "recorded", "level_percent": persen}

# ==========================================
# 3. ENDPOINT: DETEKSI PENYAKIT (ESP32-CAM)
# ==========================================
@app.post("/iot/detect-disease", response_model=schemas.DiseaseResponse)
async def detect_disease(
    tanaman_id: int, 
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    if not ai_engine:
        raise HTTPException(status_code=500, detail="AI Engine belum siap")

    # A. Simpan Gambar
    waktu_sekarang = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{waktu_sekarang}_tanaman{tanaman_id}.jpg" 
    
    file_path = f"static/images/{filename}"
    
    # Simpan fisik file
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal simpan gambar: {e}")

    # B. Prediksi Menggunakan AI Engine
    print(f"🔍 Analisa: {filename} ...")
    hasil_ai = ai_engine.predict_image(file_path)
    
    nama_penyakit = hasil_ai["dominan"]     # Contoh: "Bercak Daun"
    confidence = hasil_ai["confidence"]
    detail_json = json.dumps(hasil_ai["detail"])

    # C. LOGIKA PENCARIAN ID (Sesuai Keinginan Anda)
    # Langkah 1: Cari di tabel rekomendasi_zat, baris mana yang nama_penyakit-nya sama dengan hasil AI
    rekomendasi_item = db.query(models.RekomendasiZat)\
                         .filter(models.RekomendasiZat.nama_penyakit == nama_penyakit)\
                         .first()
    
    # Langkah 2: Jika ketemu, ambil ID-nya. Jika tidak (misal "Sehat"), biarkan None/Null.
    rekomendasi_id = rekomendasi_item.id if rekomendasi_item else None
    
    # Langkah 3: Ambil teks rekomendasi untuk dikirim balik ke ESP32/HP (Opsional)
    # PERBAIKAN: Ganti .zat_aktif menjadi .rekomendasi (Sesuai kolom database Anda)
    rekomendasi_text = rekomendasi_item.rekomendasi if rekomendasi_item else "Tidak ada tindakan khusus"

    # D. Simpan ke Database
    try:
        new_disease = models.PenyakitDaun(
            tanaman_id=tanaman_id,
            user_id=1, 
            gambar=file_path,
            hasil_deteksi=nama_penyakit,
            tingkat_keyakinan=confidence,
            detail_persentase=detail_json,
            rekomendasi_id=rekomendasi_id # <--- ID yang ditemukan tadi disimpan di sini
        )
        db.add(new_disease)
        db.commit()
    except Exception as e:
        print(f"❌ Error Database Penyakit: {e}")
        # Lanjut saja agar return tetap jalan

    print(f"✅ Selesai. Hasil: {nama_penyakit} (ID Rekomendasi: {rekomendasi_id})")

    return {
        "message": "Deteksi Selesai",
        "hasil": nama_penyakit,
        "confidence": confidence,
        "rekomendasi": rekomendasi_text
    }

# ==========================================
# 4. ENDPOINT: KONTROL MANUAL (JSON Body)
# ==========================================
@app.post("/web/manual-control", response_model=schemas.WebControlResponse)
def manual_control(data: schemas.ManualControlInput): # <-- JSON Body
    """
    Web Mengirim JSON: {"action": "on"} atau {"action": "off"}
    """
    global MANUAL_WATERING_ON
    
    act = data.action.lower()
    
    if act == "on":
        MANUAL_WATERING_ON = True
        status_msg = "MANUAL_ON"
        print("🚨 [WEB] Manual Mode ON")
    else:
        MANUAL_WATERING_ON = False
        status_msg = "AUTO"
        print("✅ [WEB] Manual Mode OFF")
        
    return {"status": "success", "mode": status_msg}

# ==========================================
# 5. ENDPOINT: CHART DATA (List Schema Output)
# ==========================================
@app.get("/web/chart-data/{tanaman_id}", response_model=List[schemas.LogKelembapanSchema])
def get_chart_data(tanaman_id: int, limit: int = 20, db: Session = Depends(get_db)):
    data = db.query(models.LogKelembapan)\
             .filter(models.LogKelembapan.tanaman_id == tanaman_id)\
             .order_by(models.LogKelembapan.created_at.desc())\
             .limit(limit)\
             .all()
    return data[::-1]