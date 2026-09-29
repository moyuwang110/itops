import { defineStore } from 'pinia'
import api from '../utils/api'

export const useAgentStore = defineStore('agent', {
  state: () => ({
    list: [],
    providers: [],
    loaded: false,
  }),
  actions: {
    async load() {
      const [{ data: list }, { data: providers }] = await Promise.all([
        api.get('/agents'),
        api.get('/agents/providers'),
      ])
      this.list = list
      this.providers = providers
      this.loaded = true
    },
    async create(payload) {
      const { data } = await api.post('/agents', payload)
      await this.load()
      return data
    },
    async update(id, payload) {
      const { data } = await api.put(`/agents/${id}`, payload)
      await this.load()
      return data
    },
    async remove(id) {
      await api.delete(`/agents/${id}`)
      await this.load()
    },
    async setDefault(id) {
      const { data } = await api.post(`/agents/${id}/default`)
      await this.load()
      return data
    },
  },
})