<template>
  <div class="stream-detail-view">
    <!-- 页面头部 -->
    <div class="page-header">
      <el-button text @click="$router.back()">
        <el-icon><ArrowLeft /></el-icon>
        返回
      </el-button>
      <h2>{{ stream?.name || '视频流详情' }}</h2>
      <div class="header-actions">
        <el-button :type="stream?.status === 'running' ? 'danger' : 'success'" @click="toggleStream">
          <el-icon>
            <VideoPause v-if="stream?.status === 'running'" />
            <VideoPlay v-else />
          </el-icon>
          {{ stream?.status === 'running' ? '停止' : '启动' }}
        </el-button>
        <el-button @click="showEditDialog = true">
          <el-icon><Edit /></el-icon>
          编辑
        </el-button>
      </div>
    </div>

    <el-row :gutter="20">
      <!-- 左侧：视频流展示 -->
      <el-col :span="16">
        <el-card class="video-card" shadow="never">
          <div class="video-wrapper">
            <img
              v-if="stream?.status === 'running'"
              :src="`/api/streams/${streamId}/live`"
              class="main-video"
              alt="视频流"
            />
            <div v-else class="video-placeholder">
              <el-icon size="64"><VideoCamera /></el-icon>
              <p>视频流已停止</p>
              <el-button type="primary" size="large" @click="startStream">
                <el-icon><VideoPlay /></el-icon>
                启动视频流
              </el-button>
            </div>
            <div v-if="stream?.status === 'running'" class="live-indicator">
              <span class="live-dot"></span>
              LIVE
            </div>
          </div>
        </el-card>

        <!-- 实时统计 -->
        <el-card class="realtime-stats" shadow="never">
          <template #header>
            <span>实时统计</span>
          </template>
          <el-row :gutter="20">
            <el-col :span="8">
              <div class="stat-item">
                <div class="stat-value">{{ todayStats.count }}</div>
                <div class="stat-label">今日违规</div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="stat-item">
                <div class="stat-value">{{ todayStats.helmet }}</div>
                <div class="stat-label">未戴安全帽</div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="stat-item">
                <div class="stat-value">{{ todayStats.vest }}</div>
                <div class="stat-label">未穿反光衣</div>
              </div>
            </el-col>
          </el-row>
        </el-card>
      </el-col>

      <!-- 右侧：信息和记录 -->
      <el-col :span="8">
        <!-- 基本信息 -->
        <el-card class="info-card" shadow="never">
          <template #header>
            <span>基本信息</span>
          </template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="ID">{{ stream?.id }}</el-descriptions-item>
            <el-descriptions-item label="名称">{{ stream?.name }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="stream?.status === 'running' ? 'success' : 'info'">
                {{ stream?.status === 'running' ? '运行中' : '已停止' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="检测器">
              {{ formatDetectorType(stream?.detector_type) }}
            </el-descriptions-item>
            <el-descriptions-item label="工地">{{ stream?.site_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="URL" :content-style="{ wordBreak: 'break-all' }">
              {{ stream?.url }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <!-- 最近违规 -->
        <el-card class="violations-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span>最近违规</span>
              <el-button text @click="$router.push('/violations')">
                查看全部
              </el-button>
            </div>
          </template>
          <div v-if="recentViolations.length === 0" class="empty-state">
            <el-empty description="暂无违规记录" />
          </div>
          <div v-else class="violation-list">
            <div
              v-for="violation in recentViolations"
              :key="violation.id"
              class="violation-item"
            >
              <div class="violation-time">{{ formatTime(violation.timestamp) }}</div>
              <div class="violation-types">
                <el-tag
                  v-for="type in violation.violation_types"
                  :key="type"
                  :type="getViolationTagType(type)"
                  size="small"
                >
                  {{ formatViolationType(type) }}
                </el-tag>
              </div>
              <el-image
                v-if="violation.snapshot_path"
                :src="`/storage/${violation.camera_id}/${violation.snapshot_path}`"
                :preview-src-list="[`/storage/${violation.camera_id}/${violation.snapshot_path}`]"
                class="violation-image"
                fit="cover"
              />
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 编辑对话框 -->
    <el-dialog v-model="showEditDialog" title="编辑视频流" width="500px">
      <el-form :model="editForm" label-width="100px">
        <el-form-item label="名称">
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="URL">
          <el-input v-model="editForm.url" />
        </el-form-item>
        <el-form-item label="检测器">
          <el-select v-model="editForm.detector_type" style="width: 100%">
            <el-option label="PPE检测" value="ppe_detector" />
            <el-option label="车辆检测" value="vehicle_detector" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useStreamsStore } from '@/stores/streams'
import { useViolationsStore } from '@/stores/violations'
import dayjs from 'dayjs'

const route = useRoute()
const router = useRouter()
const streamsStore = useStreamsStore()
const violationsStore = useViolationsStore()

const streamId = computed(() => route.params.id as string)
const stream = computed(() => streamsStore.getStreamById(streamId.value))

const showEditDialog = ref(false)
const editForm = ref({
  name: '',
  url: '',
  detector_type: 'ppe_detector'
})

const todayStats = computed(() => {
  const today = violationsStore.todayViolations.filter(
    v => v.camera_id === streamId.value
  )
  return {
    count: today.length,
    helmet: today.filter(v => v.violation_types.includes('no_helmet')).length,
    vest: today.filter(v => v.violation_types.includes('no_vest')).length
  }
})

const recentViolations = computed(() => {
  return violationsStore.violations
    .filter(v => v.camera_id === streamId.value)
    .slice(0, 5)
})

const toggleStream = async () => {
  if (stream.value?.status === 'running') {
    await streamsStore.stopStream(streamId.value)
  } else {
    await streamsStore.startStream(streamId.value)
  }
}

const startStream = async () => {
  await streamsStore.startStream(streamId.value)
}

const saveEdit = () => {
  // 保存编辑逻辑
  showEditDialog.value = false
}

const formatTime = (timestamp: string) => {
  return dayjs(timestamp).format('MM-DD HH:mm')
}

const formatViolationType = (type: string) => {
  const map: Record<string, string> = {
    'no_helmet': '未戴安全帽',
    'no_vest': '未穿反光衣',
    'no_mask': '未戴口罩'
  }
  return map[type] || type
}

const getViolationTagType = (type: string) => {
  const map: Record<string, any> = {
    'no_helmet': 'danger',
    'no_vest': 'warning',
    'no_mask': 'info'
  }
  return map[type] || 'info'
}

const formatDetectorType = (type?: string) => {
  const map: Record<string, string> = {
    'ppe_detector': 'PPE检测',
    'vehicle_detector': '车辆检测'
  }
  return map[type || ''] || type || '-'
}

onMounted(() => {
  streamsStore.fetchStreams()
  violationsStore.fetchViolations({ camera_id: streamId.value, limit: 20 })
})

watch(stream, (newStream) => {
  if (newStream) {
    editForm.value = {
      name: newStream.name,
      url: newStream.url,
      detector_type: newStream.detector_type
    }
  }
}, { immediate: true })
</script>

<style scoped lang="scss">
.stream-detail-view {
  .page-header {
    display: flex;
    align-items: center;
    gap: 20px;
    margin-bottom: 20px;

    h2 {
      flex: 1;
      margin: 0;
      font-size: 20px;
      font-weight: 600;
    }

    .header-actions {
      display: flex;
      gap: 12px;
    }
  }

  .video-card {
    margin-bottom: 20px;

    .video-wrapper {
      position: relative;
      width: 100%;
      height: 480px;
      background: #000;
      border-radius: 8px;
      overflow: hidden;

      .main-video {
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
          margin: 16px 0;
          font-size: 16px;
        }
      }

      .live-indicator {
        position: absolute;
        top: 16px;
        left: 16px;
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 6px 12px;
        background: rgba(245, 34, 45, 0.9);
        color: #fff;
        font-size: 14px;
        font-weight: 600;
        border-radius: 4px;

        .live-dot {
          width: 10px;
          height: 10px;
          background: #fff;
          border-radius: 50%;
          animation: pulse 1.5s infinite;
        }
      }
    }
  }

  .realtime-stats {
    margin-bottom: 20px;

    .stat-item {
      text-align: center;
      padding: 20px;

      .stat-value {
        font-size: 32px;
        font-weight: 600;
        color: #303133;
        line-height: 1;
      }

      .stat-label {
        font-size: 14px;
        color: #909399;
        margin-top: 8px;
      }
    }
  }

  .info-card,
  .violations-card {
    margin-bottom: 20px;

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
  }

  .violation-list {
    .violation-item {
      padding: 12px 0;
      border-bottom: 1px solid #ebeef5;

      &:last-child {
        border-bottom: none;
      }

      .violation-time {
        font-size: 13px;
        color: #909399;
        margin-bottom: 8px;
      }

      .violation-types {
        display: flex;
        gap: 8px;
        margin-bottom: 8px;
      }

      .violation-image {
        width: 100%;
        height: 120px;
        border-radius: 4px;
        cursor: pointer;
      }
    }
  }

  .empty-state {
    padding: 40px 0;
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
