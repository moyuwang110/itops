<template>
  <div class="page-container">
    <h2 class="page-title">集成配置</h2>
    <el-card shadow="never">
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <!-- Zabbix -->
        <el-tab-pane label="Zabbix" name="zabbix">
          <el-form :model="forms.zabbix" label-width="120px" class="cfg-form" v-loading="loading">
            <el-form-item label="服务地址">
              <el-input v-model="forms.zabbix.url" placeholder="http://zabbix.example.com/api_jsonrpc.php" />
            </el-form-item>
            <el-form-item label="API Token">
              <el-input v-model="forms.zabbix.api_token" type="password" show-password
                        placeholder="Zabbix 6.4+ 推荐 API Token；不修改请保持掩码" />
            </el-form-item>
            <el-form-item label="用户名">
              <el-input v-model="forms.zabbix.username" placeholder="或使用用户名/密码（与 Token 二选一）" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="forms.zabbix.password" type="password" show-password
                        placeholder="不修改请保持掩码" />
            </el-form-item>
            <el-form-item label="校验证书">
              <el-switch v-model="forms.zabbix.verify_ssl" />
            </el-form-item>
            <el-form-item label="启用">
              <el-switch v-model="forms.zabbix.enabled" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="save('zabbix', 'zabbix')">保存</el-button>
              <el-button :loading="testing" :disabled="!ids.zabbix" @click="test('zabbix')">连通性测试</el-button>
              <el-tag v-if="resultOf('zabbix')" :type="resultOf('zabbix').ok ? 'success' : 'danger'" style="margin-left:10px">
                {{ resultOf('zabbix').message }}
              </el-tag>
            </el-form-item>
          </el-form>
          <el-alert type="info" :closable="false"
                    title="告警 Webhook 接收地址：/api/v1/webhooks/zabbix，请求头 X-Webhook-Token 或查询参数 ?token=，在 Zabbix 动作/媒介中配置。" />
        </el-tab-pane>

        <!-- 大模型 -->
        <el-tab-pane label="大模型" name="llm">
          <el-alert type="info" :closable="false" style="margin-bottom:12px"
                    title="只需填入「订阅 Key」即可使用（支持普通 API Key 与 Token Plan 套餐订阅 Key）；Base URL 与模型已按供应商预填，通常无需修改。可启用多家构成降级链：默认供应商优先，其余按优先级数字升序兜底。" />
          <el-row :gutter="14">
            <el-col v-for="p in llmProviders" :key="p.key" :xs="24" :md="12">
              <el-card class="provider-card" shadow="hover">
                <template #header>
                  <div class="provider-head">
                    <b>{{ p.label }}</b>
                    <span class="mono text-muted">{{ p.key }}</span>
                  </div>
                </template>
                <el-form :model="forms.llm[p.key]" label-width="86px" size="small">
                  <el-form-item label="名称"><el-input v-model="forms.llm[p.key].name" /></el-form-item>
                  <el-form-item label="订阅 Key">
                    <el-input v-model="forms.llm[p.key].api_key" type="password" show-password
                              placeholder="粘贴 API Key 或 Token Plan 订阅 Key；不修改请保持掩码" />
                    <div class="form-tip">支持普通 API Key 与 Token Plan 套餐订阅 Key，在 {{ p.label }} 控制台创建，以 sk- 开头</div>
                  </el-form-item>
                  <el-form-item label="Base URL">
                    <el-input v-model="forms.llm[p.key].base_url" />
                    <div class="form-tip">已按 {{ p.label }} 预填，通常无需修改</div>
                  </el-form-item>
                  <el-form-item label="模型">
                    <el-input v-model="forms.llm[p.key].model" />
                    <div class="form-tip">已预填默认模型，可按需更换</div>
                  </el-form-item>
                  <el-form-item label="温度">
                    <el-input-number v-model="forms.llm[p.key].temperature" :min="0" :max="2" :step="0.1" />
                  </el-form-item>
                  <el-form-item label="优先级">
                    <el-input-number v-model="forms.llm[p.key].priority" :min="1" :max="999" />
                  </el-form-item>
                  <el-form-item label="设为默认">
                    <el-switch v-model="forms.llm[p.key].is_default" />
                  </el-form-item>
                  <el-form-item label="启用">
                    <el-switch v-model="forms.llm[p.key].enabled" />
                  </el-form-item>
                  <el-form-item>
                    <el-button type="primary" size="small" @click="save('llm', p.key)">保存</el-button>
                    <el-button size="small" :disabled="!ids.llm[p.key]" @click="test('llm', p.key)">连通测试</el-button>
                    <el-button size="small" type="danger" plain :disabled="!ids.llm[p.key]" @click="remove('llm', p.key)">删除</el-button>
                  </el-form-item>
                  <el-tag v-if="resultOf('llm', p.key)" size="small"
                          :type="resultOf('llm', p.key).ok ? 'success' : 'danger'">
                    {{ resultOf('llm', p.key).message }}
                  </el-tag>
                </el-form>
              </el-card>
            </el-col>
          </el-row>
        </el-tab-pane>

        <!-- 日志平台 -->
        <el-tab-pane label="日志平台" name="logs">
          <el-row :gutter="14">
            <el-col v-for="p in logProviders" :key="p.key" :xs="24" :md="12" :lg="8">
              <el-card class="provider-card" shadow="hover">
                <template #header><b>{{ p.label }} <span class="mono text-muted" style="font-weight:400">{{ p.key }}</span></b></template>
                <el-form :model="forms.logs[p.key]" label-width="92px" size="small">
                  <el-form-item label="地址"><el-input v-model="forms.logs[p.key].url" :placeholder="p.urlPlaceholder" /></el-form-item>
                  <template v-if="p.key === 'graylog'">
                    <el-form-item label="API Token"><el-input v-model="forms.logs[p.key].api_token" type="password" show-password placeholder="不修改保持掩码" /></el-form-item>
                    <el-form-item label="用户名"><el-input v-model="forms.logs[p.key].username" /></el-form-item>
                    <el-form-item label="密码"><el-input v-model="forms.logs[p.key].password" type="password" show-password /></el-form-item>
                    <el-form-item label="主机字段"><el-input v-model="forms.logs[p.key].host_field" placeholder="source" /></el-form-item>
                  </template>
                  <template v-else-if="p.key === 'loki'">
                    <el-form-item label="用户名"><el-input v-model="forms.logs[p.key].username" /></el-form-item>
                    <el-form-item label="密码"><el-input v-model="forms.logs[p.key].password" type="password" show-password /></el-form-item>
                    <el-form-item label="主机标签"><el-input v-model="forms.logs[p.key].host_label" placeholder="host" /></el-form-item>
                    <el-form-item label="默认选择器"><el-input v-model="forms.logs[p.key].default_selector" placeholder='{job=~".+"}' /></el-form-item>
                  </template>
                  <template v-else>
                    <el-form-item label="索引模式"><el-input v-model="forms.logs[p.key].index" placeholder="filebeat-*" /></el-form-item>
                    <el-form-item label="API Key"><el-input v-model="forms.logs[p.key].api_key" type="password" show-password /></el-form-item>
                    <el-form-item label="用户名"><el-input v-model="forms.logs[p.key].username" /></el-form-item>
                    <el-form-item label="密码"><el-input v-model="forms.logs[p.key].password" type="password" show-password /></el-form-item>
                    <el-form-item label="主机字段"><el-input v-model="forms.logs[p.key].host_field" placeholder="host.name" /></el-form-item>
                    <el-form-item label="消息字段"><el-input v-model="forms.logs[p.key].message_field" placeholder="message" /></el-form-item>
                    <el-form-item label="时间字段"><el-input v-model="forms.logs[p.key].timestamp_field" placeholder="@timestamp" /></el-form-item>
                  </template>
                  <el-form-item label="校验证书"><el-switch v-model="forms.logs[p.key].verify_ssl" /></el-form-item>
                  <el-form-item label="启用"><el-switch v-model="forms.logs[p.key].enabled" /></el-form-item>
                  <el-form-item>
                    <el-button type="primary" size="small" @click="save('logs', p.key)">保存</el-button>
                    <el-button size="small" :disabled="!ids.logs[p.key]" @click="test('logs', p.key)">连通性测试</el-button>
                    <el-button size="small" type="danger" plain :disabled="!ids.logs[p.key]" @click="remove('logs', p.key)">删除</el-button>
                  </el-form-item>
                  <el-tag v-if="resultOf('logs', p.key)" size="small"
                          :type="resultOf('logs', p.key).ok ? 'success' : 'danger'">
                    {{ resultOf('logs', p.key).message }}
                  </el-tag>
                </el-form>
              </el-card>
            </el-col>
          </el-row>
        </el-tab-pane>

        <!-- VMware vCenter -->
        <el-tab-pane label="VMware vCenter" name="vmware">
          <el-row :gutter="14">
            <el-col :xs="24" :md="12">
              <el-card class="provider-card" shadow="hover">
                <template #header><b>vCenter Server <span class="mono text-muted" style="font-weight:400">vcenter</span></b></template>
                <el-form :model="forms.vmware.vcenter" label-width="100px" size="small">
                  <el-form-item label="服务地址">
                    <el-input v-model="forms.vmware.vcenter.host" placeholder="vcenter.example.com 或 IP" />
                  </el-form-item>
                  <el-form-item label="端口">
                    <el-input-number v-model="forms.vmware.vcenter.port" :min="1" :max="65535" />
                  </el-form-item>
                  <el-form-item label="用户名">
                    <el-input v-model="forms.vmware.vcenter.username" placeholder="administrator@vsphere.local" />
                  </el-form-item>
                  <el-form-item label="密码">
                    <el-input v-model="forms.vmware.vcenter.password" type="password" show-password
                              placeholder="不修改请保持掩码" />
                  </el-form-item>
                  <el-form-item label="校验证书">
                    <el-switch v-model="forms.vmware.vcenter.verify_ssl" />
                  </el-form-item>
                  <el-form-item label="启用">
                    <el-switch v-model="forms.vmware.vcenter.enabled" />
                  </el-form-item>
                  <el-form-item>
                    <el-button type="primary" size="small" @click="save('vmware', 'vcenter')">保存</el-button>
                    <el-button size="small" :disabled="!ids.vmware.vcenter" @click="test('vmware', 'vcenter')">连通性测试</el-button>
                    <el-button size="small" type="danger" plain :disabled="!ids.vmware.vcenter" @click="remove('vmware', 'vcenter')">删除</el-button>
                  </el-form-item>
                  <el-tag v-if="resultOf('vmware', 'vcenter')" size="small"
                          :type="resultOf('vmware', 'vcenter').ok ? 'success' : 'danger'">
                    {{ resultOf('vmware', 'vcenter').message }}
                  </el-tag>
                </el-form>
              </el-card>
            </el-col>
          </el-row>
        </el-tab-pane>

        <!-- CMDB -->
        <el-tab-pane label="CMDB" name="cmdb">
          <el-row :gutter="14">
            <el-col :xs="24" :md="12">
              <el-card class="provider-card" shadow="hover">
                <template #header><b>OneOps CMDB <span class="mono text-muted" style="font-weight:400">oneops</span></b></template>
                <el-form :model="forms.cmdb.oneops" label-width="100px" size="small">
                  <el-form-item label="服务地址">
                    <el-input v-model="forms.cmdb.oneops.base_url" placeholder="http://192.168.107.150:8000" />
                  </el-form-item>
                  <el-form-item label="用户名">
                    <el-input v-model="forms.cmdb.oneops.username" placeholder="登录用户名" />
                  </el-form-item>
                  <el-form-item label="密码">
                    <el-input v-model="forms.cmdb.oneops.password" type="password" show-password
                              placeholder="不修改请保持掩码" />
                  </el-form-item>
                  <el-form-item label="校验证书">
                    <el-switch v-model="forms.cmdb.oneops.verify_ssl" />
                  </el-form-item>
                  <el-form-item label="启用">
                    <el-switch v-model="forms.cmdb.oneops.enabled" />
                  </el-form-item>
                  <el-form-item>
                    <el-button type="primary" size="small" @click="save('cmdb', 'oneops')">保存</el-button>
                    <el-button size="small" :disabled="!ids.cmdb.oneops" @click="test('cmdb', 'oneops')">连通性测试</el-button>
                    <el-button size="small" type="danger" plain :disabled="!ids.cmdb.oneops" @click="remove('cmdb', 'oneops')">删除</el-button>
                  </el-form-item>
                  <el-tag v-if="resultOf('cmdb', 'oneops')" size="small"
                          :type="resultOf('cmdb', 'oneops').ok ? 'success' : 'danger'">
                    {{ resultOf('cmdb', 'oneops').message }}
                  </el-tag>
                </el-form>
              </el-card>
            </el-col>
          </el-row>
        </el-tab-pane>

        <!-- 通知渠道 -->
        <el-tab-pane label="通知渠道" name="notify">
          <el-row :gutter="14">
            <el-col v-for="p in notifyProviders" :key="p.key" :xs="24" :md="12">
              <el-card class="provider-card" shadow="hover">
                <template #header><b>{{ p.label }} <span class="mono text-muted" style="font-weight:400">{{ p.key }}</span></b></template>
                <el-form :model="forms.notify[p.key]" label-width="100px" size="small">
                  <el-form-item label="Webhook">
                    <el-input v-model="forms.notify[p.key].webhook_url" type="textarea" :rows="2"
                              placeholder="群机器人 Webhook 完整地址；不修改请保持掩码" />
                  </el-form-item>
                  <el-form-item label="加签密钥">
                    <el-input v-model="forms.notify[p.key].secret" type="password" show-password
                              placeholder="群安全设置中的签名密钥；不修改请保持掩码" />
                  </el-form-item>
                  <el-form-item label="启用"><el-switch v-model="forms.notify[p.key].enabled" /></el-form-item>
                  <el-form-item>
                    <el-button type="primary" size="small" @click="save('notify', p.key)">保存</el-button>
                    <el-button size="small" :disabled="!ids.notify[p.key]" @click="test('notify', p.key)">测试发送</el-button>
                    <el-button size="small" type="danger" plain :disabled="!ids.notify[p.key]" @click="remove('notify', p.key)">删除</el-button>
                  </el-form-item>
                  <el-tag v-if="resultOf('notify', p.key)" size="small"
                          :type="resultOf('notify', p.key).ok ? 'success' : 'danger'">
                    {{ resultOf('notify', p.key).message }}
                  </el-tag>
                </el-form>
              </el-card>
            </el-col>
          </el-row>
        </el-tab-pane>

        <!-- 分析参数 -->
        <el-tab-pane label="分析参数" name="system">
          <el-form :model="sysForm" label-width="180px" class="cfg-form" v-loading="loading">
            <el-form-item label="收到告警自动分析">
              <el-switch v-model="sysForm.auto_analysis" />
              <span class="text-muted" style="margin-left:10px">关闭后仅支持手动触发分析</span>
            </el-form-item>
            <el-form-item label="告警前取数窗口（分钟）">
              <el-input-number v-model="sysForm.before_minutes" :min="1" :max="1440" />
            </el-form-item>
            <el-form-item label="告警后取数窗口（分钟）">
              <el-input-number v-model="sysForm.after_minutes" :min="0" :max="720" />
            </el-form-item>
            <el-form-item label="日志检索关键词">
              <el-input v-model="sysForm.log_keywords" style="max-width:420px"
                        placeholder="以英文逗号分隔，如 error,exception,超时,OOM" />
            </el-form-item>
            <el-form-item label="分析后自动推送渠道">
              <el-checkbox-group v-model="sysForm.auto_notify_channels">
                <el-checkbox v-for="c in enabledNotifyChannels" :key="c.provider" :label="c.provider">
                  {{ c.name }}（{{ c.provider }}）
                </el-checkbox>
              </el-checkbox-group>
              <div v-if="!enabledNotifyChannels.length" class="text-muted">暂无已启用通知渠道</div>
            </el-form-item>
            <el-divider content-position="left">告警降噪</el-divider>
            <el-form-item label="智能去重">
              <el-switch v-model="sysForm.dedup_enabled" />
              <span class="text-muted" style="margin-left:10px">同一主机+触发器+标题在窗口内合并</span>
            </el-form-item>
            <el-form-item label="去重时间窗口（分钟）">
              <el-input-number v-model="sysForm.dedup_window_minutes" :min="1" :max="1440" />
            </el-form-item>
            <el-form-item label="告警抑制">
              <el-switch v-model="sysForm.suppression_enabled" />
              <span class="text-muted" style="margin-left:10px">维护窗口、主机宕机、风暴时抑制低级别告警</span>
            </el-form-item>
            <el-form-item label="关联分析">
              <el-switch v-model="sysForm.correlation_enabled" />
              <span class="text-muted" style="margin-left:10px">父子关联（主机宕机抑制服务告警）+ 风暴检测</span>
            </el-form-item>
            <el-form-item label="风暴阈值（条）">
              <el-input-number v-model="sysForm.storm_threshold" :min="1" :max="10000" />
              <span class="text-muted" style="margin-left:10px">窗口内同主机告警数达到该值判定为风暴</span>
            </el-form-item>
            <el-form-item label="风暴时间窗口（分钟）">
              <el-input-number v-model="sysForm.storm_window_minutes" :min="1" :max="1440" />
            </el-form-item>
            <el-divider content-position="left">自动分析条件规则</el-divider>
            <el-alert type="info" :closable="false" style="margin-bottom:12px"
                      title="规则间为「或」关系，单条规则内各条件为「且」关系；条件留空表示不限制。无规则时所有告警自动分析。" />
            <div class="rules-list">
              <el-card v-for="(rule, idx) in sysForm.auto_analysis_rules" :key="idx"
                       class="rule-card" shadow="never">
                <div class="rule-head">
                  <el-input v-model="rule.name" placeholder="规则名称（可选）" style="max-width:220px" size="small" />
                  <el-switch v-model="rule.enabled" active-text="启用" inactive-text="停用" size="small" />
                  <el-button link type="danger" size="small" @click="removeRule(idx)">删除</el-button>
                </div>
                <el-form label-width="110px" size="small" class="rule-form">
                  <el-form-item label="告警级别">
                    <el-select v-model="rule.severities" multiple collapse-tags collapse-tags-tooltip
                               placeholder="不限" style="width:100%">
                      <el-option v-for="s in severityOptions" :key="s" :label="s" :value="s" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="指定主机">
                    <el-select v-model="rule.hosts" multiple filterable allow-create collapse-tags collapse-tags-tooltip
                               placeholder="不限，可输入主机名回车添加" style="width:100%" />
                  </el-form-item>
                  <el-form-item label="主机通配符">
                    <el-input v-model="rule.host_pattern" placeholder="如 prod-*，匹配主机名" clearable />
                  </el-form-item>
                  <el-form-item label="生效时段">
                    <div class="time-ranges">
                      <div v-for="(tr, ti) in rule.time_ranges" :key="ti" class="time-range-row">
                        <el-time-picker v-model="tr.start" format="HH:mm" value-format="HH:mm" placeholder="开始" style="width:110px" />
                        <span>-</span>
                        <el-time-picker v-model="tr.end" format="HH:mm" value-format="HH:mm" placeholder="结束" style="width:110px" />
                        <el-button link type="danger" size="small" @click="rule.time_ranges.splice(ti, 1)">移除</el-button>
                      </div>
                      <el-button size="small" plain @click="rule.time_ranges.push({ start: '', end: '' })">+ 添加时段</el-button>
                    </div>
                  </el-form-item>
                  <el-form-item label="标题关键字">
                    <el-select v-model="rule.keywords" multiple filterable allow-create collapse-tags collapse-tags-tooltip
                               placeholder="不限，标题需包含任一关键字" style="width:100%" />
                  </el-form-item>
                </el-form>
              </el-card>
              <el-button type="primary" plain size="small" @click="addRule" :icon="Plus">+ 添加规则</el-button>
            </div>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="saveSystem">保存设置</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '../../utils/api'

const route = useRoute()
const router = useRouter()

const TABS = ['zabbix', 'llm', 'logs', 'vmware', 'cmdb', 'notify', 'system']
const activeTab = ref(TABS.includes(route.params.tab) ? route.params.tab : 'zabbix')

watch(() => route.params.tab, (t) => {
  if (TABS.includes(t)) activeTab.value = t
})
function onTabChange(name) {
  router.replace(`/settings/${name}`)
}

const llmProviders = [
  { key: 'deepseek', label: 'DeepSeek', base: 'https://api.deepseek.com', model: 'deepseek-chat' },
  { key: 'doubao', label: '豆包（火山方舟）', base: 'https://ark.cn-beijing.volces.com/api/v3', model: 'doubao-seed-1-6-250615' },
  { key: 'qwen', label: '通义千问', base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  { key: 'minimax', label: 'MiniMax', base: 'https://api.minimax.io/v1', model: 'MiniMax-M1' },
]
const logProviders = [
  { key: 'graylog', label: 'Graylog', urlPlaceholder: 'http://graylog.example.com:9000' },
  { key: 'loki', label: 'Grafana Loki', urlPlaceholder: 'http://loki.example.com:3100' },
  { key: 'elasticsearch', label: 'Elasticsearch / ELK', urlPlaceholder: 'http://es.example.com:9200' },
]
const notifyProviders = [
  { key: 'feishu', label: '飞书群机器人' },
  { key: 'wecom', label: '企业微信群机器人' },
]

function emptyLlm(p) {
  return { name: p.label, base_url: p.base, api_key: '', model: p.model, temperature: 0.2, priority: 100, is_default: false, enabled: false }
}

const forms = reactive({
  zabbix: { url: '', api_token: '', username: '', password: '', verify_ssl: true, enabled: false },
  llm: Object.fromEntries(llmProviders.map((p) => [p.key, emptyLlm(p)])),
  logs: {
    graylog: { url: '', api_token: '', username: '', password: '', host_field: 'source', verify_ssl: true, enabled: false },
    loki: { url: '', username: '', password: '', host_label: 'host', default_selector: '{job=~".+"}', verify_ssl: true, enabled: false },
    elasticsearch: { url: '', index: 'filebeat-*', api_key: '', username: '', password: '', host_field: 'host.name', message_field: 'message', timestamp_field: '@timestamp', verify_ssl: true, enabled: false },
  },
  notify: {
    feishu: { webhook_url: '', secret: '', enabled: false },
    wecom: { webhook_url: '', secret: '', enabled: false },
  },
  vmware: {
    vcenter: { host: '', port: 443, username: '', password: '', verify_ssl: false, enabled: false },
  },
  cmdb: {
    oneops: { base_url: '', username: '', password: '', verify_ssl: false, enabled: false },
  },
})

const ids = reactive({ zabbix: null, llm: {}, logs: {}, notify: {}, vmware: {}, cmdb: {} })
const testResults = reactive({})
const enabledNotifyChannels = ref([])
const sysForm = reactive({
  auto_analysis: true, before_minutes: 30, after_minutes: 10,
  log_keywords: 'error,exception,超时,failed,OOM', auto_notify_channels: [],
  dedup_enabled: true, dedup_window_minutes: 5,
  suppression_enabled: true, correlation_enabled: true,
  storm_threshold: 10, storm_window_minutes: 5,
  auto_analysis_rules: [],
})

const severityOptions = ['未分类', '信息', '警告', '一般严重', '严重', '灾难']

function addRule() {
  sysForm.auto_analysis_rules.push({
    name: '', enabled: true, severities: [], hosts: [],
    host_pattern: '', time_ranges: [], keywords: [],
  })
}

function removeRule(idx) {
  sysForm.auto_analysis_rules.splice(idx, 1)
}

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)

function resultOf(type, provider) {
  const key = provider ? `${type}:${provider}` : type
  return testResults[key]
}

// 含掩码的敏感值视为未修改，提交时剔除该键
const SENSITIVE = {
  zabbix: ['api_token', 'password'],
  llm: ['api_key'],
  logs: { graylog: ['api_token', 'password'], loki: ['password'], elasticsearch: ['api_key', 'password'] },
  notify: ['webhook_url', 'secret'],
  vmware: ['password'],
  cmdb: ['password'],
}

function buildSettings(type, provider) {
  const src = type === 'zabbix' ? forms.zabbix
    : forms[type][provider]
  let sensitiveKeys = []
  if (type === 'logs') sensitiveKeys = SENSITIVE.logs[provider]
  else sensitiveKeys = SENSITIVE[type]
  const out = {}
  for (const [k, v] of Object.entries(src)) {
    if (sensitiveKeys.includes(k) && typeof v === 'string' && v.includes('*')) continue
    out[k] = v
  }
  return out
}

async function loadAll() {
  loading.value = true
  try {
    const { data } = await api.get('/configs')
    for (const row of data) {
      if (row.type === 'zabbix') {
        ids.zabbix = row.id
        Object.assign(forms.zabbix, { ...row.settings, enabled: row.enabled })
      } else if (row.type === 'llm' && forms.llm[row.provider]) {
        ids.llm[row.provider] = row.id
        Object.assign(forms.llm[row.provider], {
          name: row.name, ...row.settings,
          enabled: row.enabled, is_default: row.is_default, priority: row.priority,
        })
      } else if (row.type === 'log_platform' && forms.logs[row.provider]) {
        ids.logs[row.provider] = row.id
        Object.assign(forms.logs[row.provider], { ...row.settings, enabled: row.enabled })
      } else if (row.type === 'notify_channel' && forms.notify[row.provider]) {
        ids.notify[row.provider] = row.id
        Object.assign(forms.notify[row.provider], { ...row.settings, enabled: row.enabled })
      } else if (row.type === 'vmware' && forms.vmware[row.provider]) {
        ids.vmware[row.provider] = row.id
        Object.assign(forms.vmware[row.provider], { ...row.settings, enabled: row.enabled })
      } else if (row.type === 'cmdb' && forms.cmdb[row.provider]) {
        ids.cmdb[row.provider] = row.id
        Object.assign(forms.cmdb[row.provider], { ...row.settings, enabled: row.enabled })
      }
    }
    enabledNotifyChannels.value = data.filter((r) => r.type === 'notify_channel' && r.enabled)

    const sys = await api.get('/configs/system')
    const sysData = sys.data
    // 归一化自动分析规则，确保旧数据缺字段时有默认值
    if (Array.isArray(sysData.auto_analysis_rules)) {
      sysData.auto_analysis_rules = sysData.auto_analysis_rules.map((r) => ({
        name: r.name || '',
        enabled: r.enabled !== false,
        severities: Array.isArray(r.severities) ? r.severities : [],
        hosts: Array.isArray(r.hosts) ? r.hosts : [],
        host_pattern: r.host_pattern || '',
        time_ranges: Array.isArray(r.time_ranges) ? r.time_ranges : [],
        keywords: Array.isArray(r.keywords) ? r.keywords : [],
      }))
    } else {
      sysData.auto_analysis_rules = []
    }
    Object.assign(sysForm, sysData)
  } finally {
    loading.value = false
  }
}

async function save(type, provider) {
  saving.value = true
  try {
    const body = type === 'zabbix'
      ? { type: 'zabbix', provider: 'zabbix', name: 'Zabbix', settings: buildSettings('zabbix'), enabled: forms.zabbix.enabled }
      : {
          type: type === 'logs' ? 'log_platform'
            : type === 'notify' ? 'notify_channel'
            : type === 'vmware' ? 'vmware'
            : type === 'cmdb' ? 'cmdb'
            : 'llm',
          provider,
          name: type === 'llm' ? forms.llm[provider].name
            : type === 'logs' ? logProviders.find((p) => p.key === provider).label
            : type === 'notify' ? notifyProviders.find((p) => p.key === provider).label
            : type === 'vmware' ? 'vCenter Server'
            : 'OneOps CMDB',
          settings: buildSettings(type, provider),
          enabled: forms[type][provider].enabled,
          is_default: type === 'llm' ? forms.llm[provider].is_default : false,
          priority: type === 'llm' ? forms.llm[provider].priority : 100,
        }
    await api.post('/configs', body)
    ElMessage.success('已保存')
    await loadAll()
  } finally {
    saving.value = false
  }
}

async function remove(type, provider) {
  const id = ids[type]?.[provider]
  if (!id) return
  await ElMessageBox.confirm(`确认删除该配置？删除后相关集成将立即失效。`, '危险操作', { type: 'warning' })
  await api.delete(`/configs/${id}`)
  ElMessage.success('已删除')
  await loadAll()
}

async function test(type, provider) {
  testing.value = true
  try {
    const id = provider ? ids[type]?.[provider] : ids.zabbix
    const { data } = await api.post(`/configs/${id}/test`)
    testResults[provider ? `${type}:${provider}` : type] = data
  } finally {
    testing.value = false
  }
}

async function saveSystem() {
  saving.value = true
  try {
    await api.put('/configs/system', { ...sysForm })
    ElMessage.success('系统设置已保存')
  } finally {
    saving.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.cfg-form {
  max-width: 680px;
}
.provider-card {
  margin-bottom: 14px;
}
.provider-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.form-tip {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
  margin-top: 2px;
}
.rules-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 8px;
}
.rule-card {
  border: 1px solid var(--el-border-color-lighter);
}
.rule-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.rule-form {
  max-width: 560px;
}
.time-ranges {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.time-range-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
