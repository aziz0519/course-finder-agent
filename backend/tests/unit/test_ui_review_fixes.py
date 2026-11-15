import base64
import io
from unittest.mock import Mock

import httpx
import pytest
from PIL import Image
from ui.api_client import ApiClient, ApiError


@pytest.mark.parametrize("operation", ["json", "binary", "login", "logout"])
@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ReadTimeout])
def test_transport_errors_are_safe_and_not_retried(operation, failure):
    attempts = []

    def fail(request):
        attempts.append(request)
        raise failure("private connection details", request=request)

    client = ApiClient(transport=httpx.MockTransport(fail))
    with pytest.raises(ApiError) as caught:
        if operation == "json":
            client.profile()
        elif operation == "binary":
            client.page_bytes("thread", "document", 1)
        elif operation == "login":
            client.login("user", "password")
        else:
            client.logout()
    assert caught.value.status_code == 503
    assert "Check your connection" in caught.value.detail
    assert "private" not in str(caught.value)
    assert len(attempts) == 1


def test_citation_images_remain_inline(monkeypatch):
    from ui import app

    source = io.BytesIO()
    Image.new("RGB", (2, 2)).save(source, format="PNG")
    client = Mock()
    client.citation.return_value = {}
    client.page_bytes.return_value = source.getvalue()
    client.asset_bytes.return_value = source.getvalue()
    monkeypatch.setattr(app, "_client", lambda state: client)
    monkeypatch.setattr(app.presenters, "citation_detail", lambda *args: "Source detail")
    detail, page, crop = app._show_citation(
        0, [{"chunk_id": "chunk", "document_id": "doc", "pdf_page_number": 1,
             "asset_id": "asset"}], None, "thread"
    )
    assert detail == "Source detail"
    for markup in (page, crop):
        assert 'src="data:image/png;base64,' in markup
        assert "/file=" not in markup
        encoded = markup.split("base64,", 1)[1].split('"', 1)[0]
        assert Image.open(io.BytesIO(base64.b64decode(encoded))).size == (2, 2)


def test_adviser_selection_clears_plan_on_success_and_error(monkeypatch):
    from ui import app

    for detail in (("Student profile", [["progress"]]), ("API unavailable", [])):
        callback = Mock(return_value=detail)
        monkeypatch.setattr(app, "_adviser_detail", callback)
        assert app._select_adviser_student("student-002", None) == (*detail, "", [], "")
        callback.assert_called_once_with("student-002", None)


def test_logout_clears_local_session_on_transport_error(monkeypatch):
    from ui import app

    client = Mock()
    client.logout.side_effect = ApiError(503, "API unavailable")
    monkeypatch.setattr(app.ApiClient, "from_session", lambda state: client)
    assert app._logout(Mock())[0] is None
