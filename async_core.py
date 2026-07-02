
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
from typing import Callable, Optional

# Настройка логирования для отладки
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

_cpp_callback: Optional[Callable[[str], None]] = None
_loop: Optional[asyncio.AbstractEventLoop] = None

async def _keep_alive() -> None:
    """Удерживает event loop активным (заглушка)."""
    while True:
        await asyncio.sleep(3600)

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
        logging.info("Главная задача вечного цикла была отменена (остановка двигателя).")
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