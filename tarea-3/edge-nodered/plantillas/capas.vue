<!--
  capas.vue — Estadistica de las cuatro capas (I-05)
  Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-09 · v1.0
  Recibe {topic:'capas', payload:{MODBUS, OPCUA, MQTT, SPARKPLUG}} cada 1 s (E1).
  Cada tarjeta: estado textual (DONE / CRC ERROR / DEVICE NOT REACHED / ERROR / SIN DATOS),
  sus contadores y la antiguedad del dato. Un dato viejo se marca: una capa que dejo de
  informar es una falla, no un estado congelado (leccion de la T1).
-->
<template>
  <div>
    <v-row dense>
      <v-col v-for="capa in orden" :key="capa" cols="12" sm="6" md="3">
        <v-card variant="outlined" class="pa-3 h-100">
          <div class="d-flex justify-space-between align-center">
            <span class="text-subtitle-1 font-weight-bold">{{ titulos[capa] }}</span>
            <v-chip size="small" :color="color(dato(capa))" variant="flat">{{ dato(capa).estado }}</v-chip>
          </div>
          <div class="text-caption mb-2">{{ antiguedad(dato(capa)) }}</div>
          <div v-for="(valor, nombre) in dato(capa).contadores" :key="nombre" class="d-flex justify-space-between">
            <span>{{ nombre }}</span><b>{{ valor }}</b>
          </div>
          <div v-if="!Object.keys(dato(capa).contadores).length" class="text-caption text-medium-emphasis">
            {{ capa === 'MODBUS' ? 'esperando la primera petición' : 'se integra en ' + fase[capa] }}
          </div>
          <v-btn v-if="capa === 'MODBUS'" class="mt-2" size="small" variant="text"
                 @click="send({ topic: 'reiniciar-contadores' })">Poner en cero</v-btn>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script>
export default {
  data () {
    return {
      orden: ['MODBUS', 'OPCUA', 'MQTT', 'SPARKPLUG'],
      titulos: { MODBUS: 'MODBus RTU', OPCUA: 'OPC UA', MQTT: 'MQTT', SPARKPLUG: 'Sparkplug B' },
      fase: { OPCUA: 'F4', MQTT: 'F5', SPARKPLUG: 'F5' },
      capas: {},
      ahora: Date.now()
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
      if (m && m.topic === 'capas') { this.capas = m.payload || {}; this.ahora = Date.now() }
    },
    dato (capa) {
      return this.capas[capa] || { estado: 'SIN DATOS', contadores: {}, ts: null }
    },
    color (d) {
      if (d.ts && this.ahora - d.ts > 10000) return 'grey'
      if (d.estado === 'DONE' || d.estado === 'ONLINE') return 'success'
      if (d.estado === 'CRC ERROR') return 'warning'
      if (d.estado === 'SIN DATOS') return 'grey'
      return 'error'
    },
    antiguedad (d) {
      if (!d.ts) return 'sin datos todavía'
      const s = Math.round((this.ahora - d.ts) / 1000)
      return s <= 1 ? 'actualizado ahora' : (s > 10 ? '¡sin novedades hace ' + s + ' s!' : 'hace ' + s + ' s')
    }
  }
}
</script>
