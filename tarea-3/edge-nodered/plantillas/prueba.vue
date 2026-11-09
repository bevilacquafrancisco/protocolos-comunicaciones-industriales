<!--
  prueba.vue — Dashboard de configuracion: "Probar conexion" y trama manual
  Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-09 · v1.0
  Probar conexion: una peticion con la configuracion vigente; muestra la trama cruda de ida
  y de vuelta y el resultado de la validacion de CRC.
  Trama manual: ID + PDU en hexadecimal (sin CRC); el maestro agrega el CRC propio. Sirve
  para dialogar con un esclavo desconocido con cualquier funcion (riesgo R-05).
-->
<template>
  <div>
    <div class="text-subtitle-2 mb-1">Probar conexión (Unit ID {{ unitId }})</div>
    <v-row dense>
      <v-col cols="12" sm="5"><v-select v-model="fc" :items="funciones" label="Función" density="compact"></v-select></v-col>
      <v-col cols="6" sm="4"><v-text-field v-model="direccion" label="Dirección (dec o 0x…)" density="compact"></v-text-field></v-col>
      <v-col cols="6" sm="3"><v-text-field v-model="cantidad" type="number" label="Cantidad" density="compact"></v-text-field></v-col>
    </v-row>
    <v-btn color="primary" :loading="esperando === 'prueba'" @click="probar">Probar conexión</v-btn>

    <div class="text-subtitle-2 mt-4 mb-1">Trama manual (sin CRC: lo agrega el maestro)</div>
    <v-text-field v-model="hex" label="ID y PDU en hexadecimal" placeholder="01 03 00 00 00 01" density="compact"></v-text-field>
    <v-btn variant="outlined" :loading="esperando === 'trama'" @click="trama">Enviar trama</v-btn>

    <v-card v-if="r" class="mt-4 pa-3" variant="tonal" :color="r.ok ? 'success' : 'error'">
      <div class="text-caption">{{ titulo }}</div>
      <div><b>TX</b> <code>{{ r.tx || '-' }}</code></div>
      <div><b>RX</b> <code>{{ r.rx || '(sin respuesta)' }}</code></div>
      <div>
        CRC de la respuesta:
        <v-chip size="small" :color="r.crcValido ? 'success' : (r.crcValido === false ? 'error' : 'grey')">
          {{ r.crcValido ? 'válido' : (r.crcValido === false ? 'INVÁLIDO' : 'sin datos') }}
        </v-chip>
        · resultado <b>{{ r.errorType }}</b>
        <span v-if="r.latenciaMs !== null && r.latenciaMs !== undefined"> · {{ r.latenciaMs }} ms</span>
      </div>
      <div v-if="r.error">{{ r.error }}</div>
      <div v-if="r.data">Datos: <code>{{ JSON.stringify(r.data) }}</code></div>
    </v-card>
  </div>
</template>

<script>
export default {
  data () {
    return {
      fc: 3, direccion: '0', cantidad: 1, hex: '', unitId: '-',
      r: null, titulo: '', esperando: null,
      funciones: [
        { title: '01 Read Coils', value: 1 }, { title: '02 Read Discrete Inputs', value: 2 },
        { title: '03 Read Holding Registers', value: 3 }, { title: '04 Read Input Registers', value: 4 }
      ]
    }
  },
  watch: {
    msg: function (m) { this.procesar(m) }
  },
  mounted () {
    if (this.msg) this.procesar(this.msg)
  },
  methods: {
    procesar (m) {
      if (!m) return
      if (m.config) this.unitId = m.config.esclavo.id
      if (m.topic === 'prueba' || m.topic === 'trama-manual') {
        this.r = m.payload
        this.titulo = m.topic === 'prueba' ? 'Probar conexión' : 'Trama manual'
        this.esperando = null
      }
    },
    probar () {
      this.esperando = 'prueba'
      this.send({ topic: 'probar', payload: { fc: this.fc, direccion: Number(this.direccion), cantidad: Number(this.cantidad) } })
    },
    trama () {
      this.esperando = 'trama'
      this.send({ topic: 'trama', payload: this.hex })
    }
  }
}
</script>
