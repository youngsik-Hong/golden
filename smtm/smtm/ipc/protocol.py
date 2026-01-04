# -*- coding: utf-8 -*-
"""
SMTM 로컬 IPC 프로토콜 (v1)

- QLocalSocket 기반 로컬 전용 통신
- 프레이밍: [uint32_be length][utf-8 JSON bytes]
- 모든 메시지는 공통 헤더(v/type/ts/run_id/symbol/seq/payload)를 권장
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


def encode_message(obj: Dict[str, Any]) -> bytes:
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return struct.pack(">I", len(data)) + data


class DecodeBuffer:
    """QLocalSocket으로 들어오는 바이트 스트림을 length-prefix JSON 단위로 파싱."""
    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> None:
        if data:
            self._buf.extend(data)

    def next_message(self) -> Optional[Dict[str, Any]]:
        if len(self._buf) < 4:
            return None
        length = struct.unpack(">I", self._buf[:4])[0]
        if len(self._buf) < 4 + length:
            return None
        payload = bytes(self._buf[4:4 + length])
        del self._buf[:4 + length]
        try:
            return json.loads(payload.decode("utf-8"))
        except Exception:
            # 파싱 실패 시, 메시지 유실로 간주하고 None 반환
            return None
