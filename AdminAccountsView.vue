<template>
  <div class="admin-container animate-fade-in">
    <header class="admin-header">
      <div>
        <h1>Hệ thống Quản trị Tài khoản</h1>
        <p class="subtitle">Bảng điều khiển cấp cao - Cấp quyền và giám sát nhân sự hệ thống</p>
      </div>
      <div class="header-actions">
        <button @click="openCreateModal" class="btn btn-primary">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="5" x2="12" y2="19"></line>
            <line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
          Thêm tài khoản mới
        </button>
      </div>
    </header>

    <div class="stats-overview">
      <div class="stat-card glass-panel">
        <div class="stat-label">Tổng số tài khoản</div>
        <div class="stat-value text-primary">{{ accounts.length }}</div>
      </div>
    </div>
    
    <div class="table-container glass-panel">
      <div class="panel-header">
        <h3>Danh sách tài khoản hệ thống</h3>
        <span class="refresh-btn" @click="fetchAccounts" title="Tải lại dữ liệu">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
        </span>
      </div>

      <div class="table-wrapper">
        <table class="admin-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Tên đăng nhập (Username)</th>
              <th>Phân quyền cấp hệ thống</th>
              <th class="text-center">Hành động</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="acc in accounts" :key="acc.id">
              <td><span class="id-badge">#{{ acc.id }}</span></td>
              <td class="username-cell">
                <div class="user-avatar">{{ acc.username.substring(0,2).toUpperCase() }}</div>
                <strong>{{ acc.username }}</strong>
              </td>
              <td>
                <span :class="['role-badge', acc.role === 'ADMIN' ? 'role-admin' : (acc.role === 'QUAN_LY' ? 'role-manager' : 'role-guard')]">
                  {{ acc.role === 'ADMIN' ? 'Quản trị tối cao' : (acc.role === 'QUAN_LY' ? 'Ban quản lý' : 'Bảo vệ trực ca') }}
                </span>
              </td>
              <td class="text-center">
                <div class="action-buttons">
                  <button 
                    @click="openEditModal(acc)" 
                    class="btn-edit"
                    :disabled="acc.username === 'admin'"
                    :title="acc.username === 'admin' ? 'Không được phép sửa tài khoản gốc' : 'Chỉnh sửa tài khoản này'"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                      <path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4Z"></path>
                    </svg>
                  </button>

                  <button 
                    @click="deleteAccount(acc)" 
                    class="btn-delete" 
                    :disabled="acc.username === 'admin'"
                    :title="acc.username === 'admin' ? 'Không được phép xóa tài khoản gốc' : 'Xóa tài khoản này'"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="3 6 5 6 21 6"></polyline>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                      <line x1="10" y1="11" x2="10" y2="17"></line>
                      <line x1="14" y1="11" x2="14" y2="17"></line>
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="accounts.length === 0">
              <td colspan="4" class="text-center no-data">Đang tải dữ liệu từ trung tâm dữ liệu...</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal-content glass-panel animate-scale-in">
        <div class="modal-header">
          <h3>{{ isEditMode ? 'Cập nhật tài khoản nhân sự' : 'Cấp tài khoản mới' }}</h3>
          <button @click="closeModal" class="close-btn">&times;</button>
        </div>
        <form @submit.prevent="handleSubmit" class="modal-form">
          <div class="form-group">
            <label>Tên đăng nhập (Username)</label>
            <input v-model="form.username" type="text" placeholder="Nhập tên viết liền không dấu..." required />
          </div>
          <div class="form-group">
            <label>{{ isEditMode ? 'Mật khẩu mới' : 'Mật khẩu đăng nhập' }}</label>
            <input v-model="form.password" type="password" placeholder="Nhập mật khẩu bí mật..." required />
          </div>
          <div class="form-group">
            <label>Cấp quyền hạn truy cập</label>
            <select v-model="form.role" required>
              <option value="BAO_VE">Bảo vệ (Màn hình Giám sát trực tiếp / Lịch sử)</option>
              <option value="QUAN_LY">Ban quản lý (Chỉ xem Báo cáo thống kê)</option>
              <option value="ADMIN">Quản trị tối cao (Đầy đủ tất cả các quyền)</option>
            </select>
          </div>
          <div class="form-actions">
            <button type="button" @click="closeModal" class="btn btn-outline">Hủy bỏ</button>
            <button type="submit" class="btn btn-primary" :disabled="isSubmitting">
              {{ isSubmitting ? 'Đang xử lý...' : (isEditMode ? 'Cập nhật ngay' : 'Xác nhận cấp phát') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'

const accounts = ref([])
const showModal = ref(false)
const isEditMode = ref(false)
const isSubmitting = ref(false)
const currentAccountId = ref(null)

const form = ref({
  username: '',
  password: '',
  role: 'BAO_VE'
})

// Tải danh sách từ backend
const fetchAccounts = async () => {
  try {
    const res = await fetch('http://localhost:8000/api/admin/accounts')
    if (!res.ok) throw new Error()
    accounts.value = await res.json()
  } catch (err) {
    alert('Không thể kết nối lấy dữ liệu danh sách tài khoản!')
  }
}

// Hàm điều phối khi bấm "Thêm tài khoản mới"
const openCreateModal = () => {
  isEditMode.value = false
  currentAccountId.value = null
  form.value = { username: '', password: '', role: 'BAO_VE' }
  showModal.value = true
}

// Hàm điều phối khi bấm nút "Sửa" hình cái bút
const openEditModal = (account) => {
  isEditMode.value = true
  currentAccountId.value = account.id
  form.value = {
    username: account.username,
    password: '', // Yêu cầu điền mật khẩu mới để tăng tính bảo mật
    role: account.role
  }
  showModal.value = true
}

const closeModal = () => {
  showModal.value = false
}

// Xử lý Gửi Form thông minh (Nhận diện POST/PUT linh hoạt)
const handleSubmit = async () => {
  isSubmitting.value = true
  const url = isEditMode.value 
    ? `http://localhost:8000/api/admin/accounts/${currentAccountId.value}`
    : 'http://localhost:8000/api/admin/accounts'
    
  const method = isEditMode.value ? 'PUT' : 'POST'

  try {
    const res = await fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form.value)
    })
    const data = await res.json()
    
    if (res.ok && data.success) {
      alert(data.message)
      closeModal()
      fetchAccounts() // Tải lại danh sách cập nhật mới
    } else {
      alert(data.detail || 'Thao tác dữ liệu thất bại!')
    }
  } catch (err) {
    alert('Lỗi đường truyền kết nối đến máy chủ Backend!')
  } finally {
    isSubmitting.value = false
  }
}

// Xóa tài khoản
const deleteAccount = async (account) => {
  if (!confirm(`Bạn có chắc chắn muốn thu hồi tài khoản "${account.username}" không?`)) return
  try {
    const res = await fetch(`http://localhost:8000/api/admin/accounts/${account.id}`, {
      method: 'DELETE'
    })
    const data = await res.json()
    if (res.ok && data.success) {
      alert(data.message)
      fetchAccounts()
    } else {
      alert(data.detail || 'Xóa tài khoản thất bại!')
    }
  } catch (err) {
    alert('Lỗi hệ thống khi thực hiện lệnh xóa!')
  }
}

onMounted(() => {
  fetchAccounts()
})
</script>

<style scoped>
.admin-container {
  padding: 1.5rem;
  color: #f8fafc;
}

.admin-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

.admin-header h1 {
  font-size: 1.75rem;
  font-weight: 700;
  margin: 0 0 0.5rem 0;
  background: linear-gradient(to right, #fff, #94a3b8);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.subtitle {
  color: #94a3b8;
  margin: 0;
  font-size: 0.95rem;
}

.stats-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.stat-card {
  padding: 1.5rem;
  border-radius: 12px;
}

.stat-label {
  color: #94a3b8;
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.5rem;
}

.stat-value {
  font-size: 2rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.active-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  background: #10b981;
  border-radius: 50%;
  box-shadow: 0 0 10px #10b981;
}

.table-container {
  border-radius: 16px;
  padding: 1.5rem;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.25rem;
}

.panel-header h3 {
  margin: 0;
  font-size: 1.15rem;
}

.refresh-btn {
  cursor: pointer;
  color: #94a3b8;
  transition: color 0.2s;
}

.refresh-btn:hover {
  color: #3b82f6;
}

.table-wrapper {
  overflow-x: auto;
}

.admin-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}

.admin-table th {
  padding: 1rem;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  color: #94a3b8;
  font-weight: 600;
  font-size: 0.9rem;
}

.admin-table td {
  padding: 1rem;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  font-size: 0.95rem;
}

.id-badge {
  background: rgba(255,255,255,0.05);
  padding: 0.2rem 0.5rem;
  border-radius: 6px;
  color: #cbd5e1;
  font-family: monospace;
}

.username-cell {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.user-avatar {
  width: 32px;
  height: 32px;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: #3b82f6;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.8rem;
}

.role-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 600;
}

.role-admin { background: rgba(139, 92, 246, 0.15); color: #a78bfa; border: 1px solid rgba(139, 92, 246, 0.3); }
.role-manager { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
.role-guard { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }

.status-indicator {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
  color: #cbd5e1;
}

.dot-online {
  width: 6px;
  height: 6px;
  background: #10b981;
  border-radius: 50%;
}

.btn-delete {
  background: transparent;
  border: none;
  color: #f87171;
  cursor: pointer;
  padding: 0.4rem;
  border-radius: 6px;
  transition: all 0.2s;
}

.btn-delete:hover:not(:disabled) {
  background: rgba(239, 64, 64, 0.2);
  color: #ef4444;
}

.btn-delete:disabled {
  color: #475569;
  cursor: not-allowed;
  opacity: 0.4;
}

/* BUTTONS */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 1.2rem;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: #3b82f6;
  color: white;
  border: none;
}

.btn-primary:hover { background: #2563eb; }

.btn-outline {
  background: transparent;
  border: 1px solid rgba(255,255,255,0.15);
  color: #cbd5e1;
}

.btn-outline:hover { background: rgba(255,255,255,0.05); }

/* MODAL STYLES */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(15, 23, 42, 0.7);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
}

.modal-content {
  width: 450px;
  padding: 2rem;
  border-radius: 16px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.modal-header h3 { margin: 0; font-size: 1.25rem; }

.close-btn {
  background: transparent;
  border: none;
  color: #94a3b8;
  font-size: 1.75rem;
  cursor: pointer;
}

.modal-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-group label {
  font-size: 0.85rem;
  color: #cbd5e1;
  font-weight: 500;
}

.form-group input, .form-group select {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(255,255,255,0.1);
  padding: 0.75rem;
  border-radius: 8px;
  color: white;
  font-size: 0.95rem;
}

.form-group input:focus, .form-group select:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.2);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1rem;
}

.text-center { text-align: center; }
.text-primary { color: #3b82f6; }
.text-success { color: #10b981; }
.no-data { color: #64748b; padding: 2rem 0 !important; }

/* ANIMATIONS */
.animate-fade-in {
  animation: fadeIn 0.4s ease forwards;
}

.animate-scale-in {
  animation: scaleIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes scaleIn {
  from { opacity: 0; transform: scale(0.92); }
  to { opacity: 1; transform: scale(1); }
}
</style>