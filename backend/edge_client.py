import os

# --- TỐI ƯU HÓA TÀI NGUYÊN (CHỐNG TREO MÁY) ---
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["OPENBLAS_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_use_mkldnn"]     = "0"
os.environ["PADDLE_USE_MKLDNN"]    = "0"

import cv2
import base64
import asyncio
import websockets
import json
import numpy as np
from ultralytics import YOLO
from paddleocr import PaddleOCR
from datetime import datetime
import time
import threading
import queue
import re
from collections import Counter
import torch

# ==========================================
# CẤU HÌNH — Chỉnh sửa tại đây
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "ver4_yolov8n.pt") # Đảm bảo tên file model đúng
DEVICE = '0' if torch.cuda.is_available() else 'cpu'

PUBLIC_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "public"))
VID_IN_PATH  = os.path.join(PUBLIC_DIR, "video_in.mp4")
VID_OUT_PATH = os.path.join(PUBLIC_DIR, "video_out.mp4")

CAM_IN_ID  = 1   
CAM_OUT_ID = 2   
WS_SERVER = "ws://localhost:8000/ws/camera"

FRAME_WIDTH  = 640
FRAME_HEIGHT = 360
JPEG_QUALITY = 50

VOTE_THRESHOLD = 5
MIN_PLATE_SIZE = 40     
MIN_SHARPNESS  = 15.0   
OCR_INTERVAL   = 0.25   
TIMEOUT_SECONDS = 3.0 # Giới hạn thời gian ép chốt (giây)

# --- KHAI BÁO VÙNG NHẬN DIỆN (ROI) ---
# Ví dụ: Chỉ nhận diện xe ở nửa dưới màn hình (từ y=150 đến y=360)
ROI_POLYGON = np.array([
    [50, 540], [640, 540], 
    [640, 1920], [540, 1080]
], np.int32)

# ==========================================
# HÀM TIỆN ÍCH
# ==========================================
def apply_vn_plate_rules(text: str) -> str:
    text = text.upper().replace(" ", "").replace("-", "").replace(".", "")
    text = re.sub(r'[^A-Z0-9]', '', text)
    if len(text) >= 7:
        lst = list(text)
        corrections = {'8': 'B', '0': 'D', '1': 'A', '4': 'A', '6': 'G'}
        if lst[2] in corrections: lst[2] = corrections[lst[2]]
        text = "".join(lst)
    return text

def get_sharpness(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()

def encode_frame_b64(frame: np.ndarray) -> str:
    resized = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
    _, buf = cv2.imencode('.jpg', resized, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode('utf-8')

def is_inside_roi(box, polygon):
    """Kiểm tra xem điểm giữa-dưới (bottom-center) của bounding box có nằm trong ROI không"""
    x1, y1, x2, y2 = box
    bottom_center = (int((x1 + x2) / 2), int(y2))
    result = cv2.pointPolygonTest(polygon, bottom_center, False)
    return result >= 0

# ==========================================
# LỚP XỬ LÝ MỘT LUỒNG VIDEO (KIẾN TRÚC PHI ĐỒNG BỘ)
# ==========================================
class StreamProcessor:
    def __init__(self, video_path: str, cam_label: str, cam_id: int,
                 ocr_queue: queue.Queue, ws_send_callback):
        self.video_path   = video_path
        self.cam_label    = cam_label
        self.cam_id       = cam_id
        self.ocr_queue    = ocr_queue
        self.ws_send      = ws_send_callback

        self.raw_queue    = queue.Queue(maxsize=30)
        self.tracking_data: dict = {}
        
        self.latest_frame = None
        self.latest_draw_data = []

        self.model = YOLO(MODEL_PATH, task='detect')
        print(f"[{cam_label}] ✅ Tải YOLO xong — Device: {'GPU' if DEVICE != 'cpu' else 'CPU'}")

    def start(self):
        threading.Thread(target=self._reader_worker,  name=f"reader_{self.cam_label}", daemon=True).start()
        threading.Thread(target=self._ai_worker,      name=f"ai_{self.cam_label}",     daemon=True).start()
        threading.Thread(target=self._live_stream_worker, name=f"stream_{self.cam_label}", daemon=True).start()

    def _reader_worker(self):
        cap = cv2.VideoCapture(self.video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        frame_time = 1.0 / fps

        while True:
            t0 = time.time()
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            self.latest_frame = frame.copy()
            if not self.raw_queue.full():
                self.raw_queue.put(frame)

            sleep_t = frame_time - (time.time() - t0)
            if sleep_t > 0: time.sleep(sleep_t)

    def _live_stream_worker(self):
        fps_stream_delay = 1.0 / 12.0 # ~12 FPS mượt mà
        
        while True:
            t0 = time.time()
            if self.latest_frame is not None:
                display_frame = self.latest_frame.copy()
                
                # Vẽ vùng ROI lên luồng Live (Màu vàng nhạt)
                cv2.polylines(display_frame, [ROI_POLYGON], isClosed=True, color=(0, 255, 255), thickness=2)

                for draw in self.latest_draw_data:
                    color = draw['color']
                    x1, y1, x2, y2 = draw['box']
                    cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)
                    if draw.get('text'):
                        cv2.putText(display_frame, draw['text'], (x1, y1 - 10), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                self.ws_send({
                    "type": "live_frame",
                    "cam_label": self.cam_label,
                    "image": encode_frame_b64(display_frame)
                })

            sleep_t = fps_stream_delay - (time.time() - t0)
            if sleep_t > 0: time.sleep(sleep_t)

    def _ai_worker(self):
        while True:
            if self.raw_queue.empty():
                time.sleep(0.01)
                continue

            frame = self.raw_queue.get()
            orig_h, orig_w = frame.shape[:2]
            current_draw_data = []

            results = self.model.track(frame, tracker="bytetrack.yaml", persist=True, verbose=False, device=DEVICE)

            if results[0].boxes.id is not None:
                boxes     = results[0].boxes.xyxy.cpu().numpy()
                track_ids = results[0].boxes.id.int().cpu().tolist()
                classes   = results[0].boxes.cls.int().cpu().tolist()

                vehicles, plates = [], []

                for box, tid, cls in zip(boxes, track_ids, classes):
                    if cls in [0, 1]:
                        # --- LOGIC ROI: Bỏ qua xe nằm ngoài vùng ROI ---
                        if not is_inside_roi(box, ROI_POLYGON): continue
                        
                        vehicles.append({'box': box, 'track_id': tid, 'cls': cls})
                        current_draw_data.append({'box': list(map(int, box)), 'color': (255, 0, 0)})
                    elif cls == 2:
                        plates.append({'box': box, 'track_id': tid})

                now = time.time()
                for plate in plates:
                    px1, py1, px2, py2 = map(int, plate['box'])
                    p_tid = plate['track_id']

                    if (px2 - px1) < MIN_PLATE_SIZE or (py2 - py1) < 15: continue

                    matched_v = None
                    for v in vehicles:
                        vx1, vy1, vx2, vy2 = map(int, v['box'])
                        if px1 > vx1 - 5 and py1 > vy1 - 5 and px2 < vx2 + 5 and py2 < vy2 + 5:
                            matched_v = v
                            break

                    if matched_v is None: continue
                    vehicle_type = "O to" if matched_v['cls'] == 0 else "Xe may"

                    # Tạo hoặc cập nhật Tracking
                    if p_tid not in self.tracking_data:
                        self.tracking_data[p_tid] = {
                            'results': [], 'final_plate': None, 'sent': False, 
                            'roi_entry_time': now, 'last_ocr': 0, 'vehicle_type': vehicle_type,
                            'best_snapshot': None 
                        }

                    td = self.tracking_data[p_tid]
                    
                    # Cập nhật ảnh snapshot đẹp nhất (kèm khung) liên tục
                    snapshot_frame = frame.copy()
                    cv2.rectangle(snapshot_frame, (int(matched_v['box'][0]), int(matched_v['box'][1])), 
                                 (int(matched_v['box'][2]), int(matched_v['box'][3])), (255, 0, 0), 2)
                    cv2.rectangle(snapshot_frame, (px1, py1), (px2, py2), (0, 165, 255), 2)
                    td['best_snapshot'] = encode_frame_b64(snapshot_frame)

                    plate_text = td['final_plate']
                    current_draw_data.append({
                        'box': [px1, py1, px2, py2], 
                        'color': (0, 255, 0) if td['sent'] else (0, 165, 255), 
                        'text': plate_text if plate_text else 'Wait...'
                    })

                    # Bỏ qua nếu đã gửi lên server
                    if td['sent']: continue

                    # --- CƠ CHẾ TIMEOUT ÉP CHỐT ---
                    time_in_roi = now - td['roi_entry_time']
                    if time_in_roi >= TIMEOUT_SECONDS:
                        td['sent'] = True
                        print(f"[{self.cam_label}] 🔴 TIMEOUT ({TIMEOUT_SECONDS}s) — Chốt ép: UNKNOWN (ID: {p_tid})")
                        self.ws_send({
                            "type":      "detection",
                            "plate":     "UNKNOWN",
                            "vehicle":   td['vehicle_type'],
                            "cam_label": self.cam_label,
                            "ma_camera": self.cam_id,
                            "time":      datetime.now().isoformat(),
                            "image":     td['best_snapshot'],
                        })
                        continue

                    # Gọi OCR nếu chưa tới timeout
                    if now - td['last_ocr'] >= OCR_INTERVAL:
                        plate_crop = frame[max(0, py1 - 5): min(orig_h, py2 + 5), max(0, px1 - 5): min(orig_w, px2 + 5)]
                        if plate_crop.size > 0 and get_sharpness(plate_crop) >= MIN_SHARPNESS:
                            if not self.ocr_queue.full():
                                td['last_ocr'] = now
                                self.ocr_queue.put((self.cam_label, self.cam_id, p_tid, plate_crop, td))

            self.latest_draw_data = current_draw_data
            
            # Xóa các xe đã biến mất quá 5 giây
            current_time = time.time()
            stale = [tid for tid, d in self.tracking_data.items() if current_time - d['roi_entry_time'] > TIMEOUT_SECONDS + 5]
            for tid in stale: del self.tracking_data[tid]

# ==========================================
# LỚP ỨNG DỤNG EDGE CHÍNH & LUỒNG OCR
# ==========================================
class EdgeClientApp:
    def __init__(self):
        self.ocr_queue = queue.Queue(maxsize=60)
        self.ws_queue = None 
        self._ws_loop = None 
        self.running = True

        print("[OCR] Đang tải PaddleOCR (PP-OCRv4 mobile, CPU)...")
        self.ocr_model = PaddleOCR(use_textline_orientation=False, lang="en", device="cpu", enable_mkldnn=False)

        self.stream_in  = StreamProcessor(VID_IN_PATH,  "IN",  CAM_IN_ID, self.ocr_queue, self._ws_enqueue)
        self.stream_out = StreamProcessor(VID_OUT_PATH, "OUT", CAM_OUT_ID, self.ocr_queue, self._ws_enqueue)

    def _ws_enqueue(self, msg: dict):
        if self._ws_loop and self.ws_queue:
            self._ws_loop.call_soon_threadsafe(self.ws_queue.put_nowait, msg)

    def _ocr_worker(self):
        while self.running:
            try: item = self.ocr_queue.get(timeout=1.0)
            except queue.Empty: continue

            if item is None: continue
            cam_label, cam_id, track_id, crop_img, td = item

            if td['sent']: continue # Đã bị Timeout chốt trước đó thì bỏ qua

            try: ocr_results = self.ocr_model.predict(crop_img)
            except Exception: continue

            raw_text = ""
            if ocr_results:
                for page in ocr_results:
                    if not page: continue
                    for text, conf in zip(page.get("rec_texts", []), page.get("rec_scores", [])):
                        if conf > 0.60: raw_text += text

            cleaned = apply_vn_plate_rules(raw_text)
            if len(cleaned) < 5: continue 

            td['results'].append(cleaned)
            counter = Counter(td['results'])
            best_plate, count = counter.most_common(1)[0]
            td['final_plate'] = best_plate

            # --- CHỐT BIỂN THÀNH CÔNG TRƯỚC TIMEOUT ---
            if count >= VOTE_THRESHOLD and not td['sent']:
                td['sent'] = True
                print(f"[{cam_label}] 🟢 CHỐT BIỂN: {best_plate} (ID: {track_id})")
                self._ws_enqueue({
                    "type":      "detection",
                    "plate":     best_plate,
                    "vehicle":   td['vehicle_type'],
                    "cam_label": cam_label,
                    "ma_camera": cam_id,
                    "time":      datetime.now().isoformat(),
                    "image":     td['best_snapshot'],
                })

    async def _ws_sender(self):
        self._ws_loop  = asyncio.get_running_loop()
        self.ws_queue  = asyncio.Queue()
        while self.running:
            try:
                async with websockets.connect(WS_SERVER, max_size=2**24) as ws:
                    print(f"[WS] 🌐 Đã kết nối tới Server: {WS_SERVER}")
                    while self.running:
                        msg = await self.ws_queue.get()
                        await ws.send(json.dumps(msg, ensure_ascii=False))
            except Exception as e:
                print(f"[WS] ⚠️ Mất kết nối. Thử lại sau 3s...")
                await asyncio.sleep(3)

    def start(self):
        threading.Thread(target=self._ocr_worker, daemon=True).start()
        self.stream_in.start()
        self.stream_out.start()
        try: asyncio.run(self._ws_sender())
        except KeyboardInterrupt: self.running = False

if __name__ == "__main__":
    EdgeClientApp().start()