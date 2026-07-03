import asyncio
import json
import logging
from aiohttp import web
import socketio

async def main(params: dict, callback: callable, inbound_queue: asyncio.Queue):
    host = params.get("host", "0.0.0.0")
    port = params.get("port", 9000)
    
    # Создаем асинхронный сервер Socket.IO
    sio = socketio.AsyncServer(async_mode='aiohttp', cors_allowed_origins='*')
    app = web.Application()
    sio.attach(app)

    runner = None
    running = True

    # --- Обработчики событий Socket.IO ---

    @sio.event
    def connect(sid, environ):
        logging.info(f"Client connected: {sid}")
        callback("ClientConnected", json.dumps({"sid": sid}))

    @sio.event
    def disconnect(sid):
        logging.info(f"Client disconnected: {sid}")
        callback("ClientDisconnected", json.dumps({"sid": sid}))

    @sio.event
    async def message_from_client(sid, data):
        """Ловим кастомное событие от веб-клиентов и пересылаем в 1С"""
        logging.info(f"Received from {sid}: {data}")
        # Отправляем в 1С структуру: кто прислал и что прислал
        event_data = {"sid": sid, "data": data}
        callback("MessageReceived", json.dumps(event_data, ensure_ascii=False))

    # --- Асинхронные задачи ---

    async def run_web_server():
        """Задача запуска и работы веб-сервера"""
        nonlocal runner, running
        try:
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host, port)
            await site.start()
            callback("ServerStarted", f"SocketIO Server running on {host}:{port}")
            
            # Удерживаем задачу, пока сервер активен
            while running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            callback("Error", f"Server error: {str(e)}")
        finally:
            running = False

    async def read_from_1c():
        """Задача обработки входящих команд из 1С"""
        nonlocal running
        try:
            while running:
                command_json_str = await inbound_queue.get()
                command_data = json.loads(command_json_str)
                
                action = command_data.get("action")
                payload = command_data.get("payload", {})

                if action == "broadcast":
                    # Отправка сообщения ВСЕМ подключенным клиентам
                    event_name = payload.get("event", "message_from_server")
                    message_data = payload.get("data", "")
                    await sio.emit(event_name, message_data)
                    callback("BroadcastSent", f"Sent event '{event_name}' to all.")
                    
                elif action == "send_to_client":
                    # Отправка конкретному клиенту по его sid
                    sid = payload.get("sid")
                    event_name = payload.get("event", "message_from_server")
                    message_data = payload.get("data", "")
                    if sid:
                        await sio.emit(event_name, message_data, to=sid)
                        callback("MessageSent", f"Sent to {sid}")
                        
                elif action == "stop":
                    # Запрос на остановку сервера из 1С
                    callback("ServerStopping", "Shutdown requested by 1C.")
                    break
                    
                inbound_queue.task_done()
        except asyncio.cancelled_error:
            pass
        finally:
            running = False

    # Запускаем сервер и чтение команд параллельно
    try:
        await asyncio.gather(run_web_server(), read_from_1c(), return_exceptions=True)
    finally:
        # Гарантированная очистка ресурсов сервера при выходе
        if runner:
            await runner.cleanup()
        callback("ServerStopped", "SocketIO Server stopped completely.")
