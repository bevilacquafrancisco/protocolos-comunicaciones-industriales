#!/usr/bin/env python3
"""
TP2 OPC UA - Raspberry Pi 2 (Cliente, modo polling)
UNRaf - Protocolos de Comunicaciones Industriales

GPIO propuestos:
- Pulsador: GPIO 17
- LED digital: GPIO 27
- LED PWM: GPIO 18

Red:
- Ethernet cliente: 192.168.10.2/24
- Servidor OPC UA: opc.tcp://192.168.10.1:4840

Este archivo implementa el Modo A pedido por la consigna:
Read periódico (polling) cada 100 ms.

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

INTERVALO_POLLING = 0.100   # 100 ms
INTERVALO_RECONEXION = 2.0  # segundos


def generar_rampa_triangular(t):
    """
    Rampa triangular 0..65535, periodo total 8 s:
    4 s de subida + 4 s de bajada.
    """
    fase = t % 8.0

    if fase < 4.0:
        return min(65535, int((fase / 4.0) * 65535))
    else:
        return max(0, int(((8.0 - fase) / 4.0) * 65535))


async def ejecutar_sesion():
    client = Client(url=URL_SERVIDOR)

    print(f"Conectando a {URL_SERVIDOR} ...")
    await client.connect()
    print("CLIENTE OPC UA CONECTADO")

    try:
        estado_servidor = client.get_node(NODE_ESTADO_SERVIDOR)
        rampa_servidor = client.get_node(NODE_RAMPA_SERVIDOR)
        estado_cliente = client.get_node(NODE_ESTADO_CLIENTE)
        rampa_cliente = client.get_node(NODE_RAMPA_CLIENTE)

        inicio_rampa = time.monotonic()
        estado_anterior = None
        ultimo_log = 0.0

        while True:
            ciclo_inicio = time.monotonic()

            # -----------------------------
            # GENERACIÓN LOCAL
            # -----------------------------
            estado_local = bool(pulsador.is_pressed)
            valor_rampa_local = generar_rampa_triangular(
                ciclo_inicio - inicio_rampa
            )

            # Escritura del pulsador solo cuando cambia.
            if estado_local != estado_anterior:
                await estado_cliente.write_value(
                    ua.Variant(estado_local, ua.VariantType.Boolean)
                )
                estado_anterior = estado_local

            # La consigna pide escribir Cliente.Rampa cada 100 ms.
            await rampa_cliente.write_value(
                ua.Variant(valor_rampa_local, ua.VariantType.UInt16)
            )

            # -----------------------------
            # MODO A: POLLING
            # -----------------------------
            data_estado = await estado_servidor.read_data_value()
            data_rampa = await rampa_servidor.read_data_value()

            estado_remoto = bool(data_estado.Value.Value)
            valor_rampa_remota = int(data_rampa.Value.Value)

            # Replicar datos recibidos en LEDs.
            if estado_remoto:
                led_digital.on()
            else:
                led_digital.off()

            led_pwm.value = max(
                0.0, min(1.0, valor_rampa_remota / 65535.0)
            )

            # SourceTimestamp de la rampa recibida.
            source_ts = data_rampa.SourceTimestamp
            if source_ts is None:
                source_ts_txt = "sin SourceTimestamp"
            elif isinstance(source_ts, datetime):
                source_ts_txt = source_ts.isoformat()
            else:
                source_ts_txt = str(source_ts)

            # Registro periódico en consola.
            ahora = time.monotonic()
            if ahora - ultimo_log >= 0.5:
                print(
                    f"Local -> pulsador={int(estado_local)} "
                    f"rampa={valor_rampa_local:5d} | "
                    f"Recibido <- pulsador={int(estado_remoto)} "
                    f"rampa={valor_rampa_remota:5d} | "
                    f"SourceTimestamp={source_ts_txt}"
                )
                ultimo_log = ahora

            # Mantener periodo aproximado de 100 ms.
            duracion = time.monotonic() - ciclo_inicio
            await asyncio.sleep(max(0.0, INTERVALO_POLLING - duracion))

    finally:
        await client.disconnect()
        print("Cliente desconectado.")


async def main():
    while True:
        try:
            await ejecutar_sesion()

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            # Ante pérdida del enlace, los LEDs quedan en el último estado,
            # tal como se observará en la prueba de desconexión.
            print(f"[ERROR DE COMUNICACIÓN] {type(exc).__name__}: {exc}")
            print(
                f"Reintentando conexión en {INTERVALO_RECONEXION:.0f} s..."
            )
            await asyncio.sleep(INTERVALO_RECONEXION)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCliente detenido por el usuario.")
    finally:
        pulsador.close()
        led_digital.close()
        led_pwm.close()
