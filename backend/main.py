"""
main.py — Server Trung Tâm (Central Server)
============================================
Chịu trách nhiệm:
  - Nhận dữ liệu từ edge_client qua WebSocket /ws/camera
  - Lưu thông tin vào/ra vào SQLite database
  - Broadcast sự kiện real-time tới Dashboard qua /ws/live_events
  - Cung cấp REST API cho Dashboard (auth, logs, stats, fix)
  - KHÔNG chứa bất kỳ logic AI (YOLO/OCR) nào

Chạy: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import uuid
import base64
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# ==========================================
# 1. CẤU HÌNH DATABASE
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(BASE_DIR, "public", "images"), exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'parking.db')}"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# 2. ORM MODELS
# ==========================================

class NhanVien(Base):
    __tablename__ = "nhan_vien"
    MaNhanVien = Column(Integer, primary_key=True, index=True)
    HoTen      = Column(String)
    ChucVu     = Column(String)
    NoiCongTac = Column(String, nullable=True)
    TrangThai  = Column(String)

class QuyenHan(Base):
    __tablename__ = "quyen_han"
    MaQuyenHan = Column(Integer, primary_key=True, index=True)
    Quyen      = Column(String, unique=True)

class TaiKhoan(Base):
    __tablename__ = "tai_khoan"
    MaTaiKhoan = Column(Integer, primary_key=True, index=True)
    username   = Column(String, unique=True, index=True)
    pass_      = Column("pass", String)
    MaQuyenHan = Column(Integer, ForeignKey("quyen_han.MaQuyenHan"))
    MaNhanVien = Column(Integer, ForeignKey("nhan_vien.MaNhanVien"))

class LoaiPhuongTien(Base):
    __tablename__ = "loai_phuong_tien"
    MaLoaiPhuongTien = Column(Integer, primary_key=True, index=True)
    LoaiPhuongTien   = Column(String)

class PhuongTien(Base):
    __tablename__ = "phuong_tien"
    MaPhuongTien     = Column(Integer, primary_key=True, index=True)
    MaLoaiPhuongTien = Column(Integer, ForeignKey("loai_phuong_tien.MaLoaiPhuongTien"))
    BienSoXe         = Column(String, unique=True, index=True)
    MaNhanVien       = Column(Integer, ForeignKey("nhan_vien.MaNhanVien"), nullable=True)

class Cong(Base):
    __tablename__ = "cong"
    MaCong  = Column(Integer, primary_key=True, index=True)
    TenCong = Column(String)

class Camera(Base):
    __tablename__ = "camera"
    MaCamera    = Column(Integer, primary_key=True, index=True)
    TenCamera   = Column(String)
    MaCong      = Column(Integer, ForeignKey("cong.MaCong"))
    TenHuongDi  = Column(String)  # 'IN' hoặc 'OUT'

class ThongTinVaoRa(Base):
    __tablename__ = "thong_tin_vao_ra"
    MaLuotVaoRa     = Column(Integer, primary_key=True, index=True)
    MaLoaiPhuongTien= Column(Integer, ForeignKey("loai_phuong_tien.MaLoaiPhuongTien"), nullable=True)
    BienSoXe        = Column(String, index=True)
    ThoiGianVao     = Column(DateTime, nullable=True)
    HinhAnhVao      = Column(String, nullable=True)
    ThoiGianRa      = Column(DateTime, nullable=True)
    HinhAnhRa       = Column(String, nullable=True)
    MaCamera        = Column(Integer, ForeignKey("camera.MaCamera"), nullable=True)
    TrangThai       = Column(String)

class SuCo(Base):
    __tablename__ = "su_co"
    MaSuCo        = Column(Integer, primary_key=True, index=True)
    TenSuCo       = Column(String)
    MaCamera      = Column(Integer, ForeignKey("camera.MaCamera"), nullable=True)
    MaLuotVaoRa   = Column(Integer, ForeignKey("thong_tin_vao_ra.MaLuotVaoRa"), nullable=True)
    MaNhanVien    = Column(Integer, ForeignKey("nhan_vien.MaNhanVien"), nullable=True)
    HinhAnh       = Column(String, nullable=True)
    TrangThaiXuLy = Column(String)

Base.metadata.create_all(bind=engine)

# ==========================================
# 3. KHỞI TẠO DỮ LIỆU MẪU
# ==========================================

def init_db():
    """Tạo dữ liệu mẫu: quyền, nhân viên, tài khoản, cổng, camera."""
    db = SessionLocal()
    try:
        if db.query(QuyenHan).first():
            return  # Đã có dữ liệu, bỏ qua

        # Quyền hạn
        q_bv = QuyenHan(Quyen="BAO_VE")
        q_ql = QuyenHan(Quyen="QUAN_LY")
        db.add_all([q_bv, q_ql])
        db.commit()

        # Nhân viên
        nv1 = NhanVien(HoTen="Nguyễn Văn An", ChucVu="Bảo vệ", TrangThai="ACTIVE")
        nv2 = NhanVien(HoTen="Trần Thị Bích", ChucVu="Quản lý", TrangThai="ACTIVE")
        db.add_all([nv1, nv2])
        db.commit()

        # Tài khoản — 2 tài khoản để test
        tk1 = TaiKhoan(username="baove",  pass_="123",  MaQuyenHan=q_bv.MaQuyenHan, MaNhanVien=nv1.MaNhanVien)
        tk2 = TaiKhoan(username="quanly", pass_="123", MaQuyenHan=q_ql.MaQuyenHan, MaNhanVien=nv2.MaNhanVien)
        db.add_all([tk1, tk2])
        db.commit()

        # Cổng & Camera
        cong = Cong(TenCong="Cổng Chính")
        db.add(cong)
        db.commit()

        cam_in  = Camera(TenCamera="Camera IN",  MaCong=cong.MaCong, TenHuongDi="IN")
        cam_out = Camera(TenCamera="Camera OUT", MaCong=cong.MaCong, TenHuongDi="OUT")
        db.add_all([cam_in, cam_out])
        db.commit()

        print("[DB] ✅ Dữ liệu mẫu đã được tạo")
        print("[DB]    Tài khoản bảo vệ : baove  / baove123")
        print("[DB]    Tài khoản quản lý: quanly / quanly123")
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 4. PYDANTIC SCHEMAS
# ==========================================

class LoginRequest(BaseModel):
    username: str
    password: str

class FixPlateRequest(BaseModel):
    correct_plate: str

class RegisterPlateRequest(BaseModel):
    bien_so:          str
    ma_loai:          int
    ma_nhan_vien:     Optional[int] = None

# ==========================================
# 5. WEBSOCKET MANAGER
# ==========================================

class ConnectionManager:
    """Quản lý kết nối WebSocket từ nhiều Dashboard client."""

    def __init__(self):
        self.frontends: List[WebSocket] = []  # Dashboard
        self.edges: List[WebSocket]     = []  # Edge clients

    async def connect_frontend(self, ws: WebSocket):
        await ws.accept()
        self.frontends.append(ws)
        print(f"[WS] Dashboard kết nối. Tổng: {len(self.frontends)}")

    async def connect_edge(self, ws: WebSocket):
        await ws.accept()
        self.edges.append(ws)
        print(f"[WS] Edge client kết nối. Tổng: {len(self.edges)}")

    def disconnect_frontend(self, ws: WebSocket):
        if ws in self.frontends:
            self.frontends.remove(ws)

    def disconnect_edge(self, ws: WebSocket):
        if ws in self.edges:
            self.edges.remove(ws)

    async def broadcast_to_frontends(self, message: dict):
        """Gửi sự kiện real-time tới tất cả Dashboard đang kết nối."""
        dead = []
        for ws in self.frontends:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_frontend(ws)

manager = ConnectionManager()

# ==========================================
# 6. BUSINESS LOGIC — XỬ LÝ SỰ KIỆN XE
# ==========================================

# Cache chống trùng lặp sự kiện trong khoảng COOLDOWN giây
_last_event: dict = {}   # {plate: {"time": float, "log_id": int}}
COOLDOWN_SECS = 30


def _save_image_from_b64(image_b64: str) -> str:
    """Lưu ảnh Base64 vào thư mục public/images, trả về URL tương đối."""
    if not image_b64:
        return ""
    try:
        raw = base64.b64decode(image_b64.split(",")[-1])
        filename = f"{uuid.uuid4().hex[:10]}.jpg"
        path = os.path.join(BASE_DIR, "public", "images", filename)
        with open(path, "wb") as f:
            f.write(raw)
        return f"/public/images/{filename}"
    except Exception as e:
        print(f"[IMG] Lỗi lưu ảnh: {e}")
        return ""


def process_vehicle_event(data: dict, db: Session) -> Optional[dict]:
    """
    Xử lý một sự kiện phát hiện xe từ edge_client.
    Trả về dict event để broadcast, hoặc None nếu bị bỏ qua.
    """
    plate     = (data.get("plate") or "").strip().upper()
    cam_label = data.get("cam_label", "IN").upper()
    cam_id    = data.get("ma_camera")
    vehicle   = data.get("vehicle", "Unknown")
    image_b64 = data.get("image", "")
    now       = datetime.now()

    if not plate or len(plate) < 5:
        return None

    # Chống trùng lặp
    if plate in _last_event:
        if time.time() - _last_event[plate]["time"] < COOLDOWN_SECS:
            return None

    img_url = _save_image_from_b64(image_b64)
    is_error = "UNKNOWN" in plate

    # Kiểm tra biển đã đăng ký
    is_registered = db.query(PhuongTien).filter(PhuongTien.BienSoXe == plate).first() is not None
    trang_thai = "CAN_KIEM_TRA" if is_error else ("HOP_LE" if is_registered else "CHUA_DANG_KY")

    if cam_label == "IN":
        log = ThongTinVaoRa(
            BienSoXe=plate,
            ThoiGianVao=now,
            HinhAnhVao=img_url,
            MaCamera=cam_id,
            TrangThai=trang_thai
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        if is_error:
            db.add(SuCo(TenSuCo="AI_DOC_SAI", MaCamera=cam_id,
                        MaLuotVaoRa=log.MaLuotVaoRa, HinhAnh=img_url, TrangThaiXuLy="CHUA_XU_LY"))
            db.commit()

        _last_event[plate] = {"time": time.time(), "log_id": log.MaLuotVaoRa}
        return {
            "action": "ENTRY", "cam_label": cam_label, "camera": cam_label,
            "plate": plate, "vehicle": vehicle,
            "time": now.isoformat(), "image": img_url,
            "id": log.MaLuotVaoRa, "is_error": is_error,
            "is_registered": is_registered
        }

    elif cam_label == "OUT":
        # Tìm lượt vào chưa có lượt ra
        existing = db.query(ThongTinVaoRa).filter(
            ThongTinVaoRa.BienSoXe == plate,
            ThongTinVaoRa.ThoiGianRa == None
        ).order_by(ThongTinVaoRa.ThoiGianVao.desc()).first()

        if existing and not is_error:
            existing.ThoiGianRa = now
            existing.HinhAnhRa  = img_url
            db.commit()
            db.refresh(existing)
            _last_event[plate] = {"time": time.time(), "log_id": existing.MaLuotVaoRa}
            return {
                "action": "EXIT", "cam_label": cam_label, "camera": cam_label,
                "plate": plate, "vehicle": vehicle,
                "time": now.isoformat(), "image": img_url,
                "id": existing.MaLuotVaoRa, "is_error": False,
                "is_registered": is_registered
            }
        else:
            log = ThongTinVaoRa(
                BienSoXe=plate, ThoiGianRa=now,
                HinhAnhRa=img_url, MaCamera=cam_id, TrangThai="CAN_KIEM_TRA"
            )
            db.add(log)
            db.commit()
            db.refresh(log)

            reason = "AI_DOC_SAI" if is_error else "RA_KHONG_CO_LUOT_VAO"
            db.add(SuCo(TenSuCo=reason, MaCamera=cam_id,
                        MaLuotVaoRa=log.MaLuotVaoRa, HinhAnh=img_url, TrangThaiXuLy="CHUA_XU_LY"))
            db.commit()
            _last_event[plate] = {"time": time.time(), "log_id": log.MaLuotVaoRa}
            return {
                "action": "EXIT_WARNING", "cam_label": cam_label, "camera": cam_label,
                "plate": plate, "vehicle": vehicle,
                "time": now.isoformat(), "image": img_url,
                "id": log.MaLuotVaoRa, "is_error": True,
                "is_registered": is_registered
            }

    return None

# ==========================================
# 7. APP FASTAPI
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Vehicle Monitoring — Central Server", version="2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve ảnh tĩnh
public_dir = os.path.join(BASE_DIR, "public")
os.makedirs(public_dir, exist_ok=True)
app.mount("/public", StaticFiles(directory=public_dir), name="public")

# ==========================================
# 8. WEBSOCKET ENDPOINTS
# ==========================================

@app.websocket("/ws/live_events")
async def ws_frontend(websocket: WebSocket):
    """Dashboard kết nối vào đây để nhận sự kiện real-time."""
    await manager.connect_frontend(websocket)
    try:
        while True:
            await websocket.receive_text()  # Giữ kết nối sống
    except WebSocketDisconnect:
        manager.disconnect_frontend(websocket)


@app.websocket("/ws/camera")
async def ws_camera(websocket: WebSocket):
    """Edge client kết nối vào đây để gửi kết quả AI."""
    await manager.connect_edge(websocket)
    db = SessionLocal()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = __import__('json').loads(raw)
            except Exception:
                continue

            msg_type = data.get("type", "detection")

            # Broadcast frame live ngay lập tức (không cần DB)
            _cam_lbl = data.get("cam_label", "IN")
            await manager.broadcast_to_frontends({
                "type":      "live_frame",
                "cam_label": _cam_lbl,
                "camera":    _cam_lbl,   # alias cho Vue frontend
                "image":     data.get("image", ""),
                "plate":     data.get("plate", "---"),
            })

            # Chỉ xử lý DB khi là sự kiện phát hiện biển số thực
            if msg_type == "detection" and data.get("plate"):
                event = process_vehicle_event(data, db)
                if event:
                    print(f"[SERVER] {event['action']} — {event['plate']} ({event['cam_label']})")
                    await manager.broadcast_to_frontends(event)

    except WebSocketDisconnect:
        manager.disconnect_edge(websocket)
    except Exception as e:
        print(f"[WS/camera] Lỗi: {e}")
        manager.disconnect_edge(websocket)
    finally:
        db.close()

# ==========================================
# 9. REST API — AUTHENTICATION
# ==========================================

@app.post("/api/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    acc = db.query(TaiKhoan).filter(
        TaiKhoan.username == req.username,
        TaiKhoan.pass_    == req.password
    ).first()
    if not acc:
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")

    quyen = db.query(QuyenHan).filter(QuyenHan.MaQuyenHan == acc.MaQuyenHan).first()
    nv    = db.query(NhanVien).filter(NhanVien.MaNhanVien == acc.MaNhanVien).first()

    return {
        "token":    f"token_{acc.username}_{int(time.time())}",
        "role":     quyen.Quyen if quyen else "UNKNOWN",
        "username": acc.username,
        "ho_ten":   nv.HoTen if nv else acc.username,
    }

# ==========================================
# 10. REST API — LOGS & HISTORY
# ==========================================

@app.get("/api/logs")
def get_logs(limit: int = 50, db: Session = Depends(get_db)):
    """Lấy nhật ký vào ra gần nhất."""
    logs = db.query(ThongTinVaoRa).order_by(
        ThongTinVaoRa.ThoiGianVao.desc()
    ).limit(limit).all()

    return [{
        "id":         log.MaLuotVaoRa,
        "plate":      log.BienSoXe,
        "vehicle":    log.MaLoaiPhuongTien,
        "time_in":    log.ThoiGianVao.isoformat() if log.ThoiGianVao else None,
        "time_out":   log.ThoiGianRa.isoformat()  if log.ThoiGianRa  else None,
        "image_in":   log.HinhAnhVao,
        "image_out":  log.HinhAnhRa,
        "status":     log.TrangThai,
        "cam_id":     log.MaCamera,
    } for log in logs]


@app.put("/api/logs/{log_id}/fix")
def fix_log(log_id: int, req: FixPlateRequest, db: Session = Depends(get_db)):
    """Bảo vệ sửa thủ công biển số bị đọc sai."""
    log = db.query(ThongTinVaoRa).filter(ThongTinVaoRa.MaLuotVaoRa == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi")

    log.BienSoXe  = req.correct_plate.strip().upper()
    log.TrangThai = "HOP_LE"

    su_co = db.query(SuCo).filter(SuCo.MaLuotVaoRa == log_id).first()
    if su_co:
        su_co.TrangThaiXuLy = "DA_XU_LY"

    db.commit()
    return {"success": True, "plate": log.BienSoXe, "id": log_id}


@app.get("/api/incidents")
def get_incidents(status: Optional[str] = None, db: Session = Depends(get_db)):
    """Lấy danh sách sự cố (có thể lọc theo trạng thái xử lý)."""
    q = db.query(SuCo)
    if status:
        q = q.filter(SuCo.TrangThaiXuLy == status)
    items = q.order_by(SuCo.MaSuCo.desc()).limit(50).all()
    return [{
        "id":           i.MaSuCo,
        "ten_su_co":    i.TenSuCo,
        "ma_luot":      i.MaLuotVaoRa,
        "hinh_anh":     i.HinhAnh,
        "trang_thai":   i.TrangThaiXuLy,
    } for i in items]


@app.put("/api/incidents/{su_co_id}/resolve")
def resolve_incident(su_co_id: int, db: Session = Depends(get_db)):
    """Đánh dấu sự cố đã được xử lý."""
    sc = db.query(SuCo).filter(SuCo.MaSuCo == su_co_id).first()
    if not sc:
        raise HTTPException(status_code=404, detail="Không tìm thấy sự cố")
    sc.TrangThaiXuLy = "DA_XU_LY"
    db.commit()
    return {"success": True, "id": su_co_id}

# ==========================================
# 11. REST API — STATISTICS
# ==========================================

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    """Thống kê tổng quan."""
    today = datetime.now().date()

    total_in        = db.query(ThongTinVaoRa).filter(ThongTinVaoRa.ThoiGianVao != None).count()
    total_out       = db.query(ThongTinVaoRa).filter(ThongTinVaoRa.ThoiGianRa  != None).count()
    in_today        = db.query(ThongTinVaoRa).filter(
                          func.date(ThongTinVaoRa.ThoiGianVao) == today).count()
    pending_in      = db.query(ThongTinVaoRa).filter(
                          ThongTinVaoRa.ThoiGianRa == None,
                          ThongTinVaoRa.ThoiGianVao != None).count()
    pending_errors  = db.query(SuCo).filter(SuCo.TrangThaiXuLy == "CHUA_XU_LY").count()
    total_incidents = db.query(SuCo).count()

    return {
        "total_in":        total_in,
        "total_out":       total_out,
        "in_today":        in_today,
        "vehicles_inside": pending_in,
        "pending_errors":  pending_errors,
        "total_incidents": total_incidents,
    }


@app.get("/api/stats/hourly")
def get_hourly_stats(db: Session = Depends(get_db)):
    """Thống kê lượt vào theo giờ trong ngày hôm nay."""
    today = datetime.now().date()
    rows = db.query(
        func.strftime('%H', ThongTinVaoRa.ThoiGianVao).label('hour'),
        func.count(ThongTinVaoRa.MaLuotVaoRa).label('count')
    ).filter(
        func.date(ThongTinVaoRa.ThoiGianVao) == today
    ).group_by('hour').all()

    return [{"hour": int(r.hour), "count": r.count} for r in rows]

# ==========================================
# 12. REST API — PHƯƠNG TIỆN & TÀI KHOẢN
# ==========================================

@app.get("/api/vehicles")
def get_vehicles(db: Session = Depends(get_db)):
    """Danh sách xe đã đăng ký."""
    items = db.query(PhuongTien).all()
    return [{
        "id":      v.MaPhuongTien,
        "plate":   v.BienSoXe,
        "type_id": v.MaLoaiPhuongTien,
        "nv_id":   v.MaNhanVien,
    } for v in items]


@app.post("/api/vehicles")
def register_vehicle(req: RegisterPlateRequest, db: Session = Depends(get_db)):
    """Đăng ký biển số mới."""
    existing = db.query(PhuongTien).filter(PhuongTien.BienSoXe == req.bien_so.upper()).first()
    if existing:
        raise HTTPException(status_code=409, detail="Biển số đã tồn tại")
    v = PhuongTien(
        BienSoXe=req.bien_so.upper(),
        MaLoaiPhuongTien=req.ma_loai,
        MaNhanVien=req.ma_nhan_vien
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return {"success": True, "id": v.MaPhuongTien, "plate": v.BienSoXe}


@app.get("/api/accounts")
def get_accounts(db: Session = Depends(get_db)):
    """Danh sách tài khoản (không trả về mật khẩu)."""
    accs = db.query(TaiKhoan).all()
    result = []
    for acc in accs:
        nv    = db.query(NhanVien).filter(NhanVien.MaNhanVien == acc.MaNhanVien).first()
        quyen = db.query(QuyenHan).filter(QuyenHan.MaQuyenHan == acc.MaQuyenHan).first()
        result.append({
            "id":       acc.MaTaiKhoan,
            "username": acc.username,
            "ho_ten":   nv.HoTen if nv else "",
            "role":     quyen.Quyen if quyen else "",
        })
    return result

# ==========================================
# 13. REST API — SETTINGS (CÀI ĐẶT AI)
# ==========================================
import json

SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {"start": "00:00", "end": "23:59", "enabled": True}
    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)

@app.get("/api/settings")
def get_sys_settings():
    return load_settings()

@app.post("/api/settings")
async def update_sys_settings(req: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(req, f)
    return {"success": True, "settings": req}

@app.get("/api/history")
def get_history_paginated(
    page: int = 1, 
    limit: int = 20, 
    plate: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    """API chính cho HistoryView.vue (Có phân trang và tìm kiếm)"""
    query = db.query(ThongTinVaoRa)
    
    # Tìm kiếm theo biển số nếu có
    if plate:
        query = query.filter(ThongTinVaoRa.BienSoXe.contains(plate.upper()))
    
    # Tính toán phân trang
    total = query.count()
    pages = (total + limit - 1) // limit
    
    # Lấy dữ liệu theo offset
    logs = query.order_by(ThongTinVaoRa.MaLuotVaoRa.desc())\
                .offset((page - 1) * limit)\
                .limit(limit).all()
    
    data = [{
        "id":         log.MaLuotVaoRa,
        "plate":      log.BienSoXe,
        "time_in":    log.ThoiGianVao.isoformat() if log.ThoiGianVao else None,
        "time_out":   log.ThoiGianRa.isoformat()  if log.ThoiGianRa  else None,
        "image_in":   log.HinhAnhVao,
        "image_out":  log.HinhAnhRa,
        "status":     log.TrangThai,
    } for log in logs]
    
    return {"data": data, "pages": pages}

# ==========================================
# ENTRY POINT
# ==========================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)