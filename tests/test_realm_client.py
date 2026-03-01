import pytest
from realm_client import extract_password_form_block, parse_form_inputs

# Simulated snippet of the exact form observed in the DOM during planning
MOCK_FORM_HTML = """
<div id="login-form-wrapper">
    <form id="login-form" method="post" action="https://auth.ministrylogin.com/authn/demo-state-token-12345" class="login-form">
        <input type="hidden" name="csrf_token" value="abc123_hidden">
        <label for="userName">Email</label>
        <input type="text" id="userName" name="userName" value="">
        
        <label for="password">Password</label>
        <input type="password" id="password" name="password" value="">
        
        <button type="submit">Log In</button>
    </form>
</div>
"""

MOCK_FORM_HTML_WITHOUT_ACTION_URL = """
<div id="login-form-wrapper">
    <form id="login-form" method="post" class="login-form">
        <label for="userName">Email</label>
        <input type="text" id="userName" name="userName" value="">
        <label for="password">Password</label>
        <input type="password" id="password" name="password" value="">
    </form>
</div>
"""

MOCK_HTML_NO_PASSWORD = """
<div id="login-form-wrapper">
    <form id="login-form" method="post" action="https://auth.ministrylogin.com/authn/demo-state-token-12345">
        <label for="userName">Email</label>
        <input type="text" id="userName" name="userName" value="">
    </form>
</div>
"""

def test_extract_password_form_block_success():
    action, form_html = extract_password_form_block(MOCK_FORM_HTML)
    assert action == "https://auth.ministrylogin.com/authn/demo-state-token-12345"
    assert 'id="login-form"' in form_html
    assert 'type="password"' in form_html

def test_extract_password_form_block_no_action():
    action, _ = extract_password_form_block(MOCK_FORM_HTML_WITHOUT_ACTION_URL)
    # The regex should fail to find the action attribute
    assert action is None

def test_extract_password_form_block_no_password_field():
    action, form_html = extract_password_form_block(MOCK_HTML_NO_PASSWORD)
    # Should ignore forms without a password field
    assert action is None
    assert form_html == ""

def test_parse_form_inputs():
    # Only test the form_html returned, not the whole document
    _, form_html = extract_password_form_block(MOCK_FORM_HTML)
    inputs = parse_form_inputs(form_html)
    
    assert "csrf_token" in inputs
    assert inputs["csrf_token"] == "abc123_hidden"
    assert "userName" in inputs
    assert inputs["userName"] == ""
    assert "password" in inputs
    assert inputs["password"] == ""
