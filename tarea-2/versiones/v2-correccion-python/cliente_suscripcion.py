#!/usr/bin/env python3
"""
cliente_suscripcion.py — Raspberry Pi 2 (Cliente OPC UA, Modo B: suscripcion)
Autores: Peralta Agustina (version original: cliente_suscripcion_v2.py),
         Bevilacqua Francisco (correccion)
Fecha de creacion: 2026-10-20
Version: 2.0
UNRaf - Protocolos de Comunicaciones Industriales - Tarea 2

Descripcion general
-------------------
Modo B de la consigna 3.4: CreateSubscription + CreateMonitoredItems con
PublishingInterval de 100 ms. Solo el bloque C3 es propio de este archivo;
el resto esta en cliente_base.py.

Uso: igual que cliente.py (--seguridad, --sin-escritura, --anonimo, --gamma).

Dependencias externas
---------------------
asyncua 2.1.0, gpiozero (+ lgpio en la Raspberry Pi).
"""

import asyncio

from asyncua import ua

import cliente_base
from comun import ahora_iso

# Parametros PEDIDOS; los que rigen son los REVISADOS por el servidor, que se
# imprimen al crear la suscripcion y se ven en la CreateSubscriptionResponse.
PUBLISHING_INTERVAL_MS = 100
SAMPLING_INTERVAL_MS = 100
QUEUE_SIZE = 1            # solo interesa el ultimo valor
# KeepAlive = 10 x 100 ms = 1 s sin cambios -> PublishResponse vacio. Con el
# valor por defecto de asyncua (4500) el KeepAlive llega cada 7,5 min y no se
# ve en una captura de 60 s.
MAX_KEEPALIVE_COUNT = 10
# Lifetime = 300 x 100 ms = 30 s sin PublishRequest -> el servidor borra la
# suscripcion. IEC 62541-4 exige Lifetime >= 3 x KeepAlive.
LIFETIME_COUNT = 300


# =============================================================================
# BLOQUE C3 (Modo B) · Suscripcion y manejo de notificaciones
# =============================================================================

class ManejadorSuscripcion:
    """
    Recibe las notificaciones de la suscripcion (asyncua las entrega desde
    una tarea propia, al llegar cada PublishResponse con datos).

    Atributos:
        nodo_estado, nodo_rampa (ua.NodeId): para saber que variable cambio.
    """

    def __init__(self, nodos, estado, salidas):
        self.nodo_estado = nodos["estado_servidor"].nodeid
        self.nodo_rampa = nodos["rampa_servidor"].nodeid
        self._estado = estado
        self._salidas = salidas

    def datachange_notification(self, node, val, data):
        """
        Un MonitoredItem cambio.

        Parametros:
            node (asyncua.Node): variable que cambio.
            val (Any): nuevo valor.
            data (DataChangeNotif): data.monitored_item.Value es el DataValue
                completo, con StatusCode y SourceTimestamp.
        """
        dv = data.monitored_item.Value
        if node.nodeid == self.nodo_estado:
            cliente_base.replicar(self._estado, self._salidas, estado_servidor=dv)   # C4
        elif node.nodeid == self.nodo_rampa:
            cliente_base.replicar(self._estado, self._salidas, rampa_servidor=dv)    # C4

    def status_change_notification(self, status):
        """
        El servidor informa un cambio de estado de la suscripcion (p. ej.
        BadTimeout) o asyncua informa la perdida del canal (BadShutdown).
        Es parte del registro de la prueba de desconexion (3.6).
        """
        codigo = status.Status if hasattr(status, "Status") else status
        print(f"{ahora_iso()} [C3] Estado de la suscripcion: {ua.StatusCode(codigo.value).name}",
              flush=True)


async def leer_por_suscripcion(client, nodos, estado, salidas):
    """
    Crea la suscripcion y los dos MonitoredItems; despues solo espera.

    No hace falta leer los valores al conectar: el servidor envia SIEMPRE una
    notificacion inicial de cada MonitoredItem. (El problema del LED de la v1
    era el ClientHandle repetido en los dos items, no la falta de una lectura
    inicial.)
    """
    parametros = ua.CreateSubscriptionParameters(
        RequestedPublishingInterval=PUBLISHING_INTERVAL_MS,
        RequestedLifetimeCount=LIFETIME_COUNT,
        RequestedMaxKeepAliveCount=MAX_KEEPALIVE_COUNT,
        MaxNotificationsPerPublish=0,       # sin limite
        PublishingEnabled=True,
        Priority=0,
    )
    # Client.create_subscription(params, handler) -> Subscription
    suscripcion = await client.create_subscription(
        parametros, ManejadorSuscripcion(nodos, estado, salidas))
    revisados = suscripcion.parameters      # asyncua guarda aqui los REVISADOS
    print(f"{ahora_iso()} [C3] Suscripcion revisada por el servidor: "
          f"PublishingInterval={revisados.RequestedPublishingInterval} ms | "
          f"MaxKeepAliveCount={revisados.RequestedMaxKeepAliveCount} | "
          f"LifetimeCount={revisados.RequestedLifetimeCount}", flush=True)

    # Subscription.subscribe_data_change(nodes, sampling_interval: float,
    # queuesize: int) -> list[int]: UN CreateMonitoredItems con los dos items,
    # cada uno con su ClientHandle.
    handles = await suscripcion.subscribe_data_change(
        [nodos["estado_servidor"], nodos["rampa_servidor"]],
        sampling_interval=SAMPLING_INTERVAL_MS, queuesize=QUEUE_SIZE)
    print(f"{ahora_iso()} [C3] MonitoredItems pedidos: SamplingInterval={SAMPLING_INTERVAL_MS} ms | "
          f"QueueSize={QUEUE_SIZE} | handles={handles} (revisados: ver "
          f"CreateMonitoredItemsResponse en Wireshark)", flush=True)

    # Las notificaciones llegan por el manejador; esta tarea solo mantiene
    # viva la suscripcion. La perdida del canal la detecta el watchdog (C7).
    await asyncio.Event().wait()


if __name__ == "__main__":
    argumentos = cliente_base.leer_argumentos("Cliente OPC UA - Modo B (suscripcion de 100 ms)")
    try:
        asyncio.run(cliente_base.main(argumentos, leer_por_suscripcion))
    except KeyboardInterrupt:
        print("\nCliente detenido por el usuario.")
