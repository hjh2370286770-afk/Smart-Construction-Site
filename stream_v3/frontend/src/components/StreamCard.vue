<template>
  <el-card class="stream-card" :class="{ 'is-running': stream.status === 'running' }" shadow="hover">
    <div class="card-header">
      <div class="stream-info">
        <h4 class="stream-name">{{ stream.name }}</h4>
        <el-tag 
          :type="stream.status === 'running' ? 'success' : 'info'"
          size="small"
          effect="dark"
        >
          <el-icon v-if="stream.status === 'running'"><VideoPlay /></el-icon>
          <el-icon v-else><VideoPause /></el-icon>
          {{ stream.status === 'running' ? '运行中' : '已停止' }}
        </el-tag>
      </div>
      <el-dropdown @command="handleCommand">
        <el-button circle size="small">
          <el-icon><More /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="detail">查看详情</el-dropdown-item>
            <el-dropdown-item command="edit">编辑</el-dropdown-item>
            <el-dropdown-item command="delete" divided type="danger">删除</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
    
    <div class="video-container" @click="handleDetail">
      <img 
        v-if="stream.status === 'running'"
        :src="`/api/streams/${stream.id}/live`"
        class="video-stream"
        alt="视频流"
        @error="handleImageError"
      />
      <div v-else class="video-placeholder">
        <el-icon size="48"><VideoCamera /></el-icon>
        <p>视频流已停止</p>
        <el-button type="primary" size="small" @click.stop="handleStart">
          <el-icon><VideoPlay /></el-icon>
          启动
        </el-button>
      </div>
      
      <!-- 实时标记 -->
      <div v-if="stream.status === 'running'" class="live-badge">
        <span class="live-dot"></span>
        LIVE
      </div>
    </div>
    
    <div class="card-footer">
      <div class="stream-meta">
        <span class="meta-item">
          <el-icon><Location /></el-icon>
          {{ stream.site_name || '未分配工地' }}
        </span>
        <span class="meta-item">
          <el-icon><Aim /></el-icon>
          {{ formatDetectorType(stream.detector_type) }}
        </span>
      </div>
      
      <div class="stream-actions">
        <el-button 
          v-if="stream.status === 'running'"
          type="danger" 
          size="small"
          @click="handleStop"
        >
          <el-icon><VideoPause /></el-icon>
          停止
        </el-button>
        <el-button 
          v-else
          type="success" 
          size="small"
          @click="handleStart"
        >
          <el-icon><VideoPlay /></el-icon>
          启动
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { Stream } from '@/stores/streams'

const props = defineProps<{
  stream: Stream
}>()

const emit = defineEmits<{
  start: [id: string]
  stop: [id: string]
  detail: [id: string]
}>()

const handleStart = () => {
  emit('start', props.stream.id)
}

const handleStop = () => {
  emit('stop', props.stream.id)
}

const handleDetail = () => {
  emit('detail', props.stream.id)
}

const handleCommand = (command: string) => {
  if (command === 'detail') {
    handleDetail()
  } else if (command === 'edit') {
    // 编辑逻辑
  } else if (command === 'delete') {
    // 删除逻辑
  }
}

const handleImageError = (e: Event) => {
  // 图片加载失败，切换到截图模式
  const img = e.target as HTMLImageElement
  img.src = `/api/streams/${props.stream.id}/snapshot`
}

const formatDetectorType = (type: string) => {
  const map: Record<string, string> = {
    'ppe_detector': 'PPE检测',
    'vehicle_detector': '车辆检测',
    'wall_defect_detector': '墙面缺陷检测'
  }
  return map[type] || type
}
</script>

<style scoped lang="scss">
.stream-card {
  margin-bottom: 20px;
  transition: all 0.3s ease;
  
  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
  }
  
  &.is-running {
    border: 1px solid #67c23a;
  }
  
  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
    
    .stream-info {
      display: flex;
      align-items: center;
      gap: 12px;
      
      .stream-name {
        margin: 0;
        font-size: 16px;
        font-weight: 600;
        color: #303133;
      }
    }
  }
  
  .video-container {
    position: relative;
    width: 100%;
    height: 200px;
    background: #000;
    border-radius: 8px;
    overflow: hidden;
    cursor: pointer;
    
    .video-stream {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    
    .video-placeholder {
      width: 100%;
      height: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      color: #909399;
      background: #f5f7fa;
      
      p {
        margin: 12px 0;
        font-size: 14px;
      }
    }
    
    .live-badge {
      position: absolute;
      top: 12px;
      left: 12px;
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      background: rgba(245, 34, 45, 0.9);
      color: #fff;
      font-size: 12px;
      font-weight: 600;
      border-radius: 4px;
      
      .live-dot {
        width: 8px;
        height: 8px;
        background: #fff;
        border-radius: 50%;
        animation: pulse 1.5s infinite;
      }
    }
  }
  
  .card-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid #ebeef5;
    
    .stream-meta {
      display: flex;
      gap: 16px;
      
      .meta-item {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 13px;
        color: #606266;
      }
    }
  }
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}
</style>
