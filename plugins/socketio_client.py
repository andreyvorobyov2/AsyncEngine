import asyncio
import json
import socketio

async def main(params: dict, callback: callable, inbound_queue: asyncio.Queue):
    host = params.get("host", "127.0.0.1")
    port = params.get("port", 9000) 
    # Получаем имя текущего сеанса 1С из параметров
    client_name = params.get("name", "1C_Client_Instance")
    
    url = f"http://{host}:{port}"
    
    sio = socketio.AsyncClient()
    running = True

    # --- Обработчики событий Socket.IO ---
    
    @sio.event
    async def connect():
        callback("Connected", f"Connected as '{client_name}' to {url}")

    @sio.event
    async def disconnect():
        callback("Disconnected", "Disconnected from server.")
        nonlocal running
        running = False

    # Событие: сервер прислал обновленный список пользователей
    @sio.on("user_list_updated")
    async def on_user_list(data):
        # data придет в виде списка: [{"sid": "...", "name": "..."}, ...]
        callback("UserListUpdated", json.dumps(data, ensure_ascii=False))

    # Событие: личное сообщение для этого клиента
    @sio.on("private_message")
    async def on_private_message(data):
        callback("PrivateMessageReceived", json.dumps(data, ensure_ascii=False))

    # Событие: глобальный броадкаст
    @sio.on("message_from_server")
    async def on_broadcast(data):
        callback("BroadcastReceived", json.dumps(data, ensure_ascii=False))

    # Универсальный перехватчик на случай кастомных событий от 1С-сервера
    @sio.on('*')
    async def catch_all(event, data):
        if event not in ["user_list_updated", "private_message", "message_from_server"]:
            callback("CustomEventReceived", json.dumps({"event": event, "data": data}, ensure_ascii=False))

    @sio.event
    async def connect_error(data):
        callback("Error", f"Connection failed: {data}")

    # --- Задача для обработки команд из 1С ---
    async def read_from_1c():
        nonlocal running
        try:
            while running and sio.connected:
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
                payload = command_data.get("payload", "")

                #if not isinstance(payload, dict):
                #     # payload = {}

                if action == "send":
                    # Отправка публичного сообщения в чат
                    await sio.emit("message_from_client", payload)
                    callback("MessageSent", json.dumps(payload, ensure_ascii=False))
                    
                elif action == "send_private":
                    # 1С отправляет личку. Структура payload должна быть: {"to_sid": "...", "msg": "текст"}
                    # Используем встроенную в Socket.IO возможность слать на конкретный sid через сервер,
                    # либо сервер сам перенаправит, если мы вызовем кастомный эмит.
                    # Для простоты: отправляем серверу команду "private_from_client"
                    to_sid = payload.get("to_sid")
                    msg = payload.get("msg")
                    
                    # Отправляем сообщение на сервер, а сервер перенаправит получателю
                    await sio.emit("message_from_client", {"to_sid": to_sid, "text": msg})
                    callback("PrivateMessageSent", json.dumps(payload, ensure_ascii=False))
                    
                elif action == "disconnect":
                    callback("Disconnected", "Disconnect requested by user.")
                    await sio.disconnect()
                    break
                    
                inbound_queue.task_done()
        except asyncio.CancelledError:
            pass
        finally:
            running = False

    # --- Основной цикл запуска ---
    try:
        # Передаем имя клиента в auth-пакете при хэндшейке!
        await sio.connect(url, auth={"name": client_name})
        await read_from_1c()

    except Exception as e:
        callback("Error", f"SocketIO Client error: {str(e)}")
        
    finally:
        if sio.connected:
            await sio.disconnect()
        callback("System", "Chat client background task stopped completely.")

