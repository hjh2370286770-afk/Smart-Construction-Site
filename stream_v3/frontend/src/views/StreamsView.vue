<template>
  <div class="streams-view">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <h3>视频流管理</h3>
          <el-button type="primary" @click="showAddDialog = true">
            <el-icon><Plus /></el-icon>
            添加视频流
          </el-button>
        </div>
      </template>

      <el-table :data="streamsStore.streams" style="width: 100%" v-loading="streamsStore.loading">
        <el-table-column type="index" width="50" />
        <el-table-column prop="id" label="ID" width="120" />
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="url" label="URL" show-overflow-tooltip />
        <el-table-column prop="detector_type" label="检测器" width="150">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ formatDetectorType(row.detector_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'running' ? 'success' : 'info'">
              {{ row.status === 'running' ? '运行中' : '已停止' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button 
              :type="row.status === 'running' ? 'danger' : 'success'" 
              size="small"
              @click="toggleStream(row)"
            >
              {{ row.status === 'running' ? '停止' : '启动' }}
            </el-button>
            <el-button type="primary" size="small" @click="viewDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 添加对话框 -->
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
            <el-option 
              v-for="detector in detectors" 
              :key="detector.id" 
              :label="formatDetectorType(detector.id)" 
              :value="detector.id" 
            />
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
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useStreamsStore, type Stream } from '@/stores/streams'
import { streamsApi, detectorsApi } from '@/api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const streamsStore = useStreamsStore()

const showAddDialog = ref(false)
const detectors = ref<{ id: string; name: string }[]>([])
const newStream = ref({
  name: '',
  url: '',
  detector_type: 'ppe_detector'
})

const toggleStream = async (row: Stream) => {
  if (row.status === 'running') {
    await streamsStore.stopStream(row.id)
  } else {
    await streamsStore.startStream(row.id)
  }
}

const viewDetail = (row: Stream) => {
  router.push(`/streams/${row.id}`)
}

const addStream = async () => {
  if (!newStream.value.name || !newStream.value.url) {
    ElMessage.warning('请填写名称和URL')
    return
  }
  
  try {
    await streamsApi.create({
      name: newStream.value.name,
      url: newStream.value.url,
      detector_type: newStream.value.detector_type
    })
    
    ElMessage.success('添加成功')
    showAddDialog.value = false
    
    // 重置表单
    newStream.value = {
      name: '',
      url: '',
      detector_type: 'ppe_detector'
    }
    
    // 刷新列表
    await streamsStore.fetchStreams()
  } catch (error) {
    console.error('添加视频流失败:', error)
    ElMessage.error('添加失败')
  }
}

const formatDetectorType = (type: string) => {
  const map: Record<string, string> = {
    'ppe_detector': 'PPE检测',
    'vehicle_detector': '车辆检测',
    'fire_detector': '火灾检测',
    'person_counter': '人员计数',
    'vehicle_wash_detector': '车辆清洗检测'
  }
  return map[type] || type
}

const fetchDetectors = async () => {
  try {
    detectors.value = await detectorsApi.getAll()
    if (detectors.value.length > 0 && !newStream.value.detector_type) {
      newStream.value.detector_type = detectors.value[0].id
    }
  } catch (error) {
    console.error('获取检测器列表失败:', error)
    // 使用默认检测器
    detectors.value = [
      { id: 'ppe_detector', name: 'PPE Detector' },
      { id: 'vehicle_detector', name: 'Vehicle Detector' },
      { id: 'fire_detector', name: 'Fire Detector' },
      { id: 'person_counter', name: 'Person Counter' },
      { id: 'vehicle_wash_detector', name: 'Vehicle Wash Detector' }
    ]
  }
}

onMounted(() => {
  streamsStore.fetchStreams()
  fetchDetectors()
})
</script>

<style scoped lang="scss">
.streams-view {
  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;

    h3 {
      margin: 0;
      font-size: 18px;
      font-weight: 600;
    }
  }
}
</style>
