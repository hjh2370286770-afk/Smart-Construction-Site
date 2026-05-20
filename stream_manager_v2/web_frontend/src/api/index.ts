import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: `${BASE_URL}/api`,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 摄像头相关 API
export const api = {
  // 获取所有摄像头
  getCameras() {
    return apiClient.get('/cameras').then(res => res.data)
  },

  // 获取摄像头状态
  getCameraStatus(cameraId: string) {
    return apiClient.get(`/cameras/${cameraId}/status`).then(res => res.data)
  },

  // 启动摄像头
  startCamera(cameraId: string) {
    return apiClient.post(`/cameras/${cameraId}/start`).then(res => res.data)
  },

  // 停止摄像头
  stopCamera(cameraId: string) {
    return apiClient.post(`/cameras/${cameraId}/stop`).then(res => res.data)
  },

  // 获取截图
  getSnapshot(cameraId: string) {
    return apiClient.get(`/cameras/${cameraId}/snapshot`).then(res => res.data)
  },

  // 获取违规记录
  getViolations(params?: {
    page?: number
    page_size?: number
    camera_id?: string
    violation_type?: string
    start_time?: string
    end_time?: string
  }) {
    return apiClient.get('/violations', { params }).then(res => res.data)
  },

  // 获取实时统计
  getRealtimeStats() {
    return apiClient.get('/stats/realtime').then(res => res.data)
  },

  // 获取所有工地
  getSites() {
    return apiClient.get('/sites').then(res => res.data)
  }
}

export default api
