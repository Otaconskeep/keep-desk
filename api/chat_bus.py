"""Operator chat bus — Keep Desk ↔ operator ↔ Codec bridge.

Durable messages under /desk/state/operator_chat.jsonl
Also optional POST to Otacon Codec (/codec/chat) so transmissions surface
in the existing Codec UI.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DESK = Path(os.environ.get('DESK_ROOT', '/desk')).resolve()
CHAT_PATH = Path(os.environ.get('STATE_DIR', str(DESK / 'state'))) / 'operator_chat.jsonl'
CODEC_URL = os.environ.get('CODEC_CHAT_URL', 'http://host.docker.internal:5757/codec/chat')
CODEC_ENABLED = os.environ.get('CODEC_BRIDGE', '1') != '0'


def _ensure():
    CHAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CHAT_PATH.exists():
        CHAT_PATH.write_text('')


def post_message(
    *,
    from_id: str,
    text: str,
    kind: str = 'chat',
    job_id: str | None = None,
    bot_id: str | None = None,
    codec: bool = False,
) -> dict:
    """Append operator-visible chat line. Optionally bridge to Codec.

    The desk chat line is written *before* Codec is called so the Command Deck
    never races a slow Codec round-trip.
    """
    _ensure()
    msg = {
        'id': f'msg_{uuid.uuid4().hex[:12]}',
        'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'from': from_id,
        'bot_id': bot_id,
        'job_id': job_id,
        'kind': kind,  # chat | status | result | codec_tx | codec_rx | system
        'text': (text or '').strip()[:4000],
    }
    # Durable desk line first
    with CHAT_PATH.open('a') as f:
        f.write(json.dumps(msg) + '\n')

    if codec and CODEC_ENABLED and msg['text']:
        codec_reply = transmit_codec(msg['text'], from_id=from_id, job_id=job_id)
        if codec_reply.get('ok') and codec_reply.get('answer'):
            rx = {
                'id': f'msg_{uuid.uuid4().hex[:12]}',
                'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'from': 'codec:otacon',
                'bot_id': None,
                'job_id': job_id,
                'kind': 'codec_rx',
                'text': str(codec_reply.get('answer'))[:4000],
                'in_reply_to': msg['id'],
            }
            msg['codec'] = {
                'ok': True,
                'reply_id': rx['id'],
                'codec_turn_id': codec_reply.get('codec_turn_id'),
            }
            with CHAT_PATH.open('a') as f:
                # annotate prior tx with codec ok via a tiny system note + rx
                note = {
                    'id': f'msg_{uuid.uuid4().hex[:12]}',
                    'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    'from': 'system',
                    'bot_id': bot_id,
                    'job_id': job_id,
                    'kind': 'system',
                    'text': f'codec_bridged ok for {msg["id"]}',
                    'codec': msg['codec'],
                    'ref': msg['id'],
                }
                f.write(json.dumps(note) + '\n')
                f.write(json.dumps(rx) + '\n')
        else:
            msg['codec'] = {
                'ok': bool(codec_reply.get('ok')),
                'error': codec_reply.get('error') or 'empty_codec_response',
            }
            with CHAT_PATH.open('a') as f:
                f.write(json.dumps({
                    'id': f'msg_{uuid.uuid4().hex[:12]}',
                    'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    'from': 'system',
                    'bot_id': bot_id,
                    'job_id': job_id,
                    'kind': 'system',
                    'text': f'codec_bridge failed for {msg["id"]}: {msg["codec"].get("error")}',
                    'codec': msg['codec'],
                    'ref': msg['id'],
                }) + '\n')
    return msg


def transmit_codec(text: str, *, from_id: str = 'keep-desk', job_id: str | None = None) -> dict:
    """Fire-and-forget friendly: POST into Otacon Codec chat surface."""
    payload = {
        'message': (
            f'[Keep Desk transmission from {from_id}'
            + (f' job={job_id}' if job_id else '')
            + f']\n{text}'
        ),
        'ai': 'otacon',
    }
    try:
        req = urllib.request.Request(
            CODEC_URL,
            data=json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode()
            data = json.loads(raw) if raw else {}
            # Otacon Codec returns the spoken turn in `response`
            answer = (
                data.get('response')
                or data.get('answer')
                or data.get('text')
                or data.get('message')
                or ''
            )
            if not answer and isinstance(data.get('result'), dict):
                answer = data['result'].get('response') or data['result'].get('answer') or ''
            return {
                'ok': True,
                'status': resp.status,
                'answer': answer,
                'codec_turn_id': data.get('codec_turn_id') or data.get('response_turn_id'),
                'agent_name': data.get('agent_name') or data.get('name'),
                'raw_keys': list(data)[:16],
            }
    except urllib.error.HTTPError as e:
        return {'ok': False, 'error': f'HTTP {e.code}: {e.read()[:200].decode(errors="replace")}'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def list_messages(limit: int = 80, since_id: str | None = None) -> list[dict]:
    _ensure()
    lines = CHAT_PATH.read_text().splitlines()
    out: list[dict] = []
    for line in lines[-max(limit * 3, 200):]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    if since_id:
        idx = next((i for i, m in enumerate(out) if m.get('id') == since_id), -1)
        out = out[idx + 1:] if idx >= 0 else out
    return out[-limit:]
