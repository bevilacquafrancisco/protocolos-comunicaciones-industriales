"""
servidor_prueba.py — servidor OPC UA de PRUEBA (asyncua) con los NodeIds del diccionario.
Autores: Bevilacqua Francisco, Peralta Agustina · 2026-11-12 · v1.0

Sustituye al dispositivo 2 en las pruebas del dispositivo 3: mismo namespace (ns=1 =
urn:unraf:pdci:t3), mismos NodeIds de cadena y tipos que edge-nodered/lib/servidor_opcua.js.
No implementa seguridad ni roles (eso se probo en F4 contra el servidor real); un Write sobre
Outputs se acepta y queda como valor, igual que cuando el esclavo confirma el eco.
"""

from __future__ import annotations

from asyncua import Server, ua

TIPOS = {"Boolean": ua.VariantType.Boolean, "UInt16": ua.VariantType.UInt16, "UInt32": ua.VariantType.UInt32,
         "Float": ua.VariantType.Float, "String": ua.VariantType.String}
INICIALES = {"Boolean": False, "UInt16": 0, "UInt32": 0, "Float": 0.0, "String": "DONE"}


class ServidorPrueba:
    """
    Atributos:
        url (str), nodos (dict[str, Node]): NodeId (cadena) -> nodo.
    """

    def __init__(self, metricas, puerto: int):
        self._metricas = metricas
        self.url = f"opc.tcp://127.0.0.1:{puerto}"
        self._server: Server | None = None
        self.nodos = {}

    async def iniciar(self) -> "ServidorPrueba":
        s = Server()
        await s.init()
        s.set_endpoint(self.url)
        s.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        # ns=1 = la ApplicationUri (patron de la T2, servidor.py:248-259)
        await s.set_application_uri("urn:unraf:pdci:t3")
        objetos = s.nodes.objects
        for m in self._metricas.suscriptas():
            nid = ua.NodeId.from_string(m.node_id)
            nodo = await objetos.add_variable(nid, f"1:{m.node_id.split('.')[-1]}",
                                              ua.Variant(INICIALES[m.tipo], TIPOS[m.tipo]))
            if m.escribible:
                await nodo.set_writable()
            self.nodos[m.node_id] = nodo
        await s.start()
        self._server = s
        return self

    async def escribir(self, node_id: str, valor) -> None:
        """Simula una lectura MODBus nueva del maestro (cambia el valor en el servidor)."""
        m = self._metricas.por_node_id(node_id)
        await self.nodos[node_id].write_value(ua.DataValue(ua.Variant(valor, TIPOS[m.tipo])))

    async def leer(self, node_id: str):
        return await self.nodos[node_id].read_value()

    async def detener(self) -> None:
        if self._server is not None:
            await self._server.stop()
            self._server = None
