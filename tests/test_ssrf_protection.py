#!/usr/bin/env python3
"""
Unit tests for SSRF protection
"""

import pytest
from utils.network import check_ssrf_protection, SSRFError

class TestSSRFProtection:
    """Test SSRF protection functionality"""
    
    def test_allowed_public_urls(self):
        """Test that public URLs are allowed"""
        public_urls = [
            "https://www.google.com",
            "http://example.com",
            "https://api.github.com",
            "https://httpbin.org/get",
        ]
        
        for url in public_urls:
            # Should not raise exception
            check_ssrf_protection(url)
    
    def test_blocked_localhost(self):
        """Test that localhost URLs are blocked"""
        localhost_urls = [
            "http://localhost:8080",
            "https://127.0.0.1:9000", 
            "http://127.1.1.1",
            "https://[::1]:8080",
        ]
        
        for url in localhost_urls:
            with pytest.raises(SSRFError):
                check_ssrf_protection(url)
    
    def test_blocked_private_networks(self):
        """Test that private network URLs are blocked"""
        private_urls = [
            "http://192.168.1.1",
            "https://10.0.0.1:8080",
            "http://172.16.0.1",
            "https://169.254.1.1",  # link-local
        ]
        
        for url in private_urls:
            with pytest.raises(SSRFError):
                check_ssrf_protection(url)
    
    def test_blocked_schemes(self):
        """Test that non-HTTP schemes are blocked"""
        blocked_schemes = [
            "ftp://example.com/file.txt",
            "file:///etc/passwd",
            "gopher://example.com",
            "data:text/plain;base64,SGVsbG8gV29ybGQ=",
        ]
        
        for url in blocked_schemes:
            with pytest.raises(SSRFError):
                check_ssrf_protection(url)
    
    def test_malformed_urls(self):
        """Test handling of malformed URLs"""
        malformed_urls = [
            "not-a-url",
            "http://",
            "https:///no-host",
        ]
        
        for url in malformed_urls:
            with pytest.raises(SSRFError):
                check_ssrf_protection(url)

if __name__ == "__main__":
    # Run basic tests without pytest
    test = TestSSRFProtection()
    
    print("Testing public URLs...")
    test.test_allowed_public_urls()
    print("✅ Public URLs test passed")
    
    print("Testing localhost blocking...")
    test.test_blocked_localhost() 
    print("✅ Localhost blocking test passed")
    
    print("Testing private network blocking...")
    test.test_blocked_private_networks()
    print("✅ Private network blocking test passed")
    
    print("Testing scheme blocking...")
    test.test_blocked_schemes()
    print("✅ Scheme blocking test passed")
    
    print("Testing malformed URLs...")
    test.test_malformed_urls()
    print("✅ Malformed URL test passed")
    
    print("\n🎉 All SSRF protection tests passed!")