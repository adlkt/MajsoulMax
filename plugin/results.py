"""改包处理结果；此模块不加载协议或运行配置。"""
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.protobuf.message import Message


@dataclass(frozen=True, slots=True)
class HandlerResult:
    data: "Message | None" = None
    modify: bool = False
    drop: bool = False
    fake: bool = False
    injected_content: bytes | None = None


@dataclass(frozen=True, slots=True)
class ModResult:
    content: bytes | None = None
    drop: bool = False
    injected_content: bytes | None = None

    @property
    def modify(self) -> bool:
        return self.content is not None
