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

SQLALCHEMY_DATABASE_URL = "sqlite:///./parking_v2.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
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
    TrangThai = Column(String)

class SuCo(Base):
    __tablename__ = "su_co"
    MaSuCo = Column(Integer, primary_key=True, index=True)
    TenSuCo = Column(String)
    MaLuotVaoRa = Column(Integer, ForeignKey("thong_tin_vao_ra.MaLuotVaoRa"))
    HinhAnh = Column(String)
    TrangThaiXuLy = Column(String)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try: 
        yield db
    finally: 
        db.close()

def init_static_data():
    db = SessionLocal()
    
    # 1. Khởi tạo dữ liệu gốc nếu DB trống
    if not db.query(QuyenHan).first():
        q1 = QuyenHan(Quyen="BAO_VE")
        q2 = QuyenHan(Quyen="QUAN_LY")
        q3 = QuyenHan(Quyen="ADMIN")
        db.add_all([q1, q2, q3])
        db.commit()
        
        nv1 = NhanVien(HoTen="Bảo vệ trực ca", ChucVu="Bảo vệ", TrangThai="ACTIVE")
        db.add(nv1)
        db.commit()
        
        db.add_all([
            TaiKhoan(username="baove", pass_="123", MaQuyenHan=q1.MaQuyenHan),
            TaiKhoan(username="quanly", pass_="123", MaQuyenHan=q2.MaQuyenHan),
            TaiKhoan(username="admin", pass_="admin123", MaQuyenHan=q3.MaQuyenHan),
            Camera(TenCamera="Camera Cổng Vào", TenHuongDi="IN"),
            Camera(TenCamera="Camera Cổng Ra", TenHuongDi="OUT")
        ])
        db.commit()

    # 2. KIỂM TRA VÀ TẠO TÀI KHOẢN ADMIN TỐI CAO (Chạy độc lập)
    admin_acc = db.query(TaiKhoan).filter(TaiKhoan.username == "admin").first()
    if not admin_acc:
        quyen_ql = db.query(QuyenHan).filter(QuyenHan.Quyen == "ADMIN").first()
        if quyen_ql:
            new_admin = TaiKhoan(
                username="admin", 
                pass_="admin123", # Mật khẩu của tài khoản Admin
                MaQuyenHan=quyen_ql.MaQuyenHan
            )
            db.add(new_admin)
            db.commit()
            print("Đã khởi tạo thành công tài khoản: admin / admin123")
            
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
    
class AccountCreateRequest(BaseModel):
    username: str
    password: str
    role: str  # "BAO_VE", "QUAN_LY" hoặc "ADMIN"
class AccountUpdateRequest(BaseModel):
    username: str
    password: str
    role: str
class AccountUpdateRequest(BaseModel):
    username: str
    password: str
    role: str
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
                TrangThai=trang_thai
            )
            db.add(new_log)
            db.commit()
            db.refresh(new_log)
            
            if is_error:
                db.add(SuCo(TenSuCo="AI_DOC_SAI", MaLuotVaoRa=new_log.MaLuotVaoRa, HinhAnh=img_url, TrangThaiXuLy="CHUA_XU_LY"))
                db.commit()
                
            broadcast_data = {"action": "ENTRY", "plate": payload.plate, "time": str(new_log.ThoiGianVao), "image": img_url, "status": trang_thai, "id": new_log.MaLuotVaoRa}

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
                broadcast_data = {"action": "EXIT", "plate": payload.plate, "time": str(existing_log.ThoiGianRa), "image": img_url, "status": "HOP_LE", "id": existing_log.MaLuotVaoRa}
            else:
                # Cảnh báo bất thường: Ra không có lượt vào hoặc AI biên đọc sai dữ liệu
                new_log = ThongTinVaoRa(
                    BienSoXe=payload.plate,
                    ThoiGianRa=datetime.now(),
                    HinhAnhRa=img_url,
                    MaCamera=payload.ma_camera,
                    TrangThai="CAN_KIEM_TRA"
                )
                db.add(new_log)
                db.commit()
                db.refresh(new_log)
                
                su_co_type = "RA_KHONG_CO_LUOT_VAO" if not is_error else "AI_DOC_SAI"
                db.add(SuCo(TenSuCo=su_co_type, MaLuotVaoRa=new_log.MaLuotVaoRa, HinhAnh=img_url, TrangThaiXuLy="CHUA_XU_LY"))
                db.commit()
                broadcast_data = {"action": "EXIT_WARNING", "plate": payload.plate, "time": str(new_log.ThoiGianRa), "image": img_url, "status": "CAN_KIEM_TRA", "id": new_log.MaLuotVaoRa}

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

# ==========================================
# ĐỊNH NGHĨA CÁC PYDANTIC MODEL NHẬN DỮ LIỆU FRONTEND
# ==========================================
class AccountCreateRequest(BaseModel):
    username: str
    password: str
    role: str

class AccountUpdateRequest(BaseModel):
    username: str
    password: str
    role: str

# ==========================================
# NHÓM API QUẢN TRỊ TÀI KHOẢN (ADMIN ACCOUNTS)
# ==========================================

@app.get("/api/admin/accounts")
def get_all_accounts(db: Session = Depends(get_db)):
    """API lấy toàn bộ danh sách tài khoản kèm quyền hạn tương ứng"""
    accounts = db.query(TaiKhoan, QuyenHan).join(QuyenHan, TaiKhoan.MaQuyenHan == QuyenHan.MaQuyenHan).all()
    
    # Định nghĩa mô tả chức năng tĩnh trực quan cho Frontend hiển thị
    capabilities = {
        "BAO_VE": "Giám sát xe vào/ra trực tiếp, sửa lỗi biển số thủ công khi AI đọc sai.",
        "QUAN_LY": "Xem báo cáo thống kê chuyên sâu toàn diện của khuôn viên trường.",
        "ADMIN": "Quyền hạn tối cao: Quản trị toàn bộ hệ thống, cấp phát và sửa đổi tài khoản mật khẩu."
    }
    
    result = []
    for acc, qh in accounts:
        result.append({
            "id": acc.MaTaiKhoan,
            "username": acc.username,
            "role": qh.Quyen,
            "capability": capabilities.get(qh.Quyen, "Chưa phân quyền chi tiết")
        })
    return result

@app.post("/api/admin/accounts")
def create_new_account(req: AccountCreateRequest, db: Session = Depends(get_db)):
    """API đăng ký cấp tài khoản mới"""
    existing_user = db.query(TaiKhoan).filter(TaiKhoan.username == req.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Tên tài khoản này đã tồn tại trên hệ thống!")
        
    quyen = db.query(QuyenHan).filter(QuyenHan.Quyen == req.role).first()
    if not quyen:
        raise HTTPException(status_code=400, detail="Quyền hạn yêu cầu không hợp lệ!")
        
    new_acc = TaiKhoan(username=req.username, pass_=req.password, MaQuyenHan=quyen.MaQuyenHan)
    db.add(new_acc)
    db.commit()
    return {"success": True, "message": "Cấp tài khoản mới thành công!"}

@app.put("/api/admin/accounts/{account_id}")
def update_account(account_id: int, req: AccountUpdateRequest, db: Session = Depends(get_db)):
    """API cập nhật chỉnh sửa thông tin tài khoản và mật khẩu nhân sự"""
    acc = db.query(TaiKhoan).filter(TaiKhoan.MaTaiKhoan == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản cần cập nhật!")
        
    # Cơ chế bảo vệ an toàn: Không cho phép sửa tài khoản tên gốc 'admin' qua giao diện web
    if acc.username == "admin":
        raise HTTPException(status_code=400, detail="Không cho phép sửa tài khoản quản trị hệ thống gốc!")

    # Kiểm tra xem tên đăng nhập mới có bị trùng lặp với người khác không
    existing_user = db.query(TaiKhoan).filter(TaiKhoan.username == req.username, TaiKhoan.MaTaiKhoan != account_id).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Tên đăng nhập này đã được sử dụng bởi một tài khoản khác!")

    quyen = db.query(QuyenHan).filter(QuyenHan.Quyen == req.role).first()
    if not quyen:
        raise HTTPException(status_code=400, detail="Quyền hạn yêu cầu không hợp lệ!")

    # Tiến hành ghi đè dữ liệu mới
    acc.username = req.username
    acc.pass_ = req.password
    acc.MaQuyenHan = quyen.MaQuyenHan
    
    db.commit()
    return {"success": True, "message": "Cập nhật thông tin tài khoản thành công!"}

@app.delete("/api/admin/accounts/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    """API xóa bỏ quyền truy cập tài khoản"""
    acc = db.query(TaiKhoan).filter(TaiKhoan.MaTaiKhoan == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản cần xóa!")
        
    if acc.username == "quanly" or acc.username == "admin":
        raise HTTPException(status_code=400, detail="Không cho phép xóa tài khoản mặc định cốt lõi của hệ thống!")
        
    db.delete(acc)
    db.commit()
    return {"success": True, "message": "Đã thu hồi tài khoản thành công!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)