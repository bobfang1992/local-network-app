import requests
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


def detect_pihole(ip: str, https: bool = False) -> Optional[Dict]:
    """
    Detect if a device is running Pi-hole by querying its API.

    Pi-hole admin interface is typically at:
    - http://[ip]/admin or https://[ip]/admin

    Pi-hole API endpoints:
    - /admin/api.php - Main API
    - /admin/api.php?summary - Summary stats
    - /admin/api.php?status - Status check

    Args:
        ip: IP address to check
        https: Whether to use HTTPS (default False, will try HTTP first)

    Returns:
        Dict with Pi-hole info if detected, None otherwise
    """
    protocol = "https" if https else "http"
    base_url = f"{protocol}://{ip}"

    # Try different common Pi-hole API endpoints (old and new formats)
    endpoints_to_try = [
        "/admin/api.php",
        "/admin/api.php?summary",
        "/admin/api.php?status",
        "/api/stats",  # New Pi-hole v6+
        "/api/summary",
        "/admin/",  # Fallback: check if admin page exists
    ]

    for endpoint in endpoints_to_try:
        try:
            url = f"{base_url}{endpoint}"
            logger.info(f"Checking for Pi-hole at {url}")

            response = requests.get(
                url,
                timeout=5,
                verify=False,  # Don't verify SSL for local devices
                headers={'User-Agent': 'LocalNetworkScanner/1.0'}
            )

            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')

                # Try JSON response first (API endpoints)
                if 'json' in content_type.lower():
                    try:
                        data = response.json()

                        # Check if response looks like Pi-hole
                        # Pi-hole API returns specific fields
                        pihole_indicators = [
                            'gravity_last_updated',  # Pi-hole specific (old API)
                            'domains_being_blocked', # Pi-hole specific (old API)
                            'dns_queries_today',     # Pi-hole specific (old API)
                            'ads_blocked_today',     # Pi-hole specific (old API)
                            'status',                # Common
                        ]

                        # If we find any Pi-hole-specific fields, it's Pi-hole
                        found_indicators = [key for key in pihole_indicators if key in data]

                        if found_indicators:
                            logger.info(f"✓ Pi-hole detected at {ip} (found indicators: {found_indicators})")

                            admin_url = f"{base_url}/admin"

                            return {
                                'detected': True,
                                'ip': ip,
                                'protocol': protocol,
                                'admin_url': admin_url,
                                'api_url': url,
                                'version': data.get('version', 'unknown'),
                                'status': data.get('status', 'unknown'),
                                'domains_blocked': data.get('domains_being_blocked', 0),
                                'queries_today': data.get('dns_queries_today', 0),
                                'ads_blocked_today': data.get('ads_blocked_today', 0),
                            }

                    except ValueError:
                        # Not valid JSON
                        pass

                # Fallback: Check HTML content for Pi-hole strings
                elif 'html' in content_type.lower():
                    text = response.text.lower()
                    pihole_strings = ['pi-hole', 'pihole', 'pi.hole']

                    if any(s in text for s in pihole_strings):
                        logger.info(f"✓ Pi-hole detected at {ip} (found in HTML)")

                        admin_url = f"{base_url}/admin"

                        return {
                            'detected': True,
                            'ip': ip,
                            'protocol': protocol,
                            'admin_url': admin_url,
                            'api_url': url,
                            'version': 'unknown',
                            'status': 'unknown',
                            'domains_blocked': 0,
                            'queries_today': 0,
                            'ads_blocked_today': 0,
                        }

        except requests.RequestException as e:
            logger.debug(f"Failed to check {url}: {e}")
            continue

    # If HTTPS didn't work and we tried HTTPS, try HTTP
    if https:
        return detect_pihole(ip, https=False)

    logger.info(f"No Pi-hole detected at {ip}")
    return None


def check_if_pihole(ip: str, open_ports: list) -> Optional[Dict]:
    """
    Check if a device with open ports is running Pi-hole.

    Args:
        ip: IP address
        open_ports: List of open port numbers

    Returns:
        Pi-hole info dict if detected, None otherwise
    """
    # Check if it has the right ports for Pi-hole
    has_dns = 53 in open_ports
    has_http = 80 in open_ports
    has_https = 443 in open_ports

    if not has_dns:
        return None

    if not (has_http or has_https):
        return None

    logger.info(f"Device {ip} has DNS + HTTP/HTTPS, checking for Pi-hole...")

    # Try HTTPS first if available, then HTTP
    if has_https:
        result = detect_pihole(ip, https=True)
        if result:
            return result

    if has_http:
        result = detect_pihole(ip, https=False)
        if result:
            return result

    return None
