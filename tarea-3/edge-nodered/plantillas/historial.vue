<!--
  historial.vue — Historico breve de eventos de las cuatro capas
  Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-09 · v1.0
  Recibe {topic:'historial', payload:[{ts, nivel, capa, texto}]} (E1), del mas nuevo al mas viejo.
  Solo se registran transiciones y acciones, no cada peticion: un historial que se llena de
  ruido no sirve para diagnosticar.
  NOTA: tablas con <table> nativo y NO con <v-table>: Dashboard 2.0 compila la plantilla con el
  analizador HTML del navegador, que saca <tr> de cualquier elemento que no sea <table> y deja
  el v-for fuera de la fila (error "Cannot read properties of undefined" en el render).
-->
<template>
  <div style="max-height: 320px; overflow-y: auto"><table class="pdci-tabla" style="width: 100%; border-collapse: collapse; font-size: 0.875rem">
    <thead><tr><th style="width: 90px">Hora</th><th style="width: 100px">Capa</th><th style="width: 70px">Nivel</th><th>Evento</th></tr></thead>
    <tbody>
      <tr v-for="(evento, i) in eventos" :key="i">
        <td>{{ hora(evento.ts) }}</td>
        <td>{{ evento.capa }}</td>
        <td><v-chip size="x-small" :color="evento.nivel === 'info' ? 'primary' : (evento.nivel === 'aviso' ? 'warning' : 'error')">{{ evento.nivel }}</v-chip></td>
        <td>{{ evento.texto }}</td>
      </tr>
      <tr v-if="!eventos.length"><td colspan="4" class="text-caption">Sin eventos todavía.</td></tr>
    </tbody>
  </table></div>
</template>

<script>
export default {
  data () { return { eventos: [] } },
  watch: { msg: function (m) { if (m && m.topic === 'historial') this.eventos = m.payload || [] } },
  mounted () { if (this.msg && this.msg.topic === 'historial') this.eventos = this.msg.payload || [] },
  methods: {
    hora (ts) {
      const d = new Date(ts)
      return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, '0')).join(':')
    }
  }
}
</script>
