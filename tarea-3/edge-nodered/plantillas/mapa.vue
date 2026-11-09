<!--
  mapa.vue — Dashboard de configuracion: tabla editable del mapa de registros (I-04)
  Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-09 · v1.0
  Por variable: nombre, codigo de funcion de lectura, direccion (offset, decimal o 0x...),
  tipo, orden de palabras (32 bits), escritura, min y max. Se agregan y quitan filas.
  Envia {topic:'aplicar-mapa', payload:[...filas]}. Recibe msg.config y 'reconfiguracion'.
  NOTA: tablas con <table> nativo y NO con <v-table>: Dashboard 2.0 compila la plantilla con el
  analizador HTML del navegador, que saca <tr> de cualquier elemento que no sea <table> y deja
  el v-for fuera de la fila (error "Cannot read properties of undefined" en el render).
-->
<template>
  <div>
    <div class="text-caption mb-2">
      La dirección es el <b>offset</b> que viaja en la trama (0x0000 = Modicon 40001 para un holding register).
      Las variables que se escriben usan FC 05 (coil) o FC 06 (holding register).
    </div>
    <table class="pdci-tabla" style="width: 100%; border-collapse: collapse; font-size: 0.875rem">
      <thead>
        <tr>
          <th>Nombre</th><th>Lectura</th><th>Dirección</th><th>Modicon</th><th>Tipo</th>
          <th>Orden</th><th>Escribe</th><th>Mín</th><th>Máx</th><th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(fila, i) in filas" :key="i">
          <td style="min-width: 210px"><v-text-field v-model="fila.nombre" density="compact" hide-details variant="plain"></v-text-field></td>
          <td style="min-width: 150px">
            <v-select v-model="fila.fc" :items="funciones" density="compact" hide-details variant="plain"
                      @update:model-value="ajustarTipo(fila)"></v-select>
          </td>
          <td style="max-width: 100px"><v-text-field v-model="fila.direccion" density="compact" hide-details variant="plain"></v-text-field></td>
          <td class="text-caption">{{ modicon(fila) }}</td>
          <td style="min-width: 110px">
            <v-select v-model="fila.tipo" :items="tiposPara(fila.fc)" density="compact" hide-details variant="plain"></v-select>
          </td>
          <td style="min-width: 90px">
            <v-select v-if="['uint32', 'int32', 'float32'].includes(fila.tipo)" v-model="fila.orden"
                      :items="['ABCD', 'CDAB']" density="compact" hide-details variant="plain"></v-select>
          </td>
          <td>
            <v-checkbox v-if="Number(fila.fc) === 1 || (Number(fila.fc) === 3 && ['uint16', 'int16'].includes(fila.tipo))"
                        v-model="fila.escritura" density="compact" hide-details></v-checkbox>
          </td>
          <td style="max-width: 70px"><v-text-field v-model="fila.min" density="compact" hide-details variant="plain"></v-text-field></td>
          <td style="max-width: 70px"><v-text-field v-model="fila.max" density="compact" hide-details variant="plain"></v-text-field></td>
          <td><v-btn icon="mdi-delete" size="small" variant="text" @click="filas.splice(i, 1)"></v-btn></td>
        </tr>
      </tbody>
    </table>
    <div class="d-flex flex-wrap ga-2 mt-3">
      <v-btn variant="outlined" prepend-icon="mdi-plus" @click="agregar">Agregar variable</v-btn>
      <v-btn color="primary" @click="aplicar">Aplicar mapa sin reiniciar</v-btn>
      <v-btn variant="text" @click="cargar(config)">Descartar cambios</v-btn>
    </div>
    <v-alert v-if="resultado" class="mt-3" density="compact" variant="tonal" :type="resultado.ok ? 'success' : 'error'">
      <div v-if="resultado.ok">Mapa aplicado y guardado.</div>
      <div v-for="mensaje in resultado.errores" :key="mensaje">{{ mensaje }}</div>
    </v-alert>
  </div>
</template>

<script>
export default {
  data () {
    return {
      filas: [],
      config: null,
      resultado: null,
      funciones: [
        { title: '01 Coils', value: 1 }, { title: '02 Discrete Inputs', value: 2 },
        { title: '03 Holding Registers', value: 3 }, { title: '04 Input Registers', value: 4 }
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
      if ((m.topic === 'config' || !this.config) && m.config) this.cargar(m.config)
      if (m.topic === 'reconfiguracion') this.resultado = m.payload
    },
    cargar (c) {
      if (!c) return
      this.config = c
      this.filas = c.mapa.map((v) => ({ nombre: v.nombre, fc: v.fc, direccion: String(v.direccion), tipo: v.tipo,
        orden: v.orden || 'ABCD', escritura: !!v.escritura,
        min: v.min === undefined ? '' : String(v.min), max: v.max === undefined ? '' : String(v.max) }))
    },
    tiposPara (fc) {
      return Number(fc) === 1 || Number(fc) === 2 ? ['bool'] : ['uint16', 'int16', 'uint32', 'int32', 'float32']
    },
    ajustarTipo (fila) {
      const posibles = this.tiposPara(fila.fc)
      if (!posibles.includes(fila.tipo)) fila.tipo = posibles[0]
      if (!(Number(fila.fc) === 1 || Number(fila.fc) === 3)) fila.escritura = false
    },
    modicon (fila) {
      // Notacion Modicon: area (0, 1, 3, 4) + offset + 1. Con offset > 9998 se usan 6 digitos.
      const dir = Number(fila.direccion)
      if (!Number.isInteger(dir) || dir < 0 || dir > 65535) return '?'
      const area = { 1: 0, 2: 1, 3: 4, 4: 3 }[Number(fila.fc)]
      return dir <= 9998 ? String(area * 10000 + dir + 1).padStart(5, '0')
                         : String(area) + String(dir + 1).padStart(5, '0')
    },
    agregar () {
      this.filas.push({ nombre: 'Nueva/Variable' + (this.filas.length + 1), fc: 3, direccion: '0', tipo: 'uint16',
        orden: 'ABCD', escritura: false, min: '', max: '' })
    },
    aplicar () {
      this.resultado = null
      this.send({ topic: 'aplicar-mapa', payload: this.filas.map((f) => {
        const v = { nombre: f.nombre, fc: Number(f.fc), direccion: f.direccion, tipo: f.tipo,
          escritura: !!f.escritura, orden: f.orden }
        if (f.min !== '') v.min = f.min
        if (f.max !== '') v.max = f.max
        return v
      }) })
    }
  }
}
</script>
