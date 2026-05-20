import { defineStore } from 'pinia'
import { ref } from 'vue'

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/events'

export const useWebSocketStore = defineStore('websocket', () => {
  // State
  const ws = ref<WebSocket | null>(null)
  const status = ref<'connected' | 'connecting' | 'disconnected'>('disconnected')
  const messageHandlers = ref<((data: any) => void)[]>([])
  let reconnectTimer: number | null = null

  // Actions
  function connect() {
    if (ws.value?.readyState === WebSocket.OPEN) return
    
    status.value = 'connecting'
    
    try {
      ws.value = new WebSocket(WS_URL)
      
      ws.value.onopen = () => {
        console.log('WebSocket connected')
        status.value = 'connected'
        // 发送心跳
        startHeartbeat()
      }
      
      ws.value.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          // 处理心跳响应
          if (data.type === 'pong') return
          
          // 分发消息给所有处理器
          messageHandlers.value.forEach(handler => handler(data))
        } catch (error) {
          console.error('WebSocket message parse error:', error)
        }
      }
      
      ws.value.onclose = () => {
        console.log('WebSocket disconnected')
        status.value = 'disconnected'
        stopHeartbeat()
        // 自动重连
        scheduleReconnect()
      }
      
      ws.value.onerror = (error) => {
        console.error('WebSocket error:', error)
        status.value = 'disconnected'
      }
    } catch (error) {
      console.error('WebSocket connection error:', error)
      status.value = 'disconnected'
      scheduleReconnect()
    }
  }

  function disconnect() {
    stopHeartbeat()
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    status.value = 'disconnected'
  }

  function onMessage(handler: (data: any) => void) {
    messageHandlers.value.push(handler)
    
    // 返回取消订阅函数
    return () => {
      const index = messageHandlers.value.indexOf(handler)
      if (index > -1) {
        messageHandlers.value.splice(index, 1)
      }
    }
  }

  function send(data: any) {
    if (ws.value?.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify(data))
    }
  }

  let heartbeatInterval: number | null = null

  function startHeartbeat() {
    heartbeatInterval = window.setInterval(() => {
      if (ws.value?.readyState === WebSocket.OPEN) {
        ws.value.send('ping')
      }
    }, 30000) // 30秒心跳
  }

  function stopHeartbeat() {
    if (heartbeatInterval) {
      clearInterval(heartbeatInterval)
      heartbeatInterval = null
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer) return
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null
      connect()
    }, 5000) // 5秒后重连
  }

  return {
    status,
    connect,
    disconnect,
    onMessage,
    send
  }
})
