<template>
  <div class="test-page">
    <h1>连接测试页面</h1>
    
    <div class="test-section">
      <h2>后端状态</h2>
      <p>API URL: {{ apiUrl }}</p>
      <p>WebSocket URL: {{ wsUrl }}</p>
      <el-button @click="testApi" :loading="testing">测试 API 连接</el-button>
      <div v-if="apiResult" class="result">
        <pre>{{ apiResult }}</pre>
      </div>
    </div>
    
    <div class="test-section">
      <h2>WebSocket 状态</h2>
      <p>连接状态: <el-tag :type="wsStatusType">{{ wsStatus }}</el-tag></p>
      <el-button @click="connectWs" :disabled="wsConnected">连接 WebSocket</el-button>
      <el-button @click="disconnectWs" :disabled="!wsConnected">断开 WebSocket</el-button>
      <div v-if="wsMessages.length > 0" class="messages">
        <h3>收到的消息:</h3>
        <pre v-for="(msg, i) in wsMessages" :key="i">{{ msg }}</pre>
      </div>
    </div>
    
    <div class="test-section">
      <h2>摄像头列表</h2>
      <el-button @click="fetchCameras" :loading="loadingCameras">获取摄像头</el-button>
      <el-table v-if="cameras.length > 0" :data="cameras" style="margin-top: 16px">
        <el-table-column prop="id" label="ID" />
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="status" label="状态" />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/events'

const testing = ref(false)
const apiResult = ref('')
const wsStatus = ref('未连接')
const wsConnected = ref(false)
const wsMessages = ref<any[]>([])
const cameras = ref<any[]>([])
const loadingCameras = ref(false)

let ws: WebSocket | null = null

const wsStatusType = computed(() => {
  if (wsStatus.value === '已连接') return 'success'
  if (wsStatus.value === '连接中') return 'warning'
  return 'danger'
})

async function testApi() {
  testing.value = true
  apiResult.value = ''
  
  try {
    // 测试健康检查
    const healthRes = await fetch('/api/health')
    const health = await healthRes.json()
    
    // 测试摄像头列表
    const camerasRes = await fetch('/api/cameras')
    const cameras = await camerasRes.json()
    
    apiResult.value = JSON.stringify({
      health,
      cameras: cameras.length
    }, null, 2)
  } catch (error: any) {
    apiResult.value = `错误: ${error.message}`
  } finally {
    testing.value = false
  }
}

function connectWs() {
  if (ws) return
  
  wsStatus.value = '连接中'
  
  try {
    ws = new WebSocket(wsUrl)
    
    ws.onopen = () => {
      wsStatus.value = '已连接'
      wsConnected.value = true
    }
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      wsMessages.value.unshift(data)
      if (wsMessages.value.length > 10) {
        wsMessages.value.pop()
      }
    }
    
    ws.onclose = () => {
      wsStatus.value = '已断开'
      wsConnected.value = false
      ws = null
    }
    
    ws.onerror = (error) => {
      wsStatus.value = '错误'
      wsConnected.value = false
      console.error('WebSocket error:', error)
    }
  } catch (error: any) {
    wsStatus.value = '错误'
    apiResult.value = `WebSocket 错误: ${error.message}`
  }
}

function disconnectWs() {
  if (ws) {
    ws.close()
    ws = null
  }
}

async function fetchCameras() {
  loadingCameras.value = true
  
  try {
    const res = await fetch('/api/cameras')
    cameras.value = await res.json()
  } catch (error: any) {
    console.error('获取摄像头失败:', error)
  } finally {
    loadingCameras.value = false
  }
}
</script>

<style scoped>
.test-page {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
}

.test-section {
  margin-bottom: 32px;
  padding: 20px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.test-section h2 {
  margin-top: 0;
  margin-bottom: 16px;
  color: #303133;
}

.result, .messages {
  margin-top: 16px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 4px;
}

pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
