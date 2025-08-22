#!/usr/bin/env python3
"""
OCR utilities with fallback handling
"""

import logging
import os
from typing import Optional, Tuple
from config import config

logger = logging.getLogger(__name__)

# Global OCR availability flag
OCR_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
    logger.info("OCR functionality available")
except ImportError:
    logger.warning("OCR modules not available - OCR functionality disabled")

def check_tesseract_installation() -> bool:
    """Check if Tesseract is properly installed"""
    if not OCR_AVAILABLE:
        return False
    
    try:
        # Try to get Tesseract version
        version = pytesseract.get_tesseract_version()
        logger.info(f"Tesseract version: {version}")
        return True
    except Exception as e:
        logger.warning(f"Tesseract not available: {e}")
        return False

def extract_text_from_image(image_path: str, languages: str = None) -> Tuple[bool, str]:
    """
    Extract text from image using OCR
    
    Args:
        image_path: Path to image file
        languages: Languages for OCR (e.g., 'rus+eng')
        
    Returns:
        Tuple of (success, text_or_error)
    """
    if not OCR_AVAILABLE:
        return False, "OCR functionality not available"
    
    if not check_tesseract_installation():
        return False, "Tesseract not installed"
    
    try:
        # Use configured languages or default
        lang = languages or config.OCR_LANGS
        
        # Open and process image
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Extract text
            text = pytesseract.image_to_string(img, lang=lang)
            
            # Clean up text
            text = text.strip()
            
            if len(text) < 10:
                return False, "Insufficient text found in image"
            
            return True, text
            
    except Exception as e:
        logger.error(f"OCR extraction failed: {e}")
        return False, f"OCR error: {str(e)}"

def extract_text_from_pdf_ocr(pdf_path: str, max_pages: int = None) -> Tuple[bool, str]:
    """
    Extract text from PDF using OCR (for scanned documents)
    
    Args:
        pdf_path: Path to PDF file
        max_pages: Maximum pages to process
        
    Returns:
        Tuple of (success, text_or_error)
    """
    if not OCR_AVAILABLE:
        return False, "OCR functionality not available"
    
    try:
        import fitz  # PyMuPDF
        
        max_pages = max_pages or config.MAX_PAGES_OCR
        extracted_text = []
        
        # Open PDF
        doc = fitz.open(pdf_path)
        
        for page_num in range(min(len(doc), max_pages)):
            page = doc.load_page(page_num)
            
            # Try to extract text normally first
            page_text = page.get_text()
            
            if len(page_text.strip()) > 100:
                # Page has text, no need for OCR
                extracted_text.append(page_text)
                logger.info(f"PDF page {page_num + 1}: text extracted directly")
            else:
                # Page needs OCR
                logger.info(f"PDF page {page_num + 1}: applying OCR")
                
                # Convert page to image
                mat = fitz.Matrix(config.PDF_OCR_DPI / 72.0, config.PDF_OCR_DPI / 72.0)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                
                # Save temporary image
                temp_img_path = f"/tmp/pdf_page_{page_num}.png"
                with open(temp_img_path, "wb") as f:
                    f.write(img_data)
                
                # Apply OCR
                success, ocr_text = extract_text_from_image(temp_img_path)
                
                # Clean up temp file
                try:
                    os.remove(temp_img_path)
                except:
                    pass
                
                if success:
                    extracted_text.append(ocr_text)
                else:
                    logger.warning(f"OCR failed for page {page_num + 1}: {ocr_text}")
        
        doc.close()
        
        if not extracted_text:
            return False, "No text could be extracted from PDF"
        
        combined_text = "\n\n".join(extracted_text)
        
        # Add metadata
        result = f"Extracted from PDF ({len(extracted_text)} pages):\n\n{combined_text}"
        
        return True, result
        
    except Exception as e:
        logger.error(f"PDF OCR extraction failed: {e}")
        return False, f"PDF OCR error: {str(e)}"

def get_ocr_info() -> dict:
    """Get OCR system information"""
    info = {
        'ocr_available': OCR_AVAILABLE,
        'tesseract_installed': False,
        'supported_languages': [],
        'version': None
    }
    
    if OCR_AVAILABLE:
        try:
            info['tesseract_installed'] = check_tesseract_installation()
            if info['tesseract_installed']:
                info['version'] = str(pytesseract.get_tesseract_version())
                info['supported_languages'] = pytesseract.get_languages()
        except Exception as e:
            logger.error(f"Error getting OCR info: {e}")
    
    return info