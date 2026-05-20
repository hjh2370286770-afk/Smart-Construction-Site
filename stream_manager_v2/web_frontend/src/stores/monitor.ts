import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/api'

export interface Camera {
  id: string
  name: string
  site_id: string
  site_name: string
  location: string
  status: 'online' | 'offline' | 'error'
  thumbnail?: string
  lastUpdate: string
}

export const useMonitorStore = defineStore('monitor', () => {
  // State
  const cameras = ref<Camera[]>([])
  const totalPersons = ref(0)
  const todayViolations = ref(0)
  const recentViolations = ref<any[]>([])

  // Getters
  const onlineCameras = computed(() => cameras.value.filter(c => c.status === 'online').length)
  const totalCameras = computed(() => cameras.value.length)
  
  const complianceRate = computed(() => {
    if (todayViolations.value === 0) return 100
    // 简化计算：假设每个违规对应一个人员
    const total = totalPersons.value + todayViolations.value
    return total > 0 ? Math.round(((total - todayViolations.value) / total) * 100) : 100
  })

  // Actions
  async function fetchCameras() {
    try {
      const data = await api.getCameras()
      cameras.value = data.map((cam: any) => ({
        id: cam.id,
        name: cam.name,
        site_id: cam.site_id,
        site_name: cam.site_name,
        location: cam.site_name,
        status: cam.status === 'running' ? 'online' : cam.status === 'error' ? 'error' : 'offline',
        lastUpdate: new Date().toISOString()
      }))
    } catch (error) {
      console.error('获取摄像头列表失败:', error)
    }
  }

  async function fetchStats() {
    try {
      const data = await api.getRealtimeStats()
      totalPersons.value = data.total_persons || 0
      todayViolations.value = data.today_violations || 0
    } catch (error) {
      console.error('获取统计数据失败:', error)
    }
  }

  function handleViolation(data: any) {
    todayViolations.value++
    recentViolations.value.unshift({
      id: Date.now(),
      cameraId: data.camera_id,
      cameraName: data.camera_name || data.camera_id,
      type: data.violation_types?.[0] || 'unknown',
      severity: data.severity || 'medium',
      description: data.violation_types?.map((t: string) => {
        const map: Record<string, string> = {
          no_helmet: '未戴安全帽',
          no_vest: '未穿反光衣',
          no_mask: '未戴口罩'
        }
        return map[t] || t
      }).join(', ') || '违规 detected',
      time: new Date().toLocaleString('zh-CN')
    })
    
    // 只保留最近 50 条
    if (recentViolations.value.length > 50) {
      recentViolations.value = recentViolations.value.slice(0, 50)
    }
  }

  function updateCameraStatus(data: any) {
    const camera = cameras.value.find(c => c.id === data.camera_id)
    if (camera) {
      camera.status = data.status === 'running' ? 'online' : 'offline'
      camera.lastUpdate = new Date().toISOString()
    }
    
    if (data.stats) {
      totalPersons.value = data.stats.person_count || 0
    }
  }

  return {
    cameras,
    totalPersons,
    todayViolations,
    recentViolations,
    onlineCameras,
    totalCameras,
    complianceRate,
    fetchCameras,
    fetchStats,
    handleViolation,
    updateCameraStatus
  }
})
