import asyncio
import json
import logging
from aiohttp import web
import socketio

async def main(params: dict, callback: callable, inbound_queue: asyncio.Queue):
    host = params.get("host", "0.0.0.0")
    port = params.get("port", 9000)
    
    sio = socketio.AsyncServer(async_mode='aiohttp', cors_allowed_origins='*')
    app = web.Application()
    sio.attach(app)

    runner = None
    running = True

    # Хранилище пользователей: { sid: "Имя Пользователя" }
    connected_users = {}

    async def broadcast_user_list():
        """Вспомогательная функция для рассылки актуального списка пользователей всем"""
        user_list = [{"sid": sid, "name": name} for sid, name in connected_users.items()]
        await sio.emit("user_list_updated", user_list)
        callback("UserListUpdated", json.dumps(user_list, ensure_ascii=False))

    # --- Обработчики событий Socket.IO ---

    @sio.event
    async def connect(sid, environ, auth=None):
        # Извлекаем имя из параметров подключения auth (например, {"name": "Иван"})
        # Если имя не передано, используем часть sid для уникальности
        client_name = "Аноним"
        if auth and isinstance(auth, dict):
            client_name = auth.get("name", f"User_{sid[:4]}")
        else:
            # На случай, если auth передан строкой или через query params
            query_params = environ.get("aiohttp.request").query if environ.get("aiohttp.request") else {}
            client_name = query_params.get("name", f"User_{sid[:4]}")

        connected_users[sid] = client_name
        logging.info(f"Client connected: {client_name} ({sid})")
        
        # Оповещаем 1С
        callback("ClientConnected", json.dumps({"sid": sid, "name": client_name}, ensure_ascii=False))
        
        # Рассылаем всем новый список пользователей
        await broadcast_user_list()

    @sio.event
    async def disconnect(sid):
        client_name = connected_users.pop(sid, "Неизвестный клиент")
        logging.info(f"Client disconnected: {client_name} ({sid})")
        
        # Оповещаем 1С
        callback("ClientDisconnected", json.dumps({"sid": sid, "name": client_name}, ensure_ascii=False))
        
        # Рассылаем обновленный список оставшимся клиентам
        await broadcast_user_list()

    @sio.event
    async def message_from_client(sid, data):
        """Обычное сообщение от клиента (публичное или личное)"""
        logging.info(f"Received from {sid}: {data}")
        event_data = {"from_sid": sid, "from_name": connected_users.get(sid, "Unknown"), "data": data}
        callback("MessageReceived", json.dumps(event_data, ensure_ascii=False))

    # --- Асинхронные задачи ---

    async def run_web_server():
        nonlocal runner, running
        try:
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host, port)
            await site.start()
            callback("ServerStarted", f"SocketIO Server running on {host}:{port}")
            
            while running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            callback("Error", f"Server error: {str(e)}")
        finally:
            running = False

    async def read_from_1c():
        """Обработка команд из 1С"""
        nonlocal running
        try:
            while running:
                command_json_str = await inbound_queue.get()
                
                try:
                    command_data = json.loads(command_json_str)
                except json.JSONDecodeError:
                    callback("Error", f"Invalid JSON command: {command_json_str}")
                    inbound_queue.task_done()
                    continue
                
                if not isinstance(command_data, dict):
                    callback("Error", f"Command is not a JSON object: {command_json_str}")
                    inbound_queue.task_done()
                    continue

                action = command_data.get("action")
                payload = command_data.get("payload", {})

                if not isinstance(payload, dict):
                    payload = {}

                if action == "broadcast":
                    # Отправка ВСЕМ
                    event_name = payload.get("event", "message_from_server")
                    message_data = payload.get("data", "")
                    await sio.emit(event_name, message_data)
                    callback("BroadcastSent", f"Sent event '{event_name}' to all.")
                    
                elif action == "send_to_client":
                    # Личное сообщение конкретному клиенту по его sid
                    sid = payload.get("sid")
                    event_name = payload.get("event", "private_message")
                    message_data = payload.get("data", "")
                    if sid in connected_users:
                        await sio.emit(event_name, {"from": "Server/1C", "data": message_data}, to=sid)
                        callback("MessageSent", f"Sent private to sid {sid}")
                    else:
                        callback("Error", f"User with sid {sid} not found")
                        
                elif action == "get_users":
                    # Запрос списка пользователей со стороны 1С
                    user_list = [{"sid": s, "name": n} for s, n in connected_users.items()]
                    callback("UserList", json.dumps(user_list, ensure_ascii=False))

                elif action == "stop":
                    callback("ServerStopped", "Shutdown requested by 1C.")
                    break
                    
                inbound_queue.task_done()
        except asyncio.CancelledError:
            pass
        finally:
            running = False

    try:
        await asyncio.gather(run_web_server(), read_from_1c(), return_exceptions=True)
    finally:
        if runner:
            await runner.cleanup()
        callback("ServerStopped", "SocketIO Server stopped completely.")
