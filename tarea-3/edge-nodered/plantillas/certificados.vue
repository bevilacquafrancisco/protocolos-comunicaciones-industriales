<!--
  certificados.vue — Lista de confianza del servidor OPC UA [DF-5.7]
  Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-10 · v1.0
  Muestra los certificados de cliente rechazados y confiados con su huella SHA-1. Antes de
  confiar, el operador COMPARA la huella con la que muestra el cliente (UaExpert: Settings >
  Manage Certificates). Confiar aplica en vivo, sin reiniciar Node-RED (docs/seguridad-opcua.md §4).
-->
<template>
  <div>
    <div class="text-caption mb-2">Huella del servidor: <code>{{ huellaPropia || '-' }}</code></div>
    <v-btn size="small" variant="outlined" @click="pedir">Actualizar</v-btn>
    <span v-if="aviso" class="ml-2 text-caption">{{ aviso }}</span>
    <table class="pdci-tabla mt-2">
      <thead><tr><th>Estado</th><th>Sujeto</th><th>Huella SHA-1</th><th>Vence</th><th></th></tr></thead>
      <tbody>
        <tr v-for="c in filas" :key="c.estado + c.huella">
          <td>{{ c.estado }}</td><td>{{ c.sujeto }}</td><td><code>{{ c.huella }}</code></td><td>{{ c.vence }}</td>
          <td>
            <v-btn v-if="c.estado === 'rechazado'" size="small" color="primary" @click="accion('confiar', c.huella)">Confiar</v-btn>
            <v-btn v-else size="small" color="error" variant="outlined" @click="accion('revocar', c.huella)">Revocar</v-btn>
          </td>
        </tr>
        <tr v-if="!filas.length"><td colspan="5">Sin certificados de cliente.</td></tr>
      </tbody>
    </table>
  </div>
</template>

<script>
export default {
  data () { return { rechazados: [], confiables: [], huellaPropia: '', aviso: '' } },
  computed: {
    filas () {
      const f = (estado) => (c) => ({ estado, sujeto: c.sujeto, huella: c.huella, vence: String(c.venceEl || '').slice(0, 10) })
      return this.rechazados.map(f('rechazado')).concat(this.confiables.map(f('confiado')))
    }
  },
  watch: {
    msg (m) {
      if (!m || m.topic !== 'certificados') return
      Object.assign(this, { rechazados: m.payload.rechazados || [], confiables: m.payload.confiables || [],
        huellaPropia: m.payload.huellaPropia, aviso: m.payload.aviso || '' })
    }
  },
  mounted () { this.pedir() },
  methods: {
    pedir () { this.send({ topic: 'certificados' }) },
    accion (topic, huella) {
      if (topic === 'confiar' && !window.confirm('¿La huella coincide con la del cliente?\n' + huella)) return
      this.send({ topic, payload: huella })
    }
  }
}
</script>
