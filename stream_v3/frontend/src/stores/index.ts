import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { SystemStatus } from '@/types'
import { systemApi } from '@/api'

export const useSystemStore = defineStore('system', () => {
  const status = ref<SystemStatus | null>(null)
  const loading = ref(false)

  const isHealthy = computed(() => {
    if (!status.value) return false
    return status.value.cpu_usage < 90 && status.value.memory_usage < 90
  })

  async function fetchStatus() {
    try {
      loading.value = true
      status.value = await systemApi.getStatus()
    } catch (error) {
      console.error('Failed to fetch system status:', error)
    } finally {
      loading.value = false
    }
  }

  function startPolling(interval = 30000) {
    fetchStatus()
    return setInterval(fetchStatus, interval)
  }

  return {
    status,
    loading,
    isHealthy,
    fetchStatus,
    startPolling
  }
})
