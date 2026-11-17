/**
 * config.example.js — plantilla de config.js (Host Application)
 * Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-12 · v2.0 (2026-11-16, ADR-028)
 *
 * Copiar a config.js (que esta en .gitignore) y completar.
 *
 * ---------------------------------------------------------------------------------------------
 * SIN CLAVES (ADR-028)
 * ---------------------------------------------------------------------------------------------
 * Hasta la v1, config.js llevaba la clave del usuario host_app: el navegador la descargaba y
 * cualquiera que abriera la pagina la veia (R-08). Desde la v2 la pagina PIDE usuario y clave al
 * entrar, los usa para el CONNECT y los guarda solo en memoria: se pierden al recargar. Asi la
 * pagina puede publicarse (por ejemplo, en GitHub Pages) sin ningun secreto adentro.
 *
 * Lo que sigue acotando el dano si una clave se filtra:
 *   - Cada usuario del broker tiene permisos MINIMOS por topico (ADR-005, ADR-027): el de la
 *     Host Application publica solo su STATE, NCMD y DCMD; no puede hacerse pasar por el Edge Node.
 *   - El Edge Node valida cada DCMD (metrica escribible, tipo, rango, tamano) y el servidor
 *     OPC UA vuelve a validar (EURange, roles): defensa en profundidad, IEC 62443-3-3 SR 3.5.
 *   - Un usuario por persona (por ejemplo, uno por profesor), revocable sin tocar a los demas.
 *
 * SOLUCION EN PRODUCCION: un backend propio (patron Backend-for-Frontend) que autentique a cada
 * persona (OIDC con MFA) y entregue tokens de vida corta que el broker valide (EMQX admite JWT).
 * ---------------------------------------------------------------------------------------------
 */
window.PDCI_CONFIG = Object.freeze({
    // WSS del broker en la nube (EMQX Cloud Serverless, ADR-027: puerto 8084, ruta /mqtt). I-03: nunca
    // un broker local en la demo. ws://127.0.0.1:<puerto>/mqtt solo para desarrollo con tools/broker_dev.py.
    url: 'wss://<direccion-del-broker>:8084/mqtt',
    // Opcional: usuario que se sugiere en la pantalla de ingreso (NO es secreto). La clave NUNCA va aca.
    usuario: '',
    // Identificadores Sparkplug (docs/diccionario-de-datos.md §4)
    grupo: 'UNRaf_PdCI_2026',
    nodo: 'EN01_Gateway',
    dispositivo: 'DEV01_ESP32_Slave',
    hostId: 'HA01_WebDashboard',
});
