#!/usr/bin/env python3
"""
TP2 OPC UA - Raspberry Pi 2 (Cliente, modo suscripción)
UNRaf - Protocolos de Comunicaciones Industriales

GPIO propuestos:
- Pulsador: GPIO 17
- LED digital: GPIO 27
- LED PWM: GPIO 18

Red:
- Ethernet cliente: 192.168.10.2/24
- Servidor OPC UA: opc.tcp://192.168.10.1:4840

Este archivo implementa el Modo B pedido por la consigna:
CreateSubscription + CreateMonitoredItems.

Parámetros de trabajo:
- PublishingInterval: 100 ms
- SamplingInterval: 100 ms
- QueueSize: 1

Requiere:
    python3 -m pip install asyncua gpiozero
"""

import asyncio
import time
from datetime import datetime

from asyncua import Client, ua
from gpiozero import Button, LED, PWMLED

# -----------------------------
# CONFIGURACIÓN GPIO
# -----------------------------
PIN_PULSADOR = 17
PIN_LED_DIGITAL = 27
PIN_LED_PWM = 18

pulsador = Button(PIN_PULSADOR, pull_up=False, bounce_time=0.05)
led_digital = LED(PIN_LED_DIGITAL)
led_pwm = PWMLED(PIN_LED_PWM)

# -----------------------------
# CONFIGURACIÓN OPC UA
# -----------------------------
URL_SERVIDOR = "opc.tcp://192.168.10.1:4840"

NODE_ESTADO_SERVIDOR = "ns=1;s=Servidor.EstadoPulsador"
NODE_RAMPA_SERVIDOR = "ns=1;s=Servidor.Rampa"
NODE_ESTADO_CLIENTE = "ns=1;s=Cliente.EstadoPulsador"
NODE_RAMPA_CLIENTE = "ns=1;s=Cliente.Rampa"

PUBLISHING_INTERVAL_MS = 100
SAMPLING_INTERVAL_MS = 100
QUEUE_SIZE = 1

INTERVALO_ESCRITURA = 0.100
INTERVALO_RECONEXION = 2.0


def generar_rampa_triangular(t):
    """
    Rampa triangular 0..65535.
    Periodo total: 8 s.
    Subida: 4 s.
    Bajada: 4 s.
    """
    fase = t % 8.0

    if fase < 4.0:
        return min(65535, int((fase / 4.0) * 65535))
    else:
        return max(0, int(((8.0 - fase) / 4.0) * 65535))


class ManejadorSuscripcion:
    """
    Recibe las notificaciones de cambios provenientes del servidor.
    """

    def __init__(self, nodo_estado, nodo_rampa):
        self.nodo_estado = nodo_estado
        self.nodo_rampa = nodo_rampa

        self.estado_servidor = False
        self.rampa_servidor = 0
        self.source_timestamp_rampa = None

    def datachange_notification(self, node, val, data):
        """
        Callback llamado por asyncua cuando cambia un valor monitoreado.
        """
        try:
            nodeid = node.nodeid.to_string()

            if nodeid == self.nodo_estado.nodeid.to_string():
                self.estado_servidor = bool(val)

                if self.estado_servidor:
                    led_digital.on()
                else:
                    led_digital.off()

            elif nodeid == self.nodo_rampa.nodeid.to_string():
                self.rampa_servidor = int(val)

                led_pwm.value = max(
                    0.0,
                    min(1.0, self.rampa_servidor / 65535.0)
                )

                # Intentar recuperar SourceTimestamp de la notificación.
                try:
                    self.source_timestamp_rampa = (
                        data.monitored_item.Value.SourceTimestamp
                    )
                except Exception:
                    self.source_timestamp_rampa = None

        except Exception as exc:
            print(f"[ADVERTENCIA NOTIFICACIÓN] {exc}")

    def event_notification(self, event):
        # No se utilizan eventos OPC UA en este TP.
        pass


async def crear_item_monitoreado(subscription, node):
    """
    Crea un MonitoredItem con parámetros explícitos:
    SamplingInterval = 100 ms
    QueueSize = 1
    DiscardOldest = True

    La API de asyncua puede variar levemente según la versión.
    """
    params = ua.MonitoringParameters()
    params.ClientHandle = 0
    params.SamplingInterval = float(SAMPLING_INTERVAL_MS)
    params.Filter = None
    params.QueueSize = QUEUE_SIZE
    params.DiscardOldest = True

    request = ua.MonitoredItemCreateRequest()
    request.ItemToMonitor = ua.ReadValueId()
    request.ItemToMonitor.NodeId = node.nodeid
    request.ItemToMonitor.AttributeId = ua.AttributeIds.Value
    request.MonitoringMode = ua.MonitoringMode.Reporting
    request.RequestedParameters = params

    result = await subscription.create_monitored_items([request])

    return result


async def ejecutar_sesion():
    client = Client(url=URL_SERVIDOR)

    print(f"Conectando a {URL_SERVIDOR} ...")
    await client.connect()
    print("CLIENTE OPC UA CONECTADO - MODO SUSCRIPCIÓN")

    try:
        estado_servidor = client.get_node(NODE_ESTADO_SERVIDOR)
        rampa_servidor = client.get_node(NODE_RAMPA_SERVIDOR)
        estado_cliente = client.get_node(NODE_ESTADO_CLIENTE)
        rampa_cliente = client.get_node(NODE_RAMPA_CLIENTE)

        manejador = ManejadorSuscripcion(
            estado_servidor,
            rampa_servidor
        )

        # -----------------------------------------------------
        # SINCRONIZACIÓN INICIAL / TRAS RECONEXIÓN
        # -----------------------------------------------------
        # Antes de crear la suscripción, leer una vez los valores actuales
        # del servidor. Esto evita que los LEDs queden con un estado viejo
        # si, al reconectar, la variable no cambia inmediatamente y por lo
        # tanto no llega una nueva notificación de DataChange.
        data_estado_inicial = await estado_servidor.read_data_value()
        data_rampa_inicial = await rampa_servidor.read_data_value()

        manejador.estado_servidor = bool(data_estado_inicial.Value.Value)
        manejador.rampa_servidor = int(data_rampa_inicial.Value.Value)
        manejador.source_timestamp_rampa = data_rampa_inicial.SourceTimestamp

        if manejador.estado_servidor:
            led_digital.on()
        else:
            led_digital.off()

        led_pwm.value = max(
            0.0,
            min(1.0, manejador.rampa_servidor / 65535.0)
        )

        print(
            "Sincronización inicial completada | "
            f"EstadoPulsador={int(manejador.estado_servidor)} | "
            f"Rampa={manejador.rampa_servidor}"
        )

        # -----------------------------------------------------
        # CREAR SUSCRIPCIÓN
        # -----------------------------------------------------
        subscription = await client.create_subscription(
            PUBLISHING_INTERVAL_MS,
            manejador
        )

        print(
            f"Suscripción creada | "
            f"PublishingInterval={PUBLISHING_INTERVAL_MS} ms"
        )

        # Crear los MonitoredItems mediante la API de alto nivel.
        # asyncua asigna ClientHandle distintos a cada nodo, evitando
        # colisiones entre EstadoPulsador y Rampa.
        handle_estado = await subscription.subscribe_data_change(
            estado_servidor,
            sampling_interval=SAMPLING_INTERVAL_MS,
            queuesize=QUEUE_SIZE
        )

        handle_rampa = await subscription.subscribe_data_change(
            rampa_servidor,
            sampling_interval=SAMPLING_INTERVAL_MS,
            queuesize=QUEUE_SIZE
        )

        print(
            "MonitoredItems creados | "
            f"SamplingInterval={SAMPLING_INTERVAL_MS} ms | "
            f"QueueSize={QUEUE_SIZE} | "
            f"handles={handle_estado},{handle_rampa}"
        )

        inicio_rampa = time.monotonic()
        estado_anterior = None
        ultimo_log = 0.0

        while True:
            ciclo_inicio = time.monotonic()

            # -----------------------------
            # DATOS LOCALES
            # -----------------------------
            estado_local = bool(pulsador.is_pressed)

            valor_rampa_local = generar_rampa_triangular(
                ciclo_inicio - inicio_rampa
            )

            # Pulsador: escribir solo al cambiar.
            if estado_local != estado_anterior:
                await estado_cliente.write_value(
                    ua.Variant(
                        estado_local,
                        ua.VariantType.Boolean
                    )
                )
                estado_anterior = estado_local

            # Rampa: escribir cada 100 ms.
            await rampa_cliente.write_value(
                ua.Variant(
                    valor_rampa_local,
                    ua.VariantType.UInt16
                )
            )

            # -----------------------------
            # LOG PERIÓDICO
            # -----------------------------
            ahora = time.monotonic()

            if ahora - ultimo_log >= 0.5:
                ts = manejador.source_timestamp_rampa

                if isinstance(ts, datetime):
                    ts_txt = ts.isoformat()
                elif ts is None:
                    ts_txt = "sin SourceTimestamp"
                else:
                    ts_txt = str(ts)

                print(
                    f"Local -> pulsador={int(estado_local)} "
                    f"rampa={valor_rampa_local:5d} | "
                    f"Recibido <- pulsador={int(manejador.estado_servidor)} "
                    f"rampa={manejador.rampa_servidor:5d} | "
                    f"SourceTimestamp={ts_txt}"
                )

                ultimo_log = ahora

            duracion = time.monotonic() - ciclo_inicio
            await asyncio.sleep(
                max(0.0, INTERVALO_ESCRITURA - duracion)
            )

    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

        print("Cliente desconectado.")


async def main():
    while True:
        try:
            await ejecutar_sesion()

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            # Si se pierde Ethernet, se mantiene el último estado
            # visible en los LEDs y se intenta reconectar.
            print(
                f"[ERROR DE COMUNICACIÓN] "
                f"{type(exc).__name__}: {exc}"
            )
            print(
                f"Reintentando en "
                f"{INTERVALO_RECONEXION:.0f} s..."
            )

            await asyncio.sleep(
                INTERVALO_RECONEXION
            )


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print("\nCliente detenido por el usuario.")

    finally:
        pulsador.close()
        led_digital.close()
        led_pwm.close()
