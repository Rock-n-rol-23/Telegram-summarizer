"""
OCR Router - Manages multiple OCR engines for best text extraction
Combines PyMuPDF, Tesseract and PaddleOCR for optimal results
"""

import logging
import tempfile
from typing import List, Tuple, Optional, Dict
from pathlib import Path

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    fitz = None

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    pytesseract = None
    Image = None

try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    PaddleOCR = None

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    easyocr = None

from config import config

logger = logging.getLogger(__name__)

class OCRRouter:
    """Routes OCR requests through multiple engines for best results"""

    def __init__(self):
        self.paddle_ocr_ru = None
        self.paddle_ocr_en = None
        self.easyocr_reader = None

        self._initialize_engines()
    
    def _initialize_engines(self):
        """Initialize available OCR engines"""
        # Initialize EasyOCR if available (primary for fallback)
        if EASYOCR_AVAILABLE:
            try:
                # Initialize with Russian and English languages
                self.easyocr_reader = easyocr.Reader(['ru', 'en'], gpu=False)
                logger.info("✅ EasyOCR initialized for RU/EN (fallback for Gemini Vision)")
            except Exception as e:
                logger.error(f"Failed to initialize EasyOCR: {e}")

        # Initialize PaddleOCR if available and enabled
        if PADDLEOCR_AVAILABLE and config.OCR_USE_PADDLE:
            try:
                self.paddle_ocr_ru = PaddleOCR(use_angle_cls=True, lang='ru', use_gpu=False)
                self.paddle_ocr_en = PaddleOCR(use_angle_cls=True, lang='en', use_gpu=False)
                logger.info("PaddleOCR initialized for RU/EN")
            except Exception as e:
                logger.error(f"Failed to initialize PaddleOCR: {e}")

        # Check Tesseract availability
        if TESSERACT_AVAILABLE and config.OCR_USE_TESSERACT:
            try:
                # Test Tesseract
                pytesseract.get_tesseract_version()
                logger.info("Tesseract OCR available")
            except Exception as e:
                logger.error(f"Tesseract not available: {e}")
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        Extract text from PDF using multiple strategies
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Extracted text
        """
        if not PYMUPDF_AVAILABLE:
            raise ImportError("PyMuPDF не установлен")
        
        # Strategy 1: Try to extract text layer first
        text_layer = self._extract_text_layer(pdf_path)
        
        # Check if text layer is good enough
        if self._is_good_text(text_layer):
            logger.info("Using text layer from PDF")
            return text_layer
        
        # Strategy 2: OCR approach for scanned PDFs
        logger.info("Text layer insufficient, using OCR")
        return self._extract_text_with_ocr(pdf_path)
    
    def extract_text_from_image(self, image_path: str, language: str = 'ru+en') -> str:
        """
        Extract text from image using best available OCR

        Args:
            image_path: Path to image file
            language: Language for OCR

        Returns:
            Extracted text
        """
        results = []

        # Try EasyOCR first (best quality, fallback for Gemini Vision)
        if EASYOCR_AVAILABLE and self.easyocr_reader:
            try:
                easyocr_result = self._extract_with_easyocr(image_path)
                if easyocr_result:
                    results.append(('easyocr', easyocr_result))
                    logger.info("✅ EasyOCR успешно извлек текст")
            except Exception as e:
                logger.error(f"EasyOCR failed: {e}")

        # Try PaddleOCR if available
        if PADDLEOCR_AVAILABLE and config.OCR_USE_PADDLE:
            try:
                paddle_result = self._extract_with_paddle(image_path, language)
                if paddle_result:
                    results.append(('paddle', paddle_result))
            except Exception as e:
                logger.error(f"PaddleOCR failed: {e}")

        # Try Tesseract as last resort
        if TESSERACT_AVAILABLE and config.OCR_USE_TESSERACT:
            try:
                tesseract_result = self._extract_with_tesseract(image_path, language)
                if tesseract_result:
                    results.append(('tesseract', tesseract_result))
            except Exception as e:
                logger.error(f"Tesseract failed: {e}")

        if not results:
            raise Exception("Не удалось извлечь текст из изображения")

        # Return the best result
        return self._select_best_result(results)
    
    def _extract_text_layer(self, pdf_path: str) -> str:
        """Extract existing text layer from PDF"""
        try:
            doc = fitz.open(pdf_path)
            text_parts = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)
            
            doc.close()
            return "\\n\\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Failed to extract text layer: {e}")
            return ""
    
    def _extract_text_with_ocr(self, pdf_path: str) -> str:
        """Extract text using OCR on PDF pages"""
        try:
            doc = fitz.open(pdf_path)
            all_text = []
            
            max_pages = min(len(doc), config.MAX_PAGES_OCR)
            
            for page_num in range(max_pages):
                page = doc[page_num]
                
                # Convert page to image
                mat = fitz.Matrix(config.PDF_OCR_DPI / 72, config.PDF_OCR_DPI / 72)
                pix = page.get_pixmap(matrix=mat)
                
                # Save as temporary image
                temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                pix.save(temp_file.name)
                
                try:
                    # OCR the page
                    page_text = self.extract_text_from_image(temp_file.name)
                    if page_text.strip():
                        all_text.append(f"Страница {page_num + 1}:\\n{page_text}")
                except Exception as e:
                    logger.error(f"OCR failed for page {page_num + 1}: {e}")
                finally:
                    # Clean up temp file
                    Path(temp_file.name).unlink(missing_ok=True)
            
            doc.close()
            return "\\n\\n".join(all_text)
            
        except Exception as e:
            logger.error(f"PDF OCR failed: {e}")
            raise Exception(f"Не удалось извлечь текст из PDF: {str(e)}")
    
    def _extract_with_tesseract(self, image_path: str, language: str) -> str:
        """Extract text using Tesseract"""
        try:
            # Map language codes
            lang_map = {
                'ru+en': 'rus+eng',
                'ru': 'rus',
                'en': 'eng'
            }
            tesseract_lang = lang_map.get(language, 'rus+eng')
            
            image = Image.open(image_path)
            text = pytesseract.image_to_string(image, lang=tesseract_lang)
            
            return text.strip()
            
        except Exception as e:
            logger.error(f"Tesseract extraction failed: {e}")
            return ""
    
    def _extract_with_paddle(self, image_path: str, language: str) -> str:
        """Extract text using PaddleOCR"""
        try:
            # Choose appropriate PaddleOCR model
            if 'ru' in language and self.paddle_ocr_ru:
                ocr = self.paddle_ocr_ru
            elif 'en' in language and self.paddle_ocr_en:
                ocr = self.paddle_ocr_en
            else:
                # Fallback to Russian model
                ocr = self.paddle_ocr_ru or self.paddle_ocr_en

            if not ocr:
                return ""

            result = ocr.ocr(image_path, cls=True)

            if not result or not result[0]:
                return ""

            # Extract text from result
            text_parts = []
            for line in result[0]:
                if line and len(line) > 1:
                    text_parts.append(line[1][0])

            return " ".join(text_parts)

        except Exception as e:
            logger.error(f"PaddleOCR extraction failed: {e}")
            return ""

    def _extract_with_easyocr(self, image_path: str) -> str:
        """Extract text using EasyOCR (primary fallback for Gemini Vision)"""
        try:
            if not self.easyocr_reader:
                return ""

            # EasyOCR returns list of (bbox, text, confidence)
            results = self.easyocr_reader.readtext(image_path)

            if not results:
                return ""

            # Extract text from results
            text_parts = []
            for (bbox, text, confidence) in results:
                # Only include text with confidence > 0.3
                if confidence > 0.3:
                    text_parts.append(text)

            extracted_text = " ".join(text_parts)
            logger.info(f"EasyOCR extracted {len(text_parts)} text blocks")

            return extracted_text

        except Exception as e:
            logger.error(f"EasyOCR extraction failed: {e}")
            return ""

    def _is_good_text(self, text: str) -> bool:
        """Check if extracted text is good enough"""
        if not text or len(text.strip()) < 50:
            return False
        
        # Check ratio of alphanumeric characters
        clean_text = ''.join(c for c in text if c.isalnum())
        if len(clean_text) / len(text) < 0.3:
            return False
        
        return True
    
    def _select_best_result(self, results: List[Tuple[str, str]]) -> str:
        """Select best OCR result based on quality metrics"""
        if not results:
            return ""
        
        if len(results) == 1:
            return results[0][1]
        
        # Score results
        scored_results = []
        for engine, text in results:
            score = self._score_text_quality(text)
            scored_results.append((score, engine, text))
        
        # Return best scored result
        scored_results.sort(reverse=True)
        best_score, best_engine, best_text = scored_results[0]
        
        logger.info(f"Selected {best_engine} result (score: {best_score:.2f})")
        return best_text
    
    def _score_text_quality(self, text: str) -> float:
        """Score text quality for selection"""
        if not text:
            return 0.0
        
        score = 0.0
        
        # Length bonus
        score += min(len(text) / 1000, 1.0) * 20
        
        # Alphanumeric ratio
        clean_chars = sum(1 for c in text if c.isalnum())
        alpha_ratio = clean_chars / len(text) if text else 0
        score += alpha_ratio * 30
        
        # Word count bonus
        words = text.split()
        score += min(len(words) / 100, 1.0) * 20
        
        # Russian/English text bonus (common letters)
        common_chars = sum(1 for c in text.lower() if c in 'abcdefghijklmnopqrstuvwxyzабвгдеёжзийклмнопрстуфхцчшщъыьэюя')
        common_ratio = common_chars / len(text) if text else 0
        score += common_ratio * 30
        
        return score
    
    def is_available(self) -> bool:
        """Check if any OCR engine is available"""
        return (
            PYMUPDF_AVAILABLE or
            EASYOCR_AVAILABLE or
            (TESSERACT_AVAILABLE and config.OCR_USE_TESSERACT) or
            (PADDLEOCR_AVAILABLE and config.OCR_USE_PADDLE)
        )

    def get_engine_info(self) -> Dict:
        """Get info about available OCR engines"""
        return {
            'pymupdf': {'available': PYMUPDF_AVAILABLE},
            'easyocr': {
                'available': EASYOCR_AVAILABLE,
                'enabled': True,  # Always enabled if available (primary fallback)
                'initialized': self.easyocr_reader is not None
            },
            'tesseract': {
                'available': TESSERACT_AVAILABLE,
                'enabled': config.OCR_USE_TESSERACT
            },
            'paddleocr': {
                'available': PADDLEOCR_AVAILABLE,
                'enabled': config.OCR_USE_PADDLE
            }
        }


# Global instance
ocr_router = None

def get_ocr_router() -> OCRRouter:
    """Get global OCR router instance"""
    global ocr_router
    if ocr_router is None:
        ocr_router = OCRRouter()
    return ocr_router

def extract_text_from_pdf(pdf_path: str) -> str:
    """Convenience function for PDF text extraction"""
    router = get_ocr_router()
    return router.extract_text_from_pdf(pdf_path)

def extract_text_from_image(image_path: str, language: str = 'ru+en') -> str:
    """Convenience function for image text extraction"""
    router = get_ocr_router()
    return router.extract_text_from_image(image_path, language)