import asyncio
import json
import socketio

async def main(params: dict, callback: callable, inbound_queue: asyncio.Queue):
    host = params.get("host", "127.0.0.1")
    port = params.get("port", 9000) 
    url = f"http://{host}:{port}"
    
    # Создаем асинхронного Socket.IO клиента
    sio = socketio.AsyncClient()
    running = True

    # --- Обработчики событий Socket.IO ---
    
    @sio.event
    async def connect():
        callback("Connected", f"Successfully connected to Socket.IO server at {url}")

    @sio.event
    async def disconnect():
        callback("Disconnected", "Disconnected from Socket.IO server.")
        nonlocal running
        running = False

    @sio.event
    async def message_from_server(data):
        """Ловим броадкаст или персональные сообщения от сервера"""
        callback("MessageReceived", json.dumps(data, ensure_ascii=False))

    @sio.event
    async def connect_error(data):
        callback("Error", f"Connection failed: {data}")

    # --- Задача для обработки команд из 1С ---
    async def read_from_1c():
        nonlocal running
        try:
            while running and sio.connected:
                command_json_str = await inbound_queue.get()
                command_data = json.loads(command_json_str)
                
                action = command_data.get("action")
                payload = command_data.get("payload", "")

                if action == "send":
                    # Отправляем кастомное событие, которое ждет ваш сервер
                    # Структура payload должна соответствовать тому, что ждет сервер
                    await sio.emit("message_from_client", payload)
                    callback("MessageSent", json.dumps(payload, ensure_ascii=False))
                    
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
        # Подключаемся к Socket.IO серверу
        await sio.connect(url)
        
        # Запускаем задачу чтения из очереди 1С
        # Чтение из сокета Socket.IO берет на себя под капотом при connect()
        await read_from_1c()

    except Exception as e:
        callback("Error", f"SocketIO Client error: {str(e)}")
        
    finally:
        if sio.connected:
            await sio.disconnect()
        callback("System", "Chat client background task stopped completely.")