<!-- frontend/src/App.vue -->
<!-- 后台配置管理主页面(Adminator 风格)：侧边栏导航切换独立配置页面，仪表盘展示 KPI 与快捷入口。 -->
<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue' // Vue 组合式 API。
import { api, ApiError, clearToken, getToken, setToken } from './api' // API 封装。
import GroupCard from './components/GroupCard.vue' // 分组卡片组件。
import FieldInput from './components/FieldInput.vue' // 字段输入组件。

// 分组展示元信息：编号、标题、描述。
const GROUP_META = {
  github: { index: '01', title: 'GitHub 配置', desc: '采集 GitHub 仓库数据使用的 Token 与 API 参数' },
  smtp: { index: '02', title: 'SMTP 邮件配置', desc: '发送邮件日报的邮箱服务器与发件人设置' },
  llm: { index: '03', title: 'LLM 大模型配置', desc: '生成中文项目画像的大模型供应商与模型参数' },
  hot: { index: '04', title: '热点榜单', desc: '榜单规模参数、自动发现关键词与今日热点项目' },
  scheduler: { index: '05', title: '调度总开关', desc: '是否启用后台定时任务' },
}
// 分组在页面上的展示顺序。
const GROUP_ORDER = ['github', 'smtp', 'llm', 'hot', 'scheduler']
// 调度任务英文名 -> 中文名。
const SCHEDULE_NAMES = {
  repository_discovery: '仓库自动发现',
  star_snapshot: '星标快照采集',
  profile_refresh: '项目画像刷新',
  hot_project_calculate: '热点榜计算',
  daily_digest: '邮件日报发送',
}
// 监控源类型中文名。
const SOURCE_TYPE_NAMES = {
  manual: '手动',
  github_search: '搜索',
  topic: '主题',
  owner: '组织',
}
// 仪表盘快捷入口。
const QUICK_LINKS = [
  { view: 'github', icon: '🔑', name: 'GitHub 配置', desc: '采集 Token 与 API 参数' },
  { view: 'smtp', icon: '✉️', name: 'SMTP 邮件配置', desc: '邮箱服务器与发件人' },
  { view: 'llm', icon: '🤖', name: 'LLM 大模型配置', desc: '供应商、模型与 Key' },
  { view: 'hot', icon: '🔥', name: '热点榜单', desc: '榜单规模参数' },
  { view: 'scheduler', icon: '⏱️', name: '调度总开关', desc: '后台定时任务开关' },
  { view: 'schedules', icon: '🕐', name: '定时任务', desc: '5 个任务的 cron 配置' },
  { view: 'system', icon: 'ℹ️', name: '系统信息', desc: '环境与运行参数' },
]
// 系统信息只读字段(key, 中文名)。
const SYS_FIELDS = [
  { key: 'app_name', label: 'APP_NAME' },
  { key: 'app_version', label: 'APP_VERSION' },
  { key: 'app_env', label: 'APP_ENV' },
  { key: 'debug', label: 'DEBUG' },
  { key: 'timezone', label: 'TIMEZONE' },
  { key: 'log_level', label: 'LOG_LEVEL' },
  { key: 'database_url', label: 'DATABASE_URL' },
]

// ===== 页面状态 =====
const tokenInput = ref('') // 登录框输入值。
const authed = ref(false) // 是否已认证。
const loading = ref(true) // 是否加载中。
const groups = ref({}) // 分组配置数据。
const system = ref(null) // 系统只读信息。
const schedules = ref([]) // 调度任务列表。
const localValues = reactive({}) // 各分组的表单值：localValues[分组][配置key]。
const saving = ref('') // 正在保存的分组 key，用于按钮 loading。
const savingSchedule = ref('') // 正在保存的调度 id。
const testingEmail = ref(false) // 测试邮件进行中。
const testingLlm = ref(false) // 测试大模型进行中。
const emailTo = ref('') // 测试邮件收件地址。
const testEmailResult = ref(null) // 测试邮件结果。
const testLlmResult = ref(null) // 测试大模型结果。
const toast = ref(null) // 顶部提示条。
const search = ref('') // 搜索关键字。
const activeView = ref('dashboard') // 当前页面：dashboard/github/smtp/llm/hot/scheduler/schedules/system。
const theme = ref(localStorage.getItem('admin_theme') || 'light') // 主题：light / dark。
let toastTimer = null // 提示条定时器。

// ===== 热点榜单页状态 =====
const monitorSources = ref([]) // 监控源列表（自动发现关键词）。
const sourceDraft = reactive({ name: '', query: '', keywords: '' }) // 新增监控源表单。
const savingSource = ref('') // 正在保存的监控源 id。
const hotProjects = ref([]) // 热点项目列表。
const hotKeywords = ref('') // 热点项目关键词过滤（逗号分隔）。
const hotLoading = ref(false) // 热点列表加载中。
const calculating = ref(false) // 热点计算进行中。

// ===== 当前页元信息 =====
const viewMeta = computed(() => { // 当前页面头部信息。
  if (activeView.value === 'dashboard') return { index: '—', title: '仪表盘', desc: '系统运行概况与快捷入口' }
  if (activeView.value === 'schedules') return { index: '06', title: '定时任务', desc: '修改后立即重载调度器；cron 语法：分 时 日 月 周' }
  if (activeView.value === 'system') return { index: '07', title: '系统信息', desc: '只读展示，修改需编辑服务器 .env 后重启' }
  return GROUP_META[activeView.value] || { index: '—', title: activeView.value, desc: '' }
})

// ===== 计算属性：统计与派生数据 =====
const query = computed(() => search.value.trim().toLowerCase()) // 搜索关键字(小写)。

const allFields = computed(() => { // 全部配置字段。
  const list = []
  for (const cat of GROUP_ORDER) {
    for (const f of groups.value[cat] || []) list.push({ ...f, cat })
  }
  return list
})

const totalConfigs = computed(() => allFields.value.length) // 配置总数。
const secretFields = computed(() => allFields.value.filter((f) => f.is_secret)) // 敏感字段。
const secretTotal = computed(() => secretFields.value.length) // 敏感字段总数。
const secretSet = computed(() => secretFields.value.filter((f) => f.value).length) // 已设置的敏感字段数。
const enabledSchedules = computed(() => schedules.value.filter((s) => s.enabled).length) // 启用调度数。
const schedulerOn = computed(() => { // 调度器总开关是否打开。
  const f = (groups.value.scheduler || []).find((x) => x.key === 'SCHEDULER_ENABLED')
  return f ? f.value === 'true' : false
})

const greeting = computed(() => { // 按小时生成问候语。
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 18) return '下午好'
  return '晚上好'
})
const todayText = computed(() => { // 中文日期。
  const d = new Date()
  const week = ['日', '一', '二', '三', '四', '五', '六']
  return `${d.getMonth() + 1}月${d.getDate()}日 · 星期${week[d.getDay()]}`
})
const summaryText = computed(() => { // 欢迎区摘要。
  if (!authed.value) return '登录后查看系统配置概况'
  return `系统共 ${totalConfigs.value} 项可管理配置，敏感项已设置 ${secretSet.value}/${secretTotal.value}；调度任务启用 ${enabledSchedules.value}/${schedules.value.length}`
})

// ===== 搜索过滤 =====
function filteredFields(cat) { // 配置页：按关键字过滤字段。
  const fields = groups.value[cat] || [] // 该分组全部字段。
  if (!query.value) return fields // 无关键字直接全量返回。
  return fields.filter((f) => `${f.key} ${f.description}`.toLowerCase().includes(query.value)) // 按 key 和说明过滤。
}
function filteredSchedules() { // 定时任务页：按名称/cron 过滤。
  if (!query.value) return schedules.value // 无关键字直接全量返回。
  return schedules.value.filter((s) => `${SCHEDULE_NAMES[s.name] || s.name} ${s.cron_expr}`.toLowerCase().includes(query.value)) // 过滤。
}
function filteredSysFields() { // 系统信息页：按 label/值过滤。
  if (!query.value || !system.value) return SYS_FIELDS // 无关键字直接全量返回。
  return SYS_FIELDS.filter((f) => `${f.label} ${system.value[f.key] || ''}`.toLowerCase().includes(query.value)) // 过滤。
}
function filteredQuickLinks() { // 仪表盘：按名称/描述过滤快捷入口。
  if (!query.value) return QUICK_LINKS // 无关键字直接全量返回。
  return QUICK_LINKS.filter((q) => `${q.name} ${q.desc}`.toLowerCase().includes(query.value)) // 过滤。
}
const hotKeywordsList = computed(() => { // 关键词过滤列表：逗号/空格分隔，转小写去空。
  return hotKeywords.value.split(/[,，\s]+/).map((k) => k.trim().toLowerCase()).filter(Boolean) // 拆分过滤。
})
function filteredHotProjects() { // 热点项目：按关键词模糊过滤。
  if (!hotKeywordsList.value.length) return hotProjects.value // 无关键词直接全量返回。
  return hotProjects.value.filter((hp) => { // 遍历热点项目。
    const text = `${hp.full_name} ${hp.description || ''} ${hp.reason || ''}`.toLowerCase() // 拼接可匹配文本。
    return hotKeywordsList.value.some((k) => text.includes(k)) // 命中任意关键词即保留。
  }) // 过滤结束。
}

// ===== 页面切换 =====
function switchView(view) { // 切换到指定页面。
  activeView.value = view // 更新当前页面。
  search.value = '' // 清空搜索。
  sessionStorage.setItem('admin_view', view) // 记住当前页面，刷新后恢复。
}

// ===== 主题切换 =====
function applyTheme(t) { // 把主题写到 html 标签。
  document.documentElement.setAttribute('data-theme', t) // 触发 CSS 变量切换。
}
function toggleTheme() { // 切换浅色/深色。
  theme.value = theme.value === 'light' ? 'dark' : 'light' // 取反。
  localStorage.setItem('admin_theme', theme.value) // 记住选择。
  applyTheme(theme.value) // 应用。
}

// ===== 提示条 =====
function showToast(text, type = 'info') { // 显示顶部提示。
  toast.value = { text, type } // 设置提示内容。
  clearTimeout(toastTimer) // 清除旧定时器。
  toastTimer = setTimeout(() => { toast.value = null }, 3600) // 3.6 秒后自动消失。
}

// ===== 数据加载 =====
async function loadAll() { // 加载配置、系统信息、调度任务。
  loading.value = true // 显示加载中。
  try {
    const data = await api.getConfigs() // 获取分组配置。
    groups.value = data.groups // 保存分组。
    system.value = data.system // 保存系统信息。
    for (const cat of Object.keys(data.groups)) { // 初始化表单值。
      localValues[cat] = {} // 每个分组一个对象。
      for (const f of data.groups[cat]) { // 遍历字段。
        localValues[cat][f.key] = f.is_secret ? '' : f.value // 敏感字段初始为空（留空=不修改）。
      }
    }
    schedules.value = normalizeSchedules(await api.getSchedules()) // 获取调度任务并转为友好时间格式。
    authed.value = true // 认证成功。
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) { // token 失效。
      authed.value = false // 回到登录态。
      showToast(e.message, 'err') // 提示重新登录。
    } else { // 其他错误。
      showToast(e.message, 'err') // 展示错误。
    }
  } finally {
    loading.value = false // 关闭加载中。
  }
}

// ===== 登录 / 退出 =====
function login() { // 保存 token 并加载数据。
  if (!tokenInput.value.trim()) { // 空 token。
    showToast('请输入管理 token', 'err') // 提示。
    return // 不继续。
  }
  setToken(tokenInput.value.trim()) // 保存 token。
  tokenInput.value = '' // 清空输入框。
  loadAll() // 加载数据。
}

function logout() { // 退出登录。
  clearToken() // 清除 token。
  authed.value = false // 回到未认证态。
  groups.value = {} // 清空配置。
  schedules.value = [] // 清空调度。
  testEmailResult.value = null // 清空测试结果。
  testLlmResult.value = null // 清空测试结果。
  showToast('已退出登录', 'info') // 提示。
}

// ===== 保存分组配置 =====
async function saveGroup(cat) { // 保存某个分组的全部字段。
  const updates = {} // 收集待更新字段。
  for (const f of groups.value[cat] || []) { // 遍历该分组字段。
    const v = localValues[cat][f.key] // 当前表单值。
    if (f.is_secret && (v === '' || v == null)) continue // 敏感字段留空 = 不修改。
    updates[f.key] = v // 收集更新项。
  }
  if (!Object.keys(updates).length) { // 没有实际更新项。
    showToast('没有需要保存的修改', 'info') // 提示。
    return // 不请求。
  }
  saving.value = cat // 按钮进入 loading。
  try {
    const result = await api.updateConfigs(updates) // 调后端更新接口。
    showToast(`已保存 ${result.updated.length} 项并生效`, 'ok') // 成功提示。
    await loadAll() // 刷新页面数据（回显新值）。
  } catch (e) {
    if (e instanceof ApiError && e.status === 400 && e.data && e.data.detail) { // 字段校验失败。
      const errs = e.data.detail.errors || {} // 提取失败字段。
      const keys = Object.keys(errs) // 失败字段名。
      showToast(keys.length ? `保存失败：${keys.map((k) => `${k}: ${errs[k]}`).join('；')}` : e.message, 'err') // 展示每个失败原因。
    } else { // 其他错误。
      showToast(e.message, 'err') // 展示错误。
    }
  } finally {
    saving.value = '' // 按钮恢复。
  }
}

// ===== 保存调度任务 =====
async function saveSchedule(s) { // 保存单个调度任务。
  savingSchedule.value = s.id // 按钮 loading。
  try {
    let cronExpr // 最终要保存的 cron。
    if (s.humanMode === 'custom') { // 自定义模式。
      cronExpr = String(s.cron_expr || '').trim() // 直接取 cron 输入框的值。
    } else { // 友好模式。
      cronExpr = humanToCron(s.humanMode, s.humanTime, s.humanIntervalValue, s.humanIntervalUnit) // 转成 cron。
    }
    await api.updateSchedule(s.id, { cron_expr: cronExpr, enabled: s.enabled }) // 更新调度。
    showToast(`「${SCHEDULE_NAMES[s.name] || s.name}」已保存并重载`, 'ok') // 成功提示。
    schedules.value = normalizeSchedules(await api.getSchedules()) // 刷新调度列表（更新 next_run_at 和友好时间）。
  } catch (e) {
    showToast(e.message, 'err') // 展示错误（包含时间格式校验提示）。
  } finally {
    savingSchedule.value = '' // 按钮恢复。
  }
}

// ===== 测试邮件 / 测试大模型 =====
async function testEmail() { // 发送测试邮件。
  if (!emailTo.value.includes('@')) { // 邮箱格式简单校验。
    showToast('请输入有效的收件邮箱', 'err') // 提示。
    return // 不请求。
  }
  testingEmail.value = true // 按钮 loading。
  testEmailResult.value = null // 清空旧结果。
  try {
    testEmailResult.value = await api.testEmail(emailTo.value) // 调测试接口。
  } catch (e) {
    showToast(e.message, 'err') // 展示错误。
  } finally {
    testingEmail.value = false // 按钮恢复。
  }
}

async function testLlm() { // 测试大模型连通性。
  testingLlm.value = true // 按钮 loading。
  testLlmResult.value = null // 清空旧结果。
  try {
    testLlmResult.value = await api.testLlm() // 调测试接口。
  } catch (e) {
    showToast(e.message, 'err') // 展示错误。
  } finally {
    testingLlm.value = false // 按钮恢复。
  }
}

// ===== 监控源(热点关键词) =====
async function loadMonitorSources() { // 加载监控源列表。
  try {
    const list = await api.getMonitorSources() // 调接口获取。
    for (const s of list) { // 为每条记录准备关键词编辑文本。
      const kws = (s.filters && s.filters.keywords) || [] // 读取数据库里的过滤关键词。
      s.keywordsText = Array.isArray(kws) ? kws.join(', ') : String(kws || '') // 列表转逗号分隔文本。
    }
    monitorSources.value = list // 保存列表。
  } catch (e) {
    showToast(e.message, 'err') // 展示错误。
  }
}

// 关键词文本转列表：支持中文逗号和英文逗号分隔，去空去重。
function parseKeywordsText(text) {
  const seen = new Set() // 去重集合。
  const list = [] // 结果列表。
  for (const part of String(text || '').split(/[,，]+/)) { // 按逗号拆分。
    const k = part.trim() // 去掉空白。
    if (k && !seen.has(k)) { // 非空且未重复。
      seen.add(k) // 记录。
      list.push(k) // 加入列表。
    }
  }
  return list // 返回关键词列表。
}

// 把逗号分隔的关键词自动转成 GitHub OR 查询；含冒号视为高级语法不转换。
function smartQuery(raw) {
  const text = String(raw || '').trim() // 去掉首尾空白。
  const parts = text.split(/[，,、;；]+/).map((p) => p.trim()).filter(Boolean) // 按中英文逗号、顿号、分号拆分。
  if (parts.length <= 1) return { query: text, converted: false } // 只有一段不需要转换。
  if (parts.some((p) => p.includes(':'))) return { query: text, converted: false } // 含冒号是高级语法（如 topic:llm），不转换。
  return { query: parts.join(' OR '), converted: true } // 多段转成 OR 查询。
}

async function saveMonitorSource(s) { // 保存单个监控源（query、启用状态和过滤关键词）。
  savingSource.value = s.id // 按钮 loading。
  try {
    const sq = smartQuery(s.query) // 逗号分隔的关键词自动转 OR 查询。
    await api.updateMonitorSource(s.id, { // 更新监控源。
      query: sq.query, // 搜索查询（可能已自动转换）。
      enabled: s.enabled, // 启用状态。
      filters: { ...(s.filters || {}), keywords: parseKeywordsText(s.keywordsText) }, // 合并过滤条件，关键词转列表。
    }) // 更新结束。
    showToast(sq.converted ? `已自动转换查询：${sq.query}` : `「${s.name}」已保存`, 'ok') // 转换时提示转换结果。
  } catch (e) {
    showToast(e.message, 'err') // 展示错误。
  } finally {
    savingSource.value = '' // 按钮恢复。
  }
}

async function deleteMonitorSource(s) { // 删除单个监控源。
  if (!window.confirm(`确定删除监控源「${s.name}」吗？删除后自动发现将不再使用该关键词`)) return // 用户确认。
  savingSource.value = s.id // 按钮 loading。
  try {
    await api.deleteMonitorSource(s.id) // 调删除接口。
    showToast('监控源已删除', 'ok') // 成功提示。
    await loadMonitorSources() // 刷新列表。
  } catch (e) {
    showToast(e.message, 'err') // 展示错误。
  } finally {
    savingSource.value = '' // 按钮恢复。
  }
}

async function addMonitorSource() { // 新增监控源。
  if (!sourceDraft.query.trim()) { // 查询为空。
    showToast('请填写监控源查询', 'err') // 提示。
    return // 不请求。
  }
  const name = sourceDraft.name.trim() || `搜索-${sourceDraft.query.trim().replace(/\s+/g, ' ').slice(0, 18)}` // 名称留空时自动生成。
  savingSource.value = 'new' // 按钮 loading。
  try {
    await api.createMonitorSource({ // 创建监控源。
      name, // 名称（自动生成或用户填写）。
      source_type: 'github_search', // 类型：GitHub 搜索。
      query: sourceDraft.query.trim(), // 查询表达式。
      filters: { keywords: parseKeywordsText(sourceDraft.keywords) }, // 本地过滤关键词。
      enabled: true, // 默认启用。
      discover_interval_minutes: 360, // 发现间隔 6 小时。
    }) // 创建结束。
    showToast('监控源已添加', 'ok') // 成功提示。
    sourceDraft.name = '' // 清空名称。
    sourceDraft.query = '' // 清空查询。
    sourceDraft.keywords = '' // 清空关键词。
    await loadMonitorSources() // 刷新列表。
  } catch (e) {
    showToast(e.message, 'err') // 展示错误。
  } finally {
    savingSource.value = '' // 按钮恢复。
  }
}

// ===== 热点项目榜单 =====
async function loadHotProjects() { // 加载今日热点项目列表。
  hotLoading.value = true // 显示加载中。
  try {
    const topN = Number(localValues.hot?.['HOT_PROJECT_TOP_N'] ?? 20) || 20 // 榜单长度用配置值。
    hotProjects.value = await api.getHotProjects(topN) // 调接口获取。
  } catch (e) {
    showToast(e.message, 'err') // 展示错误。
  } finally {
    hotLoading.value = false // 关闭加载中。
  }
}

async function runHotProjects() { // 手动计算热点榜。
  calculating.value = true // 按钮 loading。
  try {
    const topN = Number(localValues.hot?.['HOT_PROJECT_TOP_N'] ?? 20) || 20 // 榜单长度用配置值。
    const result = await api.runHotProjects(topN) // 调计算接口。
    showToast(`热点计算完成：生成 ${result.generated} 个热点项目`, 'ok') // 成功提示。
    await loadHotProjects() // 刷新榜单。
  } catch (e) {
    showToast(e.message, 'err') // 展示错误。
  } finally {
    calculating.value = false // 按钮恢复。
  }
}

// ===== 工具函数 =====
function fmtTime(t) { // 数据库时间显示为 YYYY-MM-DD HH:mm。
  if (!t) return '—' // 空值占位。
  return String(t).replace('T', ' ').slice(0, 16) // 去掉 T 并截断到分钟。
}

// ===== cron 与友好时间互转 =====
function cronToHuman(cron) { // 把 cron 表达式转成用户友好的调度描述。
  const parts = String(cron || '').trim().split(/\s+/) // 按空白拆分 cron 的 5 段。
  if (parts.length !== 5) return { mode: 'custom', time: '09:00', intervalValue: 1, intervalUnit: 'hour', cron } // 非标准 cron 走自定义。
  const [minute, hour, day, month, weekday] = parts // 解包：分 时 日 月 周。
  const isDaily = day === '*' && month === '*' && weekday === '*' // 是否每天执行。
  if (isDaily && /^\d+$/.test(minute) && /^\d+$/.test(hour)) { // 每天固定时刻，例如 30 8 * * *。
    return {
      mode: 'daily', // 模式：每天执行。
      time: `${String(Number(hour)).padStart(2, '0')}:${String(Number(minute)).padStart(2, '0')}`, // 转成 HH:MM。
      intervalValue: 1, // 间隔字段用不到。
      intervalUnit: 'hour', // 间隔字段用不到。
      cron, // 保留原始 cron。
    }
  }
  if (isDaily && minute === '0' && hour === '*') { // 每小时整点执行 0 * * * *。
    return { mode: 'interval', time: '09:00', intervalValue: 1, intervalUnit: 'hour', cron } // 每 1 小时。
  }
  if (isDaily && minute === '0' && hour.startsWith('*/')) { // 每 N 小时执行 0 */N * * *。
    const n = Number(hour.slice(2)) // 提取 N。
    if (Number.isInteger(n) && n >= 1 && n <= 23) { // N 合法。
      return { mode: 'interval', time: '09:00', intervalValue: n, intervalUnit: 'hour', cron } // 每 N 小时。
    }
  }
  if (isDaily && hour === '*' && minute.startsWith('*/')) { // 每 N 分钟执行 */N * * * *。
    const n = Number(minute.slice(2)) // 提取 N。
    if (Number.isInteger(n) && n >= 1 && n <= 59 && 60 % n === 0) { // N 合法且能整除 60（cron 分钟间隔均匀的前提）。
      return { mode: 'interval', time: '09:00', intervalValue: n, intervalUnit: 'min', cron } // 每 N 分钟。
    }
  }
  return { mode: 'custom', time: '09:00', intervalValue: 1, intervalUnit: 'hour', cron } // 其他情况走自定义。
}

function humanToCron(mode, time, intervalValue, intervalUnit) { // 把用户友好的描述转回 cron。
  if (mode === 'interval') { // 间隔模式。
    const v = Number(intervalValue) // 间隔数值。
    if (!Number.isInteger(v) || v < 1) throw new Error('间隔需为不小于 1 的整数') // 数值校验。
    if (intervalUnit === 'hour') { // 按小时间隔。
      if (v > 23) throw new Error('小时间隔需为 1-23') // 范围校验。
      return v === 1 ? '0 * * * *' : `0 */${v} * * *` // 每 N 小时 cron。
    }
    if (v > 59) throw new Error('分钟间隔需为 1-59') // 分钟范围校验。
    if (60 % v !== 0) throw new Error('分钟间隔需能整除 60（支持 1、2、3、4、5、6、10、12、15、20、30 分钟）') // 均匀间隔校验。
    return `*/${v} * * * *` // 每 N 分钟 cron。
  }
  if (mode === 'custom') { // 自定义模式。
    const raw = String(time || '').trim() // 原始 cron 输入。
    if (!raw) throw new Error('请输入 cron 表达式') // 空值校验。
    return raw // 原样返回，由后端校验。
  }
  const m = String(time || '').match(/^(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?$/) // 解析 HH:MM[:SS]。
  if (!m) throw new Error('时间格式应为 HH:MM，例如 09:00') // 格式校验。
  const hour = Number(m[1]) // 小时。
  const minute = Number(m[2]) // 分钟。
  if (hour > 23 || minute > 59) throw new Error('时间不合法') // 范围校验。
  return `${minute} ${hour} * * *` // 转成每天执行的 cron。
}

function normalizeSchedules(list) { // 为每条调度附加用户友好的时间字段。
  for (const s of list) { // 遍历调度。
    const h = cronToHuman(s.cron_expr) // cron 转友好格式。
    s.humanMode = h.mode // 模式：daily / interval / custom。
    s.humanTime = h.time // 每天执行时间 HH:MM。
    s.humanIntervalValue = h.intervalValue // 间隔数值。
    s.humanIntervalUnit = h.intervalUnit // 间隔单位：hour / min。
  }
  return list // 返回处理后的列表。
}

// ===== 页面切换监听 =====
watch(activeView, (view) => { // 切换页面时按需加载数据。
  if (view === 'hot') { // 进入热点榜单页。
    loadMonitorSources() // 加载监控源。
    loadHotProjects() // 加载热点榜单。
  }
})

// ===== 初始化 =====
onMounted(() => { // 页面挂载时。
  applyTheme(theme.value) // 应用上次选择的主题。
  const saved = sessionStorage.getItem('admin_view') // 读取上次所在页面。
  if (saved && ['dashboard', 'github', 'smtp', 'llm', 'hot', 'scheduler', 'schedules', 'system'].includes(saved)) {
    activeView.value = saved // 恢复上次页面。
  }
  if (getToken()) { // 如果 sessionStorage 里有 token。
    loadAll().then(() => { // 加载基础数据完成后。
      if (activeView.value === 'hot') { // 如果直接进入热点页。
        loadMonitorSources() // 加载监控源。
        loadHotProjects() // 加载热点榜单。
      }
    }) // 加载结束。
  } else { // 没有 token。
    loading.value = false // 显示登录界面。
  }
})
</script>

<template>
  <div class="app">
    <!-- ===== 左侧边栏 ===== -->
    <aside class="sidebar">
      <div class="sidebar-brand">
        <span class="brand-mark">AI</span>
        <div>
          <div class="brand-name">AI Hot Events</div>
          <div class="brand-sub">配置管理后台</div>
        </div>
      </div>
      <nav class="sidebar-nav">
        <div class="nav-group">工作台</div>
        <a class="nav-item" :class="{ active: activeView === 'dashboard' }" @click="switchView('dashboard')">仪表盘</a>
        <div class="nav-group">配置管理</div>
        <a class="nav-item" :class="{ active: activeView === 'github' }" @click="switchView('github')">GitHub 配置</a>
        <a class="nav-item" :class="{ active: activeView === 'smtp' }" @click="switchView('smtp')">SMTP 邮件配置</a>
        <a class="nav-item" :class="{ active: activeView === 'llm' }" @click="switchView('llm')">LLM 大模型配置</a>
        <a class="nav-item" :class="{ active: activeView === 'hot' }" @click="switchView('hot')">热点榜单</a>
        <a class="nav-item" :class="{ active: activeView === 'scheduler' }" @click="switchView('scheduler')">调度总开关</a>
        <div class="nav-group">运行状态</div>
        <a class="nav-item" :class="{ active: activeView === 'schedules' }" @click="switchView('schedules')">定时任务</a>
        <a class="nav-item" :class="{ active: activeView === 'system' }" @click="switchView('system')">系统信息</a>
      </nav>
    </aside>

    <!-- ===== 右侧主区域 ===== -->
    <div class="main-wrap">
      <!-- 顶部栏 -->
      <header class="topbar">
        <div class="topbar-search">
          <input v-model="search" class="search-input" :placeholder="activeView === 'dashboard' ? '搜索快捷入口…' : '搜索当前页配置…'" />
        </div>
        <div class="topbar-actions">
          <template v-if="!authed">
            <input v-model="tokenInput" type="password" class="token-input mono" placeholder="管理 API Token" @keyup.enter="login" />
            <button class="btn btn-primary" @click="login">登录</button>
          </template>
          <template v-else>
            <span class="env-badge mono">{{ system?.app_env || '-' }} · v{{ system?.app_version || '-' }}</span>
            <button class="icon-btn" title="通知" @click="showToast('暂无新通知', 'info')">🔔</button>
            <button class="icon-btn" :title="theme === 'light' ? '切换到深色' : '切换到浅色'" @click="toggleTheme">{{ theme === 'light' ? '🌙' : '☀️' }}</button>
            <div class="avatar" title="退出登录" @click="logout">管</div>
          </template>
        </div>
      </header>

      <!-- 内容区 -->
      <main class="content">
        <div v-if="loading" class="loading mono">LOADING CONFIG …</div>

        <template v-else-if="authed">
          <!-- ===== 仪表盘 ===== -->
          <div v-if="activeView === 'dashboard'">
            <div class="welcome">
              <div>
                <h1 class="welcome-title">{{ greeting }}，欢迎回来</h1>
                <p class="welcome-sub">{{ todayText }} · {{ summaryText }}</p>
              </div>
              <button class="btn btn-ghost" @click="loadAll">刷新数据</button>
            </div>

            <!-- KPI 卡片 -->
            <div class="kpi-grid">
              <div class="kpi">
                <div class="kpi-head">
                  <span class="kpi-label">配置总数</span>
                  <span class="kpi-dot muted"></span>
                </div>
                <div class="kpi-value">{{ totalConfigs }}</div>
                <div class="kpi-sub">全部可管理配置项</div>
              </div>
              <div class="kpi">
                <div class="kpi-head">
                  <span class="kpi-label">敏感配置</span>
                  <span class="kpi-dot" :class="secretTotal && secretSet === secretTotal ? 'ok' : 'err'"></span>
                </div>
                <div class="kpi-value">{{ secretSet }}<span style="font-size:15px;color:var(--muted);"> / {{ secretTotal }}</span></div>
                <div class="kpi-sub">Token、密码、API Key 已设置数量</div>
              </div>
              <div class="kpi">
                <div class="kpi-head">
                  <span class="kpi-label">定时任务</span>
                  <span class="kpi-dot ok"></span>
                </div>
                <div class="kpi-value">{{ enabledSchedules }}<span style="font-size:15px;color:var(--muted);"> / {{ schedules.length }}</span></div>
                <div class="kpi-sub">已启用的后台调度任务</div>
              </div>
              <div class="kpi">
                <div class="kpi-head">
                  <span class="kpi-label">调度器状态</span>
                  <span class="kpi-dot" :class="schedulerOn ? 'ok' : 'err'"></span>
                </div>
                <div class="kpi-value" style="font-size:22px;">{{ schedulerOn ? '运行中' : '已停用' }}</div>
                <div class="kpi-sub">SCHEDULER_ENABLED 总开关</div>
              </div>
            </div>

            <!-- 快捷入口 -->
            <GroupCard index="—" title="快捷入口" desc="点击进入对应的配置页面">
              <div class="quick-grid">
                <div v-for="q in filteredQuickLinks()" :key="q.view" class="quick-card" @click="switchView(q.view)">
                  <span class="quick-icon">{{ q.icon }}</span>
                  <div>
                    <div class="quick-name">{{ q.name }}</div>
                    <div class="quick-desc">{{ q.desc }}</div>
                  </div>
                  <span class="quick-arrow">→</span>
                </div>
              </div>
            </GroupCard>
          </div>

          <!-- ===== 独立配置页面 ===== -->
          <div v-else class="view">
            <!-- 页面头部 -->
            <div class="page-head">
              <div>
                <div class="page-title-row">
                  <span class="page-index mono">{{ viewMeta.index }}</span>
                  <h1 class="page-title">{{ viewMeta.title }}</h1>
                </div>
                <p class="page-desc">{{ viewMeta.desc }}</p>
              </div>
              <button class="btn btn-ghost" @click="loadAll">刷新数据</button>
            </div>

            <!-- GitHub 配置 -->
            <GroupCard v-if="activeView === 'github'" :index="GROUP_META.github.index" :title="GROUP_META.github.title" :desc="GROUP_META.github.desc">
              <template v-if="filteredFields('github').length">
                <FieldInput v-for="f in filteredFields('github')" :key="f.key" :field="f" v-model="localValues.github[f.key]" />
              </template>
              <p v-else class="no-match">没有匹配的配置项</p>
              <template #footer>
                <button class="btn btn-primary" :disabled="saving === 'github'" @click="saveGroup('github')">
                  {{ saving === 'github' ? '保存中…' : '保存并生效' }}
                </button>
              </template>
            </GroupCard>

            <!-- SMTP 邮件配置 -->
            <GroupCard v-else-if="activeView === 'smtp'" :index="GROUP_META.smtp.index" :title="GROUP_META.smtp.title" :desc="GROUP_META.smtp.desc">
              <template v-if="filteredFields('smtp').length">
                <FieldInput v-for="f in filteredFields('smtp')" :key="f.key" :field="f" v-model="localValues.smtp[f.key]" />
              </template>
              <p v-else class="no-match">没有匹配的配置项</p>
              <div v-if="!query" class="test-zone">
                <div class="test-zone-title mono">测试 · 发送测试邮件</div>
                <div class="test-zone-row">
                  <input v-model="emailTo" type="email" class="input mono" placeholder="收件邮箱，例如 you@163.com" />
                  <button class="btn btn-outline" :disabled="testingEmail" @click="testEmail">
                    {{ testingEmail ? '发送中…' : '发送' }}
                  </button>
                </div>
                <div v-if="testEmailResult" class="test-result" :class="testEmailResult.ok ? 'ok' : 'err'">
                  <span class="mono">{{ testEmailResult.ok ? 'OK' : 'FAIL' }}</span> {{ testEmailResult.message }}
                </div>
              </div>
              <template #footer>
                <button class="btn btn-primary" :disabled="saving === 'smtp'" @click="saveGroup('smtp')">
                  {{ saving === 'smtp' ? '保存中…' : '保存并生效' }}
                </button>
              </template>
            </GroupCard>

            <!-- LLM 大模型配置 -->
            <GroupCard v-else-if="activeView === 'llm'" :index="GROUP_META.llm.index" :title="GROUP_META.llm.title" :desc="GROUP_META.llm.desc">
              <template v-if="filteredFields('llm').length">
                <FieldInput v-for="f in filteredFields('llm')" :key="f.key" :field="f" v-model="localValues.llm[f.key]" />
              </template>
              <p v-else class="no-match">没有匹配的配置项</p>
              <div v-if="!query" class="test-zone">
                <div class="test-zone-title mono">测试 · 模型连通性</div>
                <div class="test-zone-row">
                  <button class="btn btn-outline" :disabled="testingLlm" @click="testLlm">
                    {{ testingLlm ? '测试中…' : '测试连接' }}
                  </button>
                </div>
                <div v-if="testLlmResult" class="test-result" :class="testLlmResult.ok ? 'ok' : 'err'">
                  <template v-if="testLlmResult.ok">
                    <span class="mono">OK</span>
                    {{ testLlmResult.model }} · {{ testLlmResult.elapsed_seconds }}s · 回复：{{ testLlmResult.reply || '(空)' }}
                  </template>
                  <template v-else>
                    <span class="mono">FAIL</span> {{ testLlmResult.message }}
                  </template>
                </div>
              </div>
              <template #footer>
                <button class="btn btn-primary" :disabled="saving === 'llm'" @click="saveGroup('llm')">
                  {{ saving === 'llm' ? '保存中…' : '保存并生效' }}
                </button>
              </template>
            </GroupCard>

            <!-- 热点榜单页（三张卡片） -->
            <template v-else-if="activeView === 'hot'">
              <!-- 榜单参数 -->
              <GroupCard index="04A" title="榜单参数" desc="热点项目榜单的规模参数">
                <template v-if="filteredFields('hot').length">
                  <FieldInput v-for="f in filteredFields('hot')" :key="f.key" :field="f" v-model="localValues.hot[f.key]" />
                </template>
                <p v-else class="no-match">没有匹配的配置项</p>
                <template #footer>
                  <button class="btn btn-primary" :disabled="saving === 'hot'" @click="saveGroup('hot')">
                    {{ saving === 'hot' ? '保存中…' : '保存并生效' }}
                  </button>
                </template>
              </GroupCard>

              <!-- 监控源关键词 -->
              <GroupCard index="04B" title="监控源关键词" desc="query 决定 GitHub 搜索范围；过滤关键词对拉回结果做本地二次过滤，保存后立即生效">
                <p v-if="!monitorSources.length" class="no-match">数据库暂无监控源，可在下方添加一个</p>
                <div v-for="s in monitorSources" :key="s.id" class="source-row">
                  <div class="source-head">
                    <span class="source-type">{{ SOURCE_TYPE_NAMES[s.source_type] || s.source_type }}</span>
                    <span class="source-name">{{ s.name }}</span>
                    <span v-if="s.last_discovered_at" class="source-time mono">最近发现 {{ fmtTime(s.last_discovered_at) }}</span>
                  </div>
                  <div class="source-controls">
                    <input v-model="s.query" class="input mono" placeholder="关键词逗号分隔自动转 OR，例如 deepseek, openai；或直接写 GitHub 语法" />
                    <label class="switch small" :title="s.enabled ? '点击停用' : '点击启用'">
                      <input type="checkbox" v-model="s.enabled" />
                      <span class="switch-track"></span>
                    </label>
                    <button class="btn btn-outline" :disabled="savingSource === s.id" @click="saveMonitorSource(s)">
                      {{ savingSource === s.id ? '保存中…' : '保存' }}
                    </button>
                    <button class="btn btn-danger" :disabled="savingSource === s.id" @click="deleteMonitorSource(s)">删除</button>
                  </div>
                  <div class="source-controls" style="margin-top: 6px;">
                    <input v-model="s.keywordsText" class="input mono" placeholder="过滤关键词，逗号分隔，例如 agent, rag（可选，命中任一才入库）" />
                  </div>
                </div>
                <div class="source-add">
                  <input v-model="sourceDraft.name" class="input" placeholder="监控源名称（可选，留空自动生成）" />
                  <input v-model="sourceDraft.query" class="input mono" placeholder="关键词逗号分隔自动转 OR，例如 deepseek, openai" />
                  <input v-model="sourceDraft.keywords" class="input mono" placeholder="过滤关键词，逗号分隔（可选）" />
                  <button class="btn btn-outline" :disabled="savingSource === 'new'" @click="addMonitorSource">
                    {{ savingSource === 'new' ? '添加中…' : '添加' }}
                  </button>
                </div>
                <template #footer>
                  <button class="btn btn-ghost" @click="loadMonitorSources">重新读取数据库</button>
                </template>
              </GroupCard>

              <!-- 今日热点项目 -->
              <GroupCard index="04C" title="今日热点项目" desc="按关键词模糊过滤，可手动触发热点计算">
                <div class="hot-toolbar">
                  <input v-model="hotKeywords" class="input mono" placeholder="关键词过滤，逗号分隔，例如 ai, agent" />
                  <button class="btn btn-outline" :disabled="calculating" @click="runHotProjects">
                    {{ calculating ? '计算中…' : '立即计算' }}
                  </button>
                </div>
                <div v-if="hotLoading" class="loading mono" style="padding: 26px 0;">LOADING …</div>
                <template v-else>
                  <div v-if="filteredHotProjects().length" class="hot-table">
                    <div class="hot-row hot-head">
                      <span class="hot-rank">#</span>
                      <span class="hot-repo">项目</span>
                      <span class="hot-lang">语言</span>
                      <span class="hot-stars">Stars</span>
                      <span class="hot-delta">24h</span>
                      <span class="hot-delta">7d</span>
                    </div>
                    <div v-for="hp in filteredHotProjects()" :key="hp.id" class="hot-row">
                      <span class="hot-rank mono">{{ hp.rank_no }}</span>
                      <span class="hot-repo">
                        <a :href="hp.html_url" target="_blank" rel="noopener">{{ hp.full_name }}</a>
                        <span class="hot-desc">{{ hp.description || '暂无简介' }}</span>
                      </span>
                      <span class="hot-lang">{{ hp.primary_language || '—' }}</span>
                      <span class="hot-stars mono">{{ hp.stars.toLocaleString() }}</span>
                      <span class="hot-delta mono up">+{{ hp.stars_delta_24h }}</span>
                      <span class="hot-delta mono up">+{{ hp.stars_delta_7d }}</span>
                    </div>
                  </div>
                  <p v-else class="no-match">
                    {{ hotKeywordsList.length ? '没有匹配的热点项目' : '今天还没有热点榜单，点击「立即计算」生成' }}
                  </p>
                </template>
              </GroupCard>
            </template>

            <!-- 调度总开关 -->
            <GroupCard v-else-if="activeView === 'scheduler'" :index="GROUP_META.scheduler.index" :title="GROUP_META.scheduler.title" :desc="GROUP_META.scheduler.desc">
              <template v-if="filteredFields('scheduler').length">
                <FieldInput v-for="f in filteredFields('scheduler')" :key="f.key" :field="f" v-model="localValues.scheduler[f.key]" />
              </template>
              <p v-else class="no-match">没有匹配的配置项</p>
              <template #footer>
                <button class="btn btn-primary" :disabled="saving === 'scheduler'" @click="saveGroup('scheduler')">
                  {{ saving === 'scheduler' ? '保存中…' : '保存并生效' }}
                </button>
              </template>
            </GroupCard>

            <!-- 定时任务 -->
            <GroupCard v-else-if="activeView === 'schedules'" index="06" title="定时任务" desc="每天固定时间执行，或按小时间隔执行；修改后立即重载调度器">
              <template v-if="filteredSchedules().length">
                <div v-for="s in filteredSchedules()" :key="s.id" class="schedule-row">
                  <div class="schedule-info">
                    <span class="schedule-name">{{ SCHEDULE_NAMES[s.name] || s.name }}</span>
                    <span class="schedule-time mono" :title="`上次运行：${fmtTime(s.last_run_at)}`">
                      next {{ fmtTime(s.next_run_at) }}
                    </span>
                  </div>
                  <div class="schedule-controls">
                    <select v-model="s.humanMode" class="input schedule-mode">
                      <option value="daily">每天执行</option>
                      <option value="interval">每 N 间隔</option>
                      <option value="custom">自定义 cron</option>
                    </select>
                    <input v-if="s.humanMode === 'daily'" v-model="s.humanTime" type="time" class="input mono time-input" />
                    <template v-else-if="s.humanMode === 'interval'">
                      <input v-model="s.humanIntervalValue" type="number" :min="1" :max="s.humanIntervalUnit === 'hour' ? 23 : 59" class="input mono interval-input" />
                      <select v-model="s.humanIntervalUnit" class="input interval-unit">
                        <option value="min">分钟</option>
                        <option value="hour">小时</option>
                      </select>
                    </template>
                    <input v-else v-model="s.cron_expr" class="input mono cron-input" placeholder="0 9 * * *" />
                    <label class="switch small" :title="s.enabled ? '点击停用' : '点击启用'">
                      <input type="checkbox" v-model="s.enabled" />
                      <span class="switch-track"></span>
                    </label>
                    <button class="btn btn-outline" :disabled="savingSchedule === s.id" @click="saveSchedule(s)">
                      {{ savingSchedule === s.id ? '保存中…' : '保存' }}
                    </button>
                  </div>
                </div>
              </template>
              <p v-else class="no-match">没有匹配的调度任务</p>
            </GroupCard>

            <!-- 系统信息 -->
            <GroupCard v-else-if="activeView === 'system'" index="07" title="系统信息" desc="只读展示，修改需编辑服务器 .env 后重启">
              <template v-if="filteredSysFields().length">
                <div v-for="f in filteredSysFields()" :key="f.key" class="sys-row">
                  <span class="sys-label">{{ f.label }}</span>
                  <span class="sys-value mono">{{ f.key === 'debug' ? (system?.debug ? 'true' : 'false') : (system?.[f.key] || '—') }}</span>
                </div>
              </template>
              <p v-else class="no-match">没有匹配的系统信息</p>
            </GroupCard>
          </div>
        </template>

        <!-- 未登录提示 -->
        <div v-else class="card login-hint">
          <h2 class="card-title" style="margin-bottom: 12px;">需要管理 Token</h2>
          <p>请输入服务器 <code class="mono">.env</code> 中配置的 <code class="mono">API_AUTH_TOKEN</code>，</p>
          <p>token 只保存在当前浏览器会话中。</p>
        </div>
      </main>
    </div>

    <!-- 顶部提示 -->
    <transition name="toast">
      <div v-if="toast" class="toast" :class="`toast-${toast.type}`">{{ toast.text }}</div>
    </transition>
  </div>
</template>
