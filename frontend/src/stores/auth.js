import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../utils/api'

const TOKEN_KEY = 'itops-token'
const NAME_KEY = 'itops-username'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const username = ref(localStorage.getItem(NAME_KEY) || '')

  function setSession(data) {
    token.value = data.access_token
    username.value = data.username
    localStorage.setItem(TOKEN_KEY, data.access_token)
    localStorage.setItem(NAME_KEY, data.username)
  }

  async function login(form) {
    const { data } = await api.post('/auth/login', form)
    setSession(data)
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
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(NAME_KEY)
  }

  return { token, username, login, logout, setSession }
})
