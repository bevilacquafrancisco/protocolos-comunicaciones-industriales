#!/usr/bin/env python3
"""
TP2 OPC UA - Raspberry Pi 1 (Servidor)
UNRaf - Protocolos de Comunicaciones Industriales

GPIO propuestos:
- Pulsador: GPIO 17
- LED digital: GPIO 27
- LED PWM: GPIO 18

Red:
- Ethernet servidor: 192.168.10.1/24
- Endpoint OPC UA: opc.tcp://192.168.10.1:4840

Requiere:
    python3 -m pip install asyncua gpiozero
"""

import asyncio
import time
from asyncua import Server, ua
from gpiozero import Button, LED, PWMLED

# -----------------------------
# CONFIGURACIÓN GPIO
# -----------------------------
PIN_PULSADOR = 17
PIN_LED_DIGITAL = 27
PIN_LED_PWM = 18

# El pulsador se planteó con resistencia pull-down externa de 10 kΩ.
pulsador = Button(PIN_PULSADOR, pull_up=False, bounce_time=0.05)
led_digital = LED(PIN_LED_DIGITAL)
led_pwm = PWMLED(PIN_LED_PWM)

# -----------------------------
# CONFIGURACIÓN OPC UA
# -----------------------------
ENDPOINT = "opc.tcp://0.0.0.0:4840"
NAMESPACE_URI = "urn:unraf:pdci:t2"


async def agregar_eurange(variable, idx):
    """Agrega la propiedad EURange = 0..65535 a una variable."""
    rango = ua.Range()
    rango.Low = 0.0
    rango.High = 65535.0

    try:
        await variable.add_property(
            ua.NodeId(f"{variable.nodeid.Identifier}.EURange", idx),
            "EURange",
            ua.Variant(rango, ua.VariantType.ExtensionObject),
        )
    except Exception as exc:
        print(f"[ADVERTENCIA] No se pudo crear EURange automáticamente: {exc}")


async def main():
    server = Server()
    await server.init()
    server.set_endpoint(ENDPOINT)
    server.set_server_name("UNRaf TP2 - Servidor OPC UA")

    # Registrar namespace pedido por la consigna.
    idx = await server.register_namespace(NAMESPACE_URI)

    objects = server.nodes.objects

    # -----------------------------
    # MODELO DE INFORMACIÓN
    # -----------------------------
    objeto_servidor = await objects.add_object(
        ua.NodeId("Servidor", idx),
        ua.QualifiedName("Servidor", idx),
    )

    objeto_cliente = await objects.add_object(
        ua.NodeId("Cliente", idx),
        ua.QualifiedName("Cliente", idx),
    )

    estado_servidor = await objeto_servidor.add_variable(
        ua.NodeId("Servidor.EstadoPulsador", idx),
        ua.QualifiedName("EstadoPulsador", idx),
        ua.Variant(False, ua.VariantType.Boolean),
    )

    rampa_servidor = await objeto_servidor.add_variable(
        ua.NodeId("Servidor.Rampa", idx),
        ua.QualifiedName("Rampa", idx),
        ua.Variant(0, ua.VariantType.UInt16),
    )

    estado_cliente = await objeto_cliente.add_variable(
        ua.NodeId("Cliente.EstadoPulsador", idx),
        ua.QualifiedName("EstadoPulsador", idx),
        ua.Variant(False, ua.VariantType.Boolean),
    )

    rampa_cliente = await objeto_cliente.add_variable(
        ua.NodeId("Cliente.Rampa", idx),
        ua.QualifiedName("Rampa", idx),
        ua.Variant(0, ua.VariantType.UInt16),
    )

    # Solo las variables Cliente.* deben permitir escritura remota.
    await estado_cliente.set_writable()
    await rampa_cliente.set_writable()

    # Propiedad EURange exigida por la consigna.
    await agregar_eurange(rampa_servidor, idx)
    await agregar_eurange(rampa_cliente, idx)

    print("=" * 62)
    print("SERVIDOR OPC UA INICIADO")
    print("IP prevista: 192.168.10.1/24")
    print("Endpoint: opc.tcp://192.168.10.1:4840")
    print("Namespace:", NAMESPACE_URI)
    print("=" * 62)

    inicio_rampa = time.monotonic()
    ultimo_log = 0.0

    try:
        async with server:
            while True:
                ahora = time.monotonic()

                # -----------------------------
                # ENTRADAS LOCALES
                # -----------------------------
                estado_local = bool(pulsador.is_pressed)

                # Rampa diente de sierra 0..65535
                # Periodo total = 4 s
                fase = ((ahora - inicio_rampa) % 4.0) / 4.0
                valor_rampa_local = min(65535, int(fase * 65536))

                # Publicar valores locales.
                await estado_servidor.write_value(
                    ua.Variant(estado_local, ua.VariantType.Boolean)
                )
                await rampa_servidor.write_value(
                    ua.Variant(valor_rampa_local, ua.VariantType.UInt16)
                )

                # -----------------------------
                # DATOS ESCRITOS POR CLIENTE
                # -----------------------------
                estado_remoto = bool(await estado_cliente.read_value())
                valor_rampa_remota = int(await rampa_cliente.read_value())

                # LED digital refleja Cliente.EstadoPulsador
                if estado_remoto:
                    led_digital.on()
                else:
                    led_digital.off()

                # LED PWM refleja Cliente.Rampa escalada de 0..65535 a 0..1
                led_pwm.value = max(0.0, min(1.0, valor_rampa_remota / 65535.0))

                # Registro periódico en consola.
                if ahora - ultimo_log >= 0.5:
                    print(
                        f"Local -> pulsador={int(estado_local)} "
                        f"rampa={valor_rampa_local:5d} | "
                        f"Recibido <- pulsador={int(estado_remoto)} "
                        f"rampa={valor_rampa_remota:5d}"
                    )
                    ultimo_log = ahora

                # La consigna pide actualización de la rampa cada 50 ms.
                await asyncio.sleep(0.05)

    finally:
        led_digital.off()
        led_pwm.off()
        pulsador.close()
        led_digital.close()
        led_pwm.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServidor detenido por el usuario.")
