<!--
  enlace.vue — Dashboard de configuracion: puerto, enlace serie, Unit ID y sondeo (I-04)
  Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-09 · v1.0
  Envia {topic:'aplicar-enlace', payload:{puerto, esclavo, sondeo}} o {topic:'restaurar-fabrica'}.
  Recibe msg.config (configuracion vigente) y {topic:'reconfiguracion', payload:{ok, errores}}.
  La validacion definitiva es del maestro (lib/configuracion.js): esto solo ayuda a cargar.
-->
<template>
  <div>
    <v-alert v-if="origen" density="compact" variant="tonal" class="mb-3"
             :type="origen === 'usuario' ? 'success' : 'warning'">
      {{ origen === 'usuario' ? 'Configuración guardada (sobrevive a un reinicio)' : 'Configuración de fábrica' }}
    </v-alert>
    <v-row dense>
      <v-col cols="12" sm="4">
        <v-select v-model="f.tipo" :items="medios" label="Medio" density="compact"></v-select>
      </v-col>
      <v-col cols="12" sm="8">
        <v-text-field v-if="f.tipo === 'serie'" v-model="f.ruta" label="Puerto serie"
                      hint="/dev/ttyUSB0 en la Raspberry Pi · COM5 en Windows" density="compact"></v-text-field>
        <v-text-field v-else v-model="f.tcp" label="Simulador TCP (host:puerto)"
                      hint="solo para desarrollo sin hardware" density="compact"></v-text-field>
      </v-col>
      <v-col cols="6" sm="3">
        <v-combobox v-model="f.baud" :items="bauds" label="Baud rate" density="compact"></v-combobox>
      </v-col>
      <v-col cols="6" sm="3">
        <v-select v-model="f.bitsDatos" :items="[8, 7]" label="Bits de datos" density="compact"></v-select>
      </v-col>
      <v-col cols="6" sm="3">
        <v-select v-model="f.paridad" :items="paridades" label="Paridad" density="compact"></v-select>
      </v-col>
      <v-col cols="6" sm="3">
        <v-select v-model="f.bitsParada" :items="[1, 2]" label="Bits de parada" density="compact"></v-select>
      </v-col>
      <v-col cols="6" sm="3">
        <v-text-field v-model="f.id" type="number" label="Unit ID (1-247)" density="compact"></v-text-field>
      </v-col>
      <v-col cols="6" sm="3">
        <v-text-field v-model="f.timeoutMs" type="number" label="Timeout (ms)" density="compact"></v-text-field>
      </v-col>
      <v-col cols="6" sm="3">
        <v-text-field v-model="f.periodoMs" type="number" label="Período de sondeo (ms)" density="compact"></v-text-field>
      </v-col>
      <v-col cols="6" sm="3">
        <v-text-field v-model="f.reintentos" type="number" label="Reintentos" density="compact"></v-text-field>
      </v-col>
      <v-col cols="12" sm="6">
        <v-text-field v-model="f.ausenciaMs" type="number" label="Ausencia para DEVICE NOT REACHED (ms)"
                      hint="ADR-014: un fallo aislado no declara al esclavo perdido" density="compact"></v-text-field>
      </v-col>
      <v-col cols="12" sm="6" class="d-flex align-center">
        <span class="text-caption">t3,5 a este baud rate: <b>{{ t35 }}</b></span>
      </v-col>
    </v-row>
    <div class="d-flex flex-wrap ga-2 mt-2">
      <v-btn color="primary" @click="aplicar">Aplicar sin reiniciar</v-btn>
      <v-btn variant="outlined" @click="cargar(config)">Descartar cambios</v-btn>
      <v-btn variant="text" color="warning" @click="send({ topic: 'restaurar-fabrica' })">Restaurar de fábrica</v-btn>
    </div>
    <v-alert v-if="resultado" class="mt-3" density="compact" variant="tonal"
             :type="resultado.ok ? 'success' : 'error'">
      <div v-if="resultado.ok">Aplicado y guardado.</div>
      <div v-for="mensaje in resultado.errores" :key="mensaje">{{ mensaje }}</div>
    </v-alert>
  </div>
</template>

<script>
export default {
  data () {
    return {
      f: { tipo: 'serie', ruta: '', tcp: '', baud: 9600, bitsDatos: 8, paridad: 'none', bitsParada: 1,
           id: 1, timeoutMs: 300, periodoMs: 250, reintentos: 1, ausenciaMs: 2000 },
      config: null,
      origen: null,
      resultado: null,
      medios: [{ title: 'Puerto serie (RS-485)', value: 'serie' }, { title: 'TCP (simulador)', value: 'tcp' }],
      bauds: [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200],
      paridades: [{ title: 'Ninguna (N)', value: 'none' }, { title: 'Par (E)', value: 'even' },
                  { title: 'Impar (O)', value: 'odd' }]
    }
  },
  computed: {
    t35 () {
      const b = Number(this.f.baud)
      if (!(b > 0)) return '-'
      return b > 19200 ? '1,75 ms (fijo por norma)' : (3.5 * 11 * 1000 / b).toFixed(3).replace('.', ',') + ' ms'
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
      if (m.topic === 'config' && m.config) {
        this.origen = m.origen || 'usuario'
        this.cargar(m.config)
      } else if (m.config && !this.config) {
        this.cargar(m.config)
      }
      if (m.topic === 'reconfiguracion') this.resultado = m.payload
    },
    cargar (c) {
      if (!c) return
      this.config = c
      this.f = { tipo: c.puerto.tipo, ruta: c.puerto.ruta, tcp: c.puerto.tcp, baud: c.puerto.baud,
                 bitsDatos: c.puerto.bitsDatos, paridad: c.puerto.paridad, bitsParada: c.puerto.bitsParada,
                 id: c.esclavo.id, timeoutMs: c.sondeo.timeoutMs, periodoMs: c.sondeo.periodoMs,
                 reintentos: c.sondeo.reintentos, ausenciaMs: c.sondeo.ausenciaMs }
    },
    aplicar () {
      const f = this.f
      this.resultado = null
      this.send({ topic: 'aplicar-enlace', payload: {
        puerto: { tipo: f.tipo, ruta: f.ruta, tcp: f.tcp, baud: f.baud, bitsDatos: f.bitsDatos,
                  paridad: f.paridad, bitsParada: f.bitsParada },
        esclavo: { id: f.id },
        sondeo: { timeoutMs: f.timeoutMs, periodoMs: f.periodoMs, reintentos: f.reintentos, ausenciaMs: f.ausenciaMs }
      } })
    }
  }
}
</script>
