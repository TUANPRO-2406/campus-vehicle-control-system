import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '../views/LoginView.vue'
import DashboardView from '../views/DashboardView.vue'
import HistoryView from '../views/HistoryView.vue'
import StatsView from '../views/StatsView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView
    },
    {
      path: '/',
      name: 'dashboard',
      component: DashboardView,
      meta: { requiresAuth: true, role: 'BAO_VE' }
    },
    {
      path: '/history',
      name: 'history',
      component: HistoryView,
      meta: { requiresAuth: true, role: 'BAO_VE' }
    },
    {
      path: '/stats',
      name: 'stats',
      component: StatsView,
      meta: { requiresAuth: true, role: 'QUAN_LY' }
    }
  ]
})

router.beforeEach((to, from, next) => {
  const isAuthenticated = localStorage.getItem('auth') === 'true'
  const role = localStorage.getItem('role')

  if (to.meta.requiresAuth && !isAuthenticated && to.name !== 'login') {
    next({ name: 'login' })
  } else if (to.name === 'login' && isAuthenticated) {
    if (role === 'QUAN_LY') next({ name: 'stats' })
    else next({ name: 'dashboard' })
  } else if (to.meta.role && to.meta.role !== role) {
    if (role === 'QUAN_LY') next({ name: 'stats' })
    else next({ name: 'dashboard' })
  } else {
    next()
  }
})

export default router
