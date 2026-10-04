"""P10-4: NFO file parser for metadata."""
from __future__ import annotations
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional

def parse_nfo(path: Path) -> dict[str, Any]:
    """Parse a basic NFO file into a dictionary of metadata."""
    metadata: dict[str, Any] = {}
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        
        for child in root:
            metadata[child.tag] = child.text
            
    except (ET.ParseError, FileNotFoundError):
        pass
    
    return metadata
