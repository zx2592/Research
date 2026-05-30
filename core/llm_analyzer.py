import json
import logging
import time

logger = logging.getLogger(__name__)


class LLMAnalyzer:
    def __init__(self, config):
        from google import genai
        from google.genai import types

        self.config = config
        self.client = genai.Client(
            api_key=config["gemini"]["api_key"],
            vertexai=False,
        )
        self.model_name = config["gemini"].get("model", "gemini-flash-latest")
        self.generate_config = types.GenerateContentConfig(
            safety_settings=[
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    threshold=types.HarmBlockThreshold.BLOCK_NONE,
                ),
            ]
        )

    def analyze_items(self, items):
        """
        Analyze a list of news/report items.
        Returns the list with 'score', 'summary', 'reasoning' added.
        """
        analyzed_items = []
        
        for item in items:
            # Skip items that are already scored (e.g. market movements)
            if 'score' in item:
                analyzed_items.append(item)
                continue
                
            prompt = self._construct_prompt(item)
            try:
                # Rate limit handling simple
                time.sleep(1)

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=self.generate_config,
                )
                result = self._parse_json_response(self._extract_response_text(response))

                item['score'] = result.get('score', 0)
                item['summary'] = result.get('summary', item.get('summary', ''))
                item['reasoning'] = result.get('reasoning', '')
                
                analyzed_items.append(item)
                
            except Exception as e:
                logger.error(f"LLM Analysis failed for {item.get('title')}: {e}")
                # Keep item but mark as unanalyzed or low score
                item['score'] = 0
                item['reasoning'] = "Analysis failed"
                analyzed_items.append(item)
                
        return analyzed_items

    def _construct_prompt(self, item):
        return f"""
        Role: Value Investing Analyst (Buffett/Munger style).
        Task: Analyze impact on Intrinsic Value (Moat, Cash Flow, Shareholder Returns).

        Item:
        Title: {item.get('title')}
        Source: {item.get('source')}
        Content: {item.get('summary')}

        Rules:
        1. IRRELEVANT (Score=0): General politics, gossip, or companies clearly outside focus.
        2. KEY INVESTORS (Score>=7): Position changes/views of Warren Buffett, Li Lu, Duan Yongping, Cathie Wood, Bill Ackman.
        
        Scoring (0-10) on Intrinsic Value Impact:
        - 8-10 (Critical): Structural change to Moat/Model/Capital Allocation.
        - 5-7 (Material): Earnings beat/miss, major product, regulatory shift.
        - 0-4 (Noise): Short-term price, rumors, general commentary.

        Output JSON:
        {{
            "score": <int>,
            "summary": "<1-sentence_summary_chinese>",
            "reasoning": "<reasoning_chinese_focus_on_value>"
        }}
        """

    @staticmethod
    def _parts_to_text(parts):
        if not parts:
            return None

        chunks = []
        for part in parts:
            text = getattr(part, "text", None)
            if text:
                chunks.append(text)

        return "".join(chunks) if chunks else None

    def _extract_response_text(self, response):
        if hasattr(response, "parts") and response.parts:
            text = self._parts_to_text(response.parts)
            if text:
                return text

        if hasattr(response, "candidates") and response.candidates:
            for candidate in response.candidates:
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", None)
                text = self._parts_to_text(parts)
                if text:
                    return text

        try:
            return response.text
        except Exception:
            return None

    def _parse_json_response(self, text):
        try:
            # Clean up markdown code blocks if present
            text = (text or "").replace('```json', '').replace('```', '').strip()
            return json.loads(text)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON from LLM: {text}")
            return {"score": 0, "summary": "Parse Error", "reasoning": "Invalid JSON from LLM"}
