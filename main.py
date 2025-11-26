from fastapi import FastAPI, Depends, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database import engine, get_db
from typing import List
import models
import schemas # Import file schemas yang baru
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
# 1. ENDPOINT: IOT SENSOR KELEMBAPAN (JSON Body)
# ==========================================
@app.post("/iot/soil-data", response_model=schemas.IotResponse)
def receive_soil_data(
    data: schemas.SoilDataInput, # <-- MENGGUNAKAN SCHEMA
    db: Session = Depends(get_db)
):
    """
    IoT Mengirim JSON: {"tanaman_id": 1, "moisture": 30.5}
    """
    global MANUAL_WATERING_ON
    
    # Akses data menggunakan titik (.)
    t_id = data.tanaman_id
    mois = data.moisture
    
    pump_status = False
    trigger = "AUTO"

    if mois < 45.0:
        pump_status = True
        print(f"🌱 [AUTO] Kering ({mois}%), Pompa NYALA.")
    elif mois > 60.0:
        pump_status = False
        print(f"💧 [AUTO] Basah ({mois}%), Pompa MATI.")
        if MANUAL_WATERING_ON: 
            MANUAL_WATERING_ON = False 
    
    if MANUAL_WATERING_ON:
        pump_status = True
        trigger = "MANUAL"

    # Simpan ke DB
    try:
        new_log = models.LogKelembapan(
            tanaman_id=t_id,
            kelembapan_tanah=mois,
            pompa_on=pump_status,
            sumber_perintah=trigger
        )
        db.add(new_log)
        db.commit()
    except Exception as e:
        print(f"❌ Error DB: {e}")
    
    return {"status": "success", "pump": "ON" if pump_status else "OFF"}

# ==========================================
# 2. ENDPOINT: IOT ULTRASONIK TANGKI (JSON Body)
# ==========================================
@app.post("/iot/water-level", response_model=schemas.IotResponse)
def receive_tank_data(
    data: schemas.TankDataInput, # <-- MENGGUNAKAN SCHEMA
    db: Session = Depends(get_db)
):
    """
    IoT Mengirim JSON: {"distance_cm": 20.5}
    """
    TINGGI_TANGKI_CM = 100.0 
    
    dist = data.distance_cm
    water_level_cm = TINGGI_TANGKI_CM - dist
    if water_level_cm < 0: water_level_cm = 0 
    
    persen = (water_level_cm / TINGGI_TANGKI_CM) * 100
    
    new_log = models.LogTangki(
        ketinggian_air=water_level_cm,
        persentase_isi=persen
    )
    db.add(new_log)
    db.commit()
    
    return {"status": "recorded", "level_percent": persen}

# ==========================================
# 3. ENDPOINT: DETEKSI PENYAKIT (Multipart Form)
#    NOTE: Upload File TIDAK BISA pakai Pydantic JSON Body standar.
#    Jadi inputnya tetap pakai UploadFile, tapi Outputnya pakai Schema.
# ==========================================
@app.post("/iot/detect-disease", response_model=schemas.DiseaseResponse)
async def detect_disease(
    tanaman_id: int, # Tetap Query/Form param karena bercampur file
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    if not ai_engine:
        raise HTTPException(status_code=500, detail="AI belum siap")

    # A. Simpan Gambar
    filename = f"{uuid.uuid4()}.jpg"
    file_path = f"static/images/{filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # B. Prediksi AI
    print(f"🔍 Analisa: {filename} ...")
    hasil_ai = ai_engine.predict_image(file_path)
    
    nama_penyakit = hasil_ai["dominan"]
    confidence = hasil_ai["confidence"]
    detail_json = json.dumps(hasil_ai["detail"])

    # C. Cari Rekomendasi
    rekomendasi = db.query(models.RekomendasiZat)\
                    .filter(models.RekomendasiZat.nama_penyakit == nama_penyakit)\
                    .first()
    rekomendasi_id = rekomendasi.id if rekomendasi else None
    rekomendasi_text = rekomendasi.zat_aktif if rekomendasi else "Belum ada data"

    # D. Simpan DB
    new_disease = models.PenyakitDaun(
        tanaman_id=tanaman_id,
        user_id=1, 
        gambar=file_path,
        hasil_deteksi=nama_penyakit,
        tingkat_keyakinan=confidence,
        detail_persentase=detail_json,
        rekomendasi_id=rekomendasi_id 
    )
    db.add(new_disease)
    db.commit()

    # Return sesuai Schema DiseaseResponse
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