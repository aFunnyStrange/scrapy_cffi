# exception.py
from typing import Any, Optional, List

class BlackboxProtobufException(Exception):
    """Base class for excepions raised by Blackbox Protobuf"""

    def __init__(self, message: str, path: Optional[List[str]]=None, *args) -> None:
        self.path = path
        super().__init__(message, *args)

    def set_path(self, path: List[str]) -> None:
        if self.path is None:
            self.path = path


class TypedefException(BlackboxProtobufException):
    """Thrown when an error is identified in the type definition, such as
    conflicting or inconsistent values."""

    def __str__(self):
        message = super().__str__()
        if self.path is not None:
            message = (
                "Encountered error within typedef for field %s: "
                % "->".join(map(str, self.path))
            ) + message
        else:
            message = ("Encountered error within typedef: ") + message
        return message


class EncoderException(BlackboxProtobufException, ValueError):
    """Thrown when there is an error encoding a dictionary to a type definition"""

    def __str__(self):
        message = super().__str__()
        if self.path is not None:
            message = (
                "Encountered error encoding field %s: " % "->".join(map(str, self.path))
            ) + message
        else:
            message = ("Encountered error encoding message: ") + message
        return message


class DecoderException(BlackboxProtobufException, ValueError):
    """Thrown when there is an error decoding a bytestring to a dictionary"""

    def __str__(self):
        message = super().__str__()
        if self.path is not None:
            message = (
                "Encountered error decoding field %s: " % "->".join(map(str, self.path))
            ) + message
        else:
            message = ("Encountered error decoding message: ") + message
        return message


class ProtofileException(BlackboxProtobufException):
    def __init__(self, message: str, path: Optional[List[str]]=None, filename: Optional[str]=None, *args) -> None:
        self.filename = filename
        super().__init__(message, path, *args)

    def __str__(self):
        message = super().__str__()
        if self.path is not None:
            message = (
                "Encountered error within protofile %s for field %s: "
                % (self.filename, "->".join(map(str, self.path)))
            ) + message
        else:
            message = (
                "Encountered error within protofile %s: " % self.filename
            ) + message

        return message
