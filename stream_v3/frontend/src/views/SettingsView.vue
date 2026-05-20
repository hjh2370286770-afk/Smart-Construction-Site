<template>
  <div class="settings-view">
    <el-card shadow="never">
      <template #header>
        <h3>系统设置</h3>
      </template>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="基本设置" name="basic">
          <el-form :model="basicSettings" label-width="150px">
            <el-form-item label="系统名称">
              <el-input v-model="basicSettings.systemName" />
            </el-form-item>
            <el-form-item label="数据保留天数">
              <el-input-number v-model="basicSettings.dataRetentionDays" :min="7" :max="365" />
            </el-form-item>
            <el-form-item label="自动清理">
              <el-switch v-model="basicSettings.autoCleanup" />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="检测设置" name="detection">
          <el-form :model="detectionSettings" label-width="150px">
            <el-form-item label="检测频率">
              <el-select v-model="detectionSettings.frameSkip">
                <el-option label="每帧检测" :value="1" />
                <el-option label="每2帧检测" :value="2" />
                <el-option label="每3帧检测" :value="3" />
                <el-option label="每5帧检测" :value="5" />
              </el-select>
            </el-form-item>
            <el-form-item label="置信度阈值">
              <el-slider v-model="detectionSettings.confidence" :min="0.1" :max="1" :step="0.05" show-stops />
            </el-form-item>
            <el-form-item label="保存截图">
              <el-switch v-model="detectionSettings.saveSnapshots" />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="通知设置" name="notification">
          <el-form :model="notificationSettings" label-width="150px">
            <el-form-item label="启用通知">
              <el-switch v-model="notificationSettings.enabled" />
            </el-form-item>
            <el-form-item label="通知方式">
              <el-checkbox-group v-model="notificationSettings.methods">
                <el-checkbox label="webhook">Webhook</el-checkbox>
                <el-checkbox label="email">邮件</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <div class="form-actions">
        <el-button type="primary" @click="saveSettings">保存设置</el-button>
        <el-button @click="resetSettings">重置</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const activeTab = ref('basic')

const basicSettings = ref({
  systemName: 'Stream V3 智能监控系统',
  dataRetentionDays: 30,
  autoCleanup: true
})

const detectionSettings = ref({
  frameSkip: 3,
  confidence: 0.45,
  saveSnapshots: true
})

const notificationSettings = ref({
  enabled: true,
  methods: ['webhook']
})

const saveSettings = () => {
  ElMessage.success('设置已保存')
}

const resetSettings = () => {
  ElMessage.info('已重置为默认值')
}
</script>

<style scoped lang="scss">
.settings-view {
  .form-actions {
    margin-top: 30px;
    padding-top: 20px;
    border-top: 1px solid #ebeef5;
  }
}
</style>
