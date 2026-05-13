<template>
  <form @submit.prevent="save">
    <input type="time" v-model="cfg.start" />
    <input type="time" v-model="cfg.end" />
    <label><input type="checkbox" v-model="cfg.enabled" /> Bật AI</label>
    <button>Lưu</button>
  </form>
</template>
<script setup>
import { ref, onMounted } from 'vue'
const cfg = ref({start:'05:00', end:'23:00', enabled:true})
const save = async () => {
  await fetch('/api/settings', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg.value)})
}
onMounted(async () => {
  const res = await fetch('/api/settings')
  cfg.value = await res.json()
})
</script>
