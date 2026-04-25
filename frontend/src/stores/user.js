import { defineStore } from 'pinia'
import { login, logout, getUserInfo } from '@/api/auth'
import router from '@/router'

const getStoredUserInfo = () => {
  const raw = localStorage.getItem('userInfo')
  if (!raw || raw === 'undefined' || raw === 'null') {
    localStorage.removeItem('userInfo')
    return {}
  }

  try {
    return JSON.parse(raw)
  } catch (error) {
    localStorage.removeItem('userInfo')
    return {}
  }
}

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    userInfo: getStoredUserInfo()
  }),

  getters: {
    isLoggedIn: (state) => !!state.token,
    username: (state) => state.userInfo.username || '',
    realName: (state) => state.userInfo.real_name || '',
    roles: (state) => state.userInfo.roles || [],
    permissions: (state) => state.userInfo.permissions || []
  },

  actions: {
    async login(loginForm) {
      try {
        const res = await login(loginForm)
        this.token = res.data.accessToken
        this.userInfo = res.data.user
        localStorage.setItem('token', res.data.accessToken)
        localStorage.setItem('userInfo', JSON.stringify(res.data.user))
        return res
      } catch (error) {
        throw error
      }
    },

    async logout() {
      try {
        await logout()
      } catch (error) {
        console.error('登出失败:', error)
      } finally {
        this.token = ''
        this.userInfo = {}
        localStorage.removeItem('token')
        localStorage.removeItem('userInfo')
        router.push('/login')
      }
    },

    async fetchUserInfo() {
      try {
        const res = await getUserInfo()
        this.userInfo = res
        localStorage.setItem('userInfo', JSON.stringify(res))
        return res
      } catch (error) {
        throw error
      }
    }
  }
})
