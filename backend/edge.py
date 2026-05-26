from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import os
import sys
import concurrent.futures

# ==========================================
# CẤU HÌNH GPU - PHẢI ĐẶT TRƯỚC KHI IMPORT PADDLE/TORCH
# ==========================================
# Giới hạn CPU threads tránh tranh chấp
os.environ["OMP_NUM_THREADS"] = "1"      # Paddle yêu cầu =1 khi không dùng data parallel
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "2"

# Chỉ dùng GPU 0
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

# Paddle GPU flags - PHẢI đặt trước khi import paddle
# Giới hạn Paddle dùng tối đa 500MB VRAM (500/4096 ≈ 12.2% của GTX 1650 4GB)
os.environ["FLAGS_fraction_of_gpu_memory_to_use"] = "0.12"
os.environ["FLAGS_initial_gpu_memory_in_mb"] = "100"
os.environ["FLAGS_reallocate_gpu_memory_in_mb"] = "50"

# Bật Paddle IR optimization và executor mới
os.environ["FLAGS_enable_pir_api"] = "1"
os.environ["FLAGS_new_executor"] = "1"

# Tắt GLOG C++ warnings từ Paddle (angle classifier, cudnn info, v.v.)
# GLOG_minloglevel: 0=INFO, 1=WARNING, 2=ERROR, 3=FATAL
os.environ["GLOG_minloglevel"] = "3"
os.environ["FLAGS_logtostderr"] = "0"

# Tắt MKLDNN (CPU-only) để tránh xung đột với GPU mode
# os.environ["FLAGS_use_mkldnn"]  = "0"   # Không cần khi dùng GPU
# os.environ["PADDLE_USE_MKLDNN"] = "0"   # Không cần khi dùng GPU

# Đảm bảo PyTorch và Paddle không block nhau (async CUDA ops)
os.environ["CUDA_LAUNCH_BLOCKING"] = "0"

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
from datetime import datetime
from ultralytics import YOLO
from paddleocr import PaddleOCR
from fastapi.responses import StreamingResponse
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    force=True  # force=True ngăn uvicorn override logging config của chúng ta
)
logger = logging.getLogger("EdgeAI")

# Suppress warning lặp lại từ ppocr (angle classifier) — áp dụng toàn cục từ đây
class _SuppressAngleWarning(logging.Filter):
    def filter(self, record):
        return "angle classifier" not in record.getMessage()
logging.getLogger("ppocr").setLevel(logging.ERROR)
logging.getLogger("ppocr").addFilter(_SuppressAngleWarning())

# ==========================================
# CẤU HÌNH HỆ THỐNG BIÊN
# ==========================================
MODEL_PATH = "ver4_yolov8n.engine"

# YOLO chạy trên GPU '0' nếu CUDA khả dụng
DEVICE = '0' if torch.cuda.is_available() else 'cpu'

API_INGEST_URL = "http://localhost:8000/api/logs/ingest"

CAMERAS = {
    "IN":  {"id": 1, "source": "../public/video_in.mp4"},
    "OUT": {"id": 2, "source": "../public/video_out.mp4"}
}

TIMEOUT_SECONDS = 3.0 
ROI_POLYGON = np.array([[80, 350], [460, 260], [1200, 330], [530, 720]], np.int32)

latest_frames = {"IN": None, "OUT": None}

# Tạo ThreadPool để gửi API phi đồng bộ, tránh block luồng xử lý AI/OCR
network_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

# ==========================================
# KIỂM TRA GPU STATUS KHI KHỞI ĐỘNG
# ==========================================
def log_gpu_status():
    """Ghi log thông tin GPU để debug"""
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        total_mem = torch.cuda.get_device_properties(0).total_memory / 1024**2
        logger.info(f"[GPU] Phát hiện GPU: {gpu_name} | VRAM: {total_mem:.0f}MB")
        logger.info(f"[GPU] YOLO sẽ chạy trên: device={DEVICE}")
        logger.info(f"[GPU] PaddleOCR sẽ dùng tối đa ~500MB VRAM (12% của {total_mem:.0f}MB)")
    else:
        logger.warning("[GPU] Không phát hiện CUDA - hệ thống sẽ chạy trên CPU!")


def apply_vn_plate_rules(text: str) -> str:
    text = text.upper().replace(" ", "").replace("-", "").replace(".", "")
    text = re.sub(r'[^A-Z0-9]', '', text)
    if len(text) >= 8:
        lst = list(text)
        corrections = {'8': 'B', '0': 'D', '1': 'A', '4': 'A', '6': 'G', '5': 'S'}
        if lst[2] in corrections: 
            lst[2] = corrections[lst[2]]
        text = "".join(lst)
    return text

def is_inside_roi(box, polygon):
    x1, y1, x2, y2 = box
    bottom_center = (int((x1 + x2) / 2), int(y2))
    return cv2.pointPolygonTest(polygon, bottom_center, False) >= 0

def calculate_sharpness(crop_img):
    """Tính độ nét của ảnh bằng phương pháp Laplacian Variance"""
    if crop_img is None or crop_img.size == 0:
        return 0
    gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()

def align_plate(crop_img):
    try:
        gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 150)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=40)
        
        if lines is not None:
            angles = []
            for line in lines:
                rho, theta = line[0]
                angle_deg = (theta * 180 / np.pi) - 90
                if -30 < angle_deg < 30:
                    angles.append(angle_deg)
            if len(angles) > 0:
                median_angle = np.median(angles)
                if abs(median_angle) > 1.5:
                    h, w = crop_img.shape[:2]
                    center = (w // 2, h // 2)
                    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
                    return cv2.warpAffine(crop_img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    except Exception as e:
        logger.warning(f"Lỗi căn chỉnh xoay biển số: {e}")
    return crop_img

class StreamProcessor:
    def __init__(self, cam_label: str, cam_config: dict, ocr_queue: queue.Queue):
        self.cam_label = cam_label
        self.cam_id = cam_config["id"]
        self.source = cam_config["source"]
        self.ocr_queue = ocr_queue
        self.raw_queue = queue.Queue(maxsize=5) # Giảm maxsize để tránh tích tụ frame cũ gây delay stream
        self.tracking_data = {}
        # YOLO khởi tạo với task='detect', sẽ dùng GPU khi gọi track()
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
                
            # ĐỒNG NHẤT VÀ STREAM Ở ĐỘ PHÂN GIẢI 720p (1280x720) Theo yêu cầu
            frame_720p = cv2.resize(frame, (1280, 720))
            
            global latest_frames
            latest_frames[self.cam_label] = frame_720p
            
            # Khử cơ chế queue đầy gây lag luồng stream: Nếu full thì giải phóng bớt frame cũ
            if self.raw_queue.full():
                try: self.raw_queue.get_nowait()
                except queue.Empty: pass
                
            self.raw_queue.put(frame_720p)
            
            sleep_t = frame_time - (time.time() - t0)
            if sleep_t > 0: 
                time.sleep(sleep_t)

    def _ai_tracking_worker(self):
        while True:
            if self.raw_queue.empty():
                time.sleep(0.005)
                continue
            frame = self.raw_queue.get()
            orig_h, orig_w = frame.shape[:2]
            
            # YOLO chạy trên GPU device='0'
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
                    
                    # Tìm phương tiện bao quanh biển số
                    matched_v = None
                    pxc, pyc = (px1 + px2) / 2, (py1 + py2) / 2
                    for v in vehicles:
                        vx1, vy1, vx2, vy2 = map(int, v['box'])
                        if vx1 - 15 <= pxc <= vx2 + 15 and vy1 - 15 <= pyc <= vy2 + 15:
                            matched_v = v
                            break
                            
                    if matched_v is None: continue
                    v_tid = matched_v['track_id']
                    v_type = "O to" if matched_v['cls'] == 0 else "Xe may"
                    
                    # Tính toán chất lượng khung hình (Quality Score = Diện tích biển số * Độ nét)
                    p_width = px2 - px1
                    p_height = py2 - py1
                    p_area = p_width * p_height
                    pad_x, pad_y = 15, 10
                    crop_p = frame[max(0, py1-pad_y):min(orig_h, py2+pad_y), max(0, px1-pad_x):min(orig_w, px2+pad_x)]
                    
                    sharpness = calculate_sharpness(crop_p)
                    quality_score = p_area * sharpness
                    
                    if v_tid not in self.tracking_data:
                        self.tracking_data[v_tid] = {
                            'final_plate': "UNKNOWN", 'sent': False, 'ocr_count': 0,
                            'roi_entry_time': now, 'vehicle_type': v_type,
                            'best_score': -1, 'best_vehicle_crop': None, 'best_plate_crop': None
                        }
                    
                    td = self.tracking_data[v_tid]
                    td['last_seen'] = now
                    
                    if td['sent']: continue
                    
                    # Tiến hành cập nhật khung hình ĐẸP NHẤT (Best Frame Selection)
                    if quality_score > td['best_score'] and crop_p.size > 0:
                        td['best_score'] = quality_score
                        td['best_plate_crop'] = crop_p.copy()
                        
                        # Cắt ảnh phương tiện có kèm padding 15px theo yêu cầu
                        vx1, vy1, vx2, vy2 = map(int, matched_v['box'])
                        v_pad = 15
                        td['best_vehicle_crop'] = frame[max(0, vy1-v_pad):min(orig_h, vy2+v_pad), max(0, vx1-v_pad):min(orig_w, vx2+v_pad)].copy()

                    # CHIẾN LƯỢC KÍCH HOẠT OCR (TỐI ĐA 2 LẦN)
                    # Lần 1: Kích hoạt sớm khi khung hình đầu tiên đạt độ nét cơ bản tốt
                    if td['ocr_count'] == 0 and sharpness > 5.0:
                        td['ocr_count'] += 1
                        if not self.ocr_queue.full():
                            self.ocr_queue.put((self.cam_label, self.cam_id, v_tid, td['best_plate_crop'].copy(), td))
                            
                    # Lần 2 (Fallback): Nếu lần 1 thất bại (hoặc chưa chốt), và tìm thấy khung hình có chất lượng vượt trội hơn hẳn (gấp 1.5 lần ảnh cũ)
                    elif td['ocr_count'] == 1 and quality_score > td['best_score'] * 1.5:
                        td['ocr_count'] += 1
                        if not self.ocr_queue.full():
                            self.ocr_queue.put((self.cam_label, self.cam_id, v_tid, td['best_plate_crop'].copy(), td))

                    # Xử lý Chốt ép (Timeout) khi xe ở trong ROI quá lâu mà chưa có kết quả OCR hợp lệ
                    if now - td['roi_entry_time'] >= TIMEOUT_SECONDS:
                        td['sent'] = True
                        network_executor.submit(dispatch_payload, td['final_plate'], td, self.cam_label, self.cam_id)
                        continue
                                
            # Dọn dẹp dữ liệu theo dõi cũ
            curr_time = time.time()
            stale = [tid for tid, d in self.tracking_data.items() if curr_time - d.get('last_seen', 0) > 8]
            for tid in stale: del self.tracking_data[tid]


def _async_send_request(payload: dict, cam_label: str, plate_text: str):
    """Hàm chạy ngầm trong ThreadPool để đẩy dữ liệu lên Central Server"""
    try:
        res = requests.post(API_INGEST_URL, json=payload, timeout=3)
        if res.status_code == 200:
            logger.info(f"Gửi Log thành công [{cam_label}] -> Biển: {plate_text}")
    except Exception as e:
        logger.warning(f"Lỗi gửi dữ liệu phi đồng bộ lên Server chính: {e}")

def dispatch_payload(plate_text: str, td: dict, cam_label: str, cam_id: int):
    """Xử lý đóng gói ảnh Crop Phương Tiện và submit nhiệm vụ gửi API lên ThreadPool"""
    try:
        # KIỂM TRA VÀ CHỈ GỬI ẢNH CROP PHƯƠNG TIỆN (Theo yêu cầu)
        crop_img = td.get('best_vehicle_crop')
        if crop_img is None or crop_img.size == 0:
            logger.warning("Không có ảnh crop phương tiện hợp lệ, hủy gửi payload.")
            return

        # Nén chất lượng JPEG xuống 65% tối ưu dung lượng truyền tải biên
        _, buf = cv2.imencode('.jpg', crop_img, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
        b64_str = "data:image/jpeg;base64," + base64.b64encode(buf).decode('utf-8')
        
        payload = {
            "plate": plate_text,
            "vehicle": td['vehicle_type'],
            "cam_label": cam_label,
            "ma_camera": cam_id,
            "time": datetime.now().isoformat(),
            "image_b64": b64_str  # Đây là ảnh CROP của phương tiện, không phải ảnh gốc
        }
        
        # Đẩy tác vụ gọi API vào ThreadPool để tránh làm nghẽn luồng xử lý chính
        network_executor.submit(_async_send_request, payload, cam_label, plate_text)
    except Exception as e:
        logger.error(f"Lỗi phân phối dữ liệu: {e}")

def ocr_worker(ocr_queue: queue.Queue, ready_event: threading.Event = None):
    """
    Worker chạy PaddleOCR trên GPU.
    - Dùng device='gpu:0' để chạy inference trên GPU
    - Giới hạn bộ nhớ GPU: 500MB (đã set qua FLAGS_fraction_of_gpu_memory_to_use=0.12)
    - Tắt MKLDNN (CPU-only) để tránh xung đột với GPU context
    - YOLO và Paddle cùng dùng GPU 0 nhưng khác CUDA streams → không conflict
    """
    logger.info("Đang khởi tạo lõi nhận diện ký tự PaddleOCR trên GPU...")

    # Import paddle tại đây để đảm bảo env flags đã được set đầy đủ
    try:
        import paddle
        paddle.device.set_device("gpu:0")
        logger.info(f"[Paddle] Đã set device: {paddle.device.get_device()}")
        logger.info(f"[Paddle] Compiled with CUDA: {paddle.is_compiled_with_cuda()}")
    except Exception as e:
        logger.warning(f"[Paddle] Không thể set GPU device: {e} - sẽ dùng CPU fallback")

    # Khởi tạo PaddleOCR trên GPU
    # Ghi chú quan trọng về conflict resolution:
    # - YOLO (PyTorch) và Paddle đều dùng CUDA 0
    # - PyTorch và Paddle dùng CUDA runtime riêng biệt → không block nhau
    # - Paddle giới hạn 500MB VRAM qua FLAGS_fraction_of_gpu_memory_to_use
    # - YOLO (YOLOv8n) dùng ~400-600MB VRAM
    # - Tổng: ~1.0-1.1GB / 4GB VRAM → an toàn
    ocr_model = PaddleOCR(
        use_textline_orientation=False,
        lang="en",
        device="gpu:0",           # Chạy OCR trên GPU thay vì CPU
        enable_mkldnn=False,      # MKLDNN là CPU-only, phải tắt khi dùng GPU
        ir_optim=True,            # Bật IR optimization để tăng tốc
        det_limit_side_len=320,
        det_db_thresh=0.45,
        det_db_box_thresh=0.6,
        use_mp=False,
        use_onnx=False,
        show_log=False
    )
    logger.info("PaddleOCR đã sẵn sàng hoạt động trên GPU.")

    # Báo hiệu cho main thread biết Paddle đã init xong, có thể khởi YOLO an toàn
    if ready_event is not None:
        ready_event.set()
        logger.info("[Paddle] Đã báo hiệu sẵn sàng cho YOLO!")
    
    while True:
        try:
            item = ocr_queue.get(timeout=1.0)
        except queue.Empty:
            continue
            
        cam_label, cam_id, v_tid, crop_img, td = item
        if td['sent']: continue
        
        try:
            crop_img = align_plate(crop_img)
            t1= time.time()
            ocr_results = ocr_model.ocr(crop_img, cls=False)  # cls=False: tắt angle classifier, không cần thiết cho biển số
            t2= time.time()
            logger.info(f"[OCR-GPU] Thời gian xử lý: {(t2 - t1)*1000:.1f} ms")
            raw_text = ""
            
            if ocr_results and len(ocr_results) > 0 and ocr_results[0]:
                valid_lines = []
                for line in ocr_results[0]:
                    try:
                        box = line[0]
                        data_part = line[1]
                        if data_part and len(data_part) >= 2:
                            text = str(data_part[0])
                            conf = float(data_part[1])
                            if conf > 0.45:
                                center_y = sum(p[1] for p in box) / 4
                                valid_lines.append((center_y, text))
                    except: pass
                
                valid_lines.sort(key=lambda x: x[0])
                raw_text = "".join([v[1] for v in valid_lines])
                        
            cleaned = apply_vn_plate_rules(raw_text)
            
            if len(cleaned) >= 5:
                td['final_plate'] = cleaned
                # Nếu OCR thành công ra biển số hợp lệ -> Chốt luôn không cần đợi chạy lần 2 hoặc timeout
                td['sent'] = True
                dispatch_payload(cleaned, td, cam_label, cam_id)
            else:
                # FALLBACK: Nếu không đọc được (UNKNOWN) và đã hết 2 lượt đọc
                if td['ocr_count'] >= 2:
                    td['final_plate'] = "UNKNOWN"
                    td['sent'] = True
                    dispatch_payload("UNKNOWN", td, cam_label, cam_id)
                
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
            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        await asyncio.sleep(0.05)  # ~20 FPS stream, giảm tải nghẽn mạng FE

@app_edge.get("/video_feed/{cam_label}")
async def video_feed(cam_label: str):
    return StreamingResponse(generate_frames(cam_label), media_type="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    log_gpu_status()

    ocr_q = queue.Queue(maxsize=20)

    # Dùng Event để chờ PaddleOCR init GPU xong thực sự trước khi khởi YOLO
    paddle_ready_event = threading.Event()

    # Khởi động OCR worker trước để Paddle chiếm CUDA context trước YOLO
    threading.Thread(target=ocr_worker, args=(ocr_q, paddle_ready_event), daemon=True).start()

    # Chờ tín hiệu từ ocr_worker rằng PaddleOCR đã sẵn sàng (tối đa 120s)
    logger.info("Đợi PaddleOCR khởi tạo GPU context (có thể mất 15-30s lần đầu)...")
    ready = paddle_ready_event.wait(timeout=120)
    if not ready:
        logger.warning("PaddleOCR khởi tạo quá lâu, tiếp tục khởi động YOLO...")
    else:
        logger.info("PaddleOCR sẵn sàng! Bắt đầu khởi động YOLO cameras...")

    for label, config in CAMERAS.items():
        processor = StreamProcessor(label, config, ocr_q)
        processor.start()

    uvicorn.run(app_edge, host="0.0.0.0", port=8001, log_level="info")