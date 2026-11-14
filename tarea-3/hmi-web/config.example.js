/**
 * config.example.js — plantilla de config.js (Host Application)
 * Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-12 · v1.0
 *
 * Copiar a config.js (que esta en .gitignore) y completar. NUNCA versionar config.js.
 *
 * ---------------------------------------------------------------------------------------------
 * POR QUE ESTO ES UNA MITIGACION Y NO UNA SOLUCION (ADR-005, riesgo R-08)
 * ---------------------------------------------------------------------------------------------
 * Sacar la clave del codigo fuente evita que quede en git, pero NO la protege: config.js se
 * descarga al navegador y cualquiera que abra la pagina la ve (herramientas de desarrollo, red).
 * En una pagina estatica no hay donde esconder un secreto. Lo que si se hace es limitar el dano:
 *
 *   - Usuario host_app con permisos MINIMOS por topico en el broker (ADR-005):
 *       publica:  spBv1.0/STATE/HA01_WebDashboard
 *                 spBv1.0/UNRaf_PdCI_2026/NCMD/EN01_Gateway
 *                 spBv1.0/UNRaf_PdCI_2026/DCMD/EN01_Gateway/DEV01_ESP32_Slave
 *       suscribe: spBv1.0/UNRaf_PdCI_2026/#  y  spBv1.0/STATE/HA01_WebDashboard
 *     Con la clave robada, un atacante puede leer el proceso y accionar los dos LED; no puede
 *     hacerse pasar por el Edge Node (no publica BIRTH/DATA/DEATH) ni tocar otro grupo.
 *   - El Edge Node valida cada DCMD (metrica escribible, tipo, rango, tamano) y el servidor
 *     OPC UA vuelve a validar (EURange, roles): la clave de la web no alcanza para escribir
 *     cualquier cosa en el campo (defensa en profundidad, IEC 62443-3-3 SR 3.5).
 *   - Clave propia de este usuario, rotable sin tocar el Edge Node.
 *
 * SOLUCION EN PRODUCCION: la pagina no habla con el broker con una clave compartida. Un backend
 * propio (patron Backend-for-Frontend) autentica a cada persona (OIDC con MFA), aplica la
 * autorizacion por rol (quien puede accionar salidas) y le entrega un token de vida corta (JWT
 * de minutos, con los topicos permitidos como claims) que el broker valida (HiveMQ y EMQX
 * soportan autenticacion JWT). Asi no hay secreto en el navegador, cada comando queda asociado
 * a una persona (no repudio) y un token robado caduca solo. En IEC 62443 eso es separar la zona
 * del usuario de la zona de control con un conducto que autentica y autoriza (SR 1.1, 2.1, 6.1).
 * ---------------------------------------------------------------------------------------------
 */
window.PDCI_CONFIG = Object.freeze({
    // WSS del broker en la nube (HiveMQ Cloud: puerto 8884, ruta /mqtt). I-03: nunca un broker local
    // en la demo. ws://127.0.0.1:<puerto>/mqtt solo para desarrollo con tools/broker_dev.py.
    url: 'wss://<id-del-cluster>.<proveedor-del-broker>:8884/mqtt',
    usuario: 'host_app',
    clave: '<clave-del-usuario-host_app>',
    // Identificadores Sparkplug (docs/diccionario-de-datos.md §4)
    grupo: 'UNRaf_PdCI_2026',
    nodo: 'EN01_Gateway',
    dispositivo: 'DEV01_ESP32_Slave',
    hostId: 'HA01_WebDashboard',
});
