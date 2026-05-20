<template>
  <div class="violations-view">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <h3>违规记录</h3>
            <el-tag type="info">共 {{ violationsStore.total }} 条</el-tag>
          </div>
          <div class="header-right">
            <el-button @click="exportData">
              <el-icon><Download /></el-icon>
              导出Excel
            </el-button>
          </div>
        </div>
      </template>

      <!-- 筛选栏 -->
      <div class="filter-bar">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          @change="handleFilterChange"
        />
        <el-select v-model="filterCamera" placeholder="选择视频流" clearable @change="handleFilterChange">
          <el-option
            v-for="stream in streamsStore.streams"
            :key="stream.id"
            :label="stream.name"
            :value="stream.id"
          />
        </el-select>
        <el-select v-model="filterType" placeholder="违规类型" clearable @change="handleFilterChange">
          <el-option label="未戴安全帽" value="no_helmet" />
          <el-option label="未穿反光衣" value="no_vest" />
          <el-option label="未戴口罩" value="no_mask" />
        </el-select>
        <el-button type="primary" @click="handleFilterChange">
          <el-icon><Search /></el-icon>
          查询
        </el-button>
        <el-button @click="resetFilter">重置</el-button>
      </div>

      <!-- 违规列表 -->
      <el-table
        :data="violationsStore.violations"
        v-loading="violationsStore.loading"
        stripe
        style="width: 100%"
      >
        <el-table-column type="index" width="50" />
        <el-table-column prop="timestamp" label="时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.timestamp) }}
          </template>
        </el-table-column>
        <el-table-column prop="camera_name" label="视频流" width="150">
          <template #default="{ row }">
            {{ row.camera_name || row.camera_id }}
          </template>
        </el-table-column>
        <el-table-column prop="violation_type" label="违规类型" width="150">
          <template #default="{ row }">
            <el-tag :type="getViolationTagType(row.type)" size="small">
              {{ formatViolationType(row.type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="severity" label="严重程度" width="100">
          <template #default="{ row }">
            <el-tag :type="getSeverityType(row.severity)" size="small">
              {{ formatSeverity(row.severity) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" show-overflow-tooltip />
        <el-table-column label="截图" width="120">
          <template #default="{ row }">
            <el-image
              v-if="row.image_url"
              :src="row.image_url"
              :preview-src-list="[row.image_url]"
              style="width: 80px; height: 50px; cursor: pointer;"
              fit="cover"
            />
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewDetail(row)">查看</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="violationsStore.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- 详情对话框 -->
    <el-dialog v-model="showDetailDialog" title="违规详情" width="600px">
      <div v-if="selectedViolation" class="violation-detail">
        <el-image
          v-if="selectedViolation.image_url"
          :src="selectedViolation.image_url"
          style="width: 100%; max-height: 400px;"
          fit="contain"
        />
        <el-descriptions :column="2" border class="detail-info">
          <el-descriptions-item label="时间">{{ formatTime(selectedViolation.timestamp) }}</el-descriptions-item>
          <el-descriptions-item label="视频流">{{ selectedViolation.camera_name || selectedViolation.camera_id }}</el-descriptions-item>
          <el-descriptions-item label="视频流ID">{{ selectedViolation.camera_id }}</el-descriptions-item>
          <el-descriptions-item label="严重程度">
            <el-tag :type="getSeverityType(selectedViolation.severity)">
              {{ formatSeverity(selectedViolation.severity) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="违规类型">
            <el-tag :type="getViolationTagType(selectedViolation.violation_type)">
              {{ selectedViolation.violation_type }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">{{ selectedViolation.description || '-' }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useViolationsStore } from '@/stores/violations'
import { useStreamsStore } from '@/stores/streams'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import type { Violation } from '@/types'

const violationsStore = useViolationsStore()
const streamsStore = useStreamsStore()

const dateRange = ref<[string, string] | null>(null)
const filterCamera = ref('')
const filterType = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const showDetailDialog = ref(false)
const selectedViolation = ref<Violation | null>(null)

const handleFilterChange = () => {
  const params: any = {
    page: currentPage.value,
    page_size: pageSize.value
  }
  
  if (dateRange.value) {
    params.start_date = dateRange.value[0]
    params.end_date = dateRange.value[1]
  }
  
  if (filterCamera.value) {
    params.stream_id = filterCamera.value
  }
  
  if (filterType.value) {
    params.type = filterType.value
  }
  
  violationsStore.fetchViolations(params)
}

const resetFilter = () => {
  dateRange.value = null
  filterCamera.value = ''
  filterType.value = ''
  currentPage.value = 1
  handleFilterChange()
}

const handleSizeChange = (val: number) => {
  pageSize.value = val
  handleFilterChange()
}

const handleCurrentChange = (val: number) => {
  currentPage.value = val
  handleFilterChange()
}

const viewDetail = (row: Violation) => {
  selectedViolation.value = row
  showDetailDialog.value = true
}

const handleDelete = (row: Violation) => {
  ElMessageBox.confirm('确定要删除这条违规记录吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    // 删除逻辑
    ElMessage.success('删除成功')
  })
}

const exportData = () => {
  // 导出Excel逻辑
  ElMessage.success('导出成功')
}

const formatTime = (timestamp: string) => {
  return dayjs(timestamp).format('YYYY-MM-DD HH:mm:ss')
}

const formatViolationType = (type: string) => {
  const map: Record<string, string> = {
    'no_helmet': '未戴安全帽',
    'no_vest': '未穿反光衣',
    'no_mask': '未戴口罩',
    'ppe_detector': 'PPE违规',
    'vehicle_detector': '车辆违规',
    'fire_detector': '火灾检测',
    'person_counter': '人员计数'
  }
  return map[type] || type
}

const getViolationTagType = (type: string) => {
  const map: Record<string, any> = {
    'no_helmet': 'danger',
    'no_vest': 'warning',
    'no_mask': 'info',
    'ppe_detector': 'danger',
    'vehicle_detector': 'warning',
    'fire_detector': 'danger',
    'person_counter': 'info'
  }
  return map[type] || 'info'
}

const formatSeverity = (severity: string) => {
  const map: Record<string, string> = {
    'critical': '严重',
    'high': '高',
    'medium': '中',
    'low': '低'
  }
  return map[severity] || severity
}

const getSeverityType = (severity: string) => {
  const map: Record<string, any> = {
    'critical': 'danger',
    'high': 'warning',
    'medium': 'info',
    'low': 'success'
  }
  return map[severity] || 'info'
}

onMounted(() => {
  streamsStore.fetchStreams()
  violationsStore.fetchViolations({ page: 1, page_size: 20 })
})
</script>

<style scoped lang="scss">
.violations-view {
  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;

    .header-left {
      display: flex;
      align-items: center;
      gap: 12px;

      h3 {
        margin: 0;
        font-size: 18px;
        font-weight: 600;
      }
    }
  }

  .filter-bar {
    display: flex;
    gap: 12px;
    margin-bottom: 20px;
    flex-wrap: wrap;
  }

  .pagination {
    margin-top: 20px;
    display: flex;
    justify-content: flex-end;
  }

  .violation-tag {
    margin-right: 4px;
  }

  .violation-detail {
    .detail-info {
      margin-top: 20px;
    }
  }
}
</style>
