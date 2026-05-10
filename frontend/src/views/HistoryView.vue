<template>
  <div class="history-container animate-fade-in">
    <header class="history-header">
      <div>
        <h1>Lịch sử ra vào & Sửa lỗi</h1>
        <p class="subtitle">Xem lại lịch sử và khắc phục các trường hợp AI đọc sai biển số</p>
      </div>
      <div class="filter-actions">
        <input type="date" class="input-field date-picker" />
        <select class="input-field status-select" v-model="filterStatus">
          <option value="all">Tất cả trạng thái</option>
          <option value="error">Cần sửa lỗi</option>
        </select>
        <button class="btn btn-primary" @click="fetchLogs">Làm mới</button>
      </div>
    </header>

    <div class="table-container glass-panel">
      <table class="history-table">
        <thead>
          <tr>
            <th>Thời gian vào</th>
            <th>Thời gian ra</th>
            <th>Biển số (AI)</th>
            <th>Ảnh vào</th>
            <th>Ảnh ra</th>
            <th>Trạng thái</th>
            <th>Thao tác</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in filteredLogs" :key="item.id" :class="{'error-row': item.status !== 'HOP_LE'}">
            <td>{{ formatDate(item.time_in) }}</td>
            <td>{{ formatDate(item.time_out) }}</td>
            <td>
              <div v-if="editId !== item.id" class="plate-display" :class="{'text-danger': item.status !== 'HOP_LE'}">
                {{ item.plate || 'KHÔNG RÕ' }}
              </div>
              <input 
                v-else 
                v-model="editPlate" 
                class="input-field edit-input" 
                placeholder="Nhập biển số đúng"
                @keyup.enter="savePlate(item.id)"
              />
            </td>
            <td>
              <img v-if="item.image_in" :src="item.image_in" class="thumb-img" @click="viewImage(item.image_in)" alt="Ảnh vào">
              <span v-else class="text-muted">Trống</span>
            </td>
            <td>
              <img v-if="item.image_out" :src="item.image_out" class="thumb-img" @click="viewImage(item.image_out)" alt="Ảnh ra">
              <span v-else class="text-muted">Trống</span>
            </td>
            <td>
              <span class="status-badge" :class="item.status !== 'HOP_LE' ? 'status-danger' : 'status-success'">
                {{ item.status === 'HOP_LE' ? 'Hợp lệ' : 'Cần sửa' }}
              </span>
            </td>
            <td>
              <div class="action-buttons">
                <button v-if="editId !== item.id && item.status !== 'HOP_LE'" @click="startEdit(item)" class="btn-action edit-btn">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                  Sửa
                </button>
                <button v-if="editId === item.id" @click="savePlate(item.id)" class="btn-action save-btn">
                  Lưu
                </button>
                <button v-if="editId === item.id" @click="editId = null" class="btn-action cancel-btn">
                  Hủy
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Image Modal -->
    <div v-if="showModal" class="modal-overlay" @click="showModal = false">
      <div class="modal-content" @click.stop>
        <img :src="modalImage" class="full-image" />
        <button class="close-modal" @click="showModal = false">×</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const logs = ref([])
const filterStatus = ref('all')

const editId = ref(null)
const editPlate = ref('')
const showModal = ref(false)
const modalImage = ref('')

const fetchLogs = async () => {
  try {
    const res = await fetch('http://localhost:8000/api/logs')
    if (res.ok) {
      logs.value = await res.json()
    }
  } catch (e) {
    console.error(e)
  }
}

onMounted(() => {
  fetchLogs()
})

const filteredLogs = computed(() => {
  if (filterStatus.value === 'error') {
    return logs.value.filter(l => l.status !== 'HOP_LE')
  }
  return logs.value
})

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleTimeString('vi-VN') + ' ' + d.toLocaleDateString('vi-VN')
}

const startEdit = (item) => {
  editId.value = item.id
  editPlate.value = item.plate === 'UNKNOWN' ? '' : item.plate
}

const savePlate = async (id) => {
  if (!editPlate.value) return
  
  try {
    const res = await fetch(`http://localhost:8000/api/logs/${id}/fix`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ correct_plate: editPlate.value })
    })
    
    if (res.ok) {
      const item = logs.value.find(i => i.id === id)
      if (item) {
        item.plate = editPlate.value
        item.status = 'HOP_LE'
      }
      editId.value = null
    }
  } catch (e) {
    console.error(e)
  }
}

const viewImage = (url) => {
  if (!url) return
  modalImage.value = url
  showModal.value = true
}
</script>

<style scoped>
.history-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.history-header h1 {
  font-size: 1.5rem;
  font-weight: 600;
  margin-bottom: 0.25rem;
}

.subtitle {
  color: var(--text-muted);
  font-size: 0.9rem;
}

.filter-actions {
  display: flex;
  gap: 1rem;
}

.date-picker, .status-select {
  width: auto;
  min-width: 150px;
}

.table-container {
  flex: 1;
  overflow: auto;
}

.history-table {
  width: 100%;
  border-collapse: collapse;
}

.history-table th {
  text-align: left;
  padding: 1rem;
  background: rgba(0, 0, 0, 0.2);
  color: var(--text-muted);
  font-weight: 500;
  position: sticky;
  top: 0;
  z-index: 10;
}

.history-table td {
  padding: 1rem;
  border-bottom: 1px solid var(--border-color);
  vertical-align: middle;
}

.history-table tr:hover {
  background: rgba(255, 255, 255, 0.02);
}

.error-row {
  background: rgba(239, 68, 68, 0.05);
}

.error-row:hover {
  background: rgba(239, 68, 68, 0.1);
}

.plate-display {
  font-weight: 700;
  letter-spacing: 1px;
}

.edit-input {
  padding: 0.4rem 0.8rem;
  max-width: 150px;
}

.thumb-img {
  width: 80px;
  height: 50px;
  object-fit: cover;
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid var(--border-color);
  transition: transform 0.2s;
}

.thumb-img:hover {
  transform: scale(1.05);
}

.action-buttons {
  display: flex;
  gap: 0.5rem;
}

.btn-action {
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-main);
  padding: 0.4rem 0.8rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  display: flex;
  align-items: center;
  gap: 0.3rem;
  transition: all 0.2s;
}

.edit-btn:hover { background: rgba(59, 130, 246, 0.1); color: var(--primary); border-color: var(--primary); }
.save-btn { background: var(--success); border-color: var(--success); color: white; }
.save-btn:hover { background: #059669; }
.cancel-btn:hover { background: rgba(239, 68, 68, 0.1); color: var(--danger); border-color: var(--danger); }

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.8);
  backdrop-filter: blur(4px);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-content {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
}

.full-image {
  max-width: 100%;
  max-height: 90vh;
  border-radius: 8px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
}

.close-modal {
  position: absolute;
  top: -40px;
  right: 0;
  background: none;
  border: none;
  color: white;
  font-size: 2rem;
  cursor: pointer;
}
</style>
