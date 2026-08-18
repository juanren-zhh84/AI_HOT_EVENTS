<!-- frontend/src/components/FieldInput.vue -->
<!-- 配置字段输入控件：根据字段类型渲染文本/密码/数字输入框或开关。 -->
<script setup>
import { computed } from 'vue' // 计算属性。

const props = defineProps({ // 组件属性。
  field: { type: Object, required: true }, // 字段元信息：{ key, value, category, value_type, is_secret, description }。
  modelValue: { type: [String, Boolean], default: '' }, // 当前值。
})
const emit = defineEmits(['update:modelValue']) // v-model 更新事件。

const isBool = computed(() => props.field.value_type === 'bool') // 是否是布尔开关。
const isSecret = computed(() => props.field.is_secret) // 是否敏感字段。
const isNumber = computed(() => ['int', 'float'].includes(props.field.value_type)) // 是否是数字。
const boolOn = computed(() => props.modelValue === true || props.modelValue === 'true') // 布尔值判断。
</script>

<template>
  <div class="field">
    <div class="field-head">
      <span class="field-key mono">{{ field.key }}</span> <!-- 配置名，等宽字体 -->
      <span v-if="isSecret" class="mask-badge" :class="{ set: field.value }">
        {{ field.value ? `已设置 · ${field.value}` : '未设置' }}
      </span> <!-- 敏感字段只显示脱敏掩码 -->
    </div>
    <div class="field-body">
      <label v-if="isBool" class="switch"> <!-- 布尔字段渲染开关 -->
        <input type="checkbox" :checked="boolOn" @change="emit('update:modelValue', $event.target.checked ? 'true' : 'false')" />
        <span class="switch-track"></span>
        <span class="switch-label">{{ boolOn ? '启用' : '停用' }}</span>
      </label>
      <input
        v-else
        class="input mono"
        :type="isNumber ? 'number' : isSecret ? 'password' : 'text'"
        :value="modelValue"
        :placeholder="isSecret ? '留空表示不修改' : ''"
        @input="emit('update:modelValue', $event.target.value)"
      />
    </div>
    <div class="field-desc">{{ field.description }}</div> <!-- 中文说明 -->
  </div>
</template>
