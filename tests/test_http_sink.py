"""Tests for HTTP output sink."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from logsynth.core.output import (
    HttpBatchFormat,
    HttpSink,
    HttpSinkConfig,
    create_sink,
    parse_output_url,
)


class TestHttpUrlParsing:
    """Tests for HTTP URL parsing."""

    def test_parse_http_url_basic(self):
        """Should parse basic HTTP URL."""
        sink_type, params = parse_output_url("http://localhost:8080/logs")
        assert sink_type == "http"
        assert params["url"] == "http://localhost:8080/logs"

    def test_parse_https_url(self):
        """Should parse HTTPS URL."""
        sink_type, params = parse_output_url("https://api.example.com/ingest")
        assert sink_type == "http"
        assert params["url"] == "https://api.example.com/ingest"

    def test_parse_url_with_batch_param(self):
        """Should parse batch size from query param."""
        sink_type, params = parse_output_url("http://localhost/logs?batch=50")
        assert params["batch_size"] == 50

    def test_parse_url_with_timeout_param(self):
        """Should parse timeout from query param."""
        sink_type, params = parse_output_url("http://localhost/logs?timeout=10")
        assert params["batch_timeout"] == 10.0

    def test_parse_url_with_format_json(self):
        """Should parse JSON format from query param."""
        sink_type, params = parse_output_url("http://localhost/logs?format=json")
        assert params["format"] == HttpBatchFormat.JSON

    def test_parse_url_with_format_ndjson(self):
        """Should parse NDJSON format from query param."""
        sink_type, params = parse_output_url("http://localhost/logs?format=ndjson")
        assert params["format"] == HttpBatchFormat.NDJSON

    def test_parse_url_with_format_text(self):
        """Should parse TEXT format from query param."""
        sink_type, params = parse_output_url("http://localhost/logs?format=text")
        assert params["format"] == HttpBatchFormat.TEXT

    def test_parse_url_with_retries_param(self):
        """Should parse retries from query param."""
        sink_type, params = parse_output_url("http://localhost/logs?retries=5")
        assert params["max_retries"] == 5

    def test_parse_url_with_multiple_params(self):
        """Should parse multiple query params."""
        url = "http://localhost:8080/logs?batch=25&timeout=3&format=ndjson"
        sink_type, params = parse_output_url(url)
        assert params["url"] == "http://localhost:8080/logs"
        assert params["batch_size"] == 25
        assert params["batch_timeout"] == 3.0
        assert params["format"] == HttpBatchFormat.NDJSON

    def test_parse_url_strips_query_from_base(self):
        """Should strip query params from base URL."""
        sink_type, params = parse_output_url("http://localhost/logs?batch=10")
        assert params["url"] == "http://localhost/logs"
        assert "?" not in params["url"]


class TestHttpSinkConfig:
    """Tests for HttpSinkConfig dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = HttpSinkConfig(url="http://localhost/logs")
        assert config.batch_size == 100
        assert config.batch_timeout == 5.0
        assert config.format == HttpBatchFormat.JSON
        assert config.max_retries == 3
        assert config.retry_delay == 0.5
        assert config.retry_backoff == 2.0

    def test_custom_values(self):
        """Should accept custom values."""
        config = HttpSinkConfig(
            url="http://example.com/ingest",
            batch_size=50,
            batch_timeout=10.0,
            format=HttpBatchFormat.NDJSON,
            max_retries=5,
        )
        assert config.url == "http://example.com/ingest"
        assert config.batch_size == 50
        assert config.format == HttpBatchFormat.NDJSON


class TestHttpSinkBatching:
    """Tests for batching behavior."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock httpx client."""
        with patch("logsynth.core.output.httpx.Client") as mock:
            client = MagicMock()
            response = MagicMock()
            response.status_code = 200
            client.post.return_value = response
            mock.return_value = client
            yield client

    def test_batch_accumulates_lines(self, mock_client):
        """Should accumulate lines until batch size."""
        config = HttpSinkConfig(
            url="http://localhost/logs",
            batch_size=5,
            batch_timeout=60.0,  # Long timeout so it doesn't flush by time
        )
        sink = HttpSink(config)

        # Write 3 lines (less than batch size)
        sink.write("line1")
        sink.write("line2")
        sink.write("line3")

        # Should not have posted yet
        mock_client.post.assert_not_called()

        sink.close()

    def test_flush_on_batch_full(self, mock_client):
        """Should flush when batch reaches batch_size."""
        config = HttpSinkConfig(
            url="http://localhost/logs",
            batch_size=3,
            batch_timeout=60.0,
        )
        sink = HttpSink(config)

        # Write exactly batch_size lines
        sink.write("line1")
        sink.write("line2")
        sink.write("line3")

        # Should have posted
        mock_client.post.assert_called_once()

        # Verify the batch content
        call_args = mock_client.post.call_args
        body = call_args.kwargs["content"]
        assert json.loads(body) == ["line1", "line2", "line3"]

        sink.close()

    def test_flush_on_close(self, mock_client):
        """Should flush pending lines on close."""
        config = HttpSinkConfig(
            url="http://localhost/logs",
            batch_size=10,  # High batch size
            batch_timeout=60.0,
        )
        sink = HttpSink(config)

        sink.write("line1")
        sink.write("line2")

        # Not flushed yet
        mock_client.post.assert_not_called()

        # Close should flush
        sink.close()

        mock_client.post.assert_called_once()
        body = mock_client.post.call_args.kwargs["content"]
        assert json.loads(body) == ["line1", "line2"]


class TestHttpSinkFormats:
    """Tests for batch format options."""

    def test_json_format(self):
        """Should format as JSON array."""
        config = HttpSinkConfig(
            url="http://localhost/logs", format=HttpBatchFormat.JSON
        )
        with patch("logsynth.core.output.httpx.Client"):
            sink = HttpSink(config)
            body, content_type = sink._format_batch(["line1", "line2", "line3"])

        assert body == '["line1", "line2", "line3"]'
        assert content_type == "application/json"

    def test_ndjson_format(self):
        """Should format as newline-delimited."""
        config = HttpSinkConfig(
            url="http://localhost/logs", format=HttpBatchFormat.NDJSON
        )
        with patch("logsynth.core.output.httpx.Client"):
            sink = HttpSink(config)
            body, content_type = sink._format_batch(["line1", "line2"])

        assert body == "line1\nline2\n"
        assert content_type == "application/x-ndjson"

    def test_text_format(self):
        """Should format as plain text."""
        config = HttpSinkConfig(
            url="http://localhost/logs", format=HttpBatchFormat.TEXT
        )
        with patch("logsynth.core.output.httpx.Client"):
            sink = HttpSink(config)
            body, content_type = sink._format_batch(["line1", "line2"])

        assert body == "line1\nline2\n"
        assert content_type == "text/plain"


class TestHttpSinkRetry:
    """Tests for retry behavior."""

    def test_no_retry_on_success(self):
        """Should not retry on 200 OK."""
        with patch("logsynth.core.output.httpx.Client") as mock_class:
            client = MagicMock()
            response = MagicMock()
            response.status_code = 200
            client.post.return_value = response
            mock_class.return_value = client

            config = HttpSinkConfig(
                url="http://localhost/logs",
                batch_size=1,
                max_retries=3,
            )
            sink = HttpSink(config)
            sink.write("line1")

            # Should only call once
            assert client.post.call_count == 1
            sink.close()

    def test_retry_on_5xx(self):
        """Should retry on 5xx responses."""
        with patch("logsynth.core.output.httpx.Client") as mock_class:
            client = MagicMock()
            response = MagicMock()
            response.status_code = 500
            response.text = "Internal Server Error"
            client.post.return_value = response
            mock_class.return_value = client

            config = HttpSinkConfig(
                url="http://localhost/logs",
                batch_size=1,
                max_retries=2,
                retry_delay=0.01,  # Fast for testing
            )
            sink = HttpSink(config)
            sink.write("line1")

            # Should retry: initial + 2 retries = 3 calls
            assert client.post.call_count == 3
            sink.close()

    def test_no_retry_on_4xx(self):
        """Should not retry on 4xx (except 429)."""
        with patch("logsynth.core.output.httpx.Client") as mock_class:
            client = MagicMock()
            response = MagicMock()
            response.status_code = 400
            response.text = "Bad Request"
            client.post.return_value = response
            mock_class.return_value = client

            config = HttpSinkConfig(
                url="http://localhost/logs",
                batch_size=1,
                max_retries=3,
            )
            sink = HttpSink(config)
            sink.write("line1")

            # Should only call once (no retry on 4xx)
            assert client.post.call_count == 1
            sink.close()

    def test_retry_on_429(self):
        """Should retry on 429 rate limit."""
        with patch("logsynth.core.output.httpx.Client") as mock_class:
            client = MagicMock()
            response = MagicMock()
            response.status_code = 429
            response.text = "Too Many Requests"
            client.post.return_value = response
            mock_class.return_value = client

            config = HttpSinkConfig(
                url="http://localhost/logs",
                batch_size=1,
                max_retries=2,
                retry_delay=0.01,
            )
            sink = HttpSink(config)
            sink.write("line1")

            # Should retry on 429
            assert client.post.call_count == 3
            sink.close()

    def test_retry_on_connection_error(self):
        """Should retry on connection failure."""
        with patch("logsynth.core.output.httpx.Client") as mock_class:
            client = MagicMock()
            client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_class.return_value = client

            config = HttpSinkConfig(
                url="http://localhost/logs",
                batch_size=1,
                max_retries=2,
                retry_delay=0.01,
            )
            sink = HttpSink(config)
            sink.write("line1")

            # Should retry on connection error
            assert client.post.call_count == 3
            sink.close()


class TestHttpSinkDeadLetter:
    """Tests for dead letter file."""

    def test_writes_dead_letter_on_failure(self):
        """Should write failed batches to dead letter file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dead_letter_path = Path(tmpdir) / "dead-letter.jsonl"

            with patch("logsynth.core.output.httpx.Client") as mock_class:
                client = MagicMock()
                response = MagicMock()
                response.status_code = 500
                response.text = "Error"
                client.post.return_value = response
                mock_class.return_value = client

                config = HttpSinkConfig(
                    url="http://localhost/logs",
                    batch_size=1,
                    max_retries=0,  # No retries for quick test
                    dead_letter_path=str(dead_letter_path),
                )
                sink = HttpSink(config)
                sink.write("failed-line")
                sink.close()

            # Check dead letter file
            assert dead_letter_path.exists()
            content = dead_letter_path.read_text()
            record = json.loads(content.strip())

            assert record["url"] == "http://localhost/logs"
            assert "Retries exhausted" in record["error"]
            assert record["batch"] == ["failed-line"]
            assert record["batch_size"] == 1


class TestHttpSinkHeaders:
    """Tests for custom headers."""

    def test_custom_headers_sent(self):
        """Should include custom headers in request."""
        with patch("logsynth.core.output.httpx.Client") as mock_class:
            client = MagicMock()
            response = MagicMock()
            response.status_code = 200
            client.post.return_value = response
            mock_class.return_value = client

            config = HttpSinkConfig(
                url="http://localhost/logs",
                batch_size=1,
                headers={"Authorization": "Bearer token123", "X-Custom": "value"},
            )
            sink = HttpSink(config)
            sink.write("line1")

            # Check headers were sent
            call_args = client.post.call_args
            headers = call_args.kwargs["headers"]
            assert headers["Authorization"] == "Bearer token123"
            assert headers["X-Custom"] == "value"
            assert headers["Content-Type"] == "application/json"

            sink.close()


class TestCreateSinkHttp:
    """Tests for create_sink with HTTP URLs."""

    def test_create_http_sink(self):
        """Should create HttpSink for HTTP URL."""
        with patch("logsynth.core.output.httpx.Client"):
            sink = create_sink("http://localhost:8080/logs")
            assert isinstance(sink, HttpSink)
            sink.close()

    def test_create_https_sink(self):
        """Should create HttpSink for HTTPS URL."""
        with patch("logsynth.core.output.httpx.Client"):
            sink = create_sink("https://api.example.com/ingest")
            assert isinstance(sink, HttpSink)
            sink.close()

    def test_create_http_sink_with_headers(self):
        """Should pass headers to HttpSink."""
        with patch("logsynth.core.output.httpx.Client"):
            sink = create_sink(
                "http://localhost/logs",
                http_headers={"Authorization": "Bearer abc"},
            )
            assert isinstance(sink, HttpSink)
            assert sink.config.headers["Authorization"] == "Bearer abc"
            sink.close()

    def test_create_http_sink_with_url_params(self):
        """Should parse URL params into config."""
        with patch("logsynth.core.output.httpx.Client"):
            sink = create_sink("http://localhost/logs?batch=50&format=ndjson")
            assert isinstance(sink, HttpSink)
            assert sink.config.batch_size == 50
            assert sink.config.format == HttpBatchFormat.NDJSON
            sink.close()
