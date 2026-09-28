import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../utils/api'

const NAME_KEY = 'itops-username'
const AVATAR_KEY = 'itops-avatar'

export const useAuthStore = defineStore('auth', () => {
  // token 由后端 httpOnly Cookie 管理，前端不再持有；仅缓存用户名/头像用于显示
  const token = ref('')
  const username = ref(localStorage.getItem(NAME_KEY) || '')
  const avatar = ref(localStorage.getItem(AVATAR_KEY) || '')

  function setSession(data) {
    token.value = data.access_token || ''
    username.value = data.username || ''
    avatar.value = data.avatar || ''
    localStorage.setItem(NAME_KEY, username.value)
    localStorage.setItem(AVATAR_KEY, avatar.value)
  }

  async function login(form) {
    // form 可能是 Vue 响应式对象，浅拷贝避免序列化异常
    const payload = { username: form.username, password: form.password }
    const { data } = await api.post('/auth/login', payload)
    setSession(data)
    return data
  }

  async function fetchProfile() {
    const { data } = await api.get('/auth/me')
    username.value = data.username || ''
    avatar.value = data.avatar || ''
    localStorage.setItem(NAME_KEY, username.value)
    localStorage.setItem(AVATAR_KEY, avatar.value)
    return data
  }

  async function updateProfile(payload) {
    const { data } = await api.put('/auth/profile', payload)
    username.value = data.username || ''
    avatar.value = data.avatar || ''
    localStorage.setItem(NAME_KEY, username.value)
    localStorage.setItem(AVATAR_KEY, avatar.value)
    return data
  }

  async function changePassword(oldPassword, newPassword) {
    const { data } = await api.put('/auth/password', {
      old_password: oldPassword,
      new_password: newPassword,
    })
    return data
  }

  async function logout() {
    try {
      await api.post('/auth/logout')
    } catch (e) {
      // 忽略服务端退出失败，本地一定清除
    }
    token.value = ''
    username.value = ''
    avatar.value = ''
    localStorage.removeItem(NAME_KEY)
    localStorage.removeItem(AVATAR_KEY)
  }

  return { token, username, avatar, login, logout, setSession, fetchProfile, updateProfile, changePassword }
})
