from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.llm_analyzer import LLMAnalyzer


def _build_config():
    return {
        "gemini": {
            "api_key": "test-key",
            "model": "gemini-test-model",
        }
    }


def test_analyzer_uses_google_genai_client():
    mock_client = MagicMock()

    with patch("google.genai.Client", return_value=mock_client) as mock_client_cls:
        analyzer = LLMAnalyzer(_build_config())

    mock_client_cls.assert_called_once_with(api_key="test-key", vertexai=False)
    assert analyzer.client is mock_client
    assert analyzer.model_name == "gemini-test-model"


def test_analyze_items_extracts_text_from_candidates():
    mock_response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(
                            text='{"score": 8, "summary": "摘要", "reasoning": "原因"}'
                        )
                    ]
                )
            )
        ]
    )

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client), patch(
        "core.llm_analyzer.time.sleep"
    ):
        analyzer = LLMAnalyzer(_build_config())
        result = analyzer.analyze_items([{"title": "Test", "source": "Unit", "summary": "Body"}])

    assert result[0]["score"] == 8
    assert result[0]["summary"] == "摘要"
    assert result[0]["reasoning"] == "原因"
    mock_client.models.generate_content.assert_called_once()


def test_parse_json_response_handles_empty_text():
    mock_client = MagicMock()

    with patch("google.genai.Client", return_value=mock_client):
        analyzer = LLMAnalyzer(_build_config())

    result = analyzer._parse_json_response(None)
    assert result["score"] == 0
    assert result["summary"] == "Parse Error"
