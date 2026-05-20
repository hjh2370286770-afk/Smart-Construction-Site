import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { streamsApi } from '@/api'
import type { Stream } from '@/types'

export const useStreamsStore = defineStore('streams', () => {
  const streams = ref<Stream[]>([])
  const loading = ref(false)
  const currentStream = ref<Stream | null>(null)

  const runningStreams = computed(() => 
    streams.value.filter(s => s.status === 'running')
  )

  const stoppedStreams = computed(() => 
    streams.value.filter(s => s.status === 'stopped')
  )

  const fetchStreams = async () => {
    loading.value = true
    try {
      streams.value = await streamsApi.getAll()
    } catch (error) {
      console.error('获取视频流列表失败:', error)
    } finally {
      loading.value = false
    }
  }

  const startStream = async (id: string) => {
    try {
      await streamsApi.start(id)
      await fetchStreams()
    } catch (error) {
      console.error('启动视频流失败:', error)
      throw error
    }
  }

  const stopStream = async (id: string) => {
    try {
      await streamsApi.stop(id)
      await fetchStreams()
    } catch (error) {
      console.error('停止视频流失败:', error)
      throw error
    }
  }

  const getStreamById = (id: string) => {
    return streams.value.find(s => s.id === id)
  }

  return {
    streams,
    loading,
    currentStream,
    runningStreams,
    stoppedStreams,
    fetchStreams,
    startStream,
    stopStream,
    getStreamById
  }
})
