// frontend/src/api.js
// API 封装：统一带管理 token、统一处理 401 与错误信息。

const BASE = '/api/v1' // 后端接口前缀。
const TOKEN_KEY = 'admin_token' // sessionStorage 里保存 token 的键名。

export function getToken() { return sessionStorage.getItem(TOKEN_KEY) || '' } // 读取 token。
export function setToken(token) { sessionStorage.setItem(TOKEN_KEY, token) } // 保存 token。
export function clearToken() { sessionStorage.removeItem(TOKEN_KEY) } // 清除 token。

export class ApiError extends Error { // 带状态码和响应体的错误类型。
  constructor(status, message, data) {
    super(message) // 错误消息。
    this.status = status // HTTP 状态码。
    this.data = data // 响应体，可能包含 detail 等字段。
  }
}

async function request(path, options = {}) { // 统一请求函数。
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) } // 基础请求头。
  const token = getToken() // 读取当前 token。
  if (token) headers['Authorization'] = `Bearer ${token}` // 带 Bearer 前缀。
  const resp = await fetch(BASE + path, { ...options, headers }) // 发起请求。
  let data = null // 响应体。
  try { data = await resp.json() } catch { /* 非 JSON 响应忽略 */ }
  if (resp.status === 401) { // token 无效。
    clearToken() // 清除无效 token。
    throw new ApiError(401, '管理 token 无效或已过期，请重新输入', data) // 抛出登录错误。
  }
  if (!resp.ok) { // 其他错误。
    const detail = data && data.detail // 提取错误详情。
    let message = '' // 错误消息。
    if (typeof detail === 'string') message = detail // 字符串直接使用。
    else if (detail && typeof detail === 'object') message = JSON.stringify(detail) // 对象转字符串。
    else message = `请求失败 (${resp.status})` // 兜底消息。
    throw new ApiError(resp.status, message, data) // 抛出错误。
  }
  return data // 返回响应体。
}

export const api = { // 接口方法集合。
  getConfigs: () => request('/admin/configs'), // 获取分组配置（敏感字段脱敏）。
  updateConfigs: (updates) => request('/admin/configs', { method: 'PUT', body: JSON.stringify({ updates }) }), // 批量更新配置。
  testEmail: (toEmail) => request('/admin/configs/test-email', { method: 'POST', body: JSON.stringify({ to_email: toEmail }) }), // 测试邮件。
  testLlm: () => request('/admin/configs/test-llm', { method: 'POST' }), // 测试大模型。
  getSchedules: () => request('/schedules'), // 获取定时任务列表。
  updateSchedule: (id, patch) => request(`/schedules/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }), // 更新定时任务。
  getMonitorSources: () => request('/monitor-sources'), // 获取监控源列表（自动发现关键词）。
  createMonitorSource: (data) => request('/monitor-sources', { method: 'POST', body: JSON.stringify(data) }), // 新增监控源。
  updateMonitorSource: (id, patch) => request(`/monitor-sources/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }), // 更新监控源。
  deleteMonitorSource: (id) => request(`/monitor-sources/${id}`, { method: 'DELETE' }), // 删除监控源。
  getHotProjects: (limit) => request(`/hot-projects?limit=${limit}`), // 获取热点项目榜单。
  runHotProjects: (topN) => request('/hot-projects/runs', { method: 'POST', body: JSON.stringify({ report_date: null, top_n: topN, include_disabled: false }) }), // 手动计算热点榜。
}
