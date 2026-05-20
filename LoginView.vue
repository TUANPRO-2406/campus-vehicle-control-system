<template>
  <div class="login-container animate-fade-in">
    <div class="login-box glass-panel">
      <div class="login-header">
        <div class="logo">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
          </svg>
        </div>
        <h1>CampusGuard</h1>
        <p>Hệ thống giám sát xe ra vào khuôn viên</p>
      </div>

      <form @submit.prevent="handleLogin" class="login-form">
        <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>
        
        <div class="form-group">
          <label>Tên đăng nhập</label>
          <input type="text" v-model="username" class="input-field" placeholder="Nhập tên đăng nhập" required />
        </div>
        
        <div class="form-group">
          <label>Mật khẩu</label>
          <input type="password" v-model="password" class="input-field" placeholder="Nhập mật khẩu" required />
        </div>

        <button type="submit" class="btn btn-primary login-btn" :disabled="isLoading">
          <span>{{ isLoading ? 'Đang đăng nhập...' : 'Đăng nhập hệ thống' }}</span>
          <svg v-if="!isLoading" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 12h14M12 5l7 7-7 7"></path>
          </svg>
        </button>
      </form>
      
      <div style="margin-top: 1.5rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
        <p>Tài khoản test:</p>
        <p>Bảo vệ: <strong>baove / 123</strong></p>
        <p>Quản lý: <strong>quanly / 123</strong></p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const username = ref('')
const password = ref('')
const errorMsg = ref('')
const isLoading = ref(false)

const handleLogin = async () => {
  if (!username.value || !password.value) return
  
  isLoading.value = true
  errorMsg.value = ''
  
  try {
    const res = await fetch('http://localhost:8000/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username.value, password: password.value })
    })
    
    const data = await res.json()
    
    if (res.ok) {
      localStorage.setItem('auth', 'true')
      localStorage.setItem('role', data.role)
      localStorage.setItem('username', data.username)
      localStorage.setItem('token', data.token)
      
      window.dispatchEvent(new Event('storage'))
      
      if (data.role === 'QUAN_LY') {
        router.push('/stats')
      } else {
        router.push('/')
      }
    } else {
      errorMsg.value = data.detail || 'Sai thông tin đăng nhập'
    }
  } catch (err) {
    errorMsg.value = 'Không thể kết nối đến server'
  } finally {
    isLoading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  width: 100%;
  background: url('https://images.unsplash.com/photo-1541888056262-171b3e7bc8a7?q=80&w=2000&auto=format&fit=crop') center/cover no-repeat;
  position: relative;
}

.login-container::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at center, rgba(15, 23, 42, 0.7), rgba(15, 23, 42, 0.95));
}

.login-box {
  position: relative;
  z-index: 10;
  width: 100%;
  max-width: 420px;
  padding: 3rem 2.5rem;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
}

.login-header {
  text-align: center;
  margin-bottom: 2.5rem;
}

.logo {
  width: 64px;
  height: 64px;
  margin: 0 auto 1.5rem;
  background: linear-gradient(135deg, var(--primary), #8b5cf6);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  box-shadow: 0 10px 25px rgba(59, 130, 246, 0.4);
}

.login-header h1 {
  font-size: 1.8rem;
  font-weight: 700;
  margin-bottom: 0.5rem;
}

.login-header p {
  color: var(--text-muted);
  font-size: 0.9rem;
}

.form-group {
  margin-bottom: 1.5rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text-muted);
}

.login-btn {
  width: 100%;
  margin-top: 1rem;
  height: 48px;
  font-size: 1rem;
}

.error-msg {
  background: rgba(239, 68, 68, 0.1);
  color: var(--danger);
  padding: 0.75rem;
  border-radius: 8px;
  margin-bottom: 1rem;
  font-size: 0.9rem;
  text-align: center;
  border: 1px solid rgba(239, 68, 68, 0.2);
}
</style>
