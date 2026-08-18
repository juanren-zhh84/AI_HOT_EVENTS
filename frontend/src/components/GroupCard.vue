<!-- frontend/src/components/GroupCard.vue -->
<!-- 分组卡片容器：编号、标题、描述、内容插槽、底部操作区插槽。 -->
<script setup>
defineProps({ // 组件属性。
  index: { type: String, required: true }, // 分组编号，例如 01。
  title: { type: String, required: true }, // 分组标题。
  desc: { type: String, default: '' }, // 分组描述。
})
</script>

<template>
  <section class="card">
    <header class="card-head">
      <span class="card-index mono">{{ index }}</span> <!-- 编号徽章 -->
      <div>
        <h2 class="card-title">{{ title }}</h2>
        <p v-if="desc" class="card-desc">{{ desc }}</p>
      </div>
    </header>
    <div class="card-body">
      <slot></slot> <!-- 分组字段内容 -->
    </div>
    <footer v-if="$slots.footer" class="card-foot">
      <slot name="footer"></slot> <!-- 底部操作区（保存按钮、测试区） -->
    </footer>
  </section>
</template>
