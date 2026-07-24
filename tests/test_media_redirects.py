"""Security tests for image redirects."""

from __future__ import annotations

from unittest.mock import MagicMock

from zhihu_cli.rendering.media_fetcher import MediaFetcher


def _response(status: int, *, location: str = ""):
    response = MagicMock()
    response.status_code = status
    response.headers = {"Location": location} if location else {}
    return response


def test_third_party_redirect_is_not_requested():
    redirect = _response(302, location="https://tracker.example/image.gif")
    session = MagicMock()
    session.headers = {}
    session.get.return_value = redirect
    fetcher = MediaFetcher(session=session)

    result = fetcher._request_image("https://pic.zhimg.com/image.gif")

    assert result is None
    assert session.get.call_count == 1
    assert "第三方地址" in (fetcher.last_error or "")
    redirect.close.assert_called_once()


def test_trusted_redirect_is_followed_without_requests_auto_redirect():
    redirect = _response(302, location="/redirected/image.jpg")
    final = _response(200)
    session = MagicMock()
    session.headers = {}
    session.get.side_effect = [redirect, final]
    fetcher = MediaFetcher(session=session)

    result = fetcher._request_image("https://pic.zhimg.com/image.jpg")

    assert result is final
    assert session.get.call_count == 2
    first_call, second_call = session.get.call_args_list
    assert first_call.args[0] == "https://pic.zhimg.com/image.jpg"
    assert second_call.args[0] == "https://pic.zhimg.com/redirected/image.jpg"
    assert first_call.kwargs["allow_redirects"] is False
    assert second_call.kwargs["allow_redirects"] is False
