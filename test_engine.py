from ai_engine import LeafDiseaseDetector
import json

# Inisialisasi Engine
try:
    print("Mencoba memuat AI Engine...")
    # Pastikan folder 'ai_models' sudah berisi file .pkl
    engine = LeafDiseaseDetector(model_folder="ai_models")
    
    # Ganti dengan salah satu path gambar tes Anda yang ada di folder dataset
    gambar_tes = "Daun Sehat 2.JPG" 
    
    # Lakukan Prediksi
    hasil = engine.predict_image(gambar_tes)
    
    # Tampilkan Hasil
    print("\n=== HASIL PREDIKSI ===")
    print(json.dumps(hasil, indent=4))
    
except Exception as e:
    print(f"Terjadi Error: {e}")