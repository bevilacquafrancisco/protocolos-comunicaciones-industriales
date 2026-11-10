// =====================================================================
// O1 · servidor OPC UA — "On Stop" del function node
// ---------------------------------------------------------------------
// Descripcion: cierra el servidor (libera el puerto 4840) antes de que un Deploy cree
//   otro. Sin esto el nuevo fallaria con EADDRINUSE y quedaria el viejo publicando.
// =====================================================================
const listo = context.get('listo');
if (listo) {
    return listo.then((servidor) => servidor && servidor.detener(500));
}
