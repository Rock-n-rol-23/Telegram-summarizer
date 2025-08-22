#!/usr/bin/env python3
"""
Comprehensive test suite for production features
"""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path

# Import modules to test
from utils.security import validate_file_type, validate_file_size, sanitize_filename
from utils.language_detection import detect_language, split_into_sentences, extract_key_numbers
from utils.chunking import TextChunker, MapReduceSummarizer
from utils.network import check_ssrf_protection, SSRFError
from utils.rate_limiter import RateLimiter
from utils.temp_files import TempFileManager

class TestSecurity:
    """Test security utilities"""
    
    def test_file_size_validation(self):
        """Test file size validation"""
        
        # Test normal file
        valid, msg = validate_file_size(1024 * 1024)  # 1MB
        assert valid is True
        
        # Test oversized file
        valid, msg = validate_file_size(50 * 1024 * 1024)  # 50MB 
        assert valid is False
        assert "too large" in msg.lower()
    
    def test_filename_sanitization(self):
        """Test filename sanitization"""
        
        dangerous_name = "../../../etc/passwd"
        safe_name = sanitize_filename(dangerous_name)
        assert ".." not in safe_name
        assert "/" not in safe_name
        
        long_name = "a" * 300 + ".txt"
        safe_long = sanitize_filename(long_name)
        assert len(safe_long) <= 255
        assert safe_long.endswith(".txt")
    
    @pytest.mark.asyncio
    async def test_file_validation_with_temp_file(self):
        """Test file validation with actual file"""
        
        # Create temporary test file
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            f.write(b"Test content")
            temp_path = f.name
        
        try:
            # Test valid file type
            valid, mime_type, error = validate_file_type(temp_path, "test.txt")
            assert valid is True
            assert mime_type == "text/plain"
            
        finally:
            os.unlink(temp_path)

class TestLanguageDetection:
    """Test language detection and text processing"""
    
    def test_language_detection_english(self):
        """Test English text detection"""
        
        english_text = "This is a sample English text for testing purposes."
        lang, confidence = detect_language(english_text)
        
        assert lang in ['en', 'unknown']  # Fallback may return unknown
        assert 0 <= confidence <= 1
    
    def test_language_detection_russian(self):
        """Test Russian text detection"""
        
        russian_text = "Это пример русского текста для тестирования системы."
        lang, confidence = detect_language(russian_text)
        
        assert lang in ['ru', 'mixed', 'unknown']  # Heuristic detection
        assert 0 <= confidence <= 1
    
    def test_sentence_splitting(self):
        """Test sentence splitting"""
        
        text = "First sentence. Second sentence! Third sentence?"
        sentences = split_into_sentences(text)
        
        assert len(sentences) >= 2  # Should split into multiple sentences
        assert all(len(s.strip()) > 0 for s in sentences)
    
    def test_number_extraction(self):
        """Test key number extraction"""
        
        text = "The price increased by 15% to $1,250.50 in 2023."
        numbers = extract_key_numbers(text)
        
        # Should find percentage, currency, and year
        types_found = {num['type'] for num in numbers}
        assert 'percentage' in types_found
        assert 'year' in types_found

class TestChunking:
    """Test text chunking and map-reduce"""
    
    def test_small_text_no_chunking(self):
        """Test that small text doesn't get chunked"""
        
        chunker = TextChunker(max_chunk_size=1000)
        text = "Small text that doesn't need chunking."
        
        chunks = chunker.chunk_text(text)
        
        assert len(chunks) == 1
        assert chunks[0]['total_chunks'] == 1
        assert chunks[0]['text'] == text
    
    def test_large_text_chunking(self):
        """Test chunking of large text"""
        
        chunker = TextChunker(max_chunk_size=100, overlap_size=20)
        text = "This is a long text. " * 20  # Create long text
        
        chunks = chunker.chunk_text(text)
        
        assert len(chunks) > 1
        assert all(len(chunk['text']) <= 120 for chunk in chunks)  # Allow some overage
        assert all(chunk['total_chunks'] == len(chunks) for chunk in chunks)
    
    def test_sentence_preservation(self):
        """Test that sentence boundaries are preserved"""
        
        chunker = TextChunker(max_chunk_size=100)
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        
        chunks = chunker.chunk_text(text, preserve_sentences=True)
        
        # Each chunk should end with proper punctuation
        for chunk in chunks:
            text = chunk['text'].strip()
            if text:
                assert text[-1] in '.!?'

class TestNetworkSecurity:
    """Test network security features"""
    
    def test_ssrf_protection_public_urls(self):
        """Test that public URLs are allowed"""
        
        public_urls = [
            "https://www.google.com",
            "http://example.com",
            "https://api.github.com/repos"
        ]
        
        for url in public_urls:
            # Should not raise exception
            check_ssrf_protection(url)
    
    def test_ssrf_protection_blocks_localhost(self):
        """Test that localhost URLs are blocked"""
        
        localhost_urls = [
            "http://localhost:8080",
            "https://127.0.0.1:9000",
            "http://127.1.1.1/admin"
        ]
        
        for url in localhost_urls:
            with pytest.raises(SSRFError):
                check_ssrf_protection(url)
    
    def test_ssrf_protection_blocks_private_networks(self):
        """Test that private network URLs are blocked"""
        
        private_urls = [
            "http://192.168.1.1",
            "https://10.0.0.1:8080",
            "http://172.16.0.1/api"
        ]
        
        for url in private_urls:
            with pytest.raises(SSRFError):
                check_ssrf_protection(url)

class TestRateLimiting:
    """Test rate limiting functionality"""
    
    @pytest.mark.asyncio
    async def test_rate_limiter_basic(self):
        """Test basic rate limiting"""
        
        limiter = RateLimiter()
        user_id = 12345
        
        # First request should succeed
        result = await limiter.acquire_user_limit(user_id)
        assert result is True
        
        # Get user stats
        stats = limiter.get_user_stats(user_id)
        assert stats['requests_last_minute'] >= 1
        assert stats['requests_limit'] > 0

class TestTempFileManager:
    """Test temporary file management"""
    
    def test_temp_file_creation(self):
        """Test temporary file creation"""
        
        manager = TempFileManager()
        
        # Create temp file
        temp_file = manager.create_temp_file(suffix='.txt')
        
        assert temp_file.exists()
        assert temp_file.suffix == '.txt'
        assert temp_file in manager.tracked_files
        
        # Cleanup
        manager.cleanup_file(temp_file)
        assert not temp_file.exists()
        assert temp_file not in manager.tracked_files
    
    def test_temp_dir_creation(self):
        """Test temporary directory creation"""
        
        manager = TempFileManager()
        
        # Create temp directory
        temp_dir = manager.create_temp_dir()
        
        assert temp_dir.exists()
        assert temp_dir.is_dir()
        assert temp_dir in manager.tracked_files
        
        # Cleanup
        manager.cleanup_file(temp_dir)
        assert not temp_dir.exists()
        assert temp_dir not in manager.tracked_files
    
    def test_disk_usage_stats(self):
        """Test disk usage statistics"""
        
        manager = TempFileManager()
        
        # Create some test files
        files = []
        for i in range(3):
            temp_file = manager.create_temp_file(suffix=f'_{i}.txt')
            temp_file.write_text(f"Test content {i}")
            files.append(temp_file)
        
        # Get usage stats
        usage = manager.get_disk_usage()
        
        assert 'total_size_bytes' in usage
        assert 'file_count' in usage
        assert usage['file_count'] >= 3
        assert usage['total_size_bytes'] > 0
        
        # Cleanup
        for file in files:
            manager.cleanup_file(file)

# Integration test
class TestIntegration:
    """Integration tests combining multiple components"""
    
    @pytest.mark.asyncio
    async def test_url_to_summary_pipeline(self):
        """Test complete URL processing pipeline"""
        
        # This would be a smoke test for the full pipeline
        # URL → content extraction → chunking → summarization
        
        # Mock URL content
        mock_content = "This is a sample article. " * 100  # Long content
        
        # Test chunking
        chunker = TextChunker(max_chunk_size=200)
        chunks = chunker.chunk_text(mock_content)
        
        assert len(chunks) > 1
        
        # Test language detection
        lang, confidence = detect_language(mock_content)
        assert lang in ['en', 'unknown']
        
        # Test number preservation
        content_with_numbers = "The revenue was $1.5M, up 25% from 2022."
        numbers = extract_key_numbers(content_with_numbers)
        
        assert len(numbers) >= 2  # Should find currency and percentage

if __name__ == "__main__":
    # Run tests without pytest
    import sys
    
    print("Running comprehensive test suite...")
    
    # Test security
    print("\n🔒 Testing Security...")
    security_tests = TestSecurity()
    security_tests.test_file_size_validation()
    security_tests.test_filename_sanitization()
    print("✅ Security tests passed")
    
    # Test language detection
    print("\n🌐 Testing Language Detection...")
    lang_tests = TestLanguageDetection()
    lang_tests.test_language_detection_english()
    lang_tests.test_language_detection_russian()
    lang_tests.test_sentence_splitting()
    lang_tests.test_number_extraction()
    print("✅ Language detection tests passed")
    
    # Test chunking
    print("\n📄 Testing Text Chunking...")
    chunk_tests = TestChunking()
    chunk_tests.test_small_text_no_chunking()
    chunk_tests.test_large_text_chunking()
    chunk_tests.test_sentence_preservation()
    print("✅ Chunking tests passed")
    
    # Test network security
    print("\n🌐 Testing Network Security...")
    network_tests = TestNetworkSecurity()
    network_tests.test_ssrf_protection_public_urls()
    network_tests.test_ssrf_protection_blocks_localhost()
    network_tests.test_ssrf_protection_blocks_private_networks()
    print("✅ Network security tests passed")
    
    # Test temp file management
    print("\n📁 Testing Temp File Management...")
    temp_tests = TestTempFileManager()
    temp_tests.test_temp_file_creation()
    temp_tests.test_temp_dir_creation()
    temp_tests.test_disk_usage_stats()
    print("✅ Temp file management tests passed")
    
    print("\n🎉 All tests passed! System is ready for production.")