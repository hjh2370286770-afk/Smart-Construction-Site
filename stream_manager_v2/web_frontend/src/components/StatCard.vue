<template>
  <div class="stat-card">
    <div class="stat-icon" :style="{ backgroundColor: props.iconBgColor }">
      <el-icon :size="28" :color="props.iconColor">
        <component :is="props.icon" />
      </el-icon>
    </div>
    <div class="stat-content">
      <div class="stat-value">{{ props.value }}</div>
      <div class="stat-label">{{ props.label }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  icon: string
  value: number | string
  label: string
  iconColor?: string
  iconBgColor?: string
}

const props = withDefaults(defineProps<Props>(), {
  iconColor: '#fff',
  iconBgColor: '#409EFF',
})
</script>

<style scoped>
.stat-card {
  display: flex;
  align-items: center;
  padding: 20px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  transition: transform 0.3s;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px 0 rgba(0, 0, 0, 0.15);
}

.stat-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 60px;
  height: 60px;
  border-radius: 8px;
  margin-right: 16px;
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: #303133;
  line-height: 1.2;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 4px;
}
</style>
