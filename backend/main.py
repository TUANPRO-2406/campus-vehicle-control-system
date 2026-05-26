# main.py
import os
import uuid
import base64
import logging
from datetime import datetime
from typing import List, Optional
from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# --- KHỞI TẠO HỆ THỐNG LƯU TRỮ ---
IMAGE_DIR = "public/images"
os.makedirs(IMAGE_DIR, exist_ok=True)

DATABASE_URL = "postgresql://postgres:tuan@localhost:5432/vehicle_control_db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CentralServer")

# ==========================================
# CẤU HÌNH CƠ SỞ DỮ LIỆU ORM
# ==========================================
class NhanVien(Base):
    __tablename__ = "nhan_vien"
    MaNhanVien = Column(Integer, primary_key=True, index=True)
    HoTen = Column(String)
    ChucVu = Column(String)
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

class Camera(Base):
    __tablename__ = "camera"
    MaCamera = Column(Integer, primary_key=True, index=True)
    TenCamera = Column(String)
    TenHuongDi = Column(String)

class ThongTinVaoRa(Base):
    __tablename__ = "thong_tin_vao_ra"
    MaLuotVaoRa = Column(Integer, primary_key=True, index=True)
    BienSoXe = Column(String, index=True)
    ThoiGianVao = Column(DateTime, nullable=True)
    HinhAnhVao = Column(String, nullable=True)
    ThoiGianRa = Column(DateTime, nullable=True)
    HinhAnhRa = Column(String, nullable=True)
    MaCamera = Column(Integer, ForeignKey("camera.MaCamera"), nullable=True)
    LoaiXe = Column(String, nullable=True)
    TrangThai = Column(String)

class SuCo(Base):
    __tablename__ = "su_co"
    MaSuCo = Column(Integer, primary_key=True, index=True)
    TenSuCo = Column(String)
    MaLuotVaoRa = Column(Integer, ForeignKey("thong_tin_vao_ra.MaLuotVaoRa"))
    HinhAnh = Column(String)
    TrangThaiXuLy = Column(String)

Base.metadata.create_all(bind=engine)

def migrate_add_loai_xe_column():
    """Thêm cột LoaiXe nếu chưa tồn tại (để hỗ trợ upgrade từ version cũ)"""
    from sqlalchemy import text
    db = SessionLocal()
    try:
        # Kiểm tra xem cột LoaiXe đã tồn tại trong bảng thong_tin_vao_ra chưa
        result = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='thong_tin_vao_ra' AND column_name='LoaiXe'"))
        if not result.fetchone():
            # Nếu chưa tồn tại, thêm cột
            db.execute(text("ALTER TABLE thong_tin_vao_ra ADD COLUMN LoaiXe VARCHAR NULL"))
            db.commit()
            logger.info("✓ Đã thêm cột LoaiXe vào bảng thong_tin_vao_ra")
    except Exception as e:
        logger.warning(f"Migration: {e}")
    finally:
        db.close()

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def init_static_data():
    migrate_add_loai_xe_column()
    db = SessionLocal()
    if not db.query(QuyenHan).first():
        q1 = QuyenHan(Quyen="BAO_VE")
        q2 = QuyenHan(Quyen="QUAN_LY")
        db.add_all([q1, q2])
        db.commit()
        
        nv1 = NhanVien(HoTen="Bảo vệ trực ca", ChucVu="Bảo vệ", TrangThai="ACTIVE")
        db.add(nv1)
        db.commit()
        
        db.add_all([
            TaiKhoan(username="baove", pass_="123", MaQuyenHan=q1.MaQuyenHan),
            TaiKhoan(username="quanly", pass_="123", MaQuyenHan=q2.MaQuyenHan),
            Camera(TenCamera="Camera Cổng Vào", TenHuongDi="IN"),
            Camera(TenCamera="Camera Cổng Ra", TenHuongDi="OUT")
        ])
        db.commit()
    db.close()

# ==========================================
# ĐIỀU PHỐI BIẾN BIẾN ĐỘNG REALTIME (WEBSOCKET)
# ==========================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try: await connection.send_json(message)
            except: pass

ws_manager = ConnectionManager()

# ==========================================
# PYDANTIC SCHEMAS (XÁC THỰC INPUT DỮ LIỆU API)
# ==========================================
class IngestPayload(BaseModel):
    plate: str
    vehicle: str
    cam_label: str
    ma_camera: int
    time: str
    image_b64: str

class LoginRequest(BaseModel):
    username: str
    password: str

class FixPlateRequest(BaseModel):
    correct_plate: str

# ==========================================
# FASTAPI LIFESPAN
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_static_data()
    yield

app = FastAPI(title="Hệ thống Quản lý Bãi xe Server trung tâm", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/public", StaticFiles(directory="public"), name="public")

# ==========================================
# API KHỚP DỮ LIỆU CHÍNH (ĐƯỢC GỌI TỪ EDGE.PY)
# ==========================================
@app.post("/api/logs/ingest")
async def ingest_detection(payload: IngestPayload, db: Session = Depends(get_db)):
    """API tiếp nhận log đóng gói từ thiết bị biên, phân tích CSDL và điều phối thời gian thực"""
    try:
        # Bước 1: Giải mã chuỗi Base64 và ghi tệp tin tĩnh (.jpg)
        header, encoded = payload.image_b64.split(",", 1)
        img_data = base64.b64decode(encoded)
        filename = f"snap_{uuid.uuid4().hex[:10]}.jpg"
        filepath = os.path.join(IMAGE_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(img_data)
        img_url = f"http://localhost:8000/public/images/{filename}"
        
        is_error = payload.plate == "UNKNOWN" or len(payload.plate) < 5
        trang_thai = "CAN_KIEM_TRA" if is_error else "HOP_LE"
        broadcast_data = {}

        # Bước 2: Điều hướng logic nghiệp vụ bãi xe theo Cổng Vào/Ra
        if payload.cam_label == "IN":
            new_log = ThongTinVaoRa(
                BienSoXe=payload.plate,
                ThoiGianVao=datetime.now(),
                HinhAnhVao=img_url,
                MaCamera=payload.ma_camera,
                LoaiXe=payload.vehicle,
                TrangThai=trang_thai
            )
            db.add(new_log)
            db.commit()
            db.refresh(new_log)
            
            if is_error:
                db.add(SuCo(TenSuCo="AI_DOC_SAI", MaLuotVaoRa=new_log.MaLuotVaoRa, HinhAnh=img_url, TrangThaiXuLy="CHUA_XU_LY"))
                db.commit()
                
            broadcast_data = {"action": "ENTRY", "cam_label": payload.cam_label, "plate": payload.plate, "vehicle": payload.vehicle, "time": str(new_log.ThoiGianVao), "image": img_url, "status": trang_thai, "id": new_log.MaLuotVaoRa}

        elif payload.cam_label == "OUT":
            # Kiểm tra xe trùng khớp luồng đã vào trong bãi chưa xe ra chưa có giờ ra
            existing_log = db.query(ThongTinVaoRa).filter(
                ThongTinVaoRa.BienSoXe == payload.plate,
                ThongTinVaoRa.ThoiGianRa == None
            ).order_by(ThongTinVaoRa.ThoiGianVao.desc()).first()
            
            if existing_log and not is_error:
                existing_log.ThoiGianRa = datetime.now()
                existing_log.HinhAnhRa = img_url
                db.commit()
                broadcast_data = {"action": "EXIT", "cam_label": payload.cam_label, "plate": payload.plate, "vehicle": existing_log.LoaiXe, "time": str(existing_log.ThoiGianRa), "image": img_url, "status": "HOP_LE", "id": existing_log.MaLuotVaoRa}
            else:
                # Cảnh báo bất thường: Ra không có lượt vào hoặc AI biên đọc sai dữ liệu
                new_log = ThongTinVaoRa(
                    BienSoXe=payload.plate,
                    ThoiGianRa=datetime.now(),
                    HinhAnhRa=img_url,
                    MaCamera=payload.ma_camera,
                    LoaiXe=payload.vehicle,
                    TrangThai="CAN_KIEM_TRA"
                )
                db.add(new_log)
                db.commit()
                db.refresh(new_log)
                
                su_co_type = "RA_KHONG_CO_LUOT_VAO" if not is_error else "AI_DOC_SAI"
                db.add(SuCo(TenSuCo=su_co_type, MaLuotVaoRa=new_log.MaLuotVaoRa, HinhAnh=img_url, TrangThaiXuLy="CHUA_XU_LY"))
                db.commit()
                broadcast_data = {"action": "EXIT_WARNING", "cam_label": payload.cam_label, "plate": payload.plate, "vehicle": payload.vehicle, "time": str(new_log.ThoiGianRa), "image": img_url, "status": "CAN_KIEM_TRA", "id": new_log.MaLuotVaoRa}

        # Phát tín hiệu lên màn hình giám sát VueJS ngay lập tức thông qua WebSocket
        await ws_manager.broadcast(broadcast_data)
        return {"success": True}
        
    except Exception as e:
        db.rollback()
        logger.error(f"Lỗi API Ingest: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# ==========================================
# CÁC API PHỤC VỤ DASHBOARD FRONTEND VUEJS
# ==========================================
@app.websocket("/ws/live_events")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Giữ trạng thái kết nối Ping/Pong ổn định
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

@app.post("/api/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    acc = db.query(TaiKhoan).filter(TaiKhoan.username == req.username, TaiKhoan.pass_ == req.password).first()
    if not acc:
        raise HTTPException(status_code=401, detail="Sai thông tin tài khoản hoặc mật khẩu")
    quyen = db.query(QuyenHan).filter(QuyenHan.MaQuyenHan == acc.MaQuyenHan).first()
    return {"token": f"token_{acc.username}", "role": quyen.Quyen, "username": acc.username}

@app.get("/api/logs")
def get_logs(db: Session = Depends(get_db)):
    """Truy vấn tối ưu lấy danh sách lượt xe mới nhất giới hạn trong 50 bản ghi"""
    logs = db.query(ThongTinVaoRa).order_by(ThongTinVaoRa.MaLuotVaoRa.desc()).limit(50).all()
    return [{
        "id": log.MaLuotVaoRa,
        "plate": log.BienSoXe,
        "time_in": log.ThoiGianVao,
        "time_out": log.ThoiGianRa,
        "image_in": log.HinhAnhVao,
        "image_out": log.HinhAnhRa,
        "vehicle": log.LoaiXe,
        "status": log.TrangThai
    } for log in logs]

@app.put("/api/logs/{log_id}/fix")
def fix_log(log_id: int, req: FixPlateRequest, db: Session = Depends(get_db)):
    """API sửa đổi biển số thủ công khi phát hiện sự cố hệ thống đọc sai"""
    log = db.query(ThongTinVaoRa).filter(ThongTinVaoRa.MaLuotVaoRa == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Bản ghi không tồn tại")
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
    return {"total_in": total_in, "total_out": total_out, "pending_errors": errors}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)