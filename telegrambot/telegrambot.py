from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import logging, os, json
import aiomysql
import matplotlib.pyplot as plt
from io import BytesIO
import paho.mqtt.publish as publish

logging.basicConfig(format='%(asctime)s - TelegramBot - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.environ["TB_TOKEN"]

# Configuracion MQTT
MQTT_HOST = "mosquitto"
MQTT_PORT = 1883
TOPICO_BASE = "pibeschorros"


async def publicar(subtopico, valor):
    """Publica un mensaje en el broker. El payload siempre es {"msg": valor}."""
    payload = json.dumps({"msg": valor})
    topico = f"{TOPICO_BASE}/{subtopico}"
    try:
        publish.single(
            topic=topico,
            payload=payload,
            hostname=MQTT_HOST,
            port=MQTT_PORT,
            auth={"username": os.environ["MQTT_USR"], "password": os.environ["MQTT_PASS"]}
        )
        logging.info(f"Publicado {topico}: {payload}")
        return True
    except Exception as e:
        logging.error(f"Error al publicar en {topico}: {e}")
        return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombre = update.message.from_user.first_name or ""
    kb = [["temperatura"], ["humedad"], ["gráfico temperatura"], ["gráfico humedad"], ["Destello"]]
    await update.message.reply_text(
        f"Bienvenido al Bot {nombre}",
        reply_markup=ReplyKeyboardMarkup(kb)
    )


async def acercade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Este bot fue creado para el curso de IoT FIO")


# --- ORDENES AL TERMOSTATO ---

async def rele(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0] == "@on":
        await publicar("rele", "on")
        await update.message.reply_text("Rele encendido")
    elif context.args and context.args[0] == "@off":
        await publicar("rele", "off")
        await update.message.reply_text("Rele apagado")
    else:
        await update.message.reply_text("Use /rele @on o /rele @off")


async def modo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0] == "@auto":
        await publicar("modo", "auto")
        await update.message.reply_text("Modo automatico")
    elif context.args and context.args[0] == "@manual":
        await publicar("modo", "manual")
        await update.message.reply_text("Modo manual")
    else:
        await update.message.reply_text("Use /modo @auto o /modo @manual")


async def editar_valor(update: Update, context: ContextTypes.DEFAULT_TYPE, subtopico):
    """Funcion compartida para setpoint y periodo. Espera: @editar <numero>."""
    if len(context.args) == 2 and context.args[0] == "@editar" and context.args[1].isdigit():
        valor = context.args[1]
        await publicar(subtopico, valor)
        await update.message.reply_text(f"{subtopico.capitalize()} actualizado a {valor}")
    else:
        await update.message.reply_text(f"Use /{subtopico} @editar <numero>. Ejemplo: /{subtopico} @editar 25")


async def setpoint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await editar_valor(update, context, "setpoint")


async def periodo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await editar_valor(update, context, "periodo")


async def destello(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await publicar("destello", "on")
    await update.message.reply_text("Senal enviada, la placa esta destellando")


# --- CONSULTAS A LA BASE DE DATOS ---

async def conectar_db():
    return await aiomysql.connect(
        host=os.environ["MARIADB_SERVER"], port=3306,
        user=os.environ["MARIADB_USER"],
        password=os.environ["MARIADB_USER_PASS"],
        db=os.environ["MARIADB_DB"]
    )


async def medicion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    variable = update.message.text
    unidad = "ºC" if variable == "temperatura" else "%"
    conn = await conectar_db()
    async with conn.cursor() as cur:
        await cur.execute(f"SELECT timestamp, {variable} FROM mediciones ORDER BY timestamp DESC LIMIT 1")
        fecha, valor = await cur.fetchone()
    conn.close()
    await update.message.reply_text(
        "La ultima {} es de {} {},\nregistrada a las {:%H:%M:%S %d/%m/%Y}"
        .format(variable, str(valor).replace(".", ","), unidad, fecha)
    )


async def graficos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    variable = update.message.text.split()[1]
    conn = await conectar_db()
    async with conn.cursor() as cur:
        await cur.execute(
            f"SELECT timestamp, {variable} FROM mediciones "
            f"WHERE id mod 2 = 0 AND timestamp >= NOW() - INTERVAL 1 DAY ORDER BY timestamp"
        )
        filas = await cur.fetchall()
    conn.close()

    fechas, valores = zip(*filas)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(fechas, valores)
    ax.grid(True)
    ax.set_title(update.message.text)
    ax.set_xlabel("fecha")
    ax.set_ylabel(variable)

    buffer = BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png")
    buffer.seek(0)
    await update.message.reply_photo(photo=buffer)


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("acercade", acercade))
    app.add_handler(CommandHandler("rele", rele))
    app.add_handler(CommandHandler("modo", modo))
    app.add_handler(CommandHandler("setpoint", setpoint))
    app.add_handler(CommandHandler("periodo", periodo))
    app.add_handler(MessageHandler(filters.Regex("^Destello$"), destello))
    app.add_handler(MessageHandler(filters.Regex("^(temperatura|humedad)$"), medicion))
    app.add_handler(MessageHandler(filters.Regex("^(gráfico temperatura|gráfico humedad)$"), graficos))

    app.run_polling()


if __name__ == "__main__":
    main()