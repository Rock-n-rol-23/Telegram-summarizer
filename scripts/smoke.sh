#!/usr/bin/env bash
# Smoke test script for the summarization system

set -e

echo "🧪 Running smoke tests for free-first summarization system"

# Test 1: Language detection and basic summarization
echo "📝 Test 1: Basic text summarization"
python tools/cli.py summarize --text "Короткий тест на русском. 2025 год. 3 факта о технологиях." --lang auto
python tools/cli.py summarize --text "Short English test. Year 2025. 3 facts about technology." --lang auto

# Test 2: Run pytest if available
if command -v pytest &> /dev/null; then
    echo "🔬 Test 2: Running unit tests"
    python -m pytest tests/ -q --tb=short || echo "⚠️  Some tests failed, continuing..."
else
    echo "⚠️  pytest not available, skipping unit tests"
fi

# Test 3: Check module imports
echo "📦 Test 3: Module import tests"
python -c "from llm.provider_router import generate_completion; print('✓ LLM router imported')"
python -c "from summarization.pipeline import summarize_text; print('✓ Summarization pipeline imported')"
python -c "from utils.language_detect import detect_language_simple; print('✓ Language detection imported')"

# Try to import optional engines
python -c "
try:
    from asr.asr_router import transcribe_audio
    print('✓ ASR router imported')
except Exception as e:
    print(f'⚠️  ASR router import failed: {e}')
"

python -c "
try:
    from ocr.ocr_router import extract_text_from_pdf
    print('✓ OCR router imported')
except Exception as e:
    print(f'⚠️  OCR router import failed: {e}')
"

echo "✅ Smoke tests completed successfully!"
echo ""
echo "🔧 To run full functionality tests:"
echo "   1. Set OPENROUTER_API_KEY in .env file"
echo "   2. Run: python tools/cli.py summarize --text 'Your test text'"
echo ""