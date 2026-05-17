# 🚗 Parking Monitor System - Quick Start Guide

## 📋 Prerequisites
- Python 3.10+ (currently using 3.12)
- Node.js 14+
- Virtual Environment configured

## 🚀 Quick Start (Run All Services)

### Option 1: PowerShell Script (Recommended)
```powershell
# Start Backend Server (main.py)
cd d:\DoAn\backend
python main.py

# In another terminal - Start Edge AI Client
cd d:\DoAn\backend
python edge_client.py

# In another terminal - Start Frontend
cd d:\DoAn\frontend
npm run dev
```

### Option 2: Manual Steps

#### Step 1️⃣: Start Central Server (Port 8000)
```powershell
cd d:\DoAn\backend
python main.py
```
Expected output:
```
[DB] ✅ Dữ liệu mẫu đã được tạo
[INFO] Uvicorn running on http://0.0.0.0:8000
```

#### Step 2️⃣: Start Edge AI Client (Port 8001)
```powershell
cd d:\DoAn\backend
python edge_client.py
```
Expected output:
```
[OCR] PaddleOCR tai xong
[IN] Tai YOLO xong -- Device: GPU
[OUT] Tai YOLO xong -- Device: GPU
[WS] Da ket noi toi Server: ws://localhost:8000/ws/camera
```

#### Step 3️⃣: Start Frontend Development Server
```powershell
cd d:\DoAn\frontend
npm install  # First time only
npm run dev
```
Expected output:
```
  ➜  Local:   http://localhost:5173/
```

## 🔑 Test Credentials
- **Username:** `baove` | **Password:** `123`
- **Username:** `quanly` | **Password:** `123`

## 🧪 Testing the System

### 1. Check Central Server is Running
```
GET http://localhost:8000/api/logs
```
Should return empty array initially

### 2. Check Edge AI is Connected
- Look at central server logs for: `Edge client kết nối`
- Look at edge client logs for: `Da ket noi toi Server`

### 3. Access Dashboard
- Open http://localhost:5173/
- Login with credentials above
- See live video streams from cameras
- Monitor events in real-time

## 📊 System Architecture

```
┌─────────────────┐
│   DASHBOARD     │ (Frontend - Vue.js)
│  Port 5173      │
└────────┬────────┘
         │ WebSocket
         ↓
┌─────────────────────────────────────────┐
│   CENTRAL SERVER - main.py              │
│   Port 8000                             │
│   - Receives AI detections              │
│   - Stores in SQLite DB                 │
│   - Broadcasts to Dashboard             │
└────────┬────────────────────────────────┘
         │ WebSocket
         ↓
┌──────────────────────────────────────────┐
│   EDGE AI CLIENT - edge_client.py        │
│   Port 8001                              │
│   - YOLO vehicle detection               │
│   - PaddleOCR license plate reading      │
│   - Sends results to Central Server      │
└──────────────────────────────────────────┘
         │
         ↓
┌──────────────────────────────────────────┐
│   VIDEO SOURCES                          │
│   - video_in.mp4 (GATE IN)               │
│   - video_out.mp4 (GATE OUT)             │
└──────────────────────────────────────────┘
```

## 🐛 Troubleshooting

### Issue: "Connection refused" on Edge Client
**Solution:** Make sure central server (main.py) is running first

### Issue: Videos not loading
**Solution:** Check if video files exist:
- `d:\DoAn\public\video_in.mp4` (59.5 MB)
- `d:\DoAn\public\video_out.mp4` (275 MB)

### Issue: OCR not reading plates
**Solution:** Check paddle installation:
```powershell
pip list | findstr paddle
# Should show: paddleocr 3.5.0, paddlepaddle 3.3.1
```

### Issue: WebSocket connection timeout
**Solution:** Increase timeout in edge_client.py (line 30):
```python
TIMEOUT_SECONDS = 10.0  # Increase from 5.0
```

## 📝 Key Files Modified

1. **frontend/src/views/DashboardView.vue**
   - Simplified UI with video focus
   - Fixed layout with scrollable event log
   - Added Settings & Logout buttons in header

2. **backend/edge_client.py**
   - PaddleOCR 3.5.0 ✅ Installed
   - Clean OCR code without unnecessary variables
   - Polygon detection working

3. **backend/requirements.txt**
   - Updated with latest package versions
   - PaddlePaddle 3.3.1 & PaddleOCR 3.5.0

## 🎯 Expected Behavior

1. **On Startup:**
   - Central server creates sample database
   - Edge client loads YOLO and OCR models
   - Dashboard connects and shows live streams

2. **Vehicle Detection:**
   - YOLO detects vehicles in ROI zone
   - PaddleOCR reads license plates
   - Results sent to central server in <5 seconds
   - Dashboard updates in real-time

3. **Event Logging:**
   - Each detection creates event in log
   - Snapshots saved to `/public/images/`
   - Manual correction available in UI

## 📚 API Endpoints Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | User login |
| GET | `/api/logs` | Get all records |
| PUT | `/api/logs/{id}/fix` | Correct plate manually |
| GET | `/api/incidents` | Get incidents/errors |
| WS | `/ws/live_events` | Dashboard events |
| WS | `/ws/camera` | Edge AI events |

## ⚙️ Configuration

### PaddleOCR Settings (edge_client.py)
```python
OCR_INTERVAL = 0.25      # Run OCR every 250ms
VOTE_THRESHOLD = 3       # Require 3 matches to lock plate
TIMEOUT_SECONDS = 5.0    # Timeout after 5 seconds
MIN_PLATE_SIZE = 25      # Min plate width
MIN_SHARPNESS = 5.0      # Min sharpness score
```

### YOLO Detection (edge_client.py)
```python
DEVICE = '0' if torch.cuda.is_available() else 'cpu'
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
```

## 🔄 Data Flow

```
Video Input
    ↓
YOLO Detection (vehicles + plates)
    ↓
Filter by ROI Polygon
    ↓
Crop Plate Region
    ↓
PaddleOCR Reading
    ↓
Voting/Consensus (3 matches needed)
    ↓
Send to Central Server
    ↓
Store in Database
    ↓
Broadcast to Dashboard
    ↓
Display in Real-time
```

---

**Last Updated:** May 16, 2026  
**Status:** ✅ Fully Functional with PaddleOCR 3.5.0
