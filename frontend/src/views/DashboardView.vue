<template>
  <div class="dashboard-container animate-fade-in">
    <header class="dashboard-header">
      <div>
        <h1>Hệ thống giám sát phương tiện - CampusGuard</h1>
      </div>
      <div class="header-status">
        <div class="status-badge" :class="wsConnected ? 'status-success' : 'status-danger'">
          <span class="dot"></span> {{ wsConnected ? 'Server: OK' : 'Server: DISCONNECTED' }}
        </div>
      </div>
    </header>

    <div class="dashboard-layout">
      <div class="video-column">
        <div class="video-card glass-panel">
          <div class="card-tag in">LỐI VÀO (IN)</div>
          <div class="video-stream-box">
            <img v-if="camInFrame" :src="camInFrame" class="live-feed" />
            <div v-else class="stream-placeholder">Đang kết nối Camera IN...</div>
          </div>
        </div>

        <div class="video-card glass-panel">
          <div class="card-tag out">LỐI RA (OUT)</div>
          <div class="video-stream-box">
            <img v-if="camOutFrame" :src="camOutFrame" class="live-feed" />
            <div v-else class="stream-placeholder">Đang kết nối Camera OUT...</div>
          </div>
        </div>
      </div>

      <div class="log-column glass-panel">
        <div class="log-header">
          <h3>Nhật ký phương tiện vừa đi qua</h3>
          <span class="count-badge">{{ eventLogs.length }} lượt</span>
        </div>

        <div class="log-list">
          <div v-for="(event, idx) in eventLogs" :key="event.id || idx" 
               class="log-card" :class="getStatusClass(event)">
            
            <div class="snapshot-box">
              <img :src="event.image" class="snapshot-img" @click="viewFullImage(event.image)" />
              <div class="direction-tag" :class="event.cam_label === 'IN' ? 'in' : 'out'">
                {{ event.cam_label === 'IN' ? 'VÀO' : 'RA' }}
              </div>
            </div>

            <div class="event-details">
              <div class="plate-section">
                <template v-if="editId !== event.id">
                  <span class="plate-text">{{ event.plate }}</span>
                  <button class="btn-edit" @click="startEdit(event)">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                  </button>
                </template>
                <div v-else class="edit-group">
                  <input v-model="tempPlate" class="input-edit" v-focus @keyup.enter="savePlate(event)" />
                  <button class="btn-save" @click="savePlate(event)">Lưu</button>
                </div>
              </div>

              <div class="meta-info">
                <span class="vehicle-type">{{ event.vehicle }}</span>
                <span class="time-stamp">{{ formatTime(event.time) }}</span>
              </div>

              <div v-if="event.warning" class="warning-text">⚠️ {{ event.warning }}</div>
            </div>
          </div>

          <div v-if="eventLogs.length === 0" class="empty-state">
            <p>Chưa có phương tiện nào đi vào vùng nhận diện ROI</p>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showModal" class="modal" @click="showModal = false">
      <img :src="modalImg" class="modal-content" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const wsConnected = ref(false)
const eventLogs = ref([])
const camInFrame = ref('')
const camOutFrame = ref('')

// Logic sửa biển số tại chỗ
const editId = ref(null)
const tempPlate = ref('')
const showModal = ref(false)
const modalImg = ref('')

// Directive tự động focus khi nhấn sửa
const vFocus = { mounted: (el) => el.focus() }

const getStatusClass = (event) => {
  if (event.plate === 'UNKNOWN' || event.is_error) return 'status-unknown'
  if (event.is_registered) return 'status-registered'
  return 'status-visitor'
}

const formatTime = (timeStr) => {
  return new Date(timeStr).toLocaleTimeString('vi-VN', { hour12: false })
}

const startEdit = (event) => {
  editId.value = event.id
  tempPlate.value = event.plate === 'UNKNOWN' ? '' : event.plate
}

const savePlate = async (event) => {
  if (!tempPlate.value) return
  try {
    const res = await fetch(`http://localhost:8000/api/logs/${event.id}/fix`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ correct_plate: tempPlate.value })
    })
    if (res.ok) {
      event.plate = tempPlate.value.toUpperCase()
      event.is_error = false
      event.is_registered = true // Giả định sau khi sửa là hợp lệ
      editId.value = null
    }
  } catch (e) { console.error(e) }
}

const viewFullImage = (url) => {
  modalImg.value = url
  showModal.value = true
}

// WebSocket kết nối
let socket = null
const connectWS = () => {
  socket = new WebSocket('ws://localhost:8000/ws/live_events')
  socket.onopen = () => wsConnected.value = true
  socket.onmessage = (e) => {
    const data = JSON.parse(e.data)
    
    if (data.type === 'live_frame') {
      if (data.cam_label === 'IN') camInFrame.value = data.image
      else camOutFrame.value = data.image
      return
    }

    // Khi nhận được sự kiện chốt biển (Snapshot)
    if (data.action) {
      eventLogs.value.unshift(data)
      if (eventLogs.value.length > 50) eventLogs.value.pop()
    }
  }
  socket.onclose = () => {
    wsConnected.value = false
    setTimeout(connectWS, 3000)
  }
}

onMounted(() => connectWS())
onUnmounted(() => socket && socket.close())
</script>

<style scoped>
.dashboard-container { height: 100vh; padding: 1rem; display: flex; flex-direction: column; background: #0f172a; color: #f8fafc; }
.dashboard-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
.dashboard-layout { display: grid; grid-template-columns: 1fr 400px; gap: 1rem; flex: 1; overflow: hidden; }

/* Video Column */
.video-column { display: flex; flex-direction: column; gap: 1rem; }
.video-card { flex: 1; position: relative; background: #000; border-radius: 12px; overflow: hidden; border: 1px solid #1e293b; }
.card-tag { position: absolute; top: 10px; left: 10px; padding: 4px 12px; border-radius: 4px; font-weight: 700; z-index: 10; font-size: 0.8rem; }
.card-tag.in { background: #10b981; }
.card-tag.out { background: #f59e0b; }
.video-stream-box { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
.live-feed { width: 100%; height: 100%; object-fit: cover; }

/* Log Column */
.log-column { display: flex; flex-direction: column; background: #1e293b; border-radius: 12px; overflow: hidden; }
.log-header { padding: 1rem; background: #334155; display: flex; justify-content: space-between; align-items: center; }
.log-list { flex: 1; overflow-y: auto; padding: 1rem; display: flex; flex-direction: column; gap: 1rem; }

/* Log Card Status Colors */
.log-card { display: flex; gap: 1rem; padding: 0.75rem; border-radius: 8px; background: #0f172a; border-left: 6px solid #64748b; }
.status-registered { border-left-color: #10b981; } /* Xanh lá: Xe đăng ký */
.status-visitor { border-left-color: #f59e0b; }    /* Vàng: Khách vãng lai */
.status-unknown { border-left-color: #ef4444; }    /* Đỏ: Không rõ biển */

.snapshot-box { position: relative; width: 120px; height: 80px; flex-shrink: 0; }
.snapshot-img { width: 100%; height: 100%; object-fit: cover; border-radius: 4px; cursor: pointer; }
.direction-tag { position: absolute; bottom: 2px; right: 2px; font-size: 0.6rem; padding: 2px 4px; border-radius: 2px; color: white; font-weight: 700; }
.direction-tag.in { background: #10b981; }
.direction-tag.out { background: #f59e0b; }

.event-details { flex: 1; display: flex; flex-direction: column; justify-content: center; }
.plate-section { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem; }
.plate-text { font-size: 1.2rem; font-weight: 800; letter-spacing: 1px; color: #fff; }
.btn-edit { background: none; border: none; color: #94a3b8; cursor: pointer; }
.btn-edit:hover { color: #3b82f6; }

.edit-group { display: flex; gap: 4px; }
.input-edit { width: 110px; background: #334155; border: 1px solid #3b82f6; color: white; padding: 2px 6px; border-radius: 4px; font-weight: 700; }
.btn-save { background: #3b82f6; border: none; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; cursor: pointer; }

.meta-info { font-size: 0.75rem; color: #94a3b8; display: flex; gap: 10px; }
.warning-text { color: #ef4444; font-size: 0.7rem; font-weight: 600; margin-top: 4px; }

.modal { position: fixed; inset: 0; background: rgba(0,0,0,0.9); z-index: 1000; display: flex; align-items: center; justify-content: center; }
.modal-content { max-width: 90%; max-height: 90%; border: 2px solid #3b82f6; border-radius: 8px; }
</style>