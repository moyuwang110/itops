import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
  // 携带 httpOnly Cookie（后端通过 Cookie 鉴权，token 不再存 localStorage）
  withCredentials: true,
})

api.interceptors.request.use((config) => config)

api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error.response?.status
    const body = error.response?.data
    const message = body?.message || error.message || '请求失败'
    const code = body?.code

    if (status === 401 || code === 'unauthorized') {
      const path = window.location.hash.replace('#', '') || '/'
      if (!path.startsWith('/login')) {
        ElMessage.warning('登录已过期，请重新登录')
        window.location.hash = '#/login'
      }
    } else if (error.config && !error.config._silentError) {
      ElMessage.error(message)
    }
    return Promise.reject(error)
  }
)

export default api
