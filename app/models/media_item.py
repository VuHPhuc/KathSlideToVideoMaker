import uuid
from pathlib import Path
from typing import Optional

TRANSITION_TYPES = [
    ("Không", "none"),
    ("Fade", "fade"),
    ("Wipe Left", "wipeleft"),
    ("Wipe Right", "wiperight"),
    ("Wipe Up", "wipeup"),
    ("Wipe Down", "wipedown"),
    ("Slide Left", "slideleft"),
    ("Slide Right", "slideright"),
    ("Slide Up", "slideup"),
    ("Slide Down", "slidedown"),
    ("Dissolve", "dissolve"),
]

class MediaItem:
    """Class representing a media item (slide, video, or image) in the timeline."""
    
    def __init__(
        self,
        media_type: str,
        path: str,
        duration_sec: float = 5.0,
        slide_info: Optional[object] = None,
    ):
        self.id = uuid.uuid4().hex
        self.media_type = media_type  # "slide" | "video" | "image"
        self.path = path
        self.duration_sec = duration_sec
        self.thumbnail_path: Optional[str] = None
        self.slide_info = slide_info  # Backward compatibility for SlideInfo
        
        self.transition_in: str = "none"
        self.transition_dur: float = 0.5
        
        self.video_volume: float = 1.0
        self.tts_volume: float = 1.0
        
        self.assigned_pos: int = -1
        self.assigned_text: str = ""
        self._display_number: int = 1

    @property
    def display_number(self) -> int:
        return self._display_number

    @display_number.setter
    def display_number(self, val: int):
        self._display_number = val

    @property
    def is_assigned(self) -> bool:
        return self.assigned_pos >= 0

    @property
    def display_name(self) -> str:
        if self.media_type == "slide":
            if self.slide_info and getattr(self.slide_info, "title", ""):
                return f"Slide {self.display_number}: {self.slide_info.title}"
            return f"Slide {self.display_number}"
        else:
            if self.path:
                return Path(self.path).name
            return f"Media {self.display_number}"

    @property
    def image_path(self) -> str:
        if self.media_type == "slide":
            if self.path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                return self.thumbnail_path or ""
            return self.path
        elif self.media_type == "image":
            return self.path
        elif self.media_type == "video":
            return self.thumbnail_path or ""
        return ""

    def __repr__(self) -> str:
        return f"<MediaItem id={self.id} type={self.media_type} path={self.path} dur={self.duration_sec}>"
