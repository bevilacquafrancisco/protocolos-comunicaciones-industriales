<!--
  variables.vue — Variables del dispositivo 1 en vivo, con escritura de las salidas
  Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-09 · v1.0
  Recibe {topic:'variables', payload:{variables:[...], ultimaEscritura}} (E2).
  Envia {topic:'escribir', payload:{nombre, valor}}: el maestro lo traduce a FC 05 o FC 06 y la
  tabla cambia recien con la LECTURA posterior (ADR-015: se muestra lo confirmado, no lo pedido).
  NOTA: tablas con <table> nativo y NO con <v-table>: Dashboard 2.0 compila la plantilla con el
  analizador HTML del navegador, que saca <tr> de cualquier elemento que no sea <table> y deja
  el v-for fuera de la fila (error "Cannot read properties of undefined" en el render).
-->
<template>
  <div>
    <table class="pdci-tabla" style="width: 100%; border-collapse: collapse; font-size: 0.875rem">
      <thead><tr><th>Variable</th><th>Valor</th><th>Calidad</th><th>Escribir</th></tr></thead>
      <tbody>
        <tr v-for="variable in variables" :key="variable.nombre">
          <td>{{ variable.nombre }}<div class="text-caption">{{ variable.tipo }}<span v-if="variable.fc"> · FC 0{{ variable.fc }} · 0x{{ hex(variable.direccion) }}</span></div></td>
          <td><b>{{ variable.valor === undefined ? '-' : String(variable.valor) }}</b></td>
          <td><v-chip size="x-small" :color="variable.calidad === 'good' ? 'success' : (variable.calidad === 'bad' ? 'error' : 'grey')">{{ variable.calidad || 'sin dato' }}</v-chip></td>
          <td>
            <template v-if="variable.escritura && variable.tipo === 'bool'">
              <v-btn size="small" variant="outlined" class="mr-1" @click="escribir(variable.nombre, true)">ON</v-btn>
              <v-btn size="small" variant="outlined" @click="escribir(variable.nombre, false)">OFF</v-btn>
            </template>
            <div v-else-if="variable.escritura" class="d-flex align-center ga-1">
              <v-text-field v-model="pedidos[variable.nombre]" type="number" density="compact" hide-details style="max-width: 110px"
                            :placeholder="(variable.min !== undefined ? variable.min : 0) + '-' + (variable.max !== undefined ? variable.max : 65535)"></v-text-field>
              <v-btn size="small" color="primary" @click="escribir(variable.nombre, Number(pedidos[variable.nombre]))">Escribir</v-btn>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
    <v-alert v-if="ultima" class="mt-2" density="compact" variant="tonal" :type="ultima.ok ? 'success' : 'error'">
      {{ ultima.nombre }} = {{ ultima.valor }}: {{ ultima.ok ? 'confirmada por el esclavo (eco)' : ultima.errorType + ' · ' + ultima.error }}
    </v-alert>
  </div>
</template>

<script>
export default {
  data () { return { variables: [], ultima: null, pedidos: {} } },
  watch: { msg: function (m) { this.procesar(m) } },
  mounted () { if (this.msg) this.procesar(this.msg) },
  methods: {
    procesar (m) {
      if (!m || m.topic !== 'variables') return
      this.variables = m.payload.variables || []
      this.ultima = m.payload.ultimaEscritura
    },
    escribir (nombre, valor) { this.send({ topic: 'escribir', payload: { nombre, valor } }) },
    hex (n) { return Number(n).toString(16).toUpperCase().padStart(4, '0') }
  }
}
</script>
