import asyncio
import json

async def main(params: dict, callback: callable, inbound_queue: asyncio.Queue):
    host = params.get("host", "127.0.0.1")
    port = params.get("port", 8888)
    
    reader, writer = None, None
    try:
        # 1. Подключаемся к серверу
        reader, writer = await asyncio.open_connection(host, port)
        callback("Connected", f"Connected to {host}:{port}")
        
        # Флаг для контролируемого выхода
        running = True

        # Корутина чтения данных из сокета сервера
        async def read_from_socket():
            nonlocal running
            try:
                while running:
                    data = await reader.read(1024)
                    if not data:
                        # Сервер закрыл соединение с той стороны
                        callback("Disconnected", "Server closed connection.")
                        break
                    message = data.decode('utf-8').strip()
                    callback("MessageReceived", message)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                callback("Error", f"Socket read error: {str(e)}")
            finally:
                running = False

        # Корутина обработки команд от 1С из очереди
        async def read_from_1c():
            nonlocal running
            try:
                while running:
                    # Ждем команду из 1С
                    command_json_str = await inbound_queue.get()
                    command_data = json.loads(command_json_str)
                    
                    action = command_data.get("action")
                    payload = command_data.get("payload", "")

                    if action == "send":
                        # Отправка сообщения в сокет
                        if writer and not writer.is_closing():
                            writer.write(f"{payload}\n".encode('utf-8'))
                            await writer.drain()
                            callback("MessageSent", payload)
                            
                    elif action == "disconnect":
                        # Запрос на отключение от 1С
                        callback("Disconnected", "Disconnect requested by user.")
                        break
                        
                    inbound_queue.task_done()
            except asyncio.CancelledError:
                pass
            finally:
                running = False

        # Запускаем обе задачи параллельно и ждем, пока одна из них не завершится
        await asyncio.gather(read_from_socket(), read_from_1c(), return_exceptions=True)

    except Exception as e:
        callback("Error", f"Connection failed: {str(e)}")
        
    finally:
        # Гарантированное закрытие сокета при выходе из метода main
        if writer:
            writer.close()
            try:
                await writer.wait_closed()
            except:
                pass
        callback("System", "Chat client background task stopped completely.")
