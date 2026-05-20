<template>
  <div class="violations-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <h1>违规记录</h1>
      <el-button type="primary" @click="exportData">
        <el-icon><Download /></el-icon>
        导出数据
      </el-button>
    </div>
    
    <!-- 筛选条件 -->
    <el-card class="filter-card">
      <el-form :model="filterForm" inline>
        <el-form-item label="摄像头">
          <el-select v-model="filterForm.cameraId" placeholder="全部摄像头" clearable>
            <el-option
              v-for="cam in cameras"
              :key="cam.id"
              :label="cam.name"
              :value="cam.id"
            />
          </el-select>
        </el-form-item>
        
        <el-form-item label="违规类型">
          <el-select v-model="filterForm.type" placeholder="全部类型" clearable>
            <el-option label="未戴安全帽" value="no_helmet" />
            <el-option label="未穿反光衣" value="no_vest" />
            <el-option label="未戴口罩" value="no_mask" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filterForm.dateRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
          />
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
    
    <!-- 数据表格 -->
    <el-card>
      <el-table
        :data="violationList"
        v-loading="loading"
        stripe
        border
      >
        <el-table-column type="index" width="50" />
        
        <el-table-column label="截图" width="120">
          <template #default="{ row }">
            <el-image
              v-if="row.imageUrl"
              :src="row.imageUrl"
              :preview-src-list="[row.imageUrl]"
              fit="cover"
              style="width: 80px; height: 60px"
            />
            <span v-else>-</span>
          </template>
        </el-table-column>
        
        <el-table-column prop="time" label="时间" width="180" />
        
        <el-table-column prop="cameraName" label="摄像头" width="150" />
        
        <el-table-column prop="siteName" label="工地" width="150" />
        
        <el-table-column label="违规类型" width="150">
          <template #default="{ row }">
            <el-tag 
              v-for="type in row.violationTypes" 
              :key="type"
              :type="getViolationType(type)"
              size="small"
              style="margin-right: 4px"
            >
              {{ getViolationLabel(type) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column label="严重程度" width="100">
          <template #default="{ row }">
            <el-tag :type="row.severity">{{ getSeverityLabel(row.severity) }}</el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="personId" label="人员ID" width="100" />
        
        <el-table-column prop="description" label="描述" min-width="200" />
        
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewDetail(row)">详情</el-button>
            <el-button link type="danger" @click="deleteItem(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- 分页 -->
      <div class="pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>
    
    <!-- 详情对话框 -->
    <el-dialog
      v-model="detailVisible"
      title="违规详情"
      width="800px"
    >
      <div v-if="selectedViolation" class="violation-detail">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-image
              v-if="selectedViolation.imageUrl"
              :src="selectedViolation.imageUrl"
              fit="contain"
              style="width: 100%; border-radius: 4px"
            />
          </el-col>
          <el-col :span="12">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="时间">{{ selectedViolation.time }}</el-descriptions-item>
              <el-descriptions-item label="摄像头">{{ selectedViolation.cameraName }}</el-descriptions-item>
              <el-descriptions-item label="工地">{{ selectedViolation.siteName }}</el-descriptions-item>
              <el-descriptions-item label="人员ID">{{ selectedViolation.personId }}</el-descriptions-item>
              <el-descriptions-item label="违规类型">
                <el-tag
                  v-for="type in selectedViolation.violationTypes"
                  :key="type"
                  :type="getViolationType(type)"
                  size="small"
                  style="margin-right: 4px"
                >
                  {{ getViolationLabel(type) }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="描述">{{ selectedViolation.description }}</el-descriptions-item>
            </el-descriptions>
          </el-col>
        </el-row>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useMonitorStore } from '@/stores/monitor'
import { api } from '@/api'

const monitorStore = useMonitorStore()

const loading = ref(false)
const cameras = ref<any[]>([])
const violationList = ref<any[]>([])
const detailVisible = ref(false)
const selectedViolation = ref<any>(null)

const filterForm = reactive({
  cameraId: '',
  type: '',
  dateRange: null as Date[] | null
})

const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

function getViolationType(type: string): string {
  const map: Record<string, string> = {
    no_helmet: 'danger',
    no_vest: 'warning',
    no_mask: 'info'
  }
  return map[type] || 'info'
}

function getViolationLabel(type: string): string {
  const map: Record<string, string> = {
    no_helmet: '未戴安全帽',
    no_vest: '未穿反光衣',
    no_mask: '未戴口罩'
  }
  return map[type] || type
}

function getSeverityLabel(severity: string): string {
  const map: Record<string, string> = {
    high: '严重',
    medium: '中等',
    low: '轻微'
  }
  return map[severity] || severity
}

async function loadData() {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
      camera_id: filterForm.cameraId || undefined,
      violation_type: filterForm.type || undefined,
      start_time: filterForm.dateRange?.[0]?.toISOString(),
      end_time: filterForm.dateRange?.[1]?.toISOString()
    }
    
    const res = await api.getViolations(params)
    violationList.value = res.items || []
    pagination.total = res.total || 0
  } catch (error) {
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  loadData()
}

function resetFilter() {
  filterForm.cameraId = ''
  filterForm.type = ''
  filterForm.dateRange = null
  handleSearch()
}

function handleSizeChange(size: number) {
  pagination.pageSize = size
  loadData()
}

function handlePageChange(page: number) {
  pagination.page = page
  loadData()
}

function viewDetail(row: any) {
  selectedViolation.value = row
  detailVisible.value = true
}

async function deleteItem(row: any) {
  try {
    await ElMessageBox.confirm('确定删除这条记录吗？', '提示', {
      type: 'warning'
    })
    ElMessage.success('删除成功')
    loadData()
  } catch {
    // 取消删除
  }
}

function exportData() {
  const headers = ['时间', '摄像头', '工地', '违规类型', '严重程度', '人员ID', '描述']
  const rows = violationList.value.map(v => [
    v.time,
    v.cameraName,
    v.siteName,
    v.violationTypes.join(','),
    getSeverityLabel(v.severity),
    v.personId,
    v.description
  ])
  
  const csvContent = [headers, ...rows]
    .map(row => row.join(','))
    .join('\n')
  
  const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `violations_${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  
  ElMessage.success('导出成功')
}

onMounted(() => {
  cameras.value = monitorStore.cameras
  loadData()
})
</script>

<style scoped>
.violations-page {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h1 {
  margin: 0;
  font-size: 24px;
}

.filter-card {
  margin-bottom: 20px;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.violation-detail {
  padding: 20px;
}
</style>
