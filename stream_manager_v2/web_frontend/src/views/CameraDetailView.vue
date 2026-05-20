<template>
  <div class="camera-detail">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <el-button @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          返回
        </el-button>
        <h1>{{ cameraInfo?.name || '摄像头详情' }}</h1>
      </div>
      <div class="header-actions">
        <el-button 
          :type="isRunning ? 'danger' : 'success'"
          @click="toggleCamera"
        >
          {{ isRunning ? '停止' : '启动' }}
        </el-button>
        <el-button @click="takeSnapshot">
          <el-icon><Camera /></el-icon>
          截图
        </el-button>
      </div>
    </div>
    
    <!-- 主要内容 -->
    <el-row :gutter="20">
      <!-- 视频区域 -->
      <el-col :xs="24" :lg="16">
        <div class="video-container">
          <LivePlayer
            v-if="cameraId"
            :camera-id="cameraId"
            :detections="currentDetections"
            :canvas-width="960"
            :canvas-height="540"
          />
          <el-empty v-else description="加载中..." />
        </div>
      </el-col>
      
      <!-- 侧边栏 -->
      <el-col :xs="24" :lg="8">
        <!-- 状态卡片 -->
        <el-card class="status-card">
          <template #header>
            <span>实时状态</span>
          </template>
          <div class="status-list">
            <div class="status-item">
              <span class="label">状态</span>
              <el-tag :type="statusType">{{ statusText }}</el-tag>
            </div>
            <div class="status-item">
              <span class="label">FPS</span>
              <span class="value">{{ cameraStats.fps }}</span>
            </div>
            <div class="status-item">
              <span class="label">处理帧数</span>
              <span class="value">{{ cameraStats.frame_count }}</span>
            </div>
            <div class="status-item">
              <span class="label">检测次数</span>
              <span class="value">{{ cameraStats.detection_count }}</span>
            </div>
            <div class="status-item">
              <span class="label">违规次数</span>
              <span class="value violation">{{ cameraStats.violation_count }}</span>
            </div>
            <div class="status-item">
              <span class="label">重连次数</span>
              <span class="value">{{ cameraStats.reconnect_count }}</span>
            </div>
          </div>
        </el-card>
        
        <!-- 实时检测列表 -->
        <el-card class="detection-card">
          <template #header>
            <span>实时检测</span>
            <el-badge :value="currentDetections.length" v-if="currentDetections.length > 0" />
          </template>
          
          <el-empty v-if="currentDetections.length === 0" description="暂无检测数据" />
          
          <el-scrollbar v-else height="300px">
            <div 
              v-for="det in currentDetections" 
              :key="det.track_id"
              class="detection-item"
            >
              <div class="detection-header">
                <span class="track-id">ID: {{ det.track_id }}</span>
                <el-tag 
                  :type="det.has_helmet && det.has_vest ? 'success' : 'danger'"
                  size="small"
                >
                  {{ det.has_helmet && det.has_vest ? '合规' : '违规' }}
                </el-tag>
              </div>
              <div class="detection-status">
                <span :class="['ppe-status', det.has_helmet ? 'ok' : 'violation']">
                  安全帽: {{ det.has_helmet ? '✓' : '✗' }}
                </span>
                <span :class="['ppe-status', det.has_vest ? 'ok' : 'violation']">
                  反光衣: {{ det.has_vest ? '✓' : '✗' }}
                </span>
                <span :class="['ppe-status', det.has_mask ? 'ok' : 'violation']">
                  口罩: {{ det.has_mask ? '✓' : '✗' }}
                </span>
              </div>
            </div>
          </el-scrollbar>
        </el-card>
        
        <!-- 最近违规 -->
        <el-card class="violation-card">
          <template #header>
            <span>最近违规</span>
          </template>
          
          <el-empty v-if="recentViolations.length === 0" description="暂无违规记录" />
          
          <el-timeline v-else>
            <el-timeline-item
              v-for="v in recentViolations.slice(0, 5)"
              :key="v.id"
              :type="v.severity"
              :timestamp="v.time"
            >
              {{ v.description }}
            </el-timeline-item>
          </el-timeline>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useMonitorStore } from '@/stores/monitor'
import { useWebSocketStore } from '@/stores/websocket'
import { api } from '@/api'
import LivePlayer from '@/components/LivePlayer.vue'

const route = useRoute()
const router = useRouter()
const monitorStore = useMonitorStore()
const wsStore = useWebSocketStore()

const cameraId = route.params.id as string

const cameraInfo = ref<any>(null)
const cameraStats = ref({
  fps: 0,
  frame_count: 0,
  detection_count: 0,
  violation_count: 0,
  reconnect_count: 0
})
const currentDetections = ref<any[]>([])
const recentViolations = ref<any[]>([])

const isRunning = computed(() => cameraInfo.value?.status === 'running')

const statusType = computed(() => {
  const status = cameraInfo.value?.status
  if (status === 'running') return 'success'
  if (status === 'stopped') return 'info'
  if (status === 'error') return 'danger'
  return 'warning'
})

const statusText = computed(() => {
  const status = cameraInfo.value?.status
  const map: Record<string, string> = {
    running: '运行中',
    stopped: '已停止',
    error: '故障',
    connecting: '连接中',
    reconnecting: '重连中'
  }
  return map[status] || status
})

function goBack() {
  router.push('/')
}

async function toggleCamera() {
  try {
    if (isRunning.value) {
      await api.stopCamera(cameraId)
      ElMessage.success('摄像头已停止')
    } else {
      await api.startCamera(cameraId)
      ElMessage.success('摄像头已启动')
    }
    await loadCameraData()
  } catch (error) {
    ElMessage.error('操作失败')
  }
}

async function takeSnapshot() {
  try {
    const res = await api.getSnapshot(cameraId)
    // 下载图片
    const link = document.createElement('a')
    link.href = `data:image/jpeg;base64,${res.image_base64}`
    link.download = `snapshot_${cameraId}_${res.timestamp}.jpg`
    link.click()
    ElMessage.success('截图已保存')
  } catch (error) {
    ElMessage.error('截图失败')
  }
}

async function loadCameraData() {
  try {
    const status = await api.getCameraStatus(cameraId)
    cameraInfo.value = {
      name: status.name,
      status: status.status,
      streamUrl: status.url || ''
    }
    cameraStats.value = status.stats
  } catch (error) {
    console.error('加载摄像头数据失败:', error)
  }
}

onMounted(() => {
  loadCameraData()
  
  // 连接 WebSocket
  wsStore.connect()
  
  // 监听消息
  wsStore.onMessage((message) => {
    if (message.data?.camera_id === cameraId) {
      if (message.type === 'violation') {
        recentViolations.value.unshift({
          id: Date.now(),
          time: new Date().toLocaleString('zh-CN'),
          severity: message.data.severity || 'warning',
          description: message.data.violation_types?.join(', ') || '违规 detected'
        })
      } else if (message.type === 'status') {
        cameraStats.value = message.data.stats
      }
    }
    
    // 更新检测数据
    if (message.data?.detections) {
      currentDetections.value = message.data.detections
    }
  })
  
  // 定时刷新状态
  const interval = setInterval(loadCameraData, 5000)
  
  onUnmounted(() => {
    clearInterval(interval)
    wsStore.disconnect()
  })
})
</script>

<style scoped>
.camera-detail {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-left h1 {
  margin: 0;
  font-size: 20px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.video-container {
  background: #000;
  border-radius: 8px;
  overflow: hidden;
  aspect-ratio: 16/9;
}

.status-card,
.detection-card,
.violation-card {
  margin-bottom: 16px;
}

.status-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.status-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.status-item .label {
  color: #606266;
}

.status-item .value {
  font-weight: 500;
}

.status-item .value.violation {
  color: #f56c6c;
}

.detection-item {
  padding: 12px;
  border-bottom: 1px solid #ebeef5;
}

.detection-item:last-child {
  border-bottom: none;
}

.detection-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.track-id {
  font-weight: 500;
  color: #303133;
}

.detection-status {
  display: flex;
  gap: 16px;
  font-size: 13px;
}

.ppe-status {
  color: #606266;
}

.ppe-status.ok {
  color: #67c23a;
}

.ppe-status.violation {
  color: #f56c6c;
}
</style>
