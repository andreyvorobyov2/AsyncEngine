
# import debugpy
# try:
#     # Открываем порт 5678 для подключения отладчика
#     debugpy.configure(python=r"C:\Users\andrey\AppData\Local\Python\pythoncore-3.14-64\python.exe")
#     debugpy.listen(("127.0.0.1", 5678))
#     print("Ожидание подключения отладчика...")
#     debugpy.wait_for_client() # Скрипт ЗАМРЕТ тут, пока вы не подключитесь из VS Code
# except Exception as e:
#     pass

import logging
import asyncio
import importlib
import json
import random
from typing import Callable, Optional, Dict

# Настройка логирования для отладки
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

_cpp_callback: Optional[Callable[[str, str], None]] = None
_loop: Optional[asyncio.AbstractEventLoop] = None
_active_plugins: Dict[str, asyncio.Task] = {}

# Хранилище очередей для отправки команд ИЗ 1С В Плагины
# Ключ: task_id, Значение: asyncio.Queue
_plugin_queues: Dict[str, asyncio.Queue] = {}


async def _keep_alive() -> None:
    """Удерживает event loop активным (заглушка)."""
    while True:
        await asyncio.sleep(3600)


async def _self_test_task(task_id: int, delay: float) -> None:
    """ Вспомогательная корутина для тестирования асинхронного движка."""
    global _cpp_callback
    try:
        await asyncio.sleep(delay)
        result_data = f"Task {task_id} completed after {delay}s. Random result: {random.randint(100, 999)}"
        if _cpp_callback:
            _cpp_callback('SelfTest', result_data)
    except asyncio.CancelledError:
        pass 


# --- Внешний интерфейс (API для вызова из C++) ---

def start_async_engine(callback_func: Callable[[str], None]) -> None:
    """
    Инициализирует и запускает цикл событий (Event Loop) Python.
    Вызывается внутри изолированного C++ потока внешней компоненты.
    """
    global _cpp_callback, _loop
    _cpp_callback = callback_func
    
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    try:
        _loop.run_until_complete(_keep_alive())
    except asyncio.CancelledError:
        # Перехватываем штатную отмену задач при остановке
        logging.info("Главная задача вечного цикла была отменена.")
    except Exception as e:
        logging.error(f"Критическая ошибка в работе Event Loop: {e}")
    finally:
        # Корректно закрываем сам loop после остановки всех задач
        _loop.close()
        logging.info("Ресурсы Event Loop успешно освобождены.")


def stop_async_engine() -> None:
    """Останавливает все активные задачи и завершает работу Event Loop."""
    global _loop
    # Проверяем наличие loop-а (он может быть не запущен, но уже создан)
    if _loop:
        # Отменяем все запущенные таски
        for task in asyncio.all_tasks(_loop):
            task.cancel()
        
        # Передаем сигнал остановки цикла в потокобезопасном режиме
        _loop.call_soon_threadsafe(_loop.stop)
        logging.info("Сигнал остановки отправлен в Event Loop.")


def self_test() -> None:
    """Проводит тестирование асинхронного движка."""
    global _loop
    if _loop:
        asyncio.run_coroutine_threadsafe(_self_test_task(1, 2.0), _loop)
        asyncio.run_coroutine_threadsafe(_self_test_task(2, 5.0), _loop)
        asyncio.run_coroutine_threadsafe(_self_test_task(3, 1.0), _loop)


def run_plugin(plugin_name: str, task_id: str, params_json: str) -> None:
    """Динамически загружает плагин и инициализирует."""
    global _loop, _cpp_callback
    if not _loop:
        logging.error("Event loop is not running")
        return

    async def _plugin_wrapper():
        # Создаем индивидуальную очередь для этого экземпляра плагина
        inbound_queue = asyncio.Queue()
        _plugin_queues[task_id] = inbound_queue

        try:
            module = importlib.import_module(f"plugins.{plugin_name}")
            
            def plugin_callback(event_type: str, data_str: str):
                if _cpp_callback:
                    _cpp_callback(f"{plugin_name}:{event_type}", json.dumps({"task_id": task_id, "payload": data_str}))

            params = json.loads(params_json) if params_json else {}
            
            # Передаем inbound_queue третьим параметром в плагин!
            await module.main(params, plugin_callback, inbound_queue)
            
        except Exception as e:
            logging.error(f"Error executing plugin {plugin_name}: {e}")
            if _cpp_callback:
                _cpp_callback(f"{plugin_name}:Error", json.dumps({"task_id": task_id, "error": str(e)}))
        finally:
            # Очищаем ресурсы при завершении корутины плагина
            _plugin_queues.pop(task_id, None)
            _active_plugins.pop(task_id, None)

    task = asyncio.run_coroutine_threadsafe(_plugin_wrapper(), _loop)
    _active_plugins[task_id] = task


def send_to_plugin(task_id: str, command_json: str) -> None:
    """
    Новый метод для C++.
    Позволяет отправить команду/сообщение в уже работающий плагин по task_id.
    """
    global _loop
    if not _loop:
        return
        
    if task_id in _plugin_queues:
        # Безопасно помещаем команду в очередь плагина внутри Event Loop
        _loop.call_soon_threadsafe(_plugin_queues[task_id].put_nowait, command_json)
    else:
        logging.warning(f"Plugin task {task_id} not found or already closed.")
