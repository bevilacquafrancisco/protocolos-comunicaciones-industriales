<!--
  tramas.vue — Ultima trama transmitida y recibida, latencia y detalle de errores
  Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-09 · v1.0
  Muestra la trama REAL que esta en el bus, en hexadecimal: sirve para la defensa y para el
  analisis byte a byte del informe sin sonda ni osciloscopio. Recibe {topic:'tramas'} (E1).
-->
<template>
  <div v-if="s">
    <div><b>Esclavo</b> Unit ID {{ s.esclavo }} · {{ s.puerto }}</div>
    <div class="mt-2"><b>TX</b> <code>{{ s.ultimaTx || '-' }}</code></div>
    <div><b>RX</b> <code>{{ s.ultimaRx || '-' }}</code></div>
    <div class="mt-2">Latencia petición → respuesta completa: <b>{{ s.latenciaMs === null ? '-' : s.latenciaMs + ' ms' }}</b>
      <span class="text-caption">(incluye la transmisión de ambas tramas y la latencia del conversor USB)</span></div>
    <div>Ciclos completos: <b>{{ s.ciclos }}</b> · duración del último: <b>{{ s.duracionCicloMs === null ? '-' : s.duracionCicloMs + ' ms' }}</b></div>
    <div class="text-caption mt-2">
      Detalle de CRC_ERROR: CRC inválido {{ s.contadores.detalle.CRC_ERROR }} · trama mal formada
      {{ s.contadores.detalle.MALFORMED }} · otro Unit ID {{ s.contadores.detalle.WRONG_SLAVE }} ·
      bytes fuera de transacción {{ s.contadores.detalle.BYTES_ESPURIOS }}
      <span v-if="s.ultimaExcepcion"> · última excepción {{ s.ultimaExcepcion }}</span>
    </div>
  </div>
  <div v-else class="text-caption">Esperando al maestro…</div>
</template>

<script>
export default {
  data () { return { s: null } },
  watch: { msg: function (m) { if (m && m.topic === 'tramas') this.s = m.payload } },
  mounted () { if (this.msg && this.msg.topic === 'tramas') this.s = this.msg.payload }
}
</script>
