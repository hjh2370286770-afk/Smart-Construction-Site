import axios from 'axios'
import type {
  Stream,
  Violation,
  DailyReport,
  SystemStatus,
  DetectionConfig,
  NotificationConfig
} from '@/types'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

export const streamsApi = {
  getAll(): Promise<Stream[]> {
    return api.get('/streams').then((res) => res.data)
  },

  getById(id: string): Promise<Stream> {
    return api.get(`/streams/${id}`).then((res) => res.data)
  },

  create(stream: Partial<Stream>): Promise<Stream> {
    return api.post('/streams', stream).then((res) => res.data)
  },

  update(id: string, stream: Partial<Stream>): Promise<Stream> {
    return api.put(`/streams/${id}`, stream).then((res) => res.data)
  },

  delete(id: string): Promise<void> {
    return api.delete(`/streams/${id}`).then((res) => res.data)
  },

  start(id: string): Promise<void> {
    return api.post(`/streams/${id}/start`).then((res) => res.data)
  },

  stop(id: string): Promise<void> {
    return api.post(`/streams/${id}/stop`).then((res) => res.data)
  },

  getSnapshotUrl(id: string): string {
    return `/api/streams/${id}/snapshot`
  },

  getMjpegUrl(id: string): string {
    return `/api/streams/${id}/mjpeg`
  },

  getStats(id: string): Promise<any> {
    return api.get(`/streams/${id}/stats`).then((res) => res.data)
  }
}

export const violationsApi = {
  getAll(params?: {
    stream_id?: string
    start_date?: string
    end_date?: string
    type?: string
    page?: number
    page_size?: number
  }): Promise<{ items: Violation[]; total: number }> {
    // 直接从截图文件读取的API
    const page = params?.page || 1
    const pageSize = params?.page_size || 20
    
    return api.get('/violations', { 
      params: { 
        camera_id: params?.stream_id,
        limit: pageSize,
        page: page
      } 
    }).then((res) => {
      const response = res.data
      let data = response.items || []
      
      // 按日期筛选（前端筛选，因为后端目前只返回文件名解析的数据）
      if (params?.start_date || params?.end_date) {
        data = data.filter((v: any) => {
          const date = v.timestamp.substring(0, 10)
          if (params.start_date && date < params.start_date) return false
          if (params.end_date && date > params.end_date) return false
          return true
        })
      }
      
      // 按类型筛选
      if (params?.type) {
        data = data.filter((v: any) => v.violation_type === params.type)
      }
      
      // 转换数据格式以匹配前端期望
      const items = data.map((v: any) => ({
        id: v.id,  // 现在是完整的文件名，如: violation_20260415_150639_ID5_no_helmet_no_vest_no_mask
        timestamp: v.timestamp,
        stream_id: v.camera_id,
        stream_name: v.camera_name || v.camera_id,
        type: v.violation_type,
        confidence: 0.85, // 默认值
        // 使用完整的文件名作为ID来获取图片，确保唯一匹配
        image_url: `/api/violations/${encodeURIComponent(v.id)}/image?camera_id=${v.camera_id}`,
        location: '',
        severity: v.severity,
        description: v.description
      }))
      
      return { items, total: response.total }
    })
  },

  getById(id: string): Promise<Violation> {
    return api.get(`/violations/${id}`).then((res) => res.data)
  },

  delete(id: string): Promise<void> {
    return api.delete(`/violations/${id}`).then((res) => res.data)
  },

  export(params?: { start_date?: string; end_date?: string }): Promise<Blob> {
    return api
      .get('/violations/export', {
        params,
        responseType: 'blob'
      })
      .then((res) => res.data)
  },

  getTypes(): Promise<string[]> {
    return api.get('/violations/types').then((res) => res.data)
  },

  getStats(params?: { days?: number; stream_id?: string }): Promise<any> {
    // 使用旧API获取内存中的违规统计
    return api.get('/violations/stats').then((res) => {
      const data = res.data
      return {
        total: data.total,
        by_type: data.by_type,
        by_stream: Object.entries(data.by_camera || {}).map(([id, count]) => ({
          stream_id: id,
          stream_name: id,
          count
        })),
        hourly: {},
        daily: {}
      }
    })
  }
}

export const reportsApi = {
  getDaily(date: string): Promise<DailyReport> {
    return api.get(`/reports/daily/${date}`).then((res) => res.data)
  },

  getHistory(params?: { page?: number; page_size?: number }): Promise<{ items: DailyReport[]; total: number }> {
    return api.get('/reports/history', { params }).then((res) => res.data)
  },

  generate(date: string): Promise<DailyReport> {
    return api.post(`/reports/generate`, { date }).then((res) => res.data)
  },

  download(date: string, format: 'pdf' | 'excel'): Promise<Blob> {
    return api
      .get(`/reports/download/${date}`, {
        params: { format },
        responseType: 'blob'
      })
      .then((res) => res.data)
  }
}

export const detectorsApi = {
  getAll(): Promise<{ id: string; name: string }[]> {
    return api.get('/detectors').then((res) => res.data)
  }
}

export const systemApi = {
  getStatus(): Promise<SystemStatus> {
    return api.get('/system/status').then((res) => res.data)
  },

  getConfig(): Promise<{ detection: DetectionConfig; notification: NotificationConfig }> {
    return api.get('/system/config').then((res) => res.data)
  },

  updateDetectionConfig(config: DetectionConfig): Promise<DetectionConfig> {
    return api.put('/system/config/detection', config).then((res) => res.data)
  },

  updateNotificationConfig(config: NotificationConfig): Promise<NotificationConfig> {
    return api.put('/system/config/notification', config).then((res) => res.data)
  },

  reloadConfig(): Promise<void> {
    return api.post('/system/reload').then((res) => res.data)
  }
}

export const vehicleWashApi = {
  getRecords(params?: {
    start_date?: string
    end_date?: string
    plate?: string
    is_washed?: boolean
    has_exited?: boolean
    limit?: number
    offset?: number
  }): Promise<any[]> {
    return api.get('/vehicle-wash/records', { params }).then((res) => res.data)
  },

  getRecordById(id: number): Promise<any> {
    return api.get(`/vehicle-wash/records/${id}`).then((res) => res.data)
  },

  getStats(): Promise<any> {
    return api.get('/vehicle-wash/stats').then((res) => res.data)
  },

  getDailyStats(days?: number): Promise<any[]> {
    return api.get('/vehicle-wash/stats/daily', { params: { days } }).then((res) => res.data)
  },

  getPlateStats(limit?: number): Promise<any[]> {
    return api.get('/vehicle-wash/stats/plates', { params: { limit } }).then((res) => res.data)
  },

  getActiveVehicles(): Promise<any[]> {
    return api.get('/vehicle-wash/active-vehicles').then((res) => res.data)
  },

  getRealtimeStatus(): Promise<any> {
    return api.get('/vehicle-wash/realtime').then((res) => res.data)
  },

  export(params?: { start_date?: string; end_date?: string; plate?: string }): Promise<any> {
    return api.post('/vehicle-wash/export', null, { params }).then((res) => res.data)
  },

  downloadExport(file: string): string {
    return `/api/vehicle-wash/download?file=${encodeURIComponent(file)}`
  }
}

export default api
