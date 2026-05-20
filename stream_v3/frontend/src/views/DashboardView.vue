<template>
  <div class="dashboard-view">
    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card class="stats-card" shadow="hover">
          <div class="stats-content">
            <div class="stats-icon running">
              <el-icon><VideoPlay /></el-icon>
            </div>
            <div class="stats-info">
              <div class="stats-value">{{ runningCount }}</div>
              <div class="stats-label">运行中视频流</div>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="stats-card" shadow="hover">
          <div class="stats-content">
            <div class="stats-icon warning">
              <el-icon><Warning /></el-icon>
            </div>
            <div class="stats-info">
              <div class="stats-value">{{ todayViolationCount }}</div>
              <div class="stats-label">今日违规</div>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="stats-card" shadow="hover">
          <div class="stats-content">
            <div class="stats-icon total">
              <el-icon><VideoCamera /></el-icon>
            </div>
            <div class="stats-info">
              <div class="stats-value">{{ totalStreams }}</div>
              <div class="stats-label">总视频流</div>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="stats-card" shadow="hover">
          <div class="stats-content">
            <div class="stats-icon online">
              <el-icon><Connection /></el-icon>
            </div>
            <div class="stats-info">
              <div class="stats-value">{{ wsStore.isConnected ? '在线' : '离线' }}</div>
              <div class="stats-label">系统状态</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 视频流网格 -->
    <el-card class="streams-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span class="title">实时视频流</span>
          <div class="actions">
            <el-button type="primary" @click="refreshStreams">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
            <el-button @click="showAddDialog = true">
              <el-icon><Plus /></el-icon>
              添加视频流
            </el-button>
          </div>
        </div>
      </template>
      
      <el-row :gutter="20">
        <el-col 
          v-for="stream in streamsStore.streams" 
          :key="stream.id" 
          :xs="24" :sm="12" :md="8" :lg="8" :xl="6"
        >
          <StreamCard 
            :stream="stream" 
            @start="handleStart"
            @stop="handleStop"
            @detail="handleDetail"
          />
        </el-col>
      </el-row>
    </el-card>

    <!-- 最近违规 -->
    <el-card class="violations-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span class="title">最近违规</span>
          <el-button text @click="$router.push('/violations')">
            查看全部
            <el-icon class="el-icon--right"><ArrowRight /></el-icon>
          </el-button>
        </div>
      </template>
      
      <el-table :data="recentViolations" style="width: 100%" v-loading="violationsStore.loading">
        <el-table-column prop="timestamp" label="时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.timestamp) }}
          </template>
        </el-table-column>
        <el-table-column prop="camera_name" label="视频流" width="150" />
        <el-table-column prop="person_id" label="人员ID" width="100" />
        <el-table-column prop="violation_types" label="违规类型">
          <template #default="{ row }">
            <el-tag 
              v-for="type in row.violation_types" 
              :key="type"
              :type="getViolationTagType(type)"
              size="small"
              class="violation-tag"
            >
              {{ formatViolationType(type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="截图" width="100">
          <template #default="{ row }">
            <el-image 
              v-if="row.snapshot_path"
              :src="`/storage/${row.camera_id}/${row.snapshot_path}`"
              :preview-src-list="[`/storage/${row.camera_id}/${row.snapshot_path}`]"
              style="width: 60px; height: 40px; cursor: pointer;"
              fit="cover"
            />
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 添加视频流对话框 -->
    <el-dialog v-model="showAddDialog" title="添加视频流" width="500px">
      <el-form :model="newStream" label-width="100px">
        <el-form-item label="名称">
          <el-input v-model="newStream.name" placeholder="请输入视频流名称" />
        </el-form-item>
        <el-form-item label="URL">
          <el-input v-model="newStream.url" placeholder="rtmp:// 或 rtsp://" />
        </el-form-item>
        <el-form-item label="检测器">
          <el-select v-model="newStream.detector_type" style="width: 100%">
            <el-option label="PPE检测" value="ppe_detector" />
            <el-option label="车辆检测" value="vehicle_detector" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="addStream">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useStreamsStore } from '@/stores/streams'
import { useViolationsStore } from '@/stores/violations'
import { useWebSocketStore } from '@/stores/websocket'
import StreamCard from '@/components/StreamCard.vue'
import dayjs from 'dayjs'

const router = useRouter()
const streamsStore = useStreamsStore()
const violationsStore = useViolationsStore()
const wsStore = useWebSocketStore()

const showAddDialog = ref(false)
const newStream = ref({
  name: '',
  url: '',
  detector_type: 'ppe_detector'
})

const runningCount = computed(() => streamsStore.runningStreams.length)
const totalStreams = computed(() => streamsStore.streams.length)
const todayViolationCount = computed(() => violationsStore.todayViolations.length)
const recentViolations = computed(() => violationsStore.violations.slice(0, 5))

const refreshStreams = () => {
  streamsStore.fetchStreams()
}

const handleStart = async (id: string) => {
  try {
    await streamsStore.startStream(id)
    ElMessage.success('视频流已启动')
  } catch (error) {
    ElMessage.error('启动失败')
  }
}

const handleStop = async (id: string) => {
  try {
    await streamsStore.stopStream(id)
    ElMessage.success('视频流已停止')
  } catch (error) {
    ElMessage.error('停止失败')
  }
}

const handleDetail = (id: string) => {
  router.push(`/streams/${id}`)
}

const addStream = () => {
  // 添加视频流逻辑
  showAddDialog.value = false
}

const formatTime = (timestamp: string) => {
  return dayjs(timestamp).format('MM-DD HH:mm:ss')
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

onMounted(() => {
  streamsStore.fetchStreams()
  violationsStore.fetchViolations({ limit: 10 })
})
</script>

<style scoped lang="scss">
.dashboard-view {
  .stats-row {
    margin-bottom: 20px;
    
    .stats-card {
      .stats-content {
        display: flex;
        align-items: center;
        gap: 16px;
        
        .stats-icon {
          width: 60px;
          height: 60px;
          border-radius: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 28px;
          
          &.running {
            background: #e6f7ff;
            color: #1890ff;
          }
          
          &.warning {
            background: #fff2e8;
            color: #fa8c16;
          }
          
          &.total {
            background: #f6ffed;
            color: #52c41a;
          }
          
          &.online {
            background: #f9f0ff;
            color: #722ed1;
          }
        }
        
        .stats-info {
          .stats-value {
            font-size: 28px;
            font-weight: 600;
            color: #303133;
            line-height: 1;
          }
          
          .stats-label {
            font-size: 14px;
            color: #909399;
            margin-top: 8px;
          }
        }
      }
    }
  }
  
  .streams-card,
  .violations-card {
    margin-bottom: 20px;
    
    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      
      .title {
        font-size: 16px;
        font-weight: 600;
      }
      
      .actions {
        display: flex;
        gap: 12px;
      }
    }
  }
  
  .violation-tag {
    margin-right: 8px;
  }
}
</style>
