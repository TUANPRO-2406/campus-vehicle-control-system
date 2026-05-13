import cv2
import asyncio
import time
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, func, extract
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import threading
import queue
import numpy as np
from collections import Counter
from ultralytics import YOLO
from paddleocr import PaddleOCR
import re
import torch
import os
import uuid

# ==========================================
# 1. CẤU HÌNH DATABASE
# ==========================================
os.makedirs("public/images", exist_ok=True)
SQLALCHEMY_DATABASE_URL = "sqlite:///./parking.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Lấy đường dẫn thư mục hiện tại của file main.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class NhanVien(Base):
    __tablename__ = "nhan_vien"
    MaNhanVien = Column(Integer, primary_key=True, index=True)
    HoTen = Column(String)
    ChucVu = Column(String)
    NoiCongTac = Column(String)
    TrangThai = Column(String)

class QuyenHan(Base):
    __tablename__ = "quyen_han"
    MaQuyenHan = Column(Integer, primary_key=True, index=True)
    Quyen = Column(String)

class TaiKhoan(Base):
    __tablename__ = "tai_khoan"
    MaTaiKhoan = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    pass_ = Column("pass", String)
    MaQuyenHan = Column(Integer, ForeignKey("quyen_han.MaQuyenHan"))
    MaNhanVien = Column(Integer, ForeignKey("nhan_vien.MaNhanVien"))

class LoaiPhuongTien(Base):
    __tablename__ = "loai_phuong_tien"
    MaLoaiPhuongTien = Column(Integer, primary_key=True, index=True)
    LoaiPhuongTien = Column(String)

class PhuongTien(Base):
    __tablename__ = "phuong_tien"
    MaPhuongTien = Column(Integer, primary_key=True, index=True)
    MaLoaiPhuongTien = Column(Integer, ForeignKey("loai_phuong_tien.MaLoaiPhuongTien"))
    BienSoXe = Column(String, unique=True, index=True)
    MaNhanVien = Column(Integer, ForeignKey("nhan_vien.MaNhanVien"), nullable=True)

class Cong(Base):
    __tablename__ = "cong"
    MaCong = Column(Integer, primary_key=True, index=True)
    TenCong = Column(String)

class Camera(Base):
    __tablename__ = "camera"
    MaCamera = Column(Integer, primary_key=True, index=True)
    TenCamera = Column(String)
    MaCong = Column(Integer, ForeignKey("cong.MaCong"))
    TenHuongDi = Column(String)

class ThongTinVaoRa(Base):
    __tablename__ = "thong_tin_vao_ra"
    MaLuotVaoRa = Column(Integer, primary_key=True, index=True)
    MaLoaiPhuongTien = Column(Integer, ForeignKey("loai_phuong_tien.MaLoaiPhuongTien"), nullable=True)
    BienSoXe = Column(String, index=True)
    ThoiGianVao = Column(DateTime, nullable=True)
    HinhAnhVao = Column(String, nullable=True)
    ThoiGianRa = Column(DateTime, nullable=True)
    HinhAnhRa = Column(String, nullable=True)
    MaCamera = Column(Integer, ForeignKey("camera.MaCamera"), nullable=True)
    TrangThai = Column(String)

class SuCo(Base):
    __tablename__ = "su_co"
    MaSuCo = Column(Integer, primary_key=True, index=True)
    TenSuCo = Column(String)
    MaCamera = Column(Integer, ForeignKey("camera.MaCamera"), nullable=True)
    MaLuotVaoRa = Column(Integer, ForeignKey("thong_tin_vao_ra.MaLuotVaoRa"), nullable=True)
    MaNhanVien = Column(Integer, ForeignKey("nhan_vien.MaNhanVien"), nullable=True)
    HinhAnh = Column(String, nullable=True)
    TrangThaiXuLy = Column(String)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    db = SessionLocal()
    if not db.query(QuyenHan).first():
        q1 = QuyenHan(Quyen="BAO_VE")
        q2 = QuyenHan(Quyen="QUAN_LY")
        db.add_all([q1, q2])
        db.commit()
        
        nv1 = NhanVien(HoTen="Bảo vệ 1", ChucVu="Bảo vệ", TrangThai="ACTIVE")
        nv2 = NhanVien(HoTen="Quản lý 1", ChucVu="Quản lý", TrangThai="ACTIVE")
        db.add_all([nv1, nv2])
        db.commit()
        
        tk1 = TaiKhoan(username="baove", pass_="123", MaQuyenHan=q1.MaQuyenHan, MaNhanVien=nv1.MaNhanVien)
        tk2 = TaiKhoan(username="quanly", pass_="123", MaQuyenHan=q2.MaQuyenHan, MaNhanVien=nv2.MaNhanVien)
        db.add_all([tk1, tk2])
        db.commit()
        
        c1 = Cong(TenCong="Cổng Chính")
        db.add(c1)
        db.commit()
        
        cam1 = Camera(TenCamera="Cam IN", MaCong=c1.MaCong, TenHuongDi="IN")
        cam2 = Camera(TenCamera="Cam OUT", MaCong=c1.MaCong, TenHuongDi="OUT")
        db.add_all([cam1, cam2])
        db.commit()
    db.close()

# ==========================================
# 2. Pydantic Models & Utils
# ==========================================
class LoginRequest(BaseModel):
    username: str
    password: str

class FixPlateRequest(BaseModel):
    correct_plate: str

# ==========================================
# 3. QUẢN LÝ TRẠNG THÁI CACHE & TRACKING
# ==========================================
ACTIVE_TRACKED_VEHICLES = {}
COOLDOWN_TIME = 60

def upload_to_cloud(image_bgr, prefix="plate"):
    filename = f"{prefix}_{uuid.uuid4().hex[:8]}.jpg"
    path = os.path.join("public/images", filename)
    cv2.imwrite(path, image_bgr)
    return f"http://localhost:8000/public/images/{filename}"

def handle_vehicle_detection(plate_text: str, vehicle_type: str, db: Session, cam_label: str, crop_img):
    current_time = time.time()
    
    if plate_text in ACTIVE_TRACKED_VEHICLES:
        time_since_last_seen = current_time - ACTIVE_TRACKED_VEHICLES[plate_text]["last_seen"]
        ACTIVE_TRACKED_VEHICLES[plate_text]["last_seen"] = current_time
        if time_since_last_seen < COOLDOWN_TIME:
            return None
            
    image_url = upload_to_cloud(crop_img)
    cam = db.query(Camera).filter(Camera.TenHuongDi == cam_label).first()
    cam_id = cam.MaCamera if cam else None
    
    is_error = len(plate_text) < 5 or "UNKNOWN" in plate_text
    trang_thai = "CAN_KIEM_TRA" if is_error else "HOP_LE"
    
    if cam_label == "IN":
        new_log = ThongTinVaoRa(
            BienSoXe=plate_text,
            ThoiGianVao=datetime.now(),
            HinhAnhVao=image_url,
            MaCamera=cam_id,
            TrangThai=trang_thai
        )
        db.add(new_log)
        db.commit()
        db.refresh(new_log)
        ACTIVE_TRACKED_VEHICLES[plate_text] = {"last_seen": current_time, "log_id": new_log.MaLuotVaoRa}
        
        if is_error:
            su_co = SuCo(TenSuCo="AI_DOC_SAI", MaCamera=cam_id, MaLuotVaoRa=new_log.MaLuotVaoRa, HinhAnh=image_url, TrangThaiXuLy="CHUA_XU_LY")
            db.add(su_co)
            db.commit()
            
        return {"action": "ENTRY", "camera": cam_label, "plate": plate_text, "vehicle": vehicle_type, "time": str(new_log.ThoiGianVao), "image": image_url, "id": new_log.MaLuotVaoRa, "is_error": is_error}
    
    elif cam_label == "OUT":
        existing_log = db.query(ThongTinVaoRa).filter(
            ThongTinVaoRa.BienSoXe == plate_text,
            ThongTinVaoRa.ThoiGianRa == None
        ).order_by(ThongTinVaoRa.ThoiGianVao.desc()).first()
        
        if existing_log and not is_error:
            existing_log.ThoiGianRa = datetime.now()
            existing_log.HinhAnhRa = image_url
            db.commit()
            db.refresh(existing_log)
            ACTIVE_TRACKED_VEHICLES[plate_text] = {"last_seen": current_time, "log_id": existing_log.MaLuotVaoRa}
            return {"action": "EXIT", "camera": cam_label, "plate": plate_text, "vehicle": vehicle_type, "time": str(existing_log.ThoiGianRa), "image": image_url, "id": existing_log.MaLuotVaoRa, "is_error": False}
        else:
            new_log = ThongTinVaoRa(
                BienSoXe=plate_text,
                ThoiGianRa=datetime.now(),
                HinhAnhRa=image_url,
                MaCamera=cam_id,
                TrangThai="CAN_KIEM_TRA"
            )
            db.add(new_log)
            db.commit()
            db.refresh(new_log)
            ACTIVE_TRACKED_VEHICLES[plate_text] = {"last_seen": current_time, "log_id": new_log.MaLuotVaoRa}
            
            su_co = SuCo(TenSuCo="RA_KHONG_CO_LUOT_VAO" if not is_error else "AI_DOC_SAI", 
                         MaCamera=cam_id, MaLuotVaoRa=new_log.MaLuotVaoRa, HinhAnh=image_url, TrangThaiXuLy="CHUA_XU_LY")
            db.add(su_co)
            db.commit()
            return {"action": "EXIT_WARNING", "camera": cam_label, "plate": plate_text, "vehicle": vehicle_type, "time": str(new_log.ThoiGianRa), "image": image_url, "id": new_log.MaLuotVaoRa, "is_error": True}

# ==========================================
# 4. HỆ THỐNG AI BACKGROUND
# ==========================================
MODEL_PATH = os.path.join(BASE_DIR, "ver4.pt")
DEVICE = '0' if torch.cuda.is_available() else 'cpu'

PUBLIC_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "public"))
VID_IN_PATH = os.path.join(PUBLIC_DIR, "video_out.mp4")
VID_OUT_PATH = os.path.join(PUBLIC_DIR, "video_out.mp4")

class AISystem:
    def __init__(self):
        self.running = False
        self.ocr_queue = queue.Queue(maxsize=50)
        self.raw_queue_in = queue.Queue(maxsize=30)
        self.raw_queue_out = queue.Queue(maxsize=30)
        self.tracking_data_in = {}
        self.tracking_data_out = {}
        
    def start(self):
        self.running = True
        print("[INFO] Đang tải Model YOLO và OCR...")
        self.model_in = YOLO(MODEL_PATH, task='detect')
        self.model_out = YOLO(MODEL_PATH, task='detect')
        self.ocr_model = PaddleOCR(lang="en")
        
        threading.Thread(target=self.video_reader_worker, args=(VID_IN_PATH, self.raw_queue_in), daemon=True).start()
        threading.Thread(target=self.video_reader_worker, args=(VID_OUT_PATH, self.raw_queue_out), daemon=True).start()
        
        threading.Thread(target=self.ai_worker, args=(self.model_in, self.raw_queue_in, self.tracking_data_in, "IN"), daemon=True).start()
        threading.Thread(target=self.ai_worker, args=(self.model_out, self.raw_queue_out, self.tracking_data_out, "OUT"), daemon=True).start()
        
        threading.Thread(target=self.ocr_worker, daemon=True).start()

    def stop(self):
        self.running = False

    def video_reader_worker(self, video_path, raw_queue):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"KHÔNG THỂ MỞ VIDEO TẠI: {video_path}")
            return
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps == 0 or np.isnan(fps): fps = 30.0
        frame_time = 1.0 / fps
        
        while self.running and cap.isOpened():
            start_t = time.time()
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            
            if not raw_queue.full():
                raw_queue.put(frame)
            else:
                time.sleep(0.01)
                
            elapsed = time.time() - start_t
            if elapsed < frame_time:
                time.sleep(frame_time - elapsed)
        cap.release()

    def get_sharpness(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.Laplacian(gray, cv2.CV_64F).var()

    def ocr_worker(self):
        db = SessionLocal()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self.running:
            if not self.ocr_queue.empty():
                item = self.ocr_queue.get()
                if item is None: continue
                cam_label, track_id, crop_img, tracking_data = item
                
                results = self.ocr_model.ocr(crop_img)
                detected_text = ""
                if results and results[0]:
                    for line in results[0]:
                        text = line[1][0]
                        confidence = line[1][1]
                        if confidence > 0.6: 
                            detected_text += text
                            
                cleaned_text = re.sub(r'[^A-Z0-9]', '', detected_text.upper())
                if len(cleaned_text) < 5:
                    cleaned_text = "UNKNOWN"
                
                if track_id in tracking_data:
                    tracking_data[track_id]['results'].append(cleaned_text)
                    counter = Counter(tracking_data[track_id]['results'])
                    best_plate, count = counter.most_common(1)[0]
                    
                    if count >= 3 and not tracking_data[track_id].get('saved', False):
                        tracking_data[track_id]['saved'] = True
                        v_type = tracking_data[track_id].get('vehicle_type', 'Unknown')
                        print(f"[+] {cam_label} - CHỐT: {best_plate} ({v_type})")
                        
                        result = handle_vehicle_detection(best_plate, v_type, db, cam_label, crop_img)
                        if result:
                            loop.run_until_complete(manager.broadcast_log(result))
            else:
                time.sleep(0.01)
        db.close()

    def ai_worker(self, model, raw_queue, tracking_data, cam_label):
        while self.running:
            if raw_queue.empty():
                time.sleep(0.01)
                continue
                
            frame = raw_queue.get()
            orig_h, orig_w = frame.shape[:2]
            
            results = model.track(frame, tracker="bytetrack.yaml", persist=True, verbose=False, device=DEVICE)
            
            if results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                track_ids = results[0].boxes.id.int().cpu().tolist()
                classes = results[0].boxes.cls.int().cpu().tolist()
                
                vehicles = []
                plates = []
                
                for box, track_id, cls in zip(boxes, track_ids, classes):
                    if cls in [0, 1]:
                        vehicles.append({'box': box, 'track_id': track_id, 'cls': cls})
                    elif cls == 2:
                        plates.append({'box': box, 'track_id': track_id})

                for plate in plates:
                    px1, py1, px2, py2 = map(int, plate['box'])
                    p_track_id = plate['track_id']
                    
                    matched_vehicle_cls = 0
                    for v in vehicles:
                        vx1, vy1, vx2, vy2 = map(int, v['box'])
                        if (px1 > vx1 - 5) and (py1 > vy1 - 5) and (px2 < vx2 + 5) and (py2 < vy2 + 5):
                            matched_vehicle_cls = v['cls']
                            break
                            
                    vehicle_type_str = "O to" if matched_vehicle_cls == 0 else "Xe may"
                    
                    if p_track_id not in tracking_data:
                        tracking_data[p_track_id] = {'results': [], 'saved': False, 'last_seen': time.time(), 'last_ocr_time': 0, 'vehicle_type': vehicle_type_str}
                    else:
                        tracking_data[p_track_id]['last_seen'] = time.time()
                        
                    current_t = time.time()
                    if current_t - tracking_data[p_track_id].get('last_ocr_time', 0) > 0.3:
                        plate_crop = frame[max(0, py1-5):min(orig_h, py2+5), max(0, px1-5):min(orig_w, px2+5)]
                        if plate_crop.size > 0 and plate_crop.shape[0] > 15 and plate_crop.shape[1] > 15:
                            if self.ocr_queue.qsize() < 40:
                                tracking_data[p_track_id]['last_ocr_time'] = current_t
                                self.ocr_queue.put((cam_label, p_track_id, plate_crop, tracking_data))      

            current_time = time.time()
            to_delete = [tid for tid, data in tracking_data.items() if current_time - data['last_seen'] > 15]
            for tid in to_delete:
                del tracking_data[tid]

# ==========================================
# 5. FASTAPI WEBSOCKET MANAGER
# ==========================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast_log(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()
ai_system = AISystem()

# ==========================================
# 6. LIFESPAN & ENDPOINTS
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ai_system.start()
    yield
    ai_system.stop()

app = FastAPI(title="Vehicle Monitoring API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/public", StaticFiles(directory="public"), name="public")

@app.websocket("/ws/live_events")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    acc = db.query(TaiKhoan).filter(TaiKhoan.username == req.username, TaiKhoan.pass_ == req.password).first()
    if not acc:
        raise HTTPException(status_code=401, detail="Sai thông tin đăng nhập")
    quyen = db.query(QuyenHan).filter(QuyenHan.MaQuyenHan == acc.MaQuyenHan).first()
    return {"token": "mock_token_" + acc.username, "role": quyen.Quyen, "username": acc.username}

@app.get("/api/logs")
def get_logs(db: Session = Depends(get_db)):
    logs = db.query(ThongTinVaoRa).order_by(ThongTinVaoRa.ThoiGianVao.desc()).limit(50).all()
    res = []
    for log in logs:
        res.append({
            "id": log.MaLuotVaoRa,
            "plate": log.BienSoXe,
            "time_in": log.ThoiGianVao,
            "time_out": log.ThoiGianRa,
            "image_in": log.HinhAnhVao,
            "image_out": log.HinhAnhRa,
            "status": log.TrangThai
        })
    return res

@app.put("/api/logs/{log_id}/fix")
def fix_log(log_id: int, req: FixPlateRequest, db: Session = Depends(get_db)):
    log = db.query(ThongTinVaoRa).filter(ThongTinVaoRa.MaLuotVaoRa == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Not found")
    log.BienSoXe = req.correct_plate
    log.TrangThai = "HOP_LE"
    
    su_co = db.query(SuCo).filter(SuCo.MaLuotVaoRa == log_id).first()
    if su_co:
        su_co.TrangThaiXuLy = "DA_XU_LY"
        
    db.commit()
    return {"success": True, "plate": log.BienSoXe}

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    total_in = db.query(ThongTinVaoRa).filter(ThongTinVaoRa.ThoiGianVao != None).count()
    total_out = db.query(ThongTinVaoRa).filter(ThongTinVaoRa.ThoiGianRa != None).count()
    errors = db.query(SuCo).filter(SuCo.TrangThaiXuLy == "CHUA_XU_LY").count()
    
    return {
        "total_in": total_in,
        "total_out": total_out,
        "pending_errors": errors
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)