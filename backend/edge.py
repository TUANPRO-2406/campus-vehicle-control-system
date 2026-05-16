from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import os
import sys

# --- TỐI ƯU HÓA TÀI NGUYÊN CPU CHỐNG TREO MÁY BIÊN ---
# Phải đặt os.environ TRƯỚC KHI import paddle/paddleocr để backend C++ nhận cấu hình đúng
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_use_mkldnn"]     = "0"
os.environ["PADDLE_USE_MKLDNN"]    = "0"
os.environ["FLAGS_new_executor"]   = "0"
os.environ["FLAGS_enable_onednn_layout_opt"] = "0"

import cv2
import time
import json
import re
import queue
import threading
import base64
import logging
import requests
import torch
import numpy as np
from collections import Counter
from datetime import datetime
from ultralytics import YOLO
from paddleocr import PaddleOCR
from fastapi.responses import StreamingResponse
import uvicorn



logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger("EdgeAI")

# ==========================================
# CẤU HÌNH HỆ THỐNG BIÊN
# ==========================================
MODEL_PATH = "ver4_yolov8n.pt"  # Đường dẫn mô hình YOLOv8 tinh chỉnh
DEVICE = '0' if torch.cuda.is_available() else 'cpu'
API_INGEST_URL = "http://localhost:8000/api/logs/ingest"

# Cấu hình luồng Camera (Thay bằng link RTSP nếu dùng camera IP thực tế)
CAMERAS = {
    "IN":  {"id": 1, "source": "../public/video_in.mp4"},
    "OUT": {"id": 2, "source": "../public/video_out.mp4"}
}

VOTE_THRESHOLD = 2       # Số lần đọc trùng tối thiểu để chốt biển số
MIN_SHARPNESS = 3.0      # Ngưỡng độ nét tối thiểu (Laplacian Variance)
OCR_INTERVAL = 0.3       # Khoảng cách thời gian giữa các lượt OCR trên cùng 1 xe (giây)
TIMEOUT_SECONDS = 4.0    # Thời gian tối đa giữ xe trong vùng ROI trước khi chốt ép

# Vùng nhận diện ROI (Điều chỉnh phù hợp góc quét camera)
ROI_POLYGON = np.array([[120, 520], [690, 400], [1800, 500], [790, 1080]], np.int32)

latest_frames = {"IN": None, "OUT": None}

def apply_vn_plate_rules(text: str) -> str:
    """Chuẩn hóa ký tự lỗi phổ biến và định dạng phông biển số VN"""
    text = text.upper().replace(" ", "").replace("-", "").replace(".", "")
    text = re.sub(r'[^A-Z0-9]', '', text)
    
    if len(text) >= 7:
        lst = list(text)
        # Sửa các lỗi AI nhận diện nhầm vị trí chữ/số phổ biến
        corrections = {'8': 'B', '0': 'D', '1': 'A', '4': 'A', '6': 'G', '5': 'S'}
        if lst[2] in corrections: 
            lst[2] = corrections[lst[2]]
        text = "".join(lst)
    return text

def is_inside_roi(box, polygon):
    x1, y1, x2, y2 = box
    bottom_center = (int((x1 + x2) / 2), int(y2))
    return cv2.pointPolygonTest(polygon, bottom_center, False) >= 0

def align_plate(crop_img):
    """Tìm các đường ngang và xoay ảnh biển số về dạng chuẩn để OCR dễ đọc hơn"""
    try:
        gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
        # Khử nhiễu nhẹ để tìm biên tốt hơn
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 150)
        
        # Tìm các đường thẳng bằng Hough Transform
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=40)
        
        if lines is not None:
            angles = []
            for line in lines:
                rho, theta = line[0]
                # Chuyển đổi góc của vector pháp tuyến sang góc của đường thẳng
                angle_deg = (theta * 180 / np.pi) - 90
                # Chỉ quan tâm các đường nằm ngang (nghiêng tối đa 30 độ)
                if -30 < angle_deg < 30:
                    angles.append(angle_deg)
            
            if len(angles) > 0:
                # Lấy góc nghiêng trung bình
                median_angle = np.median(angles)
                
                # Nếu độ nghiêng đáng kể (> 1.5 độ), thực hiện xoay
                if abs(median_angle) > 1.5:
                    h, w = crop_img.shape[:2]
                    center = (w // 2, h // 2)
                    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
                    # Thực hiện xoay, giữ nguyên viền (BORDER_REPLICATE)
                    rotated = cv2.warpAffine(crop_img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
                    return rotated
    except Exception as e:
        logger.warning(f"Lỗi căn chỉnh xoay biển số: {e}")
    return crop_img

class StreamProcessor:
    def __init__(self, cam_label: str, cam_config: dict, ocr_queue: queue.Queue):
        self.cam_label = cam_label
        self.cam_id = cam_config["id"]
        self.source = cam_config["source"]
        self.ocr_queue = ocr_queue
        self.raw_queue = queue.Queue(maxsize=30)
        self.tracking_data = {}
        self.model = YOLO(MODEL_PATH, task='detect')
        
    def start(self):
        threading.Thread(target=self._reader_worker, daemon=True).start()
        threading.Thread(target=self._ai_tracking_worker, daemon=True).start()
        logger.info(f"Khởi động thành công Camera luồng: {self.cam_label}")

    def _reader_worker(self):
        cap = cv2.VideoCapture(self.source)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        frame_time = 1.0 / fps
        while True:
            t0 = time.time()
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            global latest_frames
            latest_frames[self.cam_label] = frame.copy()
            if not self.raw_queue.full():
                self.raw_queue.put(frame)
            sleep_t = frame_time - (time.time() - t0)
            if sleep_t > 0: 
                time.sleep(sleep_t)

    def _ai_tracking_worker(self):
        while True:
            if self.raw_queue.empty():
                time.sleep(0.01)
                continue
            frame = self.raw_queue.get()
            orig_h, orig_w = frame.shape[:2]
            
            results = self.model.track(frame, tracker="bytetrack.yaml", persist=True, verbose=False, device=DEVICE)
            
            if results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                track_ids = results[0].boxes.id.int().cpu().tolist()
                classes = results[0].boxes.cls.int().cpu().tolist()
                
                vehicles, plates = [], []
                for box, tid, cls in zip(boxes, track_ids, classes):
                    if cls in [0, 1]:  # 0: Ô tô, 1: Xe máy
                        if not is_inside_roi(box, ROI_POLYGON): continue
                        vehicles.append({'box': box, 'track_id': tid, 'cls': cls})
                    elif cls == 2:     # 2: Biển số
                        plates.append({'box': box, 'track_id': tid})
                
                now = time.time()
                for plate in plates:
                    px1, py1, px2, py2 = map(int, plate['box'])
                    p_tid = plate['track_id']
                    
                    # Tìm phương tiện bao quanh biển số này
                    matched_v = None
                    pxc, pyc = (px1 + px2) / 2, (py1 + py2) / 2
                    for v in vehicles:
                        vx1, vy1, vx2, vy2 = map(int, v['box'])
                        if vx1 - 10 <= pxc <= vx2 + 10 and vy1 - 10 <= pyc <= vy2 + 10:
                            matched_v = v
                            break
                            
                    if matched_v is None: continue
                    v_tid = matched_v['track_id']
                    v_type = "O to" if matched_v['cls'] == 0 else "Xe may"
                    
                    if v_tid not in self.tracking_data:
                        self.tracking_data[v_tid] = {
                            'results': [], 'final_plate': None, 'sent': False,
                            'roi_entry_time': now, 'last_ocr': 0, 'vehicle_type': v_type,
                            'raw_frame': frame.copy(), 'v_box': matched_v['box'], 'p_box': plate['box']
                        }
                    
                    td = self.tracking_data[v_tid]
                    td['last_seen'] = now
                    
                    if td['sent']: continue
                    
                    # Xử lý Chốt ép (Timeout) khi xe ở trong ROI quá lâu mà chưa đạt ngưỡng Vote
                    if now - td['roi_entry_time'] >= TIMEOUT_SECONDS:
                        td['sent'] = True
                        chot_plate = td['final_plate'] if td['final_plate'] else "UNKNOWN"
                        dispatch_payload(chot_plate, td, self.cam_label, self.cam_id)
                        continue
                        
                    # Gửi vùng cắt biển số vào hàng đợi OCR định kỳ
                    if now - td['last_ocr'] >= OCR_INTERVAL:
                        pad_x, pad_y = 15, 10  # Mở rộng padding 15px ngang, 10px dọc
                        crop = frame[max(0, py1-pad_y):min(orig_h, py2+pad_y), max(0, px1-pad_x):min(orig_w, px2+pad_x)]
                        if crop.size > 0:
                            td['last_ocr'] = now
                            if not self.ocr_queue.full():
                                self.ocr_queue.put((self.cam_label, self.cam_id, v_tid, crop, td))
                                
            # Dọn dẹp dữ liệu theo dõi cũ của các xe đã rời đi
            curr_time = time.time()
            stale = [tid for tid, d in self.tracking_data.items() if curr_time - d.get('last_seen', 0) > 10]
            for tid in stale: del self.tracking_data[tid]

def dispatch_payload(plate_text: str, td: dict, cam_label: str, cam_id: int):
    """Vẽ bounding box và chỉ thực hiện chuyển đổi Base64 khi gửi log lên server trung tâm"""
    try:
        snap = td['raw_frame'].copy()
        # Vẽ khung phương tiện (Màu xanh dương)
        cv2.rectangle(snap, (int(td['v_box'][0]), int(td['v_box'][1])), (int(td['v_box'][2]), int(td['v_box'][3])), (255, 0, 0), 2)
        # Vẽ khung biển số (Màu cam)
        cv2.rectangle(snap, (int(td['p_box'][0]), int(td['p_box'][1])), (int(td['p_box'][2]), int(td['p_box'][3])), (0, 165, 255), 2)
        
        # Nén chất lượng JPEG xuống 60% để giảm tải băng thông đường truyền mạng
        _, buf = cv2.imencode('.jpg', snap, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
        b64_str = "data:image/jpeg;base64," + base64.b64encode(buf).decode('utf-8')
        
        payload = {
            "plate": plate_text,
            "vehicle": td['vehicle_type'],
            "cam_label": cam_label,
            "ma_camera": cam_id,
            "time": datetime.now().isoformat(),
            "image_b64": b64_str
        }
        
        # Gửi dữ liệu phi đồng bộ tới Server chính thông qua HTTP POST REST API
        res = requests.post(API_INGEST_URL, json=payload, timeout=3)
        if res.status_code == 200:
            logger.info(f"Gửi Log thành công [{cam_label}] -> Biển: {plate_text}")
    except requests.exceptions.ConnectionError:
        logger.warning(f"Không thể kết nối đến Máy chủ Trung tâm ({API_INGEST_URL}). Vui lòng đảm bảo 'main.py' đang chạy ở cổng 8000!")
    except requests.exceptions.Timeout:
        logger.warning("Quá thời gian kết nối (Timeout) khi gửi dữ liệu lên Máy chủ Trung tâm.")
    except Exception as e:
        logger.error(f"Lỗi phân phối dữ liệu lên Server chính: {e}")

def ocr_worker(ocr_queue: queue.Queue):
    logger.info("Đang khởi tạo lõi nhận diện ký tự PaddleOCR trên Edge...")
    ocr_model = PaddleOCR(
        use_textline_orientation=False,
        lang="en",
        device="cpu",
        enable_mkldnn=False,
        ir_optim=False,
        det_limit_side_len=960,
        det_db_thresh=0.3,
        det_db_box_thresh=0.5,
        use_mp=False,
        use_onnx=False
    )
    logger.info("PaddleOCR đã sẵn sàng hoạt động.")
    
    while True:
        try:
            item = ocr_queue.get(timeout=1.0)
        except queue.Empty:
            continue
            
        cam_label, cam_id, v_tid, crop_img, td = item
        if td['sent']: continue
        
        try:
            # Căn chỉnh (xoay) biển số trước khi cho vào OCR
            crop_img = align_plate(crop_img)
            ocr_results = ocr_model.ocr(crop_img)
            raw_text = ""
            
            # Kiểm tra cấu trúc kết quả trả về an toàn
            if ocr_results and len(ocr_results) > 0 and ocr_results[0]:
                valid_lines = []
                for line in ocr_results[0]:
                    try:
                        box = line[0]
                        data_part = line[1]
                        if data_part and len(data_part) >= 2:
                            text = str(data_part[0])  # Ký tự chữ đọc được
                            conf = float(data_part[1]) # Độ tin cậy (Confidence)
                            
                            if conf > 0.40:  # Nới lỏng ngưỡng xuống 40% để dễ bắt chữ hơn
                                # Tính Y trung bình của box để phân biệt các dòng text (biển số 2 dòng)
                                center_y = sum(p[1] for p in box) / 4
                                valid_lines.append((center_y, text))
                    except Exception as e:
                        pass
                
                # Sắp xếp các dòng text từ trên xuống dưới (tránh lỗi ghép ngược biển số 2 dòng)
                valid_lines.sort(key=lambda x: x[0])
                raw_text = "".join([v[1] for v in valid_lines])
                        
            cleaned = apply_vn_plate_rules(raw_text)
            if len(cleaned) < 5: cleaned = "UNKNOWN"
            
            td['results'].append(cleaned)
            counter = Counter(td['results'])
            best_plate, count = counter.most_common(1)[0]
            td['final_plate'] = best_plate
            
            # Đạt số lượt biểu quyết an toàn -> Tiến hành chốt biển sớm
            if count >= VOTE_THRESHOLD and best_plate != "UNKNOWN" and not td['sent']:
                td['sent'] = True
                dispatch_payload(best_plate, td, cam_label, cam_id)
                
        except Exception as e:
            logger.error(f"Lỗi tiến trình OCR biên: {e}")

app_edge = FastAPI()
app_edge.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def generate_frames(cam_label: str):
    global latest_frames
    while True:
        frame = latest_frames.get(cam_label)
        if frame is not None:
            # Mã hóa JPEG chất lượng để stream ổn định
            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if ret:
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        await asyncio.sleep(0.03)

@app_edge.get("/video_feed/{cam_label}")
async def video_feed(cam_label: str):
    return StreamingResponse(generate_frames(cam_label), media_type="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    ocr_q = queue.Queue(maxsize=60)
    threading.Thread(target=ocr_worker, args=(ocr_q,), daemon=True).start()
    
    for label, config in CAMERAS.items():
        processor = StreamProcessor(label, config, ocr_q)
        processor.start()
        
    # Chạy uvicorn trên port 8001 cho server edge stream video
    uvicorn.run(app_edge, host="0.0.0.0", port=8001, log_level="info")