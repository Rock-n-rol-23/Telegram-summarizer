import os
import tempfile
import logging
import aiofiles
import aiohttp
from typing import Dict, Any, Optional
import chardet
import re

# Импорты для работы с разными форматами файлов
try:
    import PyPDF2
    import pdfplumber
    HAS_PDF_SUPPORT = True
except ImportError:
    HAS_PDF_SUPPORT = False

try:
    from docx import Document
    HAS_DOCX_SUPPORT = True
except ImportError:
    HAS_DOCX_SUPPORT = False

try:
    import mammoth
    HAS_DOC_SUPPORT = True
except ImportError:
    HAS_DOC_SUPPORT = False

logger = logging.getLogger(__name__)

class FileProcessor:
    """Класс для обработки файлов и извлечения текста"""
    
    def __init__(self):
        self.supported_extensions = ['.pdf', '.docx', '.doc', '.txt']
        self.max_file_size = 20 * 1024 * 1024  # 20MB - лимит Telegram
        
    async def download_telegram_file(self, file_info: Dict[str, Any], file_name: str, file_size: int) -> Dict[str, Any]:
        """Скачивает файл от Telegram бота"""
        try:
            # Проверяем размер файла
            if file_size > self.max_file_size:
                return {
                    'success': False,
                    'error': 'Файл слишком большой (максимум 20MB)'
                }
            
            # Проверяем расширение файла
            file_extension = os.path.splitext(file_name.lower())[1]
            if file_extension not in self.supported_extensions:
                return {
                    'success': False,
                    'error': f'Неподдерживаемый формат файла. Поддерживаются: {", ".join(self.supported_extensions)}'
                }
            
            # Создаем временную директорию
            temp_dir = tempfile.mkdtemp()
            local_file_path = os.path.join(temp_dir, file_name)
            
            # Скачиваем файл
            async with aiohttp.ClientSession() as session:
                async with session.get(file_info['file_path']) as response:
                    if response.status == 200:
                        async with aiofiles.open(local_file_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                await f.write(chunk)
                    else:
                        return {
                            'success': False,
                            'error': f'Ошибка скачивания файла: HTTP {response.status}'
                        }
            
            return {
                'success': True,
                'file_path': local_file_path,
                'file_name': file_name,
                'file_size': file_size,
                'file_extension': file_extension,
                'temp_dir': temp_dir
            }
            
        except Exception as e:
            logger.error(f"Ошибка при скачивании файла: {e}")
            return {
                'success': False,
                'error': f'Ошибка при скачивании файла: {str(e)}'
            }
    
    def extract_text_from_pdf(self, file_path: str) -> Dict[str, Any]:
        """Извлекает текст из PDF файла"""
        if not HAS_PDF_SUPPORT:
            return {
                'success': False,
                'error': 'PDF библиотеки не установлены'
            }
        
        try:
            text = ""
            
            # Сначала пробуем pdfplumber (лучше для сложных PDF)
            try:
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n\n"
                            
                if text.strip():
                    return {
                        'success': True,
                        'text': text.strip(),
                        'method': 'pdfplumber'
                    }
            except Exception as e:
                logger.warning(f"pdfplumber не сработал: {e}")
            
            # Fallback на PyPDF2
            try:
                with open(file_path, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    
                    # Проверяем, зашифрован ли PDF
                    if reader.is_encrypted:
                        return {
                            'success': False,
                            'error': 'PDF файл защищен паролем'
                        }
                    
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n\n"
                            
                if text.strip():
                    return {
                        'success': True,
                        'text': text.strip(),
                        'method': 'PyPDF2'
                    }
                else:
                    return {
                        'success': False,
                        'error': 'PDF не содержит извлекаемого текста (возможно, только изображения)'
                    }
                    
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Ошибка чтения PDF: {str(e)}'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка обработки PDF: {str(e)}'
            }
    
    def extract_text_from_docx(self, file_path: str) -> Dict[str, Any]:
        """Извлекает текст из DOCX файла"""
        if not HAS_DOCX_SUPPORT:
            return {
                'success': False,
                'error': 'DOCX библиотека не установлена'
            }
        
        try:
            doc = Document(file_path)
            text = ""
            
            # Извлекаем текст из параграфов
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text += paragraph.text + "\n"
            
            # Извлекаем текст из таблиц
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text.strip():
                            text += cell.text + " "
                    text += "\n"
            
            if text.strip():
                return {
                    'success': True,
                    'text': text.strip(),
                    'method': 'python-docx'
                }
            else:
                return {
                    'success': False,
                    'error': 'DOCX файл не содержит текста'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка чтения DOCX: {str(e)}'
            }
    
    def extract_text_from_doc(self, file_path: str) -> Dict[str, Any]:
        """Извлекает текст из DOC файла (старый формат Word)"""
        if not HAS_DOC_SUPPORT:
            return {
                'success': False,
                'error': 'DOC библиотека не установлена'
            }
        
        try:
            # Пробуем mammoth для DOC файлов
            with open(file_path, "rb") as doc_file:
                result = mammoth.convert_to_html(doc_file)
                
                if result.value:
                    # Убираем HTML теги
                    text = re.sub('<[^<]+?>', '', result.value)
                    text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
                    
                    return {
                        'success': True,
                        'text': text.strip(),
                        'method': 'mammoth',
                        'warnings': result.messages
                    }
                else:
                    return {
                        'success': False,
                        'error': 'DOC файл не содержит извлекаемого текста'
                    }
                    
        except Exception as e:
            # Fallback - предлагаем конвертировать в DOCX
            return {
                'success': False,
                'error': f'Ошибка чтения DOC файла: {str(e)}. Попробуйте сохранить файл в формате DOCX'
            }
    
    def extract_text_from_txt(self, file_path: str) -> Dict[str, Any]:
        """Извлекает текст из TXT файла с автоопределением кодировки"""
        try:
            # Определяем кодировку файла
            with open(file_path, 'rb') as file:
                raw_data = file.read()
                encoding_result = chardet.detect(raw_data)
                encoding = encoding_result['encoding']
                
            if not encoding:
                encoding = 'utf-8'  # Fallback
            
            # Читаем файл с определенной кодировкой
            try:
                with open(file_path, 'r', encoding=encoding) as file:
                    text = file.read()
                    
                return {
                    'success': True,
                    'text': text.strip(),
                    'method': f'text file ({encoding})'
                }
                
            except UnicodeDecodeError:
                # Пробуем другие популярные кодировки
                encodings_to_try = ['utf-8', 'cp1251', 'cp866', 'iso-8859-1', 'latin-1']
                
                for enc in encodings_to_try:
                    try:
                        with open(file_path, 'r', encoding=enc) as file:
                            text = file.read()
                            
                        return {
                            'success': True,
                            'text': text.strip(),
                            'method': f'text file ({enc})'
                        }
                    except:
                        continue
                
                return {
                    'success': False,
                    'error': 'Не удалось определить кодировку текстового файла'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'Ошибка чтения TXT файла: {str(e)}'
            }
    
    def extract_text_from_file(self, file_path: str, file_extension: str) -> Dict[str, Any]:
        """Универсальная функция извлечения текста из файлов"""
        
        # Нормализуем расширение
        extension = file_extension.lower()
        
        # Выбираем метод в зависимости от расширения
        if extension == '.pdf':
            return self.extract_text_from_pdf(file_path)
        elif extension == '.docx':
            return self.extract_text_from_docx(file_path)
        elif extension == '.doc':
            return self.extract_text_from_doc(file_path)
        elif extension == '.txt':
            return self.extract_text_from_txt(file_path)
        else:
            return {
                'success': False,
                'error': f'Неподдерживаемый формат файла: {extension}'
            }
    
    def cleanup_temp_file(self, temp_dir: str):
        """Очищает временные файлы"""
        try:
            import shutil
            shutil.rmtree(temp_dir)
            logger.info(f"Временная директория удалена: {temp_dir}")
        except Exception as e:
            logger.error(f"Ошибка при удалении временной директории {temp_dir}: {e}")