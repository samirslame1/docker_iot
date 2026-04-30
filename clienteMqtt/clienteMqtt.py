import asyncio
import os
import logging
import aiomqtt

# Filtro mínimo para inyectar el nombre de la corrutina (Task) en el logging para Python 3.11
class TaskFilter(logging.Filter):
    def filter(self, record):
        try:
            task = asyncio.current_task()
            record.taskName = task.get_name() if task else "Main"
        except RuntimeError:
            record.taskName = "Main"
        return True

# Configuración del logging usando el atributo %(taskName)s
logging.basicConfig(
    format='%(asctime)s - [%(taskName)s] - %(levelname)s - %(message)s',
    level=logging.INFO
)
for handler in logging.root.handlers:
    handler.addFilter(TaskFilter())

async def atender_topico(nombre_topico, queue):
    """Corrutina dedicada a atender un tópico específico."""
    while True:
        mensaje = await queue.get()
        payload = mensaje.payload.decode()
        logging.info(f"Mensaje recibido en {nombre_topico}: {payload}")

async def publicar_estado(client, topico_p, estado):
    """Corrutina que publica el estado del contador cada 5 segundos."""
    while True:
        await asyncio.sleep(5)
        await client.publish(topico_p, str(estado['contador']))
        logging.info(f"Contador publicado: {estado['contador']}")

async def incrementar_contador(estado):
    """Corrutina que incrementa el contador cada 3 segundos."""
    while True:
        await asyncio.sleep(3)
        estado['contador'] += 1
        logging.info(f"Contador incrementado a {estado['contador']}")

async def main():
    # 1. Obtener variables de entorno
    broker = os.environ.get("direccionbroker")
    topico_s = os.environ.get("topicoS")
    topico_s1 = os.environ.get("topicoS1")
    topico_p = os.environ.get("topicoP")

    # 2. Estado local (reemplaza el uso de variables globales)
    estado = {"contador": 0}
    
    # Colas para enrutar los mensajes a sus respectivas corrutinas
    queue_s = asyncio.Queue()
    queue_s1 = asyncio.Queue()

    # 3. Configuración MQTTS (Cifrado)
    tls_params = aiomqtt.TLSParameters()

    logging.info(f"Conectando a MQTTS Broker en {broker}...")

    # 4. Un solo objeto cliente
    async with aiomqtt.Client(hostname=broker, port=8883, tls_params=tls_params) as client:
        
        # 5. Crear e iniciar todas las corrutinas (tasks)
        asyncio.create_task(atender_topico(topico_s, queue_s), name="Task-Suscripcion1")
        asyncio.create_task(atender_topico(topico_s1, queue_s1), name="Task-Suscripcion2")
        asyncio.create_task(publicar_estado(client, topico_p, estado), name="Task-Publicador")
        asyncio.create_task(incrementar_contador(estado), name="Task-Incrementador")

        # 6. Suscribirse a los tópicos
        await client.subscribe(topico_s)
        await client.subscribe(topico_s1)

        # 7. Ciclo principal de recepción y enrutamiento
        async for mensaje in client.messages:
            if mensaje.topic.matches(topico_s):
                await queue_s.put(mensaje)
            elif mensaje.topic.matches(topico_s1):
                await queue_s1.put(mensaje)

if __name__ == "__main__":
    try:
        # Ejecución asincrónica principal
        asyncio.run(main())
    except KeyboardInterrupt:
        # Captura de excepción Ctrl-C
        print("\nmqtt final")