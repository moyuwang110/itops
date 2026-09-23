import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

const STORAGE_KEY = 'itops-theme'
const darkMatcher = window.matchMedia('(prefers-color-scheme: dark)')

export const useThemeStore = defineStore('theme', () => {
  const mode = ref(localStorage.getItem(STORAGE_KEY) || 'system') // system|light|dark
  const systemDark = ref(darkMatcher.matches)
  let bound = false

  const isDark = computed(() =>
    mode.value === 'dark' || (mode.value === 'system' && systemDark.value)
  )

  function apply() {
    document.documentElement.classList.toggle('dark', isDark.value)
  }

  function init() {
    if (!bound) {
      darkMatcher.addEventListener('change', (e) => {
        systemDark.value = e.matches
        apply()
      })
      bound = true
    }
    apply()
  }

  function setMode(next) {
    mode.value = next
    localStorage.setItem(STORAGE_KEY, next)
    apply()
  }

  return { mode, isDark, init, setMode }
})
