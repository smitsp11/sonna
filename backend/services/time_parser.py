"""
Natural language time parsing service.

Converts phrases like "in 2 hours", "tomorrow at 5pm", "next Monday"
into actual datetime objects.
"""

from datetime import datetime, timedelta
from typing import Optional
import dateparser
import pytz
import logging

logger = logging.getLogger(__name__)


def parse_time_expression(
    time_string: str,
    timezone: str = "America/Toronto",
    relative_base: Optional[datetime] = None
) -> Optional[datetime]:
    """
    Parse natural language time expressions into datetime objects.
    
    Examples:
        - "in 2 hours" → datetime 2 hours from now
        - "tomorrow at 3pm" → datetime for tomorrow at 3pm
        - "next Monday at 9am" → datetime for next Monday at 9am
        - "in 30 minutes" → datetime 30 minutes from now
        - "5pm today" → datetime for today at 5pm
    
    Args:
        time_string: Natural language time expression
        timezone: Timezone for interpretation
        relative_base: Base datetime for relative expressions (defaults to now)
        
    Returns:
        Parsed datetime object or None if parsing fails
    """
    try:
        tz = pytz.timezone(timezone)
        
        # Use current time as base if not provided
        if relative_base is None:
            relative_base = datetime.now(tz)
        
        # Parse using dateparser
        parsed = dateparser.parse(
            time_string,
            settings={
                'TIMEZONE': timezone,
                'RETURN_AS_TIMEZONE_AWARE': True,
                'RELATIVE_BASE': relative_base,
                'PREFER_DATES_FROM': 'future'  # Assume future dates
            }
        )
        
        if parsed is None:
            logger.warning(f"Failed to parse time expression: '{time_string}'")
            return None
        
        # If parsed time is in the past, try adding a day
        if parsed < relative_base:
            logger.info(f"Parsed time {parsed} is in past, trying tomorrow")
            tomorrow_base = relative_base + timedelta(days=1)
            parsed = dateparser.parse(
                time_string,
                settings={
                    'TIMEZONE': timezone,
                    'RETURN_AS_TIMEZONE_AWARE': True,
                    'RELATIVE_BASE': tomorrow_base,
                    'PREFER_DATES_FROM': 'future'
                }
            )
        
        logger.info(f"✅ Parsed '{time_string}' → {parsed}")
        return parsed
        
    except Exception as e:
        logger.error(f"Error parsing time expression '{time_string}': {e}")
        return None


def extract_time_from_text(text: str, timezone: str = "America/Toronto") -> Optional[datetime]:
    """
    Extract time information from a longer text.
    
    Looks for time expressions in phrases like:
    - "Remind me to call mom at 3pm"
    - "Set a reminder for tomorrow morning"
    
    Args:
        text: Text containing time expression
        timezone: Timezone for interpretation
        
    Returns:
        Parsed datetime or None
    """
    # Common time trigger words
    time_triggers = [
        "at", "in", "on", "tomorrow", "today", "tonight",
        "next", "this", "every", "morning", "afternoon",
        "evening", "night", "am", "pm"
    ]
    
    # Check if text contains time-related words
    text_lower = text.lower()
    has_time_ref = any(trigger in text_lower for trigger in time_triggers)
    
    if not has_time_ref:
        logger.warning(f"No time reference found in: '{text}'")
        return None
    
    # Try to parse the entire text
    result = parse_time_expression(text, timezone)
    
    if result:
        return result
    
    # Try extracting just the time portion
    # Look for phrases after "at", "in", "on"
    for trigger in ["at", "in", "on"]:
        if trigger in text_lower:
            parts = text_lower.split(trigger, 1)
            if len(parts) > 1:
                time_part = parts[1].strip()
                result = parse_time_expression(time_part, timezone)
                if result:
                    return result
    
    return None


# Common test cases for validation
if __name__ == "__main__":
    test_cases = [
        "in 2 hours",
        "tomorrow at 3pm",
        "next Monday at 9am",
        "in 30 minutes",
        "5pm today",
        "tomorrow morning",
        "tonight at 8",
        "in 1 day",
        "next week",
    ]
    
    print("Testing time parser:\n")
    for test in test_cases:
        result = parse_time_expression(test)
        print(f"'{test}' → {result}")