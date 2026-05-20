<template>
  <div class="camera-card" @click="handleClick">
    <div class="camera-thumbnail">
      <!-- 使用 MJPEG 流预览 -->
      <img 
        v-if="props.camera.status === 'online'" 
        :src="`/stream/${props.camera.id}/mjpeg`" 
        alt="camera stream"
        class="stream-preview"
      />
      <div v-else class="no-thumbnail">
        <el-icon :size="48"><VideoCamera /></el-icon>
        <p>{{ statusText }}</p>
      </div>
      <div class="camera-status" :class="props.camera.status">
        <span class="status-dot"></span>
        {{ statusText }}
      </div>
    </div>
    <div class="camera-info">
      <h3 class="camera-name">{{ props.camera.name }}</h3>
      <p class="camera-location">
        <el-icon><Location /></el-icon>
        {{ props.camera.location }}
      </p>
      <p class="camera-time">
        <el-icon><Clock /></el-icon>
        {{ lastUpdateText }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Camera } from '@/stores/monitor'

interface Props {
  camera: Camera
}

const props = defineProps<Props>()
const emit = defineEmits<{
  click: [cameraId: string]
}>()

const statusText = computed(() => {
  const statusMap = {
    online: '在线',
    offline: '离线',
    error: '故障',
  }
  return statusMap[props.camera.status]
})

const lastUpdateText = computed(() => {
  const date = new Date(props.camera.lastUpdate)
  return date.toLocaleString('zh-CN')
})

function handleClick() {
  emit('click', props.camera.id)
}
</script>

<style scoped>
.camera-card {
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  cursor: pointer;
  transition: transform 0.3s, box-shadow 0.3s;
}

.camera-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px 0 rgba(0, 0, 0, 0.15);
}

.camera-thumbnail {
  position: relative;
  width: 100%;
  height: 160px;
  background: #1a1a1a;
  display: flex;
  align-items: center;
  justify-content: center;
}

.camera-thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.no-thumbnail {
  color: #606266;
  text-align: center;
}

.no-thumbnail p {
  margin-top: 8px;
  font-size: 12px;
}

.stream-preview {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.camera-status {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
}

.camera-status.online .status-dot {
  background: #67c23a;
  box-shadow: 0 0 4px #67c23a;
}

.camera-status.offline .status-dot {
  background: #909399;
}

.camera-status.error .status-dot {
  background: #f56c6c;
  box-shadow: 0 0 4px #f56c6c;
}

.camera-info {
  padding: 16px;
}

.camera-name {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.camera-location,
.camera-time {
  display: flex;
  align-items: center;
  font-size: 13px;
  color: #909399;
  margin-bottom: 4px;
}

.camera-location .el-icon,
.camera-time .el-icon {
  margin-right: 4px;
}
</style>
