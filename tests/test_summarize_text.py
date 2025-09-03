"""
Tests for unified text summarization
"""

import pytest
from unittest.mock import patch, MagicMock

# Mock the LLM router to avoid API calls in tests
@patch('summarization.pipeline.generate_completion')
def test_summarize_text_basic(mock_generate):
    """Test basic text summarization"""
    mock_generate.return_value = "• Test summary bullet point"
    
    from summarization.pipeline import summarize_text
    
    text = "This is a test text for summarization. It should be processed correctly."
    result = summarize_text(text, 'en')
    
    assert isinstance(result, str)
    assert len(result) > 0
    mock_generate.assert_called_once()

@patch('summarization.pipeline.generate_completion')
def test_summarize_text_russian(mock_generate):
    """Test Russian text summarization"""
    mock_generate.return_value = "• Тестовая сводка на русском языке"
    
    from summarization.pipeline import summarize_text
    
    text = "Это тестовый текст для проверки суммаризации. Он должен быть обработан корректно."
    result = summarize_text(text, 'ru')
    
    assert isinstance(result, str)
    assert len(result) > 0
    mock_generate.assert_called_once()

@patch('summarization.pipeline.generate_completion')
def test_summarize_document(mock_generate):
    """Test document summarization with metadata"""
    mock_generate.return_value = "• Web page summary with key facts"
    
    from summarization.pipeline import summarize_document
    
    text = "This is web page content with navigation and main content."
    meta = {'source': 'web', 'language': 'en'}
    
    result = summarize_document(text, meta)
    
    assert isinstance(result, str)
    assert len(result) > 0
    mock_generate.assert_called_once()

def test_chunk_text_smart():
    """Test smart text chunking"""
    from summarization.pipeline import _chunk_text_smart
    
    # Short text should not be chunked
    short_text = "Short text."
    chunks = _chunk_text_smart(short_text)
    assert len(chunks) == 1
    assert chunks[0] == short_text
    
    # Long text should be chunked
    long_text = "Long text. " * 1000  # Very long text
    chunks = _chunk_text_smart(long_text)
    assert len(chunks) > 1
    
    # Each chunk should be reasonably sized
    for chunk in chunks:
        assert len(chunk) > 0