from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

# ==========================================
# A. SCHEMA INPUT (DATA MASUK)
#    Digunakan oleh IoT dan Web saat mengirim request (JSON Body)
# ==========================================

# 1. Input Data Kelembapan (Dari IoT)
class SoilDataInput(BaseModel):
    tanaman_id: int
    moisture: float

# 2. Input Data Tangki (Dari IoT)
class TankDataInput(BaseModel):
    distance_cm: float

# 3. Input Kontrol Manual (Dari Web)
class ManualControlInput(BaseModel):
    action: str  # "on" atau "off"

# ==========================================
# B. SCHEMA OUTPUT (DATA KELUAR)
#    Digunakan untuk memformat balasan ke IoT/Web
# ==========================================

# 1. Balasan Standar untuk IoT
class IotResponse(BaseModel):
    status: str
    pump: Optional[str] = None
    level_percent: Optional[float] = None
    mode: Optional[str] = None

# 2. Balasan untuk Web (Manual Control)
class WebControlResponse(BaseModel):
    status: str
    mode: str

# 3. Balasan Deteksi Penyakit
class DiseaseResponse(BaseModel):
    message: str
    hasil: str
    confidence: float
    rekomendasi: str

# 4. Schema untuk Data Log (Agar Grafik Web Rapi)
#    Ini digunakan untuk mengubah object Database menjadi JSON
class LogKelembapanSchema(BaseModel):
    id: int
    tanaman_id: int
    kelembapan_tanah: float
    pompa_on: bool
    created_at: datetime

    class Config:
        from_attributes = True # PENTING: Agar bisa baca data dari SQLAlchemy