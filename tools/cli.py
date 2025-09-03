#!/usr/bin/env python3
"""
CLI tool for testing summarization functionality
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from summarization.pipeline import summarize_text, summarize_document
from asr.asr_router import transcribe_audio
from ocr.ocr_router import extract_text_from_pdf, extract_text_from_image
import logging

logging.basicConfig(level=logging.INFO)

def main():
    parser = argparse.ArgumentParser(description='Test summarization functionality')
    parser.add_argument('action', choices=['summarize', 'transcribe', 'ocr'], help='Action to perform')
    parser.add_argument('--text', help='Text to summarize')
    parser.add_argument('--file', help='File to process')
    parser.add_argument('--url', help='URL to process')
    parser.add_argument('--youtube', help='YouTube URL to process')
    parser.add_argument('--lang', choices=['ru', 'en', 'auto'], default='auto', help='Language hint')
    
    args = parser.parse_args()
    
    try:
        if args.action == 'summarize':
            if args.text:
                result = summarize_text(args.text, args.lang if args.lang != 'auto' else None)
                print("Summary:", result)
            elif args.file:
                with open(args.file, 'r', encoding='utf-8') as f:
                    text = f.read()
                meta = {'source': 'file', 'language': args.lang if args.lang != 'auto' else None}
                result = summarize_document(text, meta)
                print("Summary:", result)
            else:
                print("Please provide --text or --file")
                return 1
        
        elif args.action == 'transcribe':
            if args.file:
                result = transcribe_audio(args.file, args.lang if args.lang != 'auto' else None)
                print("Transcription:", result)
            else:
                print("Please provide --file for audio transcription")
                return 1
        
        elif args.action == 'ocr':
            if args.file:
                file_path = Path(args.file)
                if file_path.suffix.lower() == '.pdf':
                    result = extract_text_from_pdf(args.file)
                elif file_path.suffix.lower() in ['.png', '.jpg', '.jpeg']:
                    result = extract_text_from_image(args.file, 'ru+en')
                else:
                    print("Unsupported file format for OCR")
                    return 1
                print("Extracted text:", result)
            else:
                print("Please provide --file for OCR")
                return 1
                
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())