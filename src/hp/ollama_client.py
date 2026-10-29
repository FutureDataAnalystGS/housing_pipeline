"""Klient lokalnego serwera Ollama (tylko biblioteka standardowa).

Najważniejsze zasady:
  * num_ctx jest ZAWSZE wysyłany — domyślnie Ollama używa 2048–4096 tokenów i po cichu ucina początek promptu
    (czyli instrukcję i definicje kodów), przez co model zwraca puste listy;
  * odpowiedź jest STRUMIENIOWANA: widać postęp, a limit czasu (timeout) dotyczy ciszy między tokenami, nie całego wywołania;
  * brak odpowiedzi w limicie to czytelny wyjątek OllamaTimeout (z wskazówkami), a nie surowy traceback;
  * odpowiedź ucięta (done_reason == "length") i prompt przekraczający okno zgłaszane są jako wyjątki,
    które wywołujący obsługuje dzieleniem fragmentu na mniejsze;
  * seed + temperature=0 + zapis wersji modelu (digest) = replikowalność.
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request


class OllamaError(RuntimeError):
    pass


class OllamaTimeout(OllamaError):
    """Serwer nie odesłał ani jednego tokenu w limicie czasu (model za wolny, przeciążony albo się ładuje)."""


class TruncatedOutput(OllamaError):
    """Model przerwał generowanie z powodu limitu num_predict."""


class PromptTooLong(OllamaError):
    """Prompt nie mieści się w oknie num_ctx (Ollama obcięłaby go po cichu)."""


CHARS_PER_TOKEN = 2.3          # konserwatywnie dla polskiego tekstu
TIMEOUT_HINT = ("Sprawdź w drugim terminalu: `ollama ps` (kolumna PROCESSOR: 100% GPU czy CPU?) oraz `ollama run <model> \"test\" --verbose` "
                "(eval rate w tokenach/s). Poniżej ok. 5 tok/s model działa na CPU: zmniejsz pracę (patrz config.yaml: facts, tasks, chunk_chars, num_ctx) "
                "albo zwiększ llm.timeout.")


def host_url() -> str:
    h = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    return h if h.startswith("http") else "http://" + h


def estimate_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN) + 1


def _open(url: str, payload: dict | None, timeout: int):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET")
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise OllamaError(f"Ollama HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}") from e
    except (socket.timeout, TimeoutError) as e:
        raise OllamaTimeout(f"Ollama nie odpowiedziała w {timeout} s. {TIMEOUT_HINT}") from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise OllamaTimeout(f"Ollama nie odpowiedziała w {timeout} s. {TIMEOUT_HINT}") from e
        raise OllamaError(f"Brak połączenia z Ollama ({url}). Uruchom aplikację Ollama / `ollama serve` i sprawdź OLLAMA_HOST.") from e


def _request(url: str, payload: dict | None, timeout: int) -> dict:
    try:
        with _open(url, payload, timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (socket.timeout, TimeoutError) as e:
        raise OllamaTimeout(f"Ollama nie odpowiedziała w {timeout} s. {TIMEOUT_HINT}") from e


def _stream_chat(url: str, payload: dict, timeout: int, progress: bool) -> dict:
    """Czyta odpowiedź NDJSON token po tokenie. timeout = maks. cisza między kolejnymi porcjami (pierwszy token może
    przyjść dopiero po załadowaniu modelu i przetworzeniu promptu, więc nie ustawiaj go zbyt nisko)."""
    parts: list[str] = []
    final: dict = {}
    n = 0
    t0 = time.time()
    try:
        with _open(url, {**payload, "stream": True}, timeout) as r:
            for raw in r:
                raw = raw.strip()
                if not raw:
                    continue
                obj = json.loads(raw)
                if obj.get("error"):
                    raise OllamaError(f"Ollama: {obj['error']}")
                parts.append((obj.get("message") or {}).get("content", ""))
                n += 1
                if progress and n % 100 == 0:
                    print(f"    … {n} tokenów, {time.time() - t0:.0f} s", file=sys.stderr, flush=True)
                if obj.get("done"):
                    final = obj
                    break
    except (socket.timeout, TimeoutError) as e:
        raise OllamaTimeout(f"Cisza przez {timeout} s (po {n} tokenach). {TIMEOUT_HINT}") from e
    final["message"] = {"content": "".join(parts)}
    return final


def parse_json(content: str) -> dict:
    c = content.strip()
    c = re.sub(r"^```(?:json)?\s*|\s*```$", "", c)
    try:
        data = json.loads(c)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", c, re.S)
        if not m:
            raise
        data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError("Oczekiwano obiektu JSON")
    return data


def chat_json(model: str, messages: list[dict], schema: dict, *, num_ctx: int = 12288, num_predict: int = 3000,
              temperature: float | None = 0.0, seed: int | None = 7, host: str | None = None, timeout: int = 600,
              retries: int = 2, keep_alive: str = "30m", progress: bool = True) -> tuple[dict, dict]:
    """Zwraca (dane, meta). meta: done_reason, prompt_eval_count, eval_count, num_ctx, seconds."""
    prompt_chars = sum(len(m["content"]) for m in messages)
    if estimate_tokens("x" * prompt_chars) + num_predict > num_ctx * 1.05:
        raise PromptTooLong(f"~{estimate_tokens('x' * prompt_chars)} tokenów promptu + {num_predict} na odpowiedź > num_ctx={num_ctx}")
    options: dict = {"num_ctx": num_ctx, "num_predict": num_predict}
    if temperature is not None:
        options["temperature"] = temperature
    if seed is not None:
        options["seed"] = seed
    payload = {"model": model, "messages": messages, "format": schema, "options": options, "keep_alive": keep_alive}
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            t0 = time.time()
            res = _stream_chat(f"{host or host_url()}/api/chat", payload, timeout, progress)
            meta = dict(done_reason=res.get("done_reason"), prompt_eval_count=res.get("prompt_eval_count"),
                        eval_count=res.get("eval_count"), num_ctx=num_ctx, seconds=round(time.time() - t0, 1))
            if res.get("done_reason") == "length":
                raise TruncatedOutput(f"odpowiedź ucięta po {res.get('eval_count')} tokenach (num_predict={num_predict})")
            if (res.get("prompt_eval_count") or 0) >= num_ctx - 8:
                raise PromptTooLong(f"prompt_eval_count={res.get('prompt_eval_count')} ≈ num_ctx={num_ctx}: Ollama obcięła prompt")
            return parse_json(res["message"]["content"]), meta
        except (TruncatedOutput, PromptTooLong, OllamaTimeout):
            raise
        except (json.JSONDecodeError, ValueError, OllamaError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise OllamaError(f"Nieudane wywołanie modelu {model}: {last}")


def model_digest(model: str, host: str | None = None) -> str | None:
    """Skrót (digest) zainstalowanego modelu — zapisujemy go przy każdym rekordzie (replikowalność)."""
    try:
        tags = _request(f"{host or host_url()}/api/tags", None, 30)
        for m in tags.get("models", []):
            if m.get("name") == model or m.get("model") == model:
                return m.get("digest")
    except OllamaError:
        return None
    return None
