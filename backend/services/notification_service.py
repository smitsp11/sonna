"""
Notification service for sending desktop notifications.

Supports cross-platform desktop notifications using plyer,
with OS-specific fallbacks for macOS, Linux, and Windows.
"""

import logging
import subprocess
import platform
from typing import Optional

logger = logging.getLogger(__name__)


def send_desktop_notification(title: str, message: str, timeout: int = 10) -> bool:
    """
    Send a desktop notification across different operating systems.
    
    Args:
        title: Notification title
        message: Notification message body
        timeout: Notification display duration in seconds (default: 10)
        
    Returns:
        bool: True if notification was sent successfully, False otherwise
    """
    # On macOS, use osascript directly (more reliable than plyer)
    os_name = platform.system()
    if os_name == "Darwin":  # macOS
        return _send_macos_notification(title, message)
    
    try:
        # Try using plyer for other platforms
        from plyer import notification
        
        notification.notify(
            title=title,
            message=message,
            app_name="Sonna",
            timeout=timeout
        )
        
        logger.info(f"✅ Desktop notification sent via plyer: {title}")
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ Plyer notification failed: {e}, trying OS-specific fallback")
        
        # Fallback to OS-specific commands
        return _send_os_specific_notification(title, message)


def _send_os_specific_notification(title: str, message: str) -> bool:
    """
    Send notification using OS-specific commands as fallback.
    
    Args:
        title: Notification title
        message: Notification message body
        
    Returns:
        bool: True if notification was sent successfully
    """
    os_name = platform.system()
    
    try:
        if os_name == "Darwin":  # macOS
            return _send_macos_notification(title, message)
        elif os_name == "Linux":
            return _send_linux_notification(title, message)
        elif os_name == "Windows":
            return _send_windows_notification(title, message)
        else:
            logger.error(f"❌ Unsupported OS: {os_name}")
            return False
            
    except Exception as e:
        logger.error(f"❌ OS-specific notification failed: {e}")
        return False


def _send_macos_notification(title: str, message: str) -> bool:
    """Send notification on macOS using osascript."""
    try:
        script = f'''
        display notification "{message}" with title "{title}" sound name "default"
        '''
        
        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True
        )
        
        logger.info(f"✅ macOS notification sent: {title}")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ macOS notification failed: {e}")
        return False


def _send_linux_notification(title: str, message: str) -> bool:
    """Send notification on Linux using notify-send."""
    try:
        subprocess.run(
            ["notify-send", title, message],
            check=True,
            capture_output=True,
            text=True
        )
        
        logger.info(f"✅ Linux notification sent: {title}")
        return True
        
    except FileNotFoundError:
        logger.error("❌ notify-send not found. Install libnotify-bin package.")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Linux notification failed: {e}")
        return False


def _send_windows_notification(title: str, message: str) -> bool:
    """Send notification on Windows using PowerShell."""
    try:
        # Use Windows 10+ toast notifications via PowerShell
        ps_script = f'''
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        
        $template = @"
        <toast>
            <visual>
                <binding template="ToastText02">
                    <text id="1">{title}</text>
                    <text id="2">{message}</text>
                </binding>
            </visual>
        </toast>
"@
        
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml($template)
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Sonna").Show($toast)
        '''
        
        subprocess.run(
            ["powershell", "-Command", ps_script],
            check=True,
            capture_output=True,
            text=True
        )
        
        logger.info(f"✅ Windows notification sent: {title}")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Windows notification failed: {e}")
        return False


def send_reminder_notification(reminder_content: str, scheduled_time: Optional[str] = None) -> dict:
    """
    Send a reminder notification with formatted content.
    
    Args:
        reminder_content: The reminder message
        scheduled_time: Optional scheduled time string
        
    Returns:
        dict: Status dictionary with success/failure info
    """
    title = "🔔 Sonna Reminder"
    
    if scheduled_time:
        message = f"{reminder_content}\n\nScheduled for: {scheduled_time}"
    else:
        message = reminder_content
    
    success = send_desktop_notification(title, message)
    
    return {
        "status": "sent" if success else "failed",
        "title": title,
        "message": message,
        "success": success
    }

