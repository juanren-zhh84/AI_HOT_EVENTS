// frontend/src/main.js
// Vue 应用入口。
import { createApp } from 'vue' // Vue 创建应用函数。
import App from './App.vue' // 根组件。
import './style.css' // 全局样式。

createApp(App).mount('#app') // 挂载到 index.html 的 #app。
