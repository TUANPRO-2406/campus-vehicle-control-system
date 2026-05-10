<template>
  <div class="dashboard-container animate-fade-in">
    <header class="dashboard-header">
      <div>
        <h1>Màn hình giám sát trực tiếp</h1>
        <p class="subtitle">Cổng số 1 - Luồng video thời gian thực</p>
      </div>
      <div class="header-actions">
        <div class="status-badge status-success">
          <span class="dot"></span> Server: Kết nối
        </div>
        <div class="status-badge status-success">
          <span class="dot"></span> AI: Sẵn sàng
        </div>
      </div>
    </header>

    <div class="dashboard-grid">
      <!-- Camera IN -->
      <div class="video-panel glass-panel">
        <div class="panel-header">
          <h3>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon-success"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>
            Camera IN (Lối vào)
          </h3>
          <span class="live-indicator">LIVE</span>
        </div>
        <div class="video-wrapper">
          <video src="http://localhost:8000/public/video_out.mp4" autoplay loop muted class="video-stream"></video>
        </div>
        <div class="panel-footer" v-if="camInResult.plate !== '---'">
          <div class="latest-event success-bg">
            <div class="event-plate">{{ camInResult.plate }}</div>
            <div class="event-info">
              <strong>{{ camInResult.type }}</strong>
              <span>Vào lúc: {{ camInResult.time ? new Date(camInResult.time).toLocaleTimeString() : '--:--:--' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Camera OUT -->
      <div class="video-panel glass-panel">
        <div class="panel-header">
          <h3>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon-warning"><path d="M9 3H3v6M15 21h6v-6M3 3l7 7M21 21l-7-7"/></svg>
            Camera OUT (Lối ra)
          </h3>
          <span class="live-indicator">LIVE</span>
        </div>
        <div class="video-wrapper error-pulse">
          <video src="http://localhost:8000/public/video_out.mp4" autoplay loop muted class="video-stream"></video>
        </div>
        <div class="panel-footer" v-if="camOutResult.plate !== '---'">
          <div class="latest-event success-bg">
            <div class="event-plate">{{ camOutResult.plate }}</div>
            <div class="event-info">
              <strong>{{ camOutResult.type }}</strong>
              <span>Ra lúc: {{ camOutResult.time ? new Date(camOutResult.time).toLocaleTimeString() : '--:--:--' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Recent Events Log -->
      <div class="events-panel glass-panel">
        <div class="panel-header">
          <h3>Nhật ký sự kiện gần đây</h3>
        </div>
        <div class="events-list">
          <div v-for="(event, idx) in eventLogs.slice(0, 10)" :key="event.id || idx" class="event-item">
            <div class="event-time">{{ event.time ? new Date(event.time).toLocaleTimeString() : '--:--:--' }}</div>
            <div class="event-details">
              <span class="plate-tag">{{ event.plate }}</span>
              <span class="type-tag" :class="event.vehicle === 'O to' ? 'staff' : 'stranger'">{{ event.vehicle }}</span>
            </div>
            <div class="event-direction" :class="event.camera === 'IN' ? 'in' : 'out'">
              {{ event.camera === 'IN' ? 'Vào' : 'Ra' }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref, onMounted, onUnmounted } from 'vue'

  // 1. Khai báo các biến phản ứng (Reactive) để lưu kết quả từ AI
  const camInResult = ref({ plate: '---', type: '---', image: '', status: 'READY', time: null })
  const camOutResult = ref({ plate: '---', type: '---', image: '', status: 'READY', time: null })
  const eventLogs = ref([])

  let socket = null

  // Lấy nhật ký sự kiện gần đây từ backend khi vào trang
  const fetchLogs = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/logs')
      const logs = await res.json()
      // Chuyển đổi dữ liệu về dạng eventLogs
      eventLogs.value = logs.map(log => ({
        id: log.id,
        plate: log.plate,
        time: log.time_in || log.time_out,
        vehicle: log.status === 'HOP_LE' ? 'O to' : 'Xe may', // Tùy chỉnh nếu có loại xe
        camera: log.time_out ? 'OUT' : 'IN',
        image: log.image_in || log.image_out
      }))
    } catch (e) {
      console.error('Không lấy được nhật ký sự kiện', e)
    }
  }

  const connectWS = () => {
    socket = new WebSocket('ws://localhost:8000/ws/live_events')

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data)
      // 2. Phân loại dữ liệu về đúng camera
      if (data.camera === "IN") {
        camInResult.value = {
          plate: data.plate,
          type: data.vehicle,
          time: data.time,
          image: data.image
        }
      } else {
        camOutResult.value = {
          plate: data.plate,
          type: data.vehicle,
          time: data.time,
          image: data.image
        }
      }
      // 3. Cập nhật vào danh sách nhật ký phía dưới
      eventLogs.value.unshift(data)
    }

    socket.onclose = () => {
      setTimeout(connectWS, 3000)
    }
  }

  onMounted(() => {
    fetchLogs()
    connectWS()
  })
</script>

<style scoped>
.dashboard-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.dashboard-header h1 {
  font-size: 1.5rem;
  font-weight: 600;
  margin-bottom: 0.25rem;
}

.subtitle {
  color: var(--text-muted);
  font-size: 0.9rem;
}

.header-actions {
  display: flex;
  gap: 1rem;
}

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  margin-right: 4px;
  animation: blink 1.5s infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.dashboard-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: auto 1fr;
  gap: 1.5rem;
  flex: 1;
}

.video-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-header h3 {
  font-size: 1.1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.icon-success { color: var(--success); }
.icon-warning { color: var(--warning); }

.live-indicator {
  background: rgba(239, 68, 68, 0.2);
  color: var(--danger);
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 1px;
  border: 1px solid rgba(239, 68, 68, 0.4);
}

.video-wrapper {
  position: relative;
  flex: 1;
  background: #000;
  min-height: 300px;
}

.video-stream {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.8;
}

.ai-overlay {
  position: absolute;
  border: 2px solid var(--success);
  background: rgba(16, 185, 129, 0.1);
}

.ai-overlay.error {
  border-color: var(--danger);
  background: rgba(239, 68, 68, 0.1);
}

.ai-label {
  position: absolute;
  background: var(--success);
  color: white;
  padding: 2px 8px;
  font-size: 0.8rem;
  font-weight: 600;
  border-radius: 4px;
  transform: translateY(-100%);
}

.ai-label.error {
  background: var(--danger);
}

.error-pulse {
  animation: pulse 2s infinite;
}

.panel-footer {
  padding: 1rem;
  background: rgba(0, 0, 0, 0.2);
}

.latest-event {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1rem;
  border-radius: 8px;
}

.success-bg {
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.2);
}

.danger-bg {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
}

.event-plate {
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: 1px;
  background: #fff;
  color: #000;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  border: 2px solid #000;
}

.event-info {
  display: flex;
  flex-direction: column;
}

.event-info strong {
  font-size: 0.95rem;
}

.event-info span {
  font-size: 0.8rem;
  color: var(--text-muted);
}

.btn-sm {
  padding: 0.4rem 0.8rem;
  font-size: 0.85rem;
}

.ml-auto {
  margin-left: auto;
}

.text-danger { color: var(--danger); }
.border-danger { border-color: var(--danger); }

.events-panel {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
}

.events-list {
  display: flex;
  flex-direction: column;
  padding: 0.5rem;
  overflow-y: auto;
  max-height: 200px;
}

.event-item {
  display: flex;
  align-items: center;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-color);
  transition: background 0.2s;
}

.event-item:hover {
  background: rgba(255, 255, 255, 0.05);
}

.event-item:last-child {
  border-bottom: none;
}

.event-time {
  width: 100px;
  color: var(--text-muted);
  font-size: 0.9rem;
}

.event-details {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 1rem;
}

.plate-tag {
  font-weight: 600;
  letter-spacing: 0.5px;
}

.type-tag {
  font-size: 0.75rem;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-weight: 500;
}

.type-tag.staff { background: rgba(16, 185, 129, 0.2); color: var(--success); }
.type-tag.stranger { background: rgba(245, 158, 11, 0.2); color: var(--warning); }

.event-direction {
  font-weight: 600;
  font-size: 0.9rem;
}

.event-direction.in { color: var(--success); }
.event-direction.out { color: var(--warning); }
</style>
