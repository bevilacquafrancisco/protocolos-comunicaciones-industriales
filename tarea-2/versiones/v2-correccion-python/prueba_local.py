#!/usr/bin/env python3
"""
prueba_local.py
Autores: Bevilacqua Francisco, Peralta Agustina
Fecha de creacion: 2026-10-20
Version: 1.0

Descripcion general
-------------------
Banco de pruebas en la PC, SIN las Raspberry Pi: GPIO simulado con la
MockFactory de gpiozero, servidor y clientes REALES (procesos separados)
sobre 127.0.0.1. Verifica lo que se puede verificar sin hardware antes de ir
al laboratorio. No reemplaza las mediciones de banco.

Que verifica
------------
1. Senales: sierra, triangular, escala 0-255 y gamma.
2. Pulsador por eventos: el flanco genera la linea LATENCIA y el aviso.
3. Servidor: 3 endpoints, modelo (ns=1, NodeIds, tipos, AccessLevel,
   EURange), rampa de 4 s, StatusCodes de escritura, usuarios y roles.
4. Certificados: rechazo de uno desconocido, carpeta rechazados/, confianza
   y conexion en Sign y SignAndEncrypt.
5. Clientes Modo A y Modo B de punta a punta, con el registro en consola.

Uso
---
    python prueba_local.py

Usa una carpeta temporal para los certificados (no toca ./pki). Sale con
codigo 0 si todo pasa y 1 si algo falla.

Dependencias externas
---------------------
asyncua 2.1.0, gpiozero 2.0.1 (con la fabrica simulada).
"""

import asyncio
import hashlib
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("GPIOZERO_PIN_FACTORY", "mock")
os.environ.setdefault("GPIOZERO_MOCK_PIN_CLASS", "mockpwmpin")

from asyncua import Client, ua  # noqa: E402
from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256  # noqa: E402

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import comun  # noqa: E402

URL = "opc.tcp://127.0.0.1:4840"
USUARIO = "operador"
CLAVE = secrets.token_urlsafe(16)     # clave de prueba, distinta en cada corrida
fallos = 0


def check(condicion, texto):
    """Registra una verificacion."""
    global fallos
    print(("  OK    " if condicion else "  FALLA ") + texto, flush=True)
    if not condicion:
        fallos += 1


def hash_de(clave):
    """Mismo formato que generar_hash.py (sin pedir la clave por teclado)."""
    sal = secrets.token_bytes(16)
    resumen = hashlib.scrypt(clave.encode(), salt=sal, n=2 ** 17, r=8, p=1, maxmem=256 * 1024 * 1024)
    return f"scrypt:{2 ** 17}:8:1:{sal.hex()}:{resumen.hex()}"


def lanzar(argumentos, entorno_extra=None):
    """Arranca un programa del trabajo como proceso aparte; salida a un archivo."""
    entorno = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", **(entorno_extra or {}))
    salida = tempfile.NamedTemporaryFile("w+", suffix=".log", delete=False, encoding="utf-8")
    proceso = subprocess.Popen([sys.executable, *argumentos], cwd=AQUI, env=entorno,
                               stdout=salida, stderr=subprocess.STDOUT)
    return proceso, Path(salida.name)


def detener(proceso):
    proceso.terminate()
    try:
        proceso.wait(5)
    except subprocess.TimeoutExpired:
        proceso.kill()


# =============================================================================
# 1-2. Senales y pulsador
# =============================================================================

def probar_senales():
    print("1. Senales")
    check(comun.rampa_diente_sierra(0) == 0, "sierra(0 s) = 0")
    check(comun.rampa_diente_sierra(2.0) == 32768, "sierra(2 s) = 32768 (mitad del periodo)")
    check(comun.rampa_diente_sierra(3.999) >= 65000, "sierra(3,999 s) cerca del maximo")
    check(comun.rampa_diente_sierra(4.0) == 0, "sierra(4 s) vuelve a 0")
    check(comun.rampa_triangular(4.0) == 65535, "triangular(4 s) = 65535")
    check(comun.rampa_triangular(8.0) == 0 and comun.rampa_triangular(2.0) == comun.rampa_triangular(6.0),
          "triangular simetrica, vuelve a 0 a los 8 s")
    check(comun.escalar_a_pwm(0) == 0 and comun.escalar_a_pwm(65535) == 255, "escala 0..65535 -> 0..255")
    check(comun.escalar_a_pwm(32768, gamma=True) == 55, "gamma 2,2: mitad de rampa -> 55/255")
    check(comun.escalar_a_pwm(70000) == 255, "valor fuera de rango saturado")


async def probar_pulsador():
    print("2. Pulsador por eventos (GPIO simulado)")
    from gpiozero import Device
    pulsador = comun.Pulsador(asyncio.get_running_loop())
    pin = Device.pin_factory.pin(comun.PIN_PULSADOR)
    pin.drive_high()
    await asyncio.wait_for(pulsador.cambio.wait(), 1.0)
    check(pulsador.presionado, "flanco ascendente -> evento y estado presionado")
    pulsador.cambio.clear()
    await asyncio.sleep(0.1)
    pin.drive_low()
    await asyncio.wait_for(pulsador.cambio.wait(), 1.0)
    check(not pulsador.presionado, "flanco descendente -> evento")
    pulsador.cerrar()


# =============================================================================
# 3-4. Servidor, seguridad y certificados
# =============================================================================

async def conectar(usuario=None, clave=None, modo=None, pki=None):
    client = Client(URL, timeout=4)
    client.application_uri = comun.URI_CLIENTE
    if modo is not None:
        await client.set_security(
            SecurityPolicyBasic256Sha256, certificate=str(pki / "own" / "cliente_cert.der"),
            private_key=str(pki / "own" / "cliente_key.pem"),
            server_certificate=str(pki / "servidor_cert.der"), mode=modo)
    if usuario:
        client.set_user(usuario)
        client.set_password(clave)
    await client.connect()
    return client


async def codigo_de(corrutina):
    """Retorna el nombre del StatusCode de una operacion, o 'Good'."""
    try:
        await corrutina
        return "Good"
    except ua.UaStatusCodeError as exc:
        return ua.StatusCode(exc.code).name


async def probar_servidor(pki_servidor, pki_cliente):
    print("3. Servidor: endpoints, modelo y rampa")
    anonimo = await conectar()
    try:
        endpoints = await anonimo.get_endpoints()
        modos = sorted({(e.SecurityPolicyUri.split("#")[-1], e.SecurityMode.name) for e in endpoints})
        check(modos == [("Basic256Sha256", "Sign"), ("Basic256Sha256", "SignAndEncrypt"), ("None", "None_")],
              f"tres endpoints: {modos}")
        check(await anonimo.get_namespace_index(comun.NAMESPACE_URI) == 1, "urn:unraf:pdci:t2 en ns=1")

        esperado = {comun.NODE_ESTADO_SERVIDOR: (ua.ObjectIds.Boolean, 1),
                    comun.NODE_RAMPA_SERVIDOR: (ua.ObjectIds.UInt16, 1),
                    comun.NODE_ESTADO_CLIENTE: (ua.ObjectIds.Boolean, 3),
                    comun.NODE_RAMPA_CLIENTE: (ua.ObjectIds.UInt16, 3)}
        for texto, (tipo, acceso) in esperado.items():
            nodo = anonimo.get_node(texto)
            dt = await nodo.read_data_type()
            al = (await nodo.read_attribute(ua.AttributeIds.AccessLevel)).Value.Value
            check(dt.Identifier == tipo and al == acceso, f"{texto}: DataType i={dt.Identifier}, AccessLevel={al}")

        for texto in (comun.NODE_RAMPA_SERVIDOR, comun.NODE_RAMPA_CLIENTE):
            eurange = await anonimo.get_node(texto).get_child("0:EURange")
            rango = await eurange.read_value()
            check((rango.Low, rango.High) == (0.0, 65535.0), f"EURange de {texto}: {rango.Low}..{rango.High}")

        rampa = anonimo.get_node(comun.NODE_RAMPA_SERVIDOR)
        muestras = []
        for _ in range(30):
            dv = await rampa.read_data_value()
            muestras.append((time.monotonic(), dv.Value.Value))
            await asyncio.sleep(0.05)
        caidas = [i for i in range(1, len(muestras)) if muestras[i][1] < muestras[i - 1][1]]
        subidas = [b[1] - a[1] for a, b in zip(muestras, muestras[1:]) if b[1] > a[1]]
        pendiente = sum(subidas) / sum(b[0] - a[0] for a, b in zip(muestras, muestras[1:]) if b[1] > a[1])
        check(abs(pendiente - 65536 / 4) / (65536 / 4) < 0.15,
              f"Servidor.Rampa sube {pendiente:.0f}/s (esperado 16384/s = periodo 4 s)")
        check(len(caidas) <= 1, "Servidor.Rampa es diente de sierra (a lo sumo una vuelta a 0 en 1,5 s)")
        check(dv.SourceTimestamp is not None and dv.ServerTimestamp is not None, "SourceTimestamp y ServerTimestamp")

        print("   Escrituras y roles")
        nodo_rampa_cli = anonimo.get_node(comun.NODE_RAMPA_CLIENTE)
        check(await codigo_de(nodo_rampa_cli.write_value(ua.Variant(1, ua.VariantType.UInt16)))
              == "BadUserAccessDenied", "anonimo NO puede escribir Cliente.Rampa (BadUserAccessDenied)")
        check(await codigo_de(rampa.read_value()) == "Good", "anonimo puede leer")
    finally:
        await anonimo.disconnect()

    operador = await conectar(USUARIO, CLAVE)
    try:
        nodo_rampa_cli = operador.get_node(comun.NODE_RAMPA_CLIENTE)
        dv = ua.DataValue(ua.Variant(12345, ua.VariantType.UInt16), SourceTimestamp=comun.ahora_utc())
        check(await codigo_de(nodo_rampa_cli.write_value(dv)) == "Good", "operador escribe Cliente.Rampa = 12345")
        leido = await nodo_rampa_cli.read_data_value()
        check(leido.Value.Value == 12345 and leido.SourceTimestamp is not None,
              "el valor y el SourceTimestamp escritos quedan en el servidor")
        check(await codigo_de(operador.get_node(comun.NODE_ESTADO_CLIENTE).write_value(
            ua.Variant(True, ua.VariantType.Boolean))) == "Good", "operador escribe Cliente.EstadoPulsador = true")
        codigo = await codigo_de(operador.get_node(comun.NODE_RAMPA_SERVIDOR).write_value(
            ua.Variant(1, ua.VariantType.UInt16)))
        check(codigo == "BadUserAccessDenied", f"escribir Servidor.Rampa (solo lectura) -> {codigo}")
        codigo = await codigo_de(nodo_rampa_cli.write_value(ua.Variant(1.5, ua.VariantType.Double)))
        check(codigo == "BadTypeMismatch", f"tipo incorrecto en Cliente.Rampa -> {codigo}")
    finally:
        await operador.disconnect()

    codigo = await codigo_de(conectar(USUARIO, CLAVE + "x"))
    check(codigo in ("BadUserAccessDenied", "BadIdentityTokenRejected"), f"clave incorrecta -> {codigo}")
    codigo = await codigo_de(conectar("intruso", CLAVE))
    check(codigo in ("BadUserAccessDenied", "BadIdentityTokenRejected"), f"usuario inexistente -> {codigo}")

    print("4. Certificados y lista de confianza")
    shutil.copy(pki_servidor / "own" / "servidor_cert.der", pki_cliente / "servidor_cert.der")
    codigo = await codigo_de(conectar(USUARIO, CLAVE, ua.MessageSecurityMode.Sign, pki_cliente))
    check(codigo == "BadCertificateUntrusted", f"certificado de cliente desconocido -> {codigo}")
    rechazados = list((pki_servidor / "rechazados").glob("*.der"))
    check(len(rechazados) == 1, "el certificado rechazado queda en pki/rechazados/")
    shutil.move(str(rechazados[0]), pki_servidor / "trusted" / "cliente_cert.der")
    for modo in (ua.MessageSecurityMode.Sign, ua.MessageSecurityMode.SignAndEncrypt):
        try:
            client = await conectar(USUARIO, CLAVE, modo, pki_cliente)
            codigo = await codigo_de(client.get_node(comun.NODE_RAMPA_CLIENTE).write_value(
                ua.Variant(7, ua.VariantType.UInt16)))
            await client.disconnect()
        except ua.UaStatusCodeError as exc:
            codigo = ua.StatusCode(exc.code).name
        check(codigo == "Good", f"confiado -> conecta y escribe en {modo.name}")


# =============================================================================
# 5. Clientes de punta a punta
# =============================================================================

def probar_clientes(pki_cliente):
    print("5. Clientes de punta a punta (4 s cada uno)")
    credenciales = {"OPCUA_CLIENTE_USUARIO": USUARIO, "OPCUA_CLIENTE_CLAVE": CLAVE}
    casos = [("cliente.py", "None"), ("cliente_suscripcion.py", "None"),
             ("cliente_suscripcion.py", "SignAndEncrypt")]
    for programa, seguridad in casos:
        proceso, registro = lanzar([programa, "--url", URL, "--pki", str(pki_cliente),
                                    "--seguridad", seguridad], credenciales)
        time.sleep(4)
        detener(proceso)
        texto = registro.read_text(encoding="utf-8")
        lineas = [lin for lin in texto.splitlines() if "[C6]" in lin]
        recibidas = {lin.split("recibida Servidor.Rampa=")[1].split()[0] for lin in lineas}
        check("Sesion activa" in texto and len(recibidas) >= 3,
              f"{programa} {seguridad}: conecta y recibe la rampa ({len(recibidas)} valores distintos)")
        check(len(lineas) >= 3 and all("sin Source" not in lin and "SIN CONEXION" not in lin for lin in lineas[-3:]),
              f"{programa}: consola con generada, recibida y SourceTimestamp")
        check("rechazado" not in texto and "Traceback" not in texto, f"{programa}: sin escrituras rechazadas ni errores")
        if "suscripcion" in programa:
            check("MaxKeepAliveCount=10" in texto and "LifetimeCount=300" in texto,
                  "suscripcion revisada: KeepAlive 10, Lifetime 300")

    proceso, registro = lanzar(["cliente.py", "--url", URL, "--pki", str(pki_cliente), "--anonimo"], credenciales)
    time.sleep(3)
    detener(proceso)
    texto = registro.read_text(encoding="utf-8")
    check("Write Cliente.Rampa rechazado: StatusCode=BadUserAccessDenied" in texto and texto.count("[C1] Sesion activa") == 1,
          "cliente anonimo: Write rechazado, informado una vez, la sesion sigue")


def main():
    probar_senales()
    asyncio.run(probar_pulsador())

    carpeta = Path(tempfile.mkdtemp(prefix="pdci_t2_"))
    pki_servidor, pki_cliente = carpeta / "pki_rpi1", carpeta / "pki_rpi2"
    for rol, pki in (("servidor", pki_servidor), ("cliente", pki_cliente)):
        subprocess.run([sys.executable, "generar_certificados.py", rol, "--pki", str(pki)],
                       cwd=AQUI, check=True, capture_output=True)

    servidor, registro_servidor = lanzar(["servidor.py", "--pki", str(pki_servidor)],
                                         {"OPCUA_CLAVE_HASH": hash_de(CLAVE), "OPCUA_USUARIO": USUARIO})
    try:
        time.sleep(4)
        asyncio.run(probar_servidor(pki_servidor, pki_cliente))
        probar_clientes(pki_cliente)
    finally:
        detener(servidor)
        texto = registro_servidor.read_text(encoding="utf-8")
        lineas = [lin for lin in texto.splitlines() if "[S7]" in lin]
        check(any("recibida Cliente.Rampa=" in lin and "sin Source" not in lin for lin in lineas),
              "servidor: consola con la rampa recibida y su SourceTimestamp")
        check(CLAVE not in texto, "[SEC] la clave no aparece en el registro del servidor")
        check("Traceback" not in texto, "servidor sin excepciones")
        if fallos:
            print("\n--- registro del servidor (ultimas 40 lineas) ---")
            print("\n".join(texto.splitlines()[-40:]))
        shutil.rmtree(carpeta, ignore_errors=True)

    print(f"\n{'TODO OK' if fallos == 0 else f'{fallos} FALLA(S)'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
