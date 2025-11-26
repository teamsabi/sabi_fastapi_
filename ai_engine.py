import cv2
import numpy as np
import mahotas
import joblib
import os
import warnings # 1. Import library warnings

# 2. Perintah untuk mematikan UserWarning (tulisan merah di terminal)
warnings.filterwarnings("ignore", category=UserWarning)

class LeafDiseaseDetector:
    def __init__(self, model_folder="ai_models"):
        """
        Saat API dinyalakan, fungsi ini jalan duluan untuk memuat Model ke memori.
        Jadi tidak perlu load berulang-ulang setiap ada request (biar cepat).
        """
        print("--- AI ENGINE: Loading Models... ---")
        
        # Pastikan path file .pkl benar
        path_svm = os.path.join(model_folder, "model_svm.pkl")
        path_scaler = os.path.join(model_folder, "scaler.pkl")
        path_le = os.path.join(model_folder, "label_encoder.pkl")
        
        # Cek apakah file ada
        if not os.path.exists(path_svm):
            raise FileNotFoundError(f"Model tidak ditemukan di: {path_svm}")

        # Load objek
        self.svm = joblib.load(path_svm)
        self.scaler = joblib.load(path_scaler)
        self.le = joblib.load(path_le)
        
        self.PATCH_SIZE = 64
        print("--- AI ENGINE: Ready! ---")

    def _extract_features(self, image):
        """
        Fungsi Privat (internal) untuk ekstraksi fitur patch.
        Logikanya SAMA PERSIS dengan saat training.
        """
        # Konversi Warna
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV) 
        
        # Fitur Warna
        mean_rgb = np.mean(image_rgb, axis=(0,1))
        std_rgb = np.std(image_rgb, axis=(0,1))
        mean_hsv = np.mean(hsv, axis=(0,1))

        # Fitur Tekstur (GLCM)
        try:
            texture = mahotas.features.haralick(gray, ignore_zeros=True).mean(axis=0)
        except ValueError:
            return None

        # Ambil 4 fitur utama
        contrast = texture[1]
        correlation = texture[2]
        energy = texture[8]
        homogeneity = texture[4]

        # Gabungkan jadi list
        features = [
            mean_rgb[0], mean_rgb[1], mean_rgb[2],
            std_rgb[0], std_rgb[1], std_rgb[2],
            mean_hsv[0], mean_hsv[1], mean_hsv[2],
            contrast, correlation, energy, homogeneity
        ]
        return features

    def predict_image(self, image_path):
        """
        Fungsi utama yang dipanggil oleh main.py.
        Input: Path file gambar
        Output: Dictionary hasil diagnosa
        """
        # 1. Baca Gambar
        img = cv2.imread(image_path)
        if img is None:
            return {"status": "error", "message": "Gambar tidak terbaca"}

        # Resize WAJIB sama dengan training (512x512)
        img = cv2.resize(img, (512, 512))
        
        # Preprocessing Masking (Otsu)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5,5), 0)
        _, mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Data Container untuk Voting
        confidence_data = {class_name: [] for class_name in self.le.classes_}
        total_valid_patches = 0
        h, w, _ = img.shape
        
        # 2. Sliding Window (Looping Kotak)
        for y in range(0, h, self.PATCH_SIZE):
            for x in range(0, w, self.PATCH_SIZE):
                patch = img[y:y+self.PATCH_SIZE, x:x+self.PATCH_SIZE]
                patch_mask = mask[y:y+self.PATCH_SIZE, x:x+self.PATCH_SIZE]
                
                # Validasi Ukuran & Isi (Bukan background)
                if patch.shape[0] != self.PATCH_SIZE or patch.shape[1] != self.PATCH_SIZE: continue
                if cv2.countNonZero(patch_mask) < (self.PATCH_SIZE * self.PATCH_SIZE * 0.3): continue 
                
                # Ekstraksi
                feats = self._extract_features(patch)
                if feats is None: continue

                # Scaling & Prediksi
                feats_scaled = self.scaler.transform([feats])
                probs = self.svm.predict_proba(feats_scaled)[0]
                
                # Ambil probabilitas tertinggi
                max_prob = np.max(probs)
                pred_idx = np.argmax(probs)
                pred_label = self.le.inverse_transform([pred_idx])[0]
                
                # Simpan vote
                confidence_data[pred_label].append(max_prob)
                total_valid_patches += 1

        # 3. Hitung Hasil Akhir (Persentase)
        if total_valid_patches == 0:
            return {
                "dominan": "Tidak Terdeteksi",
                "confidence": 0.0,
                "detail": {}
            }

        final_results = {}
        max_area = -1
        dominan_label = "Sehat"
        dominan_conf = 0.0

        for penyakit, list_conf in confidence_data.items():
            count = len(list_conf)
            if count > 0:
                # Hitung % Area
                persen_area = (count / total_valid_patches) * 100
                # Hitung Rata-rata Keyakinan AI
                avg_conf = np.mean(list_conf) * 100
                
                final_results[penyakit] = round(persen_area, 1)
                
                # Cari juara 1 (Dominan)
                if persen_area > max_area:
                    max_area = persen_area
                    dominan_label = penyakit
                    dominan_conf = avg_conf
            else:
                final_results[penyakit] = 0.0

        # Format nama kelas agar rapi (hilangkan underscore)
        clean_dominan = dominan_label.replace("_", " ").title() # "bercak_daun" -> "Bercak Daun"

        # Kembalikan Dictionary rapi untuk JSON
        return {
            "dominan": clean_dominan,     # String untuk kolom 'hasil_deteksi'
            "confidence": round(dominan_conf, 2), # Float untuk kolom 'tingkat_keyakinan'
            "detail": final_results       # Dict untuk kolom 'detail_persentase'
        }