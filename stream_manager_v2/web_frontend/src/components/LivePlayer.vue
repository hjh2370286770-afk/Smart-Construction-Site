<template>
  <div class="live-player">
    <!-- 视频层 - 使用 MJPEG -->
    <img 
      v-if="!error"
      ref="videoEl" 
      class="video-layer"
      :src="mjpegUrl"
      alt="视频流"
      @error="handleError"
      @load="handleLoad"
    />
    
    <!-- 检测框 overlay 层 -->
    <canvas 
      ref="overlayEl" 
      class="overlay-layer"
      :width="canvasWidth"
      :height="canvasHeight"
    />
    
    <!-- 状态信息 -->
    <div class="status-bar">
      <div class="status-item">
        <span class="label">人员:</span>
        <span class="value">{{ stats.personCount }}</span>
      </div>
      <div class="status-item">
        <span class="label">合规率:</span>
        <span class="value" :class="complianceClass">{{ stats.complianceRate }}%</span>
      </div>
      <div class="status-item" v-if="stats.violations > 0">
        <span class="label">违规:</span>
        <span class="value violation">{{ stats.violations }}</span>
      </div>
    </div>
    
    <!-- 错误提示 -->
    <div v-if="error" class="error-overlay">
      <el-icon :size="48" color="#f56c6c"><VideoPlay /></el-icon>
      <p>视频流加载失败</p>
      <p class="error-detail">{{ error }}</p>
      <el-button @click="retry" type="primary">重试</el-button>
    </div>
    
    <!-- 加载提示 -->
    <div v-if="loading && !error" class="loading-overlay">
      <el-icon :size="32" class="is-loading"><Loading /></el-icon>
      <p>正在加载视频流...</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

interface Detection {
  bbox: [number, number, number, number]
  track_id: number
  has_helmet: boolean
  has_vest: boolean
  has_mask: boolean
}

interface Props {
  cameraId: string
  detections: Detection[]
  canvasWidth?: number
  canvasHeight?: number
}

const props = withDefaults(defineProps<Props>(), {
  canvasWidth: 960,
  canvasHeight: 540
})

const videoEl = ref<HTMLImageElement>()
const overlayEl = ref<HTMLCanvasElement>()
const error = ref('')
const loading = ref(true)

// MJPEG 流 URL - 添加时间戳防止缓存
const mjpegUrl = computed(() => {
  return `/stream/${props.cameraId}/mjpeg?t=${Date.now()}`
})

const stats = ref({
  personCount: 0,
  complianceRate: 100,
  violations: 0
})

const complianceClass = computed(() => {
  const rate = stats.value.complianceRate
  if (rate >= 90) return 'good'
  if (rate >= 70) return 'warning'
  return 'danger'
})

// 绘制检测框
function drawDetections() {
  const canvas = overlayEl.value
  if (!canvas) return
  
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  
  // 清空画布
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  
  if (!props.detections || props.detections.length === 0) return
  
  // 计算缩放比例
  const scaleX = canvas.width / 960
  const scaleY = canvas.height / 540
  
  let compliant = 0
  let violations = 0
  
  props.detections.forEach((det) => {
    const [x1, y1, x2, y2] = det.bbox
    
    // 根据合规状态选择颜色
    let color = '#67c23a' // 绿色 - 合规
    let status = 'OK'
    
    if (!det.has_helmet && !det.has_vest) {
      color = '#f56c6c' // 红色 - 严重违规
      status = 'NO Helmet+Vest!'
      violations++
    } else if (!det.has_helmet) {
      color = '#e6a23c' // 橙色 - 未戴安全帽
      status = 'NO Helmet!'
      violations++
    } else if (!det.has_vest) {
      color = '#409eff' // 蓝色 - 未穿反光衣
      status = 'NO Vest!'
      violations++
    } else {
      compliant++
    }
    
    // 绘制边界框
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.strokeRect(
      x1 * scaleX,
      y1 * scaleY,
      (x2 - x1) * scaleX,
      (y2 - y1) * scaleY
    )
    
    // 绘制标签背景
    const label = `ID:${det.track_id} ${status}`
    ctx.font = 'bold 12px Arial'
    const textWidth = ctx.measureText(label).width
    ctx.fillStyle = color
    ctx.fillRect(x1 * scaleX, y1 * scaleY - 18, textWidth + 8, 18)
    
    // 绘制标签文字
    ctx.fillStyle = '#fff'
    ctx.fillText(label, x1 * scaleX + 4, y1 * scaleY - 5)
  })
  
  // 更新统计
  const total = props.detections.length
  stats.value.personCount = total
  stats.value.violations = violations
  stats.value.complianceRate = total > 0 ? Math.round((compliant / total) * 100) : 100
}

// 监听检测数据变化
watch(() => props.detections, drawDetections, { deep: true })

function handleLoad() {
  loading.value = false
  error.value = ''
}

function handleError(e: Event) {
  loading.value = false
  error.value = '无法连接到视频流'
  console.error('Video stream error:', e)
}

function retry() {
  error.value = ''
  loading.value = true
  // 强制重新加载
  window.location.reload()
}
</script>

<style scoped>
.live-player {
  position: relative;
  width: 100%;
  height: 100%;
  background: #000;
  overflow: hidden;
}

.video-layer {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.overlay-layer {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.status-bar {
  position: absolute;
  top: 10px;
  left: 10px;
  display: flex;
  gap: 16px;
  padding: 8px 16px;
  background: rgba(0, 0, 0, 0.7);
  border-radius: 4px;
  color: #fff;
  font-size: 14px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.status-item .label {
  color: #909399;
}

.status-item .value {
  font-weight: 600;
}

.status-item .value.good {
  color: #67c23a;
}

.status-item .value.warning {
  color: #e6a23c;
}

.status-item .value.danger {
  color: #f56c6c;
}

.status-item .value.violation {
  color: #f56c6c;
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0.3; }
}

.error-overlay,
.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.8);
  color: #fff;
  gap: 12px;
}

.error-overlay p {
  margin: 0;
  color: #f56c6c;
}

.error-overlay .error-detail {
  font-size: 12px;
  color: #909399;
}

.loading-overlay p {
  margin: 0;
  color: #909399;
}

.is-loading {
  animation: rotating 2s linear infinite;
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
