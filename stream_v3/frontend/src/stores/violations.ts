import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { violationsApi } from '@/api'
import type { Violation } from '@/types'
import dayjs from 'dayjs'

export const useViolationsStore = defineStore('violations', () => {
  const violations = ref<Violation[]>([])
  const loading = ref(false)
  const total = ref(0)

  const todayViolations = computed(() => {
    const today = dayjs().format('YYYY-MM-DD')
    return violations.value.filter(v => v.timestamp.startsWith(today))
  })

  const violationsByType = computed(() => {
    const counts: Record<string, number> = {}
    violations.value.forEach(v => {
      counts[v.type] = (counts[v.type] || 0) + 1
    })
    return counts
  })

  const violationsByCamera = computed(() => {
    const counts: Record<string, number> = {}
    violations.value.forEach(v => {
      counts[v.stream_id] = (counts[v.stream_id] || 0) + 1
    })
    return counts
  })

  const fetchViolations = async (params?: { 
    stream_id?: string
    start_date?: string
    end_date?: string
    type?: string
    page?: number
    page_size?: number
  }) => {
    loading.value = true
    try {
      const response = await violationsApi.getAll(params)
      violations.value = response.items
      total.value = response.total
    } catch (error) {
      console.error('获取违规记录失败:', error)
    } finally {
      loading.value = false
    }
  }

  const fetchViolationStats = async (days?: number) => {
    try {
      return await violationsApi.getStats({ days })
    } catch (error) {
      console.error('获取违规统计失败:', error)
      return null
    }
  }

  const addViolation = (violation: Violation) => {
    violations.value.unshift(violation)
    total.value++
  }

  return {
    violations,
    loading,
    total,
    todayViolations,
    violationsByType,
    violationsByCamera,
    fetchViolations,
    fetchViolationStats,
    addViolation
  }
})
