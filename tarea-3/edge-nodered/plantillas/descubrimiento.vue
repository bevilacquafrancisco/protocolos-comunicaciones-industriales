<!--
  descubrimiento.vue — Asistente de descubrimiento y exploracion de direcciones (ADR-007, I-04)
  Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-09 · v1.0
  Descubrir: barre Unit ID x baud x paridad con FC 03 sobre la direccion 0; una respuesta,
  normal o de EXCEPCION, demuestra que hay un esclavo con esa configuracion. Primero prueba
  los Unit ID habituales en todas las combinaciones (lib/maestro.js, PRIORITARIOS).
  "Aplicar" pasa la combinacion encontrada al maestro sin reiniciar.
  Explorar: con el enlace vigente, que direcciones existen para una funcion de lectura;
  "Agregar al mapa" las incorpora.
  NOTA: tablas con <table> nativo y NO con <v-table>: Dashboard 2.0 compila la plantilla con el
  analizador HTML del navegador, que saca <tr> de cualquier elemento que no sea <table> y deja
  el v-for fuera de la fila (error "Cannot read properties of undefined" en el render).
-->
<template>
  <div>
    <v-row dense>
      <v-col cols="6" sm="2"><v-text-field v-model="idDesde" type="number" label="Unit ID desde" density="compact"></v-text-field></v-col>
      <v-col cols="6" sm="2"><v-text-field v-model="idHasta" type="number" label="hasta" density="compact"></v-text-field></v-col>
      <v-col cols="6" sm="2"><v-text-field v-model="timeoutMs" type="number" label="Timeout por prueba (ms)" density="compact"></v-text-field></v-col>
      <v-col cols="6" sm="3"><v-switch v-model="detenerEnPrimero" label="Detener en el primero" density="compact" hide-details></v-switch></v-col>
      <v-col cols="12" sm="3" class="text-caption">IDs habituales en todas las combinaciones: <b>{{ fase1 }}</b><br>peor caso (barrido completo): <b>{{ peorCaso }}</b></v-col>
    </v-row>
    <div class="text-caption mb-1">Combinaciones (en este orden; la primera es la de fábrica de la norma, 19200 8E1):</div>
    <div class="d-flex flex-wrap ga-1 mb-2">
      <v-chip v-for="(combinacion, i) in combinaciones" :key="i" size="small" filter
              :color="combinacion.activa ? 'primary' : undefined" :variant="combinacion.activa ? 'flat' : 'outlined'"
              @click="combinacion.activa = !combinacion.activa">{{ combinacion.baud }} {{ combinacion.paridad[0].toUpperCase() }}</v-chip>
    </div>
    <div class="d-flex flex-wrap ga-2">
      <v-btn color="primary" :disabled="corriendo" @click="descubrir">Descubrir esclavo</v-btn>
      <v-btn variant="outlined" color="warning" :disabled="!corriendo" @click="send({ topic: 'cancelar' })">Cancelar</v-btn>
    </div>
    <v-progress-linear v-if="corriendo" class="mt-3" :model-value="progreso" height="8" color="primary"></v-progress-linear>
    <div v-if="corriendo && ultimo" class="text-caption">probando Unit ID {{ ultimo.id }} a {{ ultimo.combinacion.baud }}
      {{ ultimo.combinacion.paridad }} · {{ ultimo.probadas }} pruebas</div>

    <v-alert v-if="resultado" class="mt-3" density="compact" variant="tonal"
             :type="resultado.encontrados && resultado.encontrados.length ? 'success' : 'warning'">
      {{ resultado.encontrados ? resultado.encontrados.length : 0 }} esclavo(s) en
      {{ (resultado.duracionMs / 1000).toFixed(1) }} s · {{ resultado.probadas }} pruebas
      <span v-if="resultado.cancelado">(cancelado)</span>
    </v-alert>
    <table v-if="resultado && resultado.encontrados && resultado.encontrados.length" class="pdci-tabla"
           style="width: 100%; border-collapse: collapse; font-size: 0.875rem">
      <thead><tr><th>Unit ID</th><th>Baud</th><th>Paridad</th><th>Respuesta</th><th>Segundos</th><th></th></tr></thead>
      <tbody>
        <tr v-for="hallazgo in resultado.encontrados" :key="hallazgo.id + '-' + hallazgo.baud + hallazgo.paridad">
          <td>{{ hallazgo.id }}</td><td>{{ hallazgo.baud }}</td><td>{{ hallazgo.paridad }}</td><td>{{ hallazgo.respuesta }}</td>
          <td>{{ hallazgo.segundos.toFixed(1) }}</td>
          <td><v-btn size="small" color="primary" @click="aplicar(hallazgo)">Aplicar</v-btn></td>
        </tr>
      </tbody>
    </table>

    <v-divider class="my-4"></v-divider>
    <div class="text-subtitle-2 mb-1">Explorar direcciones (con el enlace y el Unit ID vigentes)</div>
    <v-row dense>
      <v-col cols="12" sm="4"><v-select v-model="xFc" :items="funciones" label="Función" density="compact"></v-select></v-col>
      <v-col cols="6" sm="3"><v-text-field v-model="xDesde" label="Desde (dec o 0x…)" density="compact"></v-text-field></v-col>
      <v-col cols="6" sm="3"><v-text-field v-model="xHasta" label="Hasta" density="compact"></v-text-field></v-col>
      <v-col cols="12" sm="2"><v-btn variant="outlined" :disabled="corriendo" @click="explorar">Explorar</v-btn></v-col>
    </v-row>
    <div v-if="exploracion">
      <div class="text-caption">{{ exploracion.existentes ? exploracion.existentes.length : 0 }} direcciones existen ·
        {{ exploracion.excepciones }} excepciones · {{ exploracion.sinRespuesta }} sin respuesta ·
        {{ (exploracion.duracionMs / 1000).toFixed(1) }} s<span v-if="exploracion.error"> · {{ exploracion.error }}</span></div>
      <div class="d-flex flex-wrap ga-1 mt-1">
        <v-chip v-for="existente in exploracion.existentes" :key="existente.direccion" size="small" append-icon="mdi-plus"
                @click="send({ topic: 'agregar-al-mapa', payload: { fc: exploracion.fc, direccion: existente.direccion } })">
          0x{{ existente.direccion.toString(16).toUpperCase().padStart(4, '0') }} = {{ existente.valor }}
        </v-chip>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  data () {
    return {
      idDesde: 1, idHasta: 247, timeoutMs: 60, detenerEnPrimero: true,
      combinaciones: [], corriendo: false, progreso: 0, ultimo: null, resultado: null,
      xFc: 3, xDesde: '0', xHasta: '31', exploracion: null, cargado: false,
      funciones: [{ title: '01 Coils', value: 1 }, { title: '02 Discrete Inputs', value: 2 },
                  { title: '03 Holding Registers', value: 3 }, { title: '04 Input Registers', value: 4 }]
    }
  },
  computed: {
    fase1 () {
      // lib/maestro.js PRIORITARIOS: 1-10, 17 y 247 se prueban primero en todas las combinaciones
      const combos = this.combinaciones.filter((c) => c.activa).length
      return Math.round(12 * combos * Number(this.timeoutMs) / 100) / 10 + ' s'
    },
    peorCaso () {
      const ids = Math.max(0, Number(this.idHasta) - Number(this.idDesde) + 1)
      const combos = this.combinaciones.filter((c) => c.activa).length
      return Math.round(ids * combos * Number(this.timeoutMs) / 1000) + ' s'
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
      if (m.config && !this.cargado) {
        const d = m.config.descubrimiento
        this.idDesde = d.idDesde; this.idHasta = d.idHasta; this.timeoutMs = d.timeoutMs
        this.detenerEnPrimero = d.detenerEnPrimero
        this.combinaciones = d.combinaciones.map((c) => ({ baud: c.baud, paridad: c.paridad, activa: true }))
        this.cargado = true
      }
      if (m.topic === 'progreso') {
        this.ultimo = m.payload
        this.progreso = 100 * m.payload.probadas / Math.max(1, m.payload.total)
      } else if (m.topic === 'descubrimiento') {
        this.resultado = m.payload; this.corriendo = false
      } else if (m.topic === 'exploracion') {
        this.exploracion = m.payload; this.corriendo = false
      }
    },
    descubrir () {
      this.corriendo = true; this.resultado = null; this.progreso = 0; this.ultimo = null
      this.send({ topic: 'descubrir', payload: {
        idDesde: Number(this.idDesde), idHasta: Number(this.idHasta), timeoutMs: Number(this.timeoutMs),
        detenerEnPrimero: this.detenerEnPrimero,
        combinaciones: this.combinaciones.filter((c) => c.activa).map((c) => ({ baud: c.baud, paridad: c.paridad }))
      } })
    },
    aplicar (e) {
      this.send({ topic: 'aplicar-descubierto', payload: { id: e.id, baud: e.baud, paridad: e.paridad } })
    },
    explorar () {
      this.corriendo = true; this.exploracion = null
      this.send({ topic: 'explorar', payload: { fc: this.xFc, desde: Number(this.xDesde), hasta: Number(this.xHasta) } })
    }
  }
}
</script>
