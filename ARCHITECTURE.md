# Hệ Thống Kiểm Soát Xe Ra Vào Không Barie - Architecture Document

## 1. PHÂN TÍCH VẤN ĐỀ HIỆN TẠI

### Vấn Đề trong edge_client.py Hiện Tại:
1. ❌ Thiếu error handling & retry logic
2. ❌ Thiếu health check / monitoring  
3. ❌ Không có reconnect mechanism (reconnect vô tận)
4. ❌ Không có local cache khi mất mạng
5. ❌ Không có structured logging
6. ❌ Không có config management (.env)
7. ❌ Không có database fallback
8. ❌ Không có duplicate detection
9. ❌ Không có anti-tailgating
10. ❌ Không có vehicle state machine
11. ❌ Không có WebSocket authentication
12. ❌ Không có metrics/monitoring
13. ❌ Không có graceful shutdown
14. ❌ Không có RTSP camera support
15. ❌ Không có adaptive frame rate

---

## 2. KIẾN TRÚC PRODUCTION-READY

### 2.1 Tổng Quan Hệ Thống

```
┌─────────────────────────────────────────────────────────────────┐
│                     FRONTEND DASHBOARD (Vue 3)                  │
│  - Realtime Camera Feed (2 cameras IN/OUT)                      │
│  - Event Log (Real-time updates)                               │
│  - Alert Popup (Anti-tailgating, Wrong direction)              │
│  - Statistics & History                                        │
│  - Camera Health Status                                        │
└────────────────────────┬────────────────────────────────────────┘
                         │ WebSocket (Secured JWT)
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                    CENTRAL SERVER (FastAPI)                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ WebSocket Handler                                        │  │
│  │ - JWT Authentication                                    │  │
│  │ - Live frame forwarding                                 │  │
│  │ - Event broadcasting                                    │  │
│  │ - Health check aggregation                              │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Business Logic                                           │  │
│  │ - Vehicle State Machine                                 │  │
│  │ - Duplicate Detection (Hash + Time Window)              │  │
│  │ - Anti-Tailgating Detection                             │  │
│  │ - Incident Management                                   │  │
│  │ - Whitelist/Blacklist Management                        │  │
│  │ - Manual Verification Support                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Database Layer (SQLAlchemy ORM)                          │  │
│  │ - PostgreSQL (Main DB)                                  │  │
│  │ - Redis Queue (Job Queue)                               │  │
│  │ - Redis Cache (Session, Duplicate Detection)            │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────┬──────────────────────────────┬───────────────────────┘
         │ WebSocket (Send Detection)   │ REST API
         │                               │
    ┌────▼────────────────────────────────▼────────────┐
    │        EDGE AI CLIENT (Python)                   │
    │  ┌──────────────────────────────────────────┐   │
    │  │ Async Multi-threaded Pipeline:          │   │
    │  │ 1. Reader Thread (RTSP/Video)           │   │
    │  │ 2. AI Worker (YOLOv8 + ByteTrack)       │   │
    │  │ 3. OCR Worker (PaddleOCR + Voting)      │   │
    │  │ 4. Stream Worker (Live Feed)            │   │
    │  │ 5. Health Check Thread                  │   │
    │  │ 6. Local Cache Thread (SQLite)          │   │
    │  └──────────────────────────────────────────┘   │
    │  ┌──────────────────────────────────────────┐   │
    │  │ Features:                                │   │
    │  │ - Reconnect with exponential backoff    │   │
    │  │ - Local SQLite cache (offline mode)     │   │
    │  │ - Structured logging                    │   │
    │  │ - Config management (.env)              │   │
    │  │ - Graceful shutdown                     │   │
    │  │ - Health metrics                        │   │
    │  └──────────────────────────────────────────┘   │
    └──────────────────────────────────────────────────┘
```

### 2.2 Thành Phần Chính

#### A. **Edge AI Client**
```
StreamProcessor (RTSP/Video Input)
├─ ReaderThread: Đọc frame từ camera
│  └─ RTSP reconnect + error recovery
│  └─ Frame queue management
│
├─ AIWorker: YOLOv8 + ByteTrack
│  └─ ROI filtering
│  └─ Vehicle detection
│  └─ License plate detection
│  └─ Tracking persistence
│
├─ OCRWorker: PaddleOCR + Voting
│  └─ Sharpness filtering
│  └─ Character corrections (Vietnamese rules)
│  └─ Vote counting (threshold-based)
│
├─ StreamWorker: Live frame streaming
│  └─ Frame encoding (JPEG base64)
│  └─ Polygon drawing (ROI)
│  └─ Bounding box visualization
│  └─ FPS calculation
│
└─ HealthCheckThread: Monitoring
   └─ Camera health (FPS, queue size)
   └─ OCR queue monitoring
   └─ Memory usage
   └─ Error rate tracking
```

#### B. **Central Server**
```
FastAPI Application
├─ WebSocket Endpoints
│  ├─ /ws/camera (Edge AI connection)
│  │  └─ JWT Authentication
│  │  └─ Event handling
│  │  └─ Health check aggregation
│  │
│  └─ /ws/dashboard (Frontend connection)
│     └─ Live frame broadcasting
│     └─ Event log updates
│     └─ Alert notifications
│
├─ REST API Endpoints
│  ├─ /api/v1/auth (Login, token refresh)
│  ├─ /api/v1/events (History, filtering)
│  ├─ /api/v1/vehicles (Whitelist, blacklist)
│  ├─ /api/v1/statistics (Daily, monthly)
│  ├─ /api/v1/incidents (Anti-tailgating, wrong direction)
│  ├─ /api/v1/camera (Health status)
│  └─ /api/v1/settings (Configuration)
│
├─ Business Logic
│  ├─ VehicleStateMachine (IDLE → DETECTED → VERIFIED → EXITED)
│  ├─ DuplicateDetector (Hash + Time window)
│  ├─ AntiTailgatingDetector (Vehicle distance + time)
│  ├─ WrongDirectionDetector (Entrance/Exit validation)
│  └─ IncidentManager (Manual verification, alerts)
│
├─ Database Layer
│  ├─ PostgreSQL Models
│  │  ├─ User, Camera
│  │  ├─ Event, Vehicle
│  │  ├─ Incident, Alert
│  │  ├─ Whitelist, Blacklist
│  │  └─ AuditLog
│  │
│  ├─ Redis Cache
│  │  ├─ Session tokens
│  │  ├─ Duplicate detection cache
│  │  ├─ Camera online status
│  │  └─ Real-time statistics
│  │
│  └─ Redis Queue
│     ├─ Image processing tasks
│     ├─ Email notifications
│     └─ Incident alerts
│
└─ Monitoring & Logging
   ├─ Structured logging (Python logging + Serilog)
   ├─ Prometheus metrics
   ├─ Error tracking
   └─ Performance monitoring
```

#### C. **Frontend Dashboard**
```
Vue 3 Application
├─ Pages
│  ├─ LoginPage (JWT authentication)
│  ├─ DashboardPage (Realtime monitoring)
│  │  ├─ Live cameras (2 cameras side-by-side)
│  │  ├─ Event log (Real-time)
│  │  ├─ Alert popup (Modal/Toast)
│  │  └─ Camera status
│  │
│  ├─ HistoryPage (Event search & filter)
│  ├─ StatisticsPage (Charts & metrics)
│  ├─ SettingsPage (User settings)
│  ├─ IncidentsPage (Tailgating, wrong direction)
│  └─ ManagementPage (Whitelist, blacklist)
│
├─ Components
│  ├─ LiveCamera (Canvas rendering + FPS)
│  ├─ EventLog (Sortable table)
│  ├─ AlertPopup (Toast notification)
│  ├─ CameraStatus (Online/offline indicator)
│  ├─ Statistics (ECharts integration)
│  └─ DarkMode Toggle
│
├─ State Management (Pinia)
│  ├─ authStore (User, tokens)
│  ├─ cameraStore (Live data, health)
│  ├─ eventStore (Event log, filtering)
│  ├─ alertStore (Notifications queue)
│  └─ settingsStore (UI preferences)
│
├─ WebSocket Client
│  ├─ Auto-reconnect with backoff
│  ├─ Message queue (offline support)
│  ├─ Heartbeat mechanism
│  └─ Error recovery
│
└─ Styling
   ├─ TailwindCSS (Utility-first)
   ├─ Dark mode (Tailwind dark:)
   ├─ Responsive design
   └─ SOC-style theme
```

---

## 3. DATABASE SCHEMA (PostgreSQL)

### Tables

```sql
-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'guard', 'viewer') NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Cameras
CREATE TABLE cameras (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    cam_label VARCHAR(10) UNIQUE NOT NULL,  -- 'IN' or 'OUT'
    rtsp_url VARCHAR(255),  -- RTSP or local video path
    location VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    health_status ENUM('online', 'offline', 'error') DEFAULT 'offline',
    last_heartbeat TIMESTAMP,
    fps FLOAT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Events (License plate detection)
CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    camera_id INT NOT NULL REFERENCES cameras(id),
    plate_number VARCHAR(20),
    vehicle_type VARCHAR(20),  -- 'Car', 'Motorcycle'
    confidence FLOAT DEFAULT 0,
    is_verified BOOLEAN DEFAULT FALSE,
    verified_by UUID REFERENCES users(id),
    snapshot_image TEXT,  -- Base64 or S3 path
    event_hash VARCHAR(64),  -- Hash for duplicate detection
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(event_hash, camera_id, created_at)  -- Prevent exact duplicates
);

-- Whitelist (Allowed vehicles)
CREATE TABLE whitelist_vehicles (
    id SERIAL PRIMARY KEY,
    plate_number VARCHAR(20) UNIQUE NOT NULL,
    vehicle_type VARCHAR(20),
    owner_name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    added_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Blacklist (Banned vehicles)
CREATE TABLE blacklist_vehicles (
    id SERIAL PRIMARY KEY,
    plate_number VARCHAR(20) UNIQUE NOT NULL,
    reason TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    added_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Incidents (Anti-tailgating, wrong direction)
CREATE TABLE incidents (
    id BIGSERIAL PRIMARY KEY,
    camera_id INT NOT NULL REFERENCES cameras(id),
    incident_type ENUM('tailgating', 'wrong_direction', 'speeding') NOT NULL,
    vehicle1_plate VARCHAR(20),
    vehicle2_plate VARCHAR(20),
    severity ENUM('low', 'medium', 'high') DEFAULT 'medium',
    is_acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Audit Log
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(50),
    changes JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Indexes
```sql
CREATE INDEX idx_events_camera_created ON events(camera_id, created_at DESC);
CREATE INDEX idx_events_plate ON events(plate_number);
CREATE INDEX idx_events_hash ON events(event_hash);
CREATE INDEX idx_incidents_type ON incidents(incident_type, created_at DESC);
CREATE INDEX idx_incidents_acknowledged ON incidents(is_acknowledged);
```

---

## 4. VEHICLE STATE MACHINE

```
                    ┌─────────────┐
                    │    IDLE     │
                    └──────┬──────┘
                           │
                     [Plate detected]
                           │
                    ┌──────▼──────┐
                    │  DETECTED   │
                    │ (Voting)    │
                    └──────┬──────┘
                           │
                  [Vote threshold reached]
                           │
                    ┌──────▼──────────┐
                    │ VERIFIED        │
                    │ (Send to server)│
                    └──────┬──────────┘
                           │
                  [Entry time < 5s]
                           │
                    ┌──────▼──────────┐
                    │ EXITED          │
                    │ (Archived)      │
                    └─────────────────┘
```

---

## 5. ANTI-TAILGATING ALGORITHM

```
Premise:
- Tailgating = Vehicle B enters immediately after Vehicle A (< 3 seconds)
- Detected on both IN and OUT cameras

Algorithm:
1. Track vehicle entry time on each camera
2. Store entry timestamp + plate + vehicle type
3. For new vehicle:
   - Calculate time gap from previous vehicle (same direction)
   - IF gap < 3 seconds → Increment tailgating counter
   - IF counter ≥ 2 times → Raise incident alert

Data Structure:
{
  "camera_in": [
    {"plate": "29A1234", "timestamp": 1234567890, "direction": "entry"}
  ]
}

Incident Trigger:
- Vehicle B enters < 3s after Vehicle A
- Store: {vehicle_a_plate, vehicle_b_plate, incident_type: 'tailgating', severity: 'high'}
- Alert: Send to dashboard + notify guards
```

---

## 6. DUPLICATE DETECTION

```
Strategy: Hash-based with time window

Hash Components:
- plate_number
- camera_id
- hour (round down to hour)
→ hash = SHA256(plate + camera_id + hour)

Time Window: 60 minutes (configurable)

Logic:
1. Generate hash when event detected
2. Query Redis for same hash in last 60 minutes
3. IF exists → Mark as duplicate (skip DB insert)
4. ELSE → Save to DB + cache hash in Redis
5. Clean up old hashes (TTL = 3600 seconds)

Benefit:
- Prevent same vehicle detected multiple times in short period
- Reduce noise in event log
- Improve accuracy
```

---

## 7. WEBSOCKET PROTOCOL

### Message Format

```json
{
  "type": "detection|live_frame|heartbeat|health_check",
  "timestamp": "ISO8601",
  "camera_id": 1,
  "cam_label": "IN",
  "data": { /* specific payload */ }
}
```

### Message Types

#### 1. Detection Event
```json
{
  "type": "detection",
  "timestamp": "2024-05-14T10:30:45.123Z",
  "camera_id": 1,
  "cam_label": "IN",
  "data": {
    "plate_number": "29A12345",
    "vehicle_type": "Car",
    "confidence": 0.95,
    "snapshot_image": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
    "ocr_results": ["29A12345", "29A12345", "29A12345"],
    "vote_count": 3
  }
}
```

#### 2. Live Frame
```json
{
  "type": "live_frame",
  "timestamp": "2024-05-14T10:30:45.123Z",
  "camera_id": 1,
  "cam_label": "IN",
  "data": {
    "image": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
    "fps": 12,
    "queue_size": 5
  }
}
```

#### 3. Health Check (Edge → Server)
```json
{
  "type": "health_check",
  "timestamp": "2024-05-14T10:30:45.123Z",
  "camera_id": 1,
  "cam_label": "IN",
  "data": {
    "status": "healthy",
    "fps": 25,
    "queue_size_raw": 10,
    "queue_size_ocr": 8,
    "memory_usage_mb": 450,
    "error_count": 0,
    "uptime_seconds": 3600
  }
}
```

#### 4. Heartbeat (Server → Frontend)
```json
{
  "type": "heartbeat",
  "timestamp": "2024-05-14T10:30:45.123Z"
}
```

### Authentication

```
Initial Handshake:
1. Client connects to /ws/camera
2. Send: {"auth_token": "JWT_TOKEN"}
3. Server validates token
4. Response: {"status": "authenticated"} or {"error": "Invalid token"}
5. Connection established or closed
```

---

## 8. ERROR HANDLING & RECOVERY

### Edge Client Recovery

```
Camera Connection Loss:
→ Reconnect Logic:
  1. Attempt: 1s delay
  2. Attempt: 2s delay
  3. Attempt: 4s delay
  4. Attempt: 8s delay
  5. Attempt: 16s delay
  6. Attempt: 32s delay
  (Cap at 60s, max 5 minutes)

WebSocket Connection Loss:
→ Exponential backoff (same as above)
→ Local cache to SQLite
→ Retry sending after reconnect

OCR Timeout:
→ Skip frame, continue processing
→ Increment error counter
→ If error_rate > 30% → Alert server

Memory Leak Detection:
→ Monitor memory every 60s
→ If memory > 80% of limit → Restart thread
→ Log memory spike events
```

### Server Recovery

```
Database Connection Loss:
→ Use connection pool with retry
→ CircuitBreaker pattern
→ Fallback to cache layer

WebSocket Client Disconnect:
→ Notify UI (camera offline)
→ Store pending frames in queue
→ Retry connection with backoff

Event Processing Error:
→ Log error + context
→ Store in error queue for manual review
→ Send alert to admin
→ Continue processing next events
```

---

## 9. FOLDER STRUCTURE

```
d:\DoAn\
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py (Environment variables)
│   │   ├── dependencies.py (Database, Redis, etc.)
│   │   │
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── v1/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py (Login, token)
│   │   │   │   ├── events.py (History, search)
│   │   │   │   ├── vehicles.py (Whitelist, blacklist)
│   │   │   │   ├── incidents.py (Tailgating, alerts)
│   │   │   │   ├── camera.py (Status, health)
│   │   │   │   ├── statistics.py (Charts, metrics)
│   │   │   │   └── settings.py (Configuration)
│   │   │   └── websocket.py (WebSocket handlers)
│   │   │
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── camera.py
│   │   │   ├── event.py
│   │   │   ├── incident.py
│   │   │   ├── whitelist.py
│   │   │   ├── blacklist.py
│   │   │   └── audit_log.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py (Login request/response)
│   │   │   ├── event.py (Detection event schema)
│   │   │   ├── incident.py
│   │   │   └── vehicle.py
│   │   │
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py (JWT, password hashing)
│   │   │   ├── event_service.py (Event CRUD, filtering)
│   │   │   ├── vehicle_service.py
│   │   │   ├── state_machine.py (Vehicle state machine)
│   │   │   ├── duplicate_detector.py (Hash-based detection)
│   │   │   ├── anti_tailgating.py (Tailgating detection)
│   │   │   └── incident_manager.py
│   │   │
│   │   ├── websocket/
│   │   │   ├── __init__.py
│   │   │   ├── connection_manager.py (WebSocket lifecycle)
│   │   │   ├── message_handler.py (Message processing)
│   │   │   └── broadcaster.py (Event broadcasting)
│   │   │
│   │   ├── cache/
│   │   │   ├── __init__.py
│   │   │   ├── redis_client.py
│   │   │   └── session_cache.py
│   │   │
│   │   ├── utils/
│   │   │   ├── __init__.py
│   │   │   ├── logging.py (Structured logging)
│   │   │   ├── decorators.py (Auth, validation)
│   │   │   ├── security.py (JWT, encryption)
│   │   │   └── constants.py
│   │   │
│   │   └── middleware/
│   │       ├── __init__.py
│   │       ├── auth_middleware.py
│   │       ├── cors_middleware.py
│   │       ├── error_handler.py
│   │       └── request_logging.py
│   │
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_auth.py
│   │   ├── test_events.py
│   │   ├── test_state_machine.py
│   │   └── test_anti_tailgating.py
│   │
│   ├── migrations/ (Alembic)
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │
│   ├── logs/
│   │   └── app.log
│   │
│   ├── .env.example
│   ├── .env (local, ignored by git)
│   ├── requirements.txt
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── gunicorn.conf.py
│   └── main.py (Entry point)
│
├── edge_client/
│   ├── __init__.py
│   ├── config.py (Environment variables)
│   ├── logger.py (Structured logging)
│   ├── main.py (Entry point)
│   │
│   ├── camera/
│   │   ├── __init__.py
│   │   ├── stream_processor.py (Core pipeline)
│   │   ├── reader_worker.py (Frame reading)
│   │   ├── ai_worker.py (YOLOv8 inference)
│   │   ├── ocr_worker.py (PaddleOCR)
│   │   ├── stream_worker.py (Live streaming)
│   │   └── health_checker.py (Monitoring)
│   │
│   ├── rtsp/
│   │   ├── __init__.py
│   │   ├── rtsp_client.py (Reconnect logic)
│   │   └── frame_buffer.py
│   │
│   ├── websocket/
│   │   ├── __init__.py
│   │   ├── ws_client.py (WebSocket + reconnect)
│   │   ├── message_builder.py (Payload construction)
│   │   └── queue_manager.py (Offline caching)
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── yolo_model.py (YOLOv8 wrapper)
│   │   ├── ocr_model.py (PaddleOCR wrapper)
│   │   └── tracker.py (ByteTrack)
│   │
│   ├── processing/
│   │   ├── __init__.py
│   │   ├── plate_utils.py (VN plate rules)
│   │   ├── frame_utils.py (Encoding, ROI)
│   │   ├── voting_engine.py (OCR voting)
│   │   └── duplicate_detector.py
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── sqlite_cache.py (Local cache)
│   │   └── schema.sql
│   │
│   ├── .env.example
│   ├── .env (local, ignored by git)
│   ├── requirements.txt
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── ver4_yolov8n.pt (model weights)
│
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── main.js
│   │   ├── App.vue
│   │   │
│   │   ├── components/
│   │   │   ├── LiveCamera.vue (Canvas rendering)
│   │   │   ├── EventLog.vue (Table with sorting)
│   │   │   ├── AlertPopup.vue (Toast/Modal)
│   │   │   ├── CameraStatus.vue (Online/offline)
│   │   │   ├── Statistics.vue (ECharts)
│   │   │   └── Sidebar.vue
│   │   │
│   │   ├── pages/
│   │   │   ├── LoginPage.vue
│   │   │   ├── DashboardPage.vue
│   │   │   ├── HistoryPage.vue
│   │   │   ├── StatisticsPage.vue
│   │   │   ├── IncidentsPage.vue
│   │   │   ├── SettingsPage.vue
│   │   │   └── ManagementPage.vue
│   │   │
│   │   ├── stores/
│   │   │   ├── authStore.js
│   │   │   ├── cameraStore.js
│   │   │   ├── eventStore.js
│   │   │   ├── alertStore.js
│   │   │   └── settingsStore.js
│   │   │
│   │   ├── services/
│   │   │   ├── api.js (REST client)
│   │   │   ├── websocket.js (WebSocket client)
│   │   │   └── auth.js (JWT handling)
│   │   │
│   │   ├── assets/
│   │   │   ├── main.css
│   │   │   └── base.css
│   │   │
│   │   └── router/
│   │       └── index.js
│   │
│   ├── .env.example
│   ├── .env (local, ignored by git)
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── tailwind.css
│   └── index.html
│
├── docker-compose.yml (Main orchestration)
├── .env.example (Root level)
├── ARCHITECTURE.md (This file)
├── DEPLOYMENT.md (Ubuntu server setup)
├── README.md (Getting started)
└── docker/
    ├── Dockerfile.backend
    ├── Dockerfile.edge
    ├── Dockerfile.frontend
    └── nginx.conf (Reverse proxy)
```

---

## 10. DEPLOYMENT STRATEGY

### Local Development
```bash
docker-compose -f docker-compose.dev.yml up
```

### Production (Ubuntu 22.04)
```bash
# Prerequisites: Docker, Docker Compose
# Setup: PostgreSQL, Redis, Nginx

# Deployment Steps:
1. Clone repository
2. Setup .env from .env.example
3. Run migrations: docker-compose exec backend alembic upgrade head
4. Start services: docker-compose -f docker-compose.prod.yml up -d
5. Configure Nginx (reverse proxy + SSL)
6. Setup systemd service for edge client
```

---

## 11. PERFORMANCE TARGETS

| Metric | Target | Notes |
|--------|--------|-------|
| Frame rate | 25 FPS | Per camera |
| Live stream FPS | 12 FPS | WebSocket broadcast |
| OCR accuracy | > 95% | For Vietnamese plates |
| Event latency | < 1s | Detection to UI |
| Duplicate detection | > 99% | False positive rate < 1% |
| Uptime | > 99.9% | With auto-recovery |
| Memory usage | < 500MB | Edge client per camera |
| Database latency | < 50ms | Event insertion |

---

## 12. SECURITY CONSIDERATIONS

1. **JWT Authentication** - All WebSocket + API endpoints
2. **CORS** - Whitelist frontend domain
3. **Password hashing** - bcrypt with salt
4. **HTTPS/WSS** - Production deployment
5. **Rate limiting** - Prevent brute force
6. **Input validation** - All API endpoints
7. **CSRF protection** - If using cookies
8. **Database encryption** - Sensitive data (snapshots)
9. **Audit logging** - All user actions
10. **Environment variables** - No hardcoded secrets

---

## 13. MONITORING & ALERTING

### Metrics to Track
- Camera FPS and connectivity
- Event processing latency
- OCR accuracy and confidence
- Database query performance
- WebSocket connection count
- Memory and CPU usage
- Error rate and types
- Incident frequency

### Alerting
- Camera offline → Immediate alert
- High error rate → Alert
- Memory leak detection → Restart
- Database down → Fallback to cache
- Duplicate event spike → Investigate

---

## Tiếp theo: Implementation

Các file sau sẽ được tạo:
1. ✅ DATABASE SCHEMA (PostgreSQL)
2. ✅ WEBSOCKET PROTOCOL
3. Backend FastAPI code
4. Edge AI client code (improved)
5. Frontend Vue3 code
6. Docker setup
7. Deploy guide

