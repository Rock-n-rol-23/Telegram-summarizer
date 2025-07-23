#!/usr/bin/env python3
"""
main.py - основной entry point с авто-детекцией режима
Исправляет все проблемы с развертыванием согласно инструкции
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
    """Автоматическое определение режима развертывания"""
    
    # Проверка переменных окружения для автоопределения
    if os.getenv('DEPLOYMENT_TYPE') == 'background':
        deployment_mode = 'background'
    elif os.getenv('DEPLOYMENT_TYPE') == 'flask':
        deployment_mode = 'flask'
    elif os.getenv('K_SERVICE') or os.getenv('REPLIT_DEPLOYMENT'):
        deployment_mode = 'cloudrun'
    else:
        deployment_mode = 'cloudrun'  # По умолчанию
    
    logger.info(f"🚀 Автоопределение режима: {deployment_mode}")
    
    try:
        if deployment_mode == 'background':
            # Background Worker режим
            logger.info("Запуск в режиме Background Worker")
            from background_worker_optimized import main as bg_main
            import asyncio
            asyncio.run(bg_main())
            
        elif deployment_mode == 'flask':
            # Flask режим
            logger.info("Запуск в режиме Flask")
            import app
            # Flask app запускается автоматически
            
        else:
            # Cloud Run режим (по умолчанию)
            logger.info("Запуск в режиме Cloud Run")
            from cloudrun_optimized import main as cr_main
            import asyncio
            asyncio.run(cr_main())
            
    except ImportError as e:
        logger.error(f"Ошибка импорта: {e}")
        logger.info("Fallback к основному deploy.py")
        import deploy
        # deploy.py содержит fallback логику
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()