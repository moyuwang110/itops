<template>
  <div ref="el" class="echart-box" :style="{ height }"></div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { useThemeStore } from '../stores/theme'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '320px' },
})

const el = ref(null)
let chart = null
const theme = useThemeStore()

function render() {
  if (!chart) return
  const dark = theme.isDark
  const base = {
    backgroundColor: 'transparent',
    textStyle: { color: dark ? '#c9d1d9' : '#303133' },
  }
  chart.setOption({ ...base, ...props.option }, true)
}

function resize() {
  chart && chart.resize()
}

onMounted(() => {
  chart = echarts.init(el.value, null, { renderer: 'canvas' })
  render()
  window.addEventListener('resize', resize)
})

watch(() => props.option, render, { deep: true })
watch(() => theme.isDark, render)

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart && chart.dispose()
  chart = null
})

defineExpose({ resize })
</script>

<style scoped>
.echart-box {
  width: 100%;
}
</style>
