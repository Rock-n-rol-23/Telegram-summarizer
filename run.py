#!/usr/bin/env python3
"""
Universal run.py entry point - фиксирует импорты и точки входа
"""
import os
import sys
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Главная функция для определения режима развертывания"""
    
    # Определение режима развертывания
    deployment_type = os.getenv('DEPLOYMENT_TYPE', 'cloudrun')
    
    # Авто-детекция окружения
    if os.getenv('K_SERVICE'):  # Google Cloud Run
        deployment_type = 'cloudrun'
    elif os.getenv('REPLIT_DEPLOYMENT'):  # Replit
        deployment_type = 'cloudrun' 
    
    logger.info(f"🚀 Запуск приложения в режиме: {deployment_type}")
    
    if deployment_type == 'background':
        logger.info("Импорт background_worker_optimized")
        from background_worker_optimized import main as worker_main
        import asyncio
        asyncio.run(worker_main())
        
    elif deployment_type == 'flask':
        logger.info("Импорт app (Flask)")
        import app
        # Flask запускается автоматически
        
    else:  # cloudrun по умолчанию
        logger.info("Импорт cloudrun_optimized")
        from cloudrun_optimized import main as cloudrun_main
        import asyncio
        asyncio.run(cloudrun_main())

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        sys.exit(1)