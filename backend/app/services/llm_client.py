import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMError(Exception):
    """Raised when an LLM request cannot be completed."""


class LLMClient:
    """Ollama chat client using its native HTTP API."""

    def __init__(
        self,
        base_url: str,
        model: str,
        temperature: float,
        system_prompt: str,
        analysis_prompt: str,
        connection_test_prompt: str,
        api_key: str = "",
        provider: str = "ollama",
        timeout_seconds: int = 180,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.system_prompt = system_prompt
        self.analysis_prompt = analysis_prompt
        self.connection_test_prompt = connection_test_prompt
        self.timeout_seconds = timeout_seconds
        self.provider = provider
        self.api_key = api_key
        self.last_raw_input = ""
        self.last_raw_output = ""

    def _request(self, prompt: str) -> dict:
        language_requirement = (
            "\n\n【硬性語言規則】所有輸出內容必須使用繁體中文（台灣用語）。"
            "JSON 的欄位名稱維持提示詞要求，但所有欄位值、摘要、事件、原因與建議都必須是繁體中文。"
            "不得使用英文或簡體中文；若 Log 原文是英文，請翻譯後再輸出。"
        )
        contract = (
            "\n\n【輸出契約】只輸出一個 JSON 物件，不要 Markdown、不要 ```、不要解釋、不要推理。"
            "必須包含 summary（字串）、severity（只能是 info/warning/critical）、"
            "key_events（字串陣列）、possible_causes（字串陣列）、"
            "recommendations（字串陣列）、error_count（整數）。"
        )
        attempts = [
            prompt + language_requirement + contract,
            (
                "請將下列要求直接轉成最精簡且完整的單一 JSON 物件。"
                "不要推理、不要 Markdown、不要額外文字；陣列最多各 5 項。"
                f"\n要求：{prompt}" + language_requirement + contract
            ),
        ]
        last_error = "LLM response was not valid JSON"
        for attempt in attempts:
            payload = self._post(attempt)
            if self.provider == "openai":
                choices = payload.get("choices")
                if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                    raise LLMError("LLM response did not contain choices")
                message = choices[0].get("message") or {}
            else:
                message = payload.get("message") or {}
            if not isinstance(message, dict):
                raise LLMError("LLM response message was not an object")
            content = message.get("content") or payload.get("response") or ""
            candidates = [content]
            thinking = message.get("thinking") or ""
            if thinking:
                candidates.append(thinking)
            for candidate in candidates:
                result = self._parse_json(candidate)
                if isinstance(result, dict):
                    return result
            if not content and not thinking:
                last_error = "LLM response did not contain message content"
        raise LLMError(last_error)

    def _post(self, prompt: str) -> dict:
        request_payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": "json",
            "options": {"temperature": min(self.temperature, 0.2), "num_predict": 768},
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
        }
        endpoint = f"{self.base_url}/api/chat"
        if self.provider == "openai":
            request_payload = {"model": self.model, "messages": request_payload["messages"], "stream": False}
            endpoint = f"{self.base_url}/chat/completions"
        serialized = json.dumps(request_payload, ensure_ascii=False, indent=2)
        self.last_raw_input = serialized
        request = Request(
            endpoint,
            data=serialized.encode(),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw_output = response.read().decode("utf-8")
                self.last_raw_output = raw_output
                payload = json.loads(raw_output)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise LLMError("LLM response was not valid JSON") from exc
        except TimeoutError as exc:
            raise LLMError(self._timeout_message()) from exc
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise LLMError(self._timeout_message()) from exc
            raise LLMError(f"LLM request failed: {exc}") from exc
        except (HTTPError, OSError) as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise LLMError("LLM response envelope was not a JSON object")
        return payload

    def _timeout_message(self) -> str:
        return (
            f"模型連線或讀取逾時（等待設定：{self.timeout_seconds} 秒）。"
            "請先將 Log 減少為 50～100 行，或在 LLM 設定提高等待秒數後重試。"
            "若仍失敗，請檢查模型服務負載與網路連線。"
        )

    @staticmethod
    def _parse_json(content: str) -> dict | None:
        if not isinstance(content, str) or not content:
            return None
        cleaned = content.strip().replace("```json", "").replace("```", "").strip()
        try:
            value = json.loads(cleaned)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            pass
        decoder = json.JSONDecoder()
        for index, character in enumerate(cleaned):
            if character != "{":
                continue
            try:
                value, _ = decoder.raw_decode(cleaned[index:])
            except json.JSONDecodeError:
                continue
            return value if isinstance(value, dict) else None
        return None

    def test_connection(self) -> None:
        self._request(self.connection_test_prompt)

    def summarize(self, log_text: str) -> dict:
        prompt = self.analysis_prompt.replace("{log_text}", log_text)
        return self._normalize_result(self._request(prompt))

    @staticmethod
    def _normalize_result(result: dict) -> dict:
        normalized = dict(result)
        report = normalized.get("log_analysis_report")
        if not normalized.get("summary"):
            report_summary = (
                report.get("summary") or report.get("摘要")
                if isinstance(report, dict)
                else ""
            )
            normalized["summary"] = (
                normalized.get("analysis_summary")
                or normalized.get("log_summary")
                or normalized.get("摘要", "")
                or normalized.get("事件摘要", "")
                or normalized.get("分析摘要", "")
                or report_summary
            )
        if not isinstance(normalized.get("key_events"), list):
            normalized["key_events"] = []
        if not normalized.get("key_events"):
            report_events = report.get("事件列表") if isinstance(report, dict) else []
            activities = (
                normalized.get("key_activities")
                or normalized.get("events")
                or normalized.get("事件", [])
                or normalized.get("關鍵活動", [])
                or normalized.get("觀察到的活動", [])
                or normalized.get("關鍵事件", [])
                or report_events
            )
            if isinstance(activities, list):
                normalized["key_events"] = [
                    item
                    if isinstance(item, str)
                    else "；".join(
                        f"{key}：{value}"
                        for key, value in item.items()
                        if value is not None
                    )
                    if isinstance(item, dict)
                    else str(item)
                    for item in activities
                ]
        if not normalized.get("possible_causes"):
            normalized["possible_causes"] = (
                [normalized.get("cause") or normalized.get("原因")]
                if normalized.get("cause") or normalized.get("原因")
                else (
                    [normalized.get("潛在原因") or normalized.get("潛在原因分析")]
                    if normalized.get("潛在原因") or normalized.get("潛在原因分析")
                    else []
                )
            )
        if not normalized.get("recommendations"):
            normalized["recommendations"] = (
                [normalized.get("recommendation") or normalized.get("建議")]
                if normalized.get("recommendation") or normalized.get("建議")
                else (
                    [normalized.get("建議行動")]
                    if normalized.get("建議行動")
                    else []
                )
            )
        if not normalized.get("severity"):
            normalized["severity"] = "info"
        if isinstance(normalized.get("error_count"), bool) or not isinstance(
            normalized.get("error_count"), int
        ):
            normalized["error_count"] = 0
        return normalized
