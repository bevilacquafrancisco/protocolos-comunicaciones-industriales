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

    <!-- ADR-029: el perfil del ESP32 propio se cambia desde aca, sin jumper en GPIO 13 -->
    <div class="text-subtitle-2 mt-4 mb-1">ESP32 propio como esclavo desconocido (ensayo de I-04)</div>
    <div class="text-caption mb-2">
      Escribe el registro de configuración 0x0F00 (FC 06) del ESP32 al que apunta el maestro.
      «Convertir»: el ESP32 responde y pasa a otro Unit ID, baud y mapa; el maestro deja de
      encontrarlo (DEVICE NOT REACHED) hasta usar el asistente de descubrimiento.
      «Volver»: con el maestro ya ajustado al desconocido, lo devuelve al dispositivo 1 y
      restaura la configuración de fábrica del maestro. Reiniciar el ESP32 (botón EN) también lo devuelve.
    </div>
    <v-btn color="warning" variant="tonal" class="mr-2 mb-2" :loading="esperando === 'perfil-2'" @click="perfil(2)">Convertir en desconocido</v-btn>
    <v-btn color="success" variant="tonal" class="mb-2" :loading="esperando === 'perfil-1'" @click="perfil(1)">Volver a dispositivo 1</v-btn>
    <div v-if="avisoPerfil" class="text-body-2">{{ avisoPerfil }}</div>

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
      r: null, titulo: '', esperando: null, avisoPerfil: '',
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
        const cambio = this.esperando && this.esperando.startsWith('perfil-') ? Number(this.esperando.slice(7)) : null
        this.r = m.payload
        this.titulo = m.topic === 'prueba' ? 'Probar conexión' : (cambio ? 'Cambio de perfil del ESP32' : 'Trama manual')
        this.esperando = null
        if (cambio) this.perfilRespondido(cambio, m.payload)
      }
    },
    // ADR-029: FC 06 al registro 0x0F00 del esclavo vigente; el maestro agrega el CRC propio
    perfil (codigo) {
      const id = Number(this.unitId)
      if (!(id >= 1 && id <= 247)) { this.avisoPerfil = 'Todavía no se conoce el Unit ID vigente del maestro.'; return }
      this.avisoPerfil = ''
      this.esperando = 'perfil-' + codigo
      const h = (n) => n.toString(16).toUpperCase().padStart(2, '0')
      this.send({ topic: 'trama', payload: `${h(id)} 06 0F 00 00 ${h(codigo)}` })
    },
    perfilRespondido (codigo, r) {
      if (!r || !r.ok) {
        this.avisoPerfil = 'El esclavo no confirmó el cambio: ¿el maestro apunta al Unit ID, baud y paridad actuales del ESP32?'
        return
      }
      if (codigo === 2) {
        this.avisoPerfil = 'Listo: el ESP32 es ahora un esclavo desconocido. Usá «Descubrimiento» para encontrarlo.'
      } else {
        this.avisoPerfil = 'Listo: el ESP32 volvió a ser el dispositivo 1. Se restaura la configuración de fábrica del maestro.'
        this.send({ topic: 'restaurar-fabrica', payload: null })
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
