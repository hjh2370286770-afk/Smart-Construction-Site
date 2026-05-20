import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { WebSocketMessage } from '@/types'

export const useWebSocketStore = defineStore('websocket', () => {
  const ws = ref<WebSocket | null>(null)
  const isConnected = ref(false)
  const reconnectAttempts = ref(0)
  const maxReconnectAttempts = 5
  const messages = ref<WebSocketMessage[]>([])

  const connect = () => {
    if (ws.value?.readyState === WebSocket.OPEN) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws`
    
    ws.value = new WebSocket(wsUrl)

    ws.value.onopen = () => {
      isConnected.value = true
      reconnectAttempts.value = 0
      console.log('WebSocket连接成功')
    }

    ws.value.onmessage = (event) => {
      try {
        const data: WebSocketMessage = JSON.parse(event.data)
        messages.value.push(data)
        
        // 处理不同类型的消息
        if (data.type === 'violation') {
          // 触发违规通知
          window.dispatchEvent(new CustomEvent('violation', { detail: data.data }))
        } else if (data.type === 'status') {
          // 触发状态更新
          window.dispatchEvent(new CustomEvent('status', { detail: data.data }))
        } else if (data.type === 'vehicle_wash_entry') {
          // 车辆进场事件
          window.dispatchEvent(new CustomEvent('vehicle-wash-entry', { detail: data.data }))
        } else if (data.type === 'vehicle_wash_exit') {
          // 车辆出场事件
          window.dispatchEvent(new CustomEvent('vehicle-wash-exit', { detail: data.data }))
        } else if (data.type === 'vehicle_wash_start') {
          // 清洗开始事件
          window.dispatchEvent(new CustomEvent('vehicle-wash-start', { detail: data.data }))
        } else if (data.type === 'vehicle_wash_complete') {
          // 清洗完成事件
          window.dispatchEvent(new CustomEvent('vehicle-wash-complete', { detail: data.data }))
        } else if (data.type === 'vehicle_wash_status') {
          // 实时状态更新
          window.dispatchEvent(new CustomEvent('vehicle-wash-status', { detail: data.data }))
        }
      } catch (e) {
        console.error('WebSocket消息解析失败:', e)
      }
    }

    ws.value.onclose = () => {
      isConnected.value = false
      if (reconnectAttempts.value < maxReconnectAttempts) {
        reconnectAttempts.value++
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.value - 1), 30000)
        console.log(`WebSocket重连中... (${reconnectAttempts.value}/${maxReconnectAttempts})`)
        setTimeout(connect, delay)
      }
    }

    ws.value.onerror = (error) => {
      console.error('WebSocket错误:', error)
    }
  }

  const disconnect = () => {
    ws.value?.close()
  }

  const send = (message: any) => {
    if (ws.value?.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify(message))
    }
  }

  return {
    ws,
    isConnected,
    messages,
    connect,
    disconnect,
    send
  }
})
