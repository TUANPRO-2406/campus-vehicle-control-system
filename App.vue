<template>
  <div id="app-container">
    <nav v-if="isAuthenticated" class="sidebar glass-panel">
      <div class="brand">
        <div class="logo">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
          </svg>
        </div>
        <h2>CampusGuard</h2>
      </div>
      
      <div class="nav-links">
        <template v-if="role === 'BAO_VE'">
          <router-link to="/" class="nav-item" active-class="active">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="7" height="9"></rect>
              <rect x="14" y="3" width="7" height="5"></rect>
              <rect x="14" y="12" width="7" height="9"></rect>
              <rect x="3" y="16" width="7" height="5"></rect>
            </svg>
            Giám sát trực tiếp
          </router-link>
          
          <router-link to="/history" class="nav-item" active-class="active">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            Lịch sử / Sửa lỗi
          </router-link>
        </template>
        
        <template v-if="role === 'QUAN_LY'">
          <router-link to="/stats" class="nav-item" active-class="active">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
              <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
              <line x1="12" y1="22.08" x2="12" y2="12"></line>
            </svg>
            Báo cáo thống kê
          </router-link>
        </template>
      </div>

      <div class="sidebar-footer">
        <div class="user-info">
          <div class="avatar">{{ role === 'QUAN_LY' ? 'QL' : 'BV' }}</div>
          <div>
            <div class="name">{{ username || (role === 'QUAN_LY' ? 'Quản lý' : 'Bảo vệ') }}</div>
            <div class="status">Đang trực</div>
          </div>
        </div>
        <button @click="logout" class="btn btn-outline logout-btn">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9"></path>
          </svg>
          Đăng xuất
        </button>
      </div>
    </nav>
    
    <main class="main-content" :class="{ 'full-width': !isAuthenticated }">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, watchEffect } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const isAuthenticated = ref(localStorage.getItem('auth') === 'true')
const role = ref(localStorage.getItem('role') || '')
const username = ref(localStorage.getItem('username') || '')

watchEffect(() => {
  isAuthenticated.value = localStorage.getItem('auth') === 'true'
  role.value = localStorage.getItem('role') || ''
  username.value = localStorage.getItem('username') || ''
})

const logout = () => {
  localStorage.removeItem('auth')
  localStorage.removeItem('role')
  localStorage.removeItem('username')
  isAuthenticated.value = false
  role.value = ''
  router.push('/login')
}
</script>

<style scoped>
#app-container {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background: radial-gradient(circle at top right, #1e293b, #0f172a);
}

.sidebar {
  width: 280px;
  height: calc(100vh - 32px);
  margin: 16px;
  display: flex;
  flex-direction: column;
  padding: 1.5rem;
}

.brand {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 2.5rem;
}

.logo {
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, var(--primary), #8b5cf6);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.brand h2 {
  font-size: 1.25rem;
  font-weight: 700;
  background: linear-gradient(to right, #fff, #cbd5e1);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.nav-links {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  color: var(--text-muted);
  text-decoration: none;
  border-radius: 12px;
  transition: all 0.3s ease;
  font-weight: 500;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-main);
}

.nav-item.active {
  background: rgba(59, 130, 246, 0.15);
  color: var(--primary);
  border-left: 3px solid var(--primary);
}

.sidebar-footer {
  margin-top: auto;
  border-top: 1px solid var(--border-color);
  padding-top: 1.5rem;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--bg-dark);
  border: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  color: var(--primary);
}

.name {
  font-size: 0.9rem;
  font-weight: 600;
}

.status {
  font-size: 0.8rem;
  color: var(--success);
  display: flex;
  align-items: center;
  gap: 0.3rem;
}

.status::before {
  content: '';
  display: inline-block;
  width: 8px;
  height: 8px;
  background: var(--success);
  border-radius: 50%;
  box-shadow: 0 0 8px var(--success);
}

.logout-btn {
  width: 100%;
  font-size: 0.9rem;
}

.main-content {
  flex: 1;
  height: 100vh;
  overflow-y: auto;
  padding: 16px 16px 16px 0;
}

.main-content.full-width {
  padding: 0;
}
</style>
