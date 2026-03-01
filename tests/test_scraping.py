import pytest
import os
from pathlib import Path

from realm_client import extract_password_form_block, parse_form_inputs

MOCK_DATA_DIR = Path(__file__).parent / "mock_data"

def test_extract_password_form_block():
    with open(MOCK_DATA_DIR / "login_page.html") as f:
        html = f.read()
    
    action, form_html = extract_password_form_block(html)
    
    assert action == "/login/authenticate?_oq=some-long-token"
    assert "id=\"loginForm\"" in form_html

def test_parse_form_inputs():
    with open(MOCK_DATA_DIR / "login_page.html") as f:
        html = f.read()
        
    _, form_html = extract_password_form_block(html)
    inputs = parse_form_inputs(form_html)
    
    assert inputs["__RequestVerificationToken"] == "abc123xyz"
    # Inputs that just exist but don't have default values still get parsed as empty strings
    assert "userName" in inputs
    assert "password" in inputs
